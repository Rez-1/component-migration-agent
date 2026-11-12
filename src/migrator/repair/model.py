"""The repair agent's model: ``init_chat_model`` behind the one cost-capped choke point.

- The chat model comes from LangChain's ``init_chat_model`` (``ChatAnthropic`` for
  Claude), so the M5 model comparison is a configuration value. The model is chosen
  per attempt from the configuration's ``attempt_models``.
- Provider features come from the model table (M7, ``migrator.model_table``): effort,
  strict tool schemas and cache breakpoints are sent only to a model whose card
  declares them. For Claude that is all three, so nothing changes from M6.
- Effort is always passed explicitly (Opus 5.5 defaults to ``medium``); ``temperature``
  and a forced ``tool_choice`` are never set (both are rejected on Opus 5.5). Tools are
  bound with ``strict=True``.
- Prompt caching (ticket #12): an explicit breakpoint on the system prompt, so the tools
  and system prompt (identical for every file and attempt of a run) are one cached
  prefix, plus top-level automatic caching for the growing conversation, on the
  5-minute cache.
- ``GuardedModel.call`` is the only way the graph calls a model. It asks the run's
  ``Budget`` to price the call's worst case and refuses to send it over a cap, and its
  ``on_llm_end``
  callback writes one ledger row per call, with the cache tokens taken from
  langchain-anthropic's breakdown fields.
- Tracing (LangSmith, from environment variables only): the call's config is merged
  explicitly into the graph node's, so the model run is a child of the run's trace,
  inherits its metadata and is named ``repair <file> · attempt <n>``. (A plain model
  called with its own ``callbacks`` list leaves the trace; the tool-bound model happens
  to merge configs itself, and the explicit merge does not rely on that.)
- Per-attempt effort (M5): ``call`` takes the attempt's effort, and one bound model is
  kept per (model, effort), so a cascade such as Haiku at high then Opus at low is a
  configuration. Effort never changes inside a file's conversation unless the model
  changes with it (an escalation starts a cold cache anyway).
- The advisor tool (M5, optional): ``advisor_20260301`` is bound next to our tools as
  a server tool (langchain-anthropic passes it through and adds its beta header). Its
  consultations bill at the advisor's rates; they are read from the raw
  ``usage.iterations`` and priced per iteration, written to the ledger as their own
  row, and the worst case of a call includes ``max_uses`` consultations of at most
  ``max_tokens`` each over the whole conversation. Advice from Opus 5.5 comes back
  encrypted, so it can be replayed but not logged.
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
from pydantic import BaseModel

from migrator.configuration import AdvisorSettings
from migrator.cost import (
    PRICES,
    Budget,
    CallRecord,
    Ledger,
    LedgerRow,
    Usage,
    cost_usd,
    estimate_tokens,
    now_utc,
    split_iterations,
    usage_from_langchain,
    worst_case_usd,
)
from migrator.model_table import card_for, chat_model

MAX_TOKENS = 16_000  # per call: the skill's non-streaming default; part of the worst case
CACHE_CONTROL = {"type": "ephemeral"}  # 5-minute cache

ModelFactory = Callable[[str, str | None, int], BaseChatModel]


def provider_model(model: str, effort: str | None, max_tokens: int) -> BaseChatModel:
    """The chat model for ``model`` from its provider, with only the features its card in
    the model table declares (needs that provider's API key in the environment)."""
    chat: BaseChatModel = chat_model(model, effort, max_tokens)
    return chat


def served_model(message: AIMessage, requested: str) -> str:
    meta = message.response_metadata or {}
    name = meta.get("model_name") or meta.get("model")
    return str(name) if name else requested


def system_message(text: str, *, caching: bool = True) -> SystemMessage:
    """The system prompt as one block, carrying the explicit cache breakpoint when the
    model declares prompt caching."""
    block: dict[str, Any] = {"type": "text", "text": text}
    if caching:
        block["cache_control"] = CACHE_CONTROL
    return SystemMessage(content=[block])


class Priced(BaseModel):
    """What one response cost: the executor's part and the advisor's consultations."""

    served: str
    usage: Usage
    cost_usd: float  # everything, advisor included
    advisor_model: str | None = None
    advisor_usage: Usage | None = None
    advisor_calls: int = 0
    advisor_cost_usd: float = 0.0


def price_message(message: AIMessage, requested_model: str) -> Priced:
    """Tokens and USD for a response, each part at the model that produced it."""
    served = served_model(message, requested_model)
    priced = served if served in PRICES else requested_model
    usage = usage_from_langchain(message.usage_metadata)
    split = split_iterations(message.response_metadata)
    if split is None:
        return Priced(served=served, usage=usage, cost_usd=cost_usd(priced, usage))
    if split.executor is not None:
        usage = split.executor
    advisor_usage = Usage()
    advisor_cost = 0.0
    for model, part in split.advisor:
        advisor_usage = advisor_usage + part
        advisor_cost += cost_usd(model, part)
    own = cost_usd(priced, usage)
    return Priced(
        served=served,
        usage=usage,
        cost_usd=round(own + advisor_cost, 6),
        advisor_model=split.advisor[0][0],
        advisor_usage=advisor_usage,
        advisor_calls=len(split.advisor),
        advisor_cost_usd=round(advisor_cost, 6),
    )


def advisor_tool(advisor: AdvisorSettings) -> dict[str, Any]:
    """The server tool definition (bound after our own tools, in a fixed position)."""
    return {
        "type": "advisor_20260301",
        "name": "advisor",
        "model": advisor.model,
        "max_uses": advisor.max_uses,
        "max_tokens": advisor.max_tokens,
        "caching": dict(CACHE_CONTROL),
    }


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
        p = price_message(message, self.requested_model)
        rows = [
            LedgerRow(
                at=now_utc(),
                model=p.served,
                requested_model=self.requested_model,
                usage=p.usage,
                cost_usd=round(p.cost_usd - p.advisor_cost_usd, 6),
                **self.context,
            )
        ]
        if p.advisor_model and p.advisor_usage is not None:
            rows.append(
                LedgerRow(
                    at=now_utc(),
                    model=p.advisor_model,
                    requested_model=p.advisor_model,
                    usage=p.advisor_usage,
                    cost_usd=p.advisor_cost_usd,
                    **self.context,
                )
            )
        for row in rows:
            self.ledger.append(row)
            self.rows.append(row)


class GuardedModel:
    """The one choke point for model calls: worst-case cap check, then the call."""

    def __init__(
        self,
        factory: ModelFactory,
        tools: Sequence[BaseTool],
        *,
        effort: str | None,
        run_id: str,
        case: str | None,
        max_tokens: int = MAX_TOKENS,
        tags: Sequence[str] = (),
        configuration: str | None = None,
        advisor: AdvisorSettings | None = None,
    ):
        self.factory = factory
        self.tools = list(tools)
        self.effort = effort
        self.run_id = run_id
        self.case = case
        self.max_tokens = max_tokens
        self.tags = list(tags)
        self.configuration = configuration
        self.advisor = advisor
        self._models: dict[tuple[str, str | None], Any] = {}
        # The tool definitions as sent, for the input estimate (fixed order).
        self._bind: list[Any] = [*self.tools, *([advisor_tool(advisor)] if advisor else [])]
        self._tool_json = json.dumps(
            [convert_to_openai_tool(t, strict=True) for t in self.tools]
            + ([advisor_tool(advisor)] if advisor else [])
        )

    def _bound(self, model: str, effort: str | None) -> Any:
        key = (model, effort)
        if key not in self._models:
            card = card_for(model)
            llm = self.factory(model, card.effort(effort), self.max_tokens)
            bound = (
                llm.bind_tools(self._bind, strict=True)
                if card.strict_tools
                else llm.bind_tools(self._bind)
            )
            self._models[key] = (
                bound.bind(cache_control=CACHE_CONTROL) if card.prompt_caching else bound
            )
        return self._models[key]

    def advisor_worst_usd(self, input_tokens: int) -> float:
        """The most the advisor can add to one call: ``max_uses`` consultations, each
        reading the whole conversation plus the executor's output so far."""
        if self.advisor is None:
            return 0.0
        a = self.advisor
        each = worst_case_usd(a.model, input_tokens + self.max_tokens, a.max_tokens)
        return round(a.max_uses * each, 6)

    def estimate_input(self, system: str, messages: Sequence[BaseMessage]) -> int:
        payload = [system, self._tool_json, *[m.model_dump(mode="json") for m in messages]]
        return estimate_tokens(payload)

    def call(
        self,
        model: str,
        system: str,
        messages: Sequence[BaseMessage],
        *,
        budget: Budget,
        file: str | None,
        attempt: int | None,
        effort: str | None = None,
    ) -> tuple[AIMessage, CallRecord]:
        """Send one call, or raise ``CostCapError`` without sending it when ``budget``
        refuses its worst case. ``effort`` defaults to the model's configured one (the
        attempt's, from the graph)."""
        effort = effort if effort is not None else self.effort
        estimate = self.estimate_input(system, messages)
        budget.check(
            model, estimate, self.max_tokens, extra_worst_usd=self.advisor_worst_usd(estimate)
        )
        callback = LedgerCallback(
            budget.ledger,
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
                "effort": effort,
            },
            "run_name": f"repair {file or '?'} · attempt {attempt}",
        }
        # Merged into the graph node's config: the call stays inside the run's trace.
        caching = card_for(model).prompt_caching
        message = self._bound(model, effort).invoke(
            [system_message(system, caching=caching), *messages],
            config=merge_configs(ensure_config(), ours),
        )
        if not isinstance(message, AIMessage):
            raise TypeError(f"the model returned {type(message).__name__}, not an AIMessage")
        p = price_message(message, model)
        meta = message.response_metadata or {}
        record = CallRecord(
            model=p.served,
            requested_model=model,
            usage=p.usage,
            cost_usd=p.cost_usd,
            file=file,
            attempt=attempt,
            stop_reason=meta.get("stop_reason"),
            duration_s=round(time.monotonic() - started, 2),
            advisor_model=p.advisor_model,
            advisor_usage=p.advisor_usage,
            advisor_calls=p.advisor_calls,
            advisor_cost_usd=p.advisor_cost_usd,
        )
        return message, record
