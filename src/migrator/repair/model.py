"""The repair agent's model: ``init_chat_model`` behind the one cost-capped choke point.

- The chat model comes from LangChain's ``init_chat_model`` (``ChatAnthropic`` for
  Claude), so the M5 model comparison is a configuration value. The model is chosen
  per attempt from the configuration's ``attempt_models``.
- Effort is always passed explicitly (Opus 5.5 defaults to ``medium``); ``temperature``
  and a forced ``tool_choice`` are never set (both are rejected on Opus 5.5). Tools are
  bound with ``strict=True``.
- Prompt caching (ticket #12): an explicit breakpoint on the system prompt, so the tools
  and system prompt (identical for every file and attempt of a run) are one cached
  prefix, plus top-level automatic caching for the growing conversation, on the
  5-minute cache.
- ``GuardedModel.call`` is the only way the graph calls a model. It prices the call's
  worst case and refuses to send it over a cap (``CostGuard``), and its ``on_llm_end``
  callback writes one ledger row per call, with the cache tokens taken from
  langchain-anthropic's breakdown fields.
- Tracing (LangSmith, from environment variables only): the call's config is merged
  explicitly into the graph node's, so the model run is a child of the run's trace,
  inherits its metadata and is named ``repair <file> · attempt <n>``. (A plain model
  called with its own ``callbacks`` list leaves the trace; the tool-bound model happens
  to merge configs itself, and the explicit merge does not rely on that.)
- Server-side refusal fallbacks are deliberately not enabled: a fallback model is
  priced differently (and may not be in the pinned table), which would break the
  worst-case check. A refusal ends the attempt and hands the file off.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import LLMResult
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import ensure_config, merge_configs
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from migrator.cost import (
    PRICES,
    CallRecord,
    CostGuard,
    Ledger,
    LedgerRow,
    cost_usd,
    estimate_tokens,
    now_utc,
    usage_from_langchain,
)

MAX_TOKENS = 16_000  # per call: the skill's non-streaming default; part of the worst case
CACHE_CONTROL = {"type": "ephemeral"}  # 5-minute cache

ModelFactory = Callable[[str, str | None, int], BaseChatModel]


def anthropic_model(model: str, effort: str | None, max_tokens: int) -> BaseChatModel:
    """A Claude chat model through ``init_chat_model`` (needs ``ANTHROPIC_API_KEY``)."""
    from langchain.chat_models import init_chat_model

    kwargs: dict[str, Any] = {"max_tokens": max_tokens, "max_retries": 2}
    if effort is not None:
        kwargs["reasoning_effort"] = effort
    chat: BaseChatModel = init_chat_model(model, model_provider="anthropic", **kwargs)
    return chat


def served_model(message: AIMessage, requested: str) -> str:
    meta = message.response_metadata or {}
    name = meta.get("model_name") or meta.get("model")
    return str(name) if name else requested


def system_message(text: str) -> SystemMessage:
    """The system prompt as one block carrying the explicit cache breakpoint."""
    return SystemMessage(content=[{"type": "text", "text": text, "cache_control": CACHE_CONTROL}])


class LedgerCallback(BaseCallbackHandler):
    """Writes one ledger row per model call (``on_llm_end``)."""

    def __init__(
        self,
        ledger: Ledger,
        *,
        run_id: str,
        case: str | None,
        file: str | None,
        attempt: int | None,
        requested_model: str,
    ):
        self.ledger = ledger
        self.context = {"run_id": run_id, "case": case, "file": file, "attempt": attempt}
        self.requested_model = requested_model
        self.rows: list[LedgerRow] = []

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        generation = response.generations[0][0] if response.generations else None
        message = getattr(generation, "message", None)
        if not isinstance(message, AIMessage):
            return
        usage = usage_from_langchain(message.usage_metadata)
        served = served_model(message, self.requested_model)
        priced = served if served in PRICES else self.requested_model
        row = LedgerRow(
            at=now_utc(),
            model=served,
            requested_model=self.requested_model,
            usage=usage,
            cost_usd=cost_usd(priced, usage),
            **self.context,
        )
        self.ledger.append(row)
        self.rows.append(row)


class GuardedModel:
    """The one choke point for model calls: worst-case cap check, then the call."""

    def __init__(
        self,
        factory: ModelFactory,
        guard: CostGuard,
        tools: Sequence[BaseTool],
        *,
        effort: str | None,
        run_id: str,
        case: str | None,
        max_tokens: int = MAX_TOKENS,
        tags: Sequence[str] = (),
        configuration: str | None = None,
    ):
        self.factory = factory
        self.guard = guard
        self.tools = list(tools)
        self.effort = effort
        self.run_id = run_id
        self.case = case
        self.max_tokens = max_tokens
        self.tags = list(tags)
        self.configuration = configuration
        self._models: dict[str, Any] = {}
        # The tool definitions as sent, for the input estimate (fixed order).
        self._tool_json = json.dumps([convert_to_openai_tool(t, strict=True) for t in self.tools])

    def _bound(self, model: str) -> Any:
        if model not in self._models:
            llm = self.factory(model, self.effort, self.max_tokens)
            self._models[model] = llm.bind_tools(self.tools, strict=True).bind(
                cache_control=CACHE_CONTROL
            )
        return self._models[model]

    def estimate_input(self, system: str, messages: Sequence[BaseMessage]) -> int:
        payload = [system, self._tool_json, *[m.model_dump(mode="json") for m in messages]]
        return estimate_tokens(payload)

    def call(
        self,
        model: str,
        system: str,
        messages: Sequence[BaseMessage],
        *,
        run_spent_usd: float,
        file: str | None,
        attempt: int | None,
    ) -> tuple[AIMessage, CallRecord]:
        """Send one call, or raise ``CostCapError`` without sending it."""
        self.guard.check(
            model, self.estimate_input(system, messages), self.max_tokens, run_spent_usd
        )
        callback = LedgerCallback(
            self.guard.ledger,
            run_id=self.run_id,
            case=self.case,
            file=file,
            attempt=attempt,
            requested_model=model,
        )
        started = time.monotonic()
        ours: RunnableConfig = {
            "callbacks": [callback],
            "tags": [*self.tags, f"attempt:{attempt}", *([f"file:{file}"] if file else [])],
            "metadata": {
                "thread_id": self.run_id,
                "run_id": self.run_id,
                "case": self.case,
                "configuration": self.configuration,
                "file": file,
                "attempt": attempt,
                "requested_model": model,
            },
            "run_name": f"repair {file or '?'} · attempt {attempt}",
        }
        # Merged into the graph node's config: the call stays inside the run's trace.
        message = self._bound(model).invoke(
            [system_message(system), *messages], config=merge_configs(ensure_config(), ours)
        )
        if not isinstance(message, AIMessage):
            raise TypeError(f"the model returned {type(message).__name__}, not an AIMessage")
        usage = usage_from_langchain(message.usage_metadata)
        served = served_model(message, model)
        priced = served if served in PRICES else model
        meta = message.response_metadata or {}
        record = CallRecord(
            model=served,
            requested_model=model,
            usage=usage,
            cost_usd=cost_usd(priced, usage),
            file=file,
            attempt=attempt,
            stop_reason=meta.get("stop_reason"),
            duration_s=round(time.monotonic() - started, 2),
        )
        return message, record
