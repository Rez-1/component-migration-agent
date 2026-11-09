"""Cost: the pinned USD price table, run cost records and the pre-flight hook.

Everything is in USD at Anthropic's first-party prices, with no exchange rate in the
code (ticket #12). Cost is always derived from recorded tokens and the model that
served them, never from an assumed flat rate. The per-machine ledger and the per-call
cap wrapper arrive with the repair loop in M3; M2 ships the price table, the cost fields
every scorecard carries, and the pre-flight check point an experiment calls before it
starts.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

# Checked against the claude-api skill's model table (cached 2026-10-06) on 2026-11-09.
PRICES_CHECKED = "2026-11-09"


class Price(BaseModel):
    """USD per million tokens."""

    model_config = ConfigDict(frozen=True)

    input: float
    output: float
    cache_read: float
    cache_write_5m: float  # 1.25x input
    cache_write_1h: float  # 2x input


def _price(input_: float, output: float, cache_read: float) -> Price:
    return Price(
        input=input_,
        output=output,
        cache_read=cache_read,
        cache_write_5m=round(input_ * 1.25, 6),
        cache_write_1h=round(input_ * 2, 6),
    )


PRICES: dict[str, Price] = {
    "claude-opus-5-5": _price(4.00, 20.00, 0.20),
    "claude-sonnet-5-5": _price(2.00, 10.00, 0.20),
    "claude-haiku-5-5": _price(0.10, 0.50, 0.01),
}


class Usage(BaseModel):
    """Tokens by type, from the API's own usage fields (never estimated)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0  # 5-minute cache writes
    cache_creation_1h_input_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            **{name: getattr(self, name) + getattr(other, name) for name in Usage.model_fields}
        )


class UnknownModelPriceError(KeyError):
    pass


def cost_usd(model: str, usage: Usage) -> float:
    """What ``usage`` on ``model`` costs, from the pinned table."""
    try:
        p = PRICES[model]
    except KeyError as exc:
        raise UnknownModelPriceError(
            f"no pinned price for {model!r}; add it to migrator.cost.PRICES"
        ) from exc
    per_token = 1_000_000
    return round(
        (
            usage.input_tokens * p.input
            + usage.output_tokens * p.output
            + usage.cache_read_input_tokens * p.cache_read
            + usage.cache_creation_input_tokens * p.cache_write_5m
            + usage.cache_creation_1h_input_tokens * p.cache_write_1h
        )
        / per_token,
        6,
    )


class RunCost(BaseModel):
    """The cost block of a scorecard: spend split by kind, and the caps it ran under."""

    total_usd: float
    output_usd: float
    input_usd: float
    cache_read_usd: float
    cache_write_usd: float
    cache_read_share: float | None  # cache reads / all input tokens; None with no calls
    model_calls: int
    models: list[str]
    usage: Usage
    run_cap_usd: float
    month_cap_usd: float
    # Spend this month on this machine, from the ledger (M3); None until it exists.
    month_spent_usd: float | None = None

    @classmethod
    def no_llm(cls, run_cap_usd: float, month_cap_usd: float) -> RunCost:
        """A run that made no model calls, such as the Baseline: $0 by construction."""
        return cls(
            total_usd=0.0,
            output_usd=0.0,
            input_usd=0.0,
            cache_read_usd=0.0,
            cache_write_usd=0.0,
            cache_read_share=None,
            model_calls=0,
            models=[],
            usage=Usage(),
            run_cap_usd=run_cap_usd,
            month_cap_usd=month_cap_usd,
        )


# --------------------------------------------------------------------------- pre-flight


class PlannedExperiment(BaseModel):
    configuration: str
    uses_llm: bool
    runs: int  # cases x repeats still to run
    max_cost_usd: float | None  # --max-cost, required for LLM configurations


class PreflightResult(BaseModel):
    ok: bool
    estimated_usd: float | None
    reason: str


class CostPreflight(Protocol):
    def check(self, plan: PlannedExperiment) -> PreflightResult:
        """Estimate an experiment's cost before it starts; refuse it over the caps."""
        ...


class NoLedgerPreflight:
    """M2's pre-flight: rules-only experiments cost $0; anything else is refused.

    M3 replaces this with one that estimates from the ledger's average cost per attempt
    and refuses an experiment whose estimate exceeds what is left of the month.
    """

    def check(self, plan: PlannedExperiment) -> PreflightResult:
        if not plan.uses_llm:
            return PreflightResult(ok=True, estimated_usd=0.0, reason="rules only: no model calls")
        if plan.max_cost_usd is None:
            return PreflightResult(
                ok=False,
                estimated_usd=None,
                reason="an experiment that calls a model must pass --max-cost",
            )
        return PreflightResult(
            ok=False,
            estimated_usd=None,
            reason="no cost ledger yet (M3), so the cost of LLM runs cannot be estimated",
        )
