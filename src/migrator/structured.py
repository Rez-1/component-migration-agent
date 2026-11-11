"""One structured-output call to any model in the model table (M7).

The test-fitting reviewer and the eval judge each ask one question and want one JSON
object back. A model whose card declares ``structured_output`` gets LangChain's
``with_structured_output(method="json_schema")``. Any other model gets the schema in the
system prompt and its first JSON object is parsed from the text, so a provider without
structured output still works and the run says so (``feature_notes``) instead of failing.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from migrator.model_table import card_for


class StructuredAnswer:
    """The parsed answer (or None and why), and the raw message for usage and model."""

    def __init__(self, parsed: Any, raw: AIMessage | None, error: str | None):
        self.parsed, self.raw, self.error = parsed, raw, error

    @property
    def served(self) -> str | None:
        meta = (self.raw.response_metadata if self.raw is not None else None) or {}
        name = meta.get("model_name") or meta.get("model")
        return str(name) if name else None

    @property
    def stop_reason(self) -> str | None:
        meta = (self.raw.response_metadata if self.raw is not None else None) or {}
        reason = meta.get("stop_reason")
        return str(reason) if reason else None


def first_json_object(text: str) -> Any:
    """The first complete JSON object in ``text`` (models often wrap it in prose)."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                value, _ = decoder.raw_decode(text, i)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    raise ValueError("no JSON object in the answer")


def ask_structured(
    chat: BaseChatModel,
    model: str,
    schema: type[BaseModel] | dict[str, Any],
    system: str,
    prompt: str,
    config: RunnableConfig | None = None,
) -> StructuredAnswer:
    """Ask ``chat`` (built for ``model``) one question. The answer is an instance of
    ``schema`` when it is a pydantic class, a dict when it is a JSON schema, or None
    with the parsing error."""
    if card_for(model).structured_output:
        runnable = chat.with_structured_output(schema, method="json_schema", include_raw=True)
        out = runnable.invoke(
            [SystemMessage(content=system), HumanMessage(content=prompt)], config=config
        )
        assert isinstance(out, dict)
        raw = out.get("raw")
        error = out.get("parsing_error")
        return StructuredAnswer(
            out.get("parsed"),
            raw if isinstance(raw, AIMessage) else None,
            str(error) if error else None,
        )
    as_json = schema if isinstance(schema, dict) else schema.model_json_schema()
    asked = (
        f"{system}\n\nAnswer with one JSON object, and nothing else, that matches this "
        f"JSON schema:\n{json.dumps(as_json, sort_keys=True)}"
    )
    message = chat.invoke(
        [SystemMessage(content=asked), HumanMessage(content=prompt)], config=config
    )
    if not isinstance(message, AIMessage):
        return StructuredAnswer(None, None, f"the model returned {type(message).__name__}")
    try:
        data = first_json_object(message.text)
        parsed = data if isinstance(schema, dict) else schema.model_validate(data)
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        return StructuredAnswer(None, message, str(exc))
    return StructuredAnswer(parsed, message, None)
