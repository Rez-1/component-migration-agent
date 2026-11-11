"""The model table and the three model levels (M7 setup).

Configurations name **levels**, never a model: ``strong`` (the repair agent),
``balanced`` (the test-fitting reviewer and the eval judge) and ``fast`` (cheap helper
tasks). A level maps to a model in the table, from any provider LangChain's
``init_chat_model`` knows. Two rules hold for every mapping:

- **Every model has a price.** The cost cap prices each call's worst case before it is
  sent, so a model without a price can't be capped and is refused before anything runs.
- **balanced is a different model from strong**, so no role reviews or judges its own
  model's work.

Provider features (effort levels, prompt caching, strict tool schemas, structured
output, the advisor tool) are declared per model in the table. ``chat_model`` and the
repair agent's binding pass only what the model declares; whatever a configuration asks
for and its model lacks is listed by ``feature_notes`` and turned off up front.

The table ships as ``models.toml`` next to this module. A user's own table
(``~/.config/migrator/models.toml``, or the file ``MIGRATOR_MODELS`` names) adds models
or replaces shipped ones by id, for example another provider's models with their prices.

This module imports nothing else from the Migrator, so ``migrator.cost`` can build its
price table from it.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHIPPED_TABLE = Path(__file__).with_name("models.toml")
USER_TABLE = Path("~/.config/migrator/models.toml")
DEFAULT_PROVIDER = "anthropic"
LEVELS = ("strong", "balanced", "fast")


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RateCard(_Frozen):
    """USD per million tokens."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float = Field(ge=0)


class LongPromptCard(RateCard):
    above: int = Field(gt=0)  # prompt tokens (cache reads and writes included)


class ModelCard(_Frozen):
    """One model: its id, its price and the provider features it supports."""

    id: str  # "provider:model"
    price: RateCard
    long_prompt: LongPromptCard | None = None
    efforts: tuple[str, ...] = ()
    effort_param: str = "reasoning_effort"  # the init_chat_model keyword for effort
    prompt_caching: bool = False
    strict_tools: bool = False
    structured_output: bool = False
    advisor: bool = False

    @field_validator("id")
    @classmethod
    def _provider_and_model(cls, v: str) -> str:
        provider, sep, model = v.partition(":")
        if not sep or not provider or not model:
            raise ValueError(f"model id {v!r} must be 'provider:model'")
        return v

    @property
    def provider(self) -> str:
        return self.id.partition(":")[0]

    @property
    def model(self) -> str:
        return self.id.partition(":")[2]

    @property
    def ref(self) -> str:
        """How configurations, the ledger and scorecards name this model: the bare id for
        the default provider (as since M2), ``provider:model`` for every other."""
        return self.model if self.provider == DEFAULT_PROVIDER else self.id

    def effort(self, wanted: str | None) -> str | None:
        """The effort to send: ``wanted`` if the model declares it, else None."""
        return wanted if wanted is not None and wanted in self.efforts else None


class ModelTable(_Frozen):
    checked: str
    cards: dict[str, ModelCard]  # by ref

    def find(self, name: str) -> ModelCard | None:
        """A card by ref, or by full id (``anthropic:claude-opus-5-5``)."""
        if name in self.cards:
            return self.cards[name]
        for card in self.cards.values():
            if card.id == name:
                return card
        return None


class UnknownModelError(ValueError):
    """A model with no entry, so no price, in the model table."""


def _read(path: Path) -> tuple[str | None, list[ModelCard]]:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    try:
        cards = [ModelCard.model_validate(m) for m in data.get("model", [])]
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc
    return data.get("checked"), cards


def user_table_path() -> Path:
    return Path(os.environ.get("MIGRATOR_MODELS") or USER_TABLE).expanduser()


@cache
def _load(user: Path | None) -> ModelTable:
    checked, cards = _read(SHIPPED_TABLE)
    by_ref = {c.ref: c for c in cards}
    if user is not None and user.is_file():
        _, extra = _read(user)
        by_ref.update({c.ref: c for c in extra})
    return ModelTable(checked=checked or "unknown", cards=by_ref)


def model_table() -> ModelTable:
    """The shipped table plus the user's own (read once per user-table path)."""
    return _load(user_table_path())


def shipped_table() -> ModelTable:
    """Only the shipped table: the prices every configuration in this repo is costed at."""
    return _load(None)


def card_for(name: str) -> ModelCard:
    """The card for a model, or ``UnknownModelError``: no price means no run."""
    card = model_table().find(name)
    if card is None:
        known = ", ".join(sorted(model_table().cards))
        raise UnknownModelError(
            f"{name!r} is not in the model table, so it has no price and the cost cap "
            f"can't cover it; the Migrator won't run it. Add it, with its price and "
            f"features, to {user_table_path()} (known: {known})"
        )
    return card


def canonical(name: str) -> str:
    """The ref a model is recorded under (``anthropic:claude-opus-5-5`` -> bare id)."""
    return card_for(name).ref


class ModelLevels(_Frozen):
    """Which model fills each level. The defaults are Claude's."""

    strong: str = "claude-opus-5-5"
    balanced: str = "claude-sonnet-5-5"
    fast: str = "claude-haiku-5-5"

    @model_validator(mode="after")
    def _priced_and_distinct(self) -> ModelLevels:
        refs = {level: canonical(getattr(self, level)) for level in LEVELS}
        if refs["balanced"] == refs["strong"]:
            raise ValueError(
                f"balanced and strong are both {refs['strong']}; balanced reviews and "
                "judges strong's work, so it must be a different model"
            )
        for level, ref in refs.items():
            object.__setattr__(self, level, ref)  # frozen; an after-validator returns self
        return self

    def resolve(self, name: str) -> str:
        """A level name to its model's ref; a model name to its canonical ref."""
        if name in LEVELS:
            return str(getattr(self, name))
        return canonical(name)


def chat_model(name: str, effort: str | None, max_tokens: int) -> Any:
    """A LangChain chat model for ``name``, given only the features its card declares.

    Needs the provider's LangChain package (``langchain-anthropic`` for Claude) and its
    API key in the environment."""
    from langchain.chat_models import init_chat_model

    card = card_for(name)
    kwargs: dict[str, Any] = {"max_tokens": max_tokens, "max_retries": 2}
    sent = card.effort(effort)
    if sent is not None:
        kwargs[card.effort_param] = sent
    return init_chat_model(card.model, model_provider=card.provider, **kwargs)


def provider_package(provider: str) -> str:
    """The LangChain integration package a provider needs (``langchain-<provider>``)."""
    return f"langchain_{provider.replace('-', '_')}"


def missing_packages(names: Iterable[str]) -> list[str]:
    """Provider packages the given models need and this environment doesn't have."""
    import importlib.util

    out = []
    for provider in sorted({card_for(n).provider for n in names}):
        package = provider_package(provider)
        if importlib.util.find_spec(package) is None:
            out.append(package.replace("_", "-"))
    return out


def feature_notes(
    role: str,
    name: str,
    *,
    effort: str | None = None,
    caching: bool = False,
    strict_tools: bool = False,
    structured_output: bool = False,
) -> list[str]:
    """One line per feature ``role`` asks of ``name`` that its card doesn't declare."""
    card = card_for(name)
    off = []
    if effort is not None and card.effort(effort) is None:
        off.append(
            f"effort {effort!r} (it accepts {', '.join(card.efforts)})"
            if card.efforts
            else f"effort {effort!r} (no effort control)"
        )
    if caching and not card.prompt_caching:
        off.append("prompt caching")
    if strict_tools and not card.strict_tools:
        off.append("strict tool schemas")
    if structured_output and not card.structured_output:
        off.append("structured output (its JSON answer is parsed from text instead)")
    return [f"{role} on {card.ref}: turned off {x}, which it doesn't declare" for x in off]
