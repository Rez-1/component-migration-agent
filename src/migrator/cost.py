"""Cost: the pinned USD price table, the ledger, the hard cap and the pre-flight.

Everything is in USD at Anthropic's first-party prices, with no exchange rate in the
code (ticket #12). Cost is always derived from recorded tokens and the model that
served them, never from an assumed flat rate.

- **Price table** (``PRICES``): pinned, with the date it was checked.
- **Ledger** (``Ledger``): one JSON line per model call, per machine, at
  ``~/.config/migrator/ledger.jsonl`` (``MIGRATOR_LEDGER`` overrides the path). The
  month cap is enforced from it. It guards against accidents, not intent: it knows
  only this machine. The only cap that covers every machine is a spend limit set in
  the Anthropic Console.
- **Hard cap** (``CostGuard``): the one choke point every model call goes through.
  Before a call it prices the call's *worst case* (estimated input tokens at the
  cache-write price, plus ``max_tokens`` at the output price, for the attempt's
  model) and refuses to send it if spend so far plus that worst case would pass the
  run cap or the month cap. Caps are on by default ($5 a run, $20 a month) and there
  is no unlimited mode: ``--max-cost`` sets the run cap to a number, never removes it.
- **Pre-flight** (``LedgerPreflight``): before an experiment starts, its cost is
  estimated from the ledger's average cost per attempt, and it is refused if the
  estimate exceeds ``--max-cost`` or what is left of the month.
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

# Checked against the claude-api skill's model table (cached 2026-10-06) on 2026-11-09,
# and again for M3 on 2026-11-09: Opus 5.5 $4 / $20 (cache reads $0.20), Sonnet 5.5
# $2 / $10 ($0.20), Haiku 5.5 $0.10 / $0.50 up to 100K prompt tokens and $0.50 / $2.50
# above (cache reads 0.1x input). Cache writes: 5-minute 1.25x input, 1-hour 2x input.
PRICES_CHECKED = "2026-11-09"


class Price(BaseModel):
    """USD per million tokens."""

    model_config = ConfigDict(frozen=True)

    input: float
    output: float
    cache_read: float
    cache_write_5m: float  # 1.25x input
    cache_write_1h: float  # 2x input
    # A second rate card for long prompts (Haiku 5.5: above 100K tokens), or None.
    long_prompt_above: int | None = None
    long_prompt: Price | None = None


def _price(
    input_: float,
    output: float,
    cache_read: float,
    *,
    long_above: int | None = None,
    long: Price | None = None,
) -> Price:
    return Price(
        input=input_,
        output=output,
        cache_read=cache_read,
        cache_write_5m=round(input_ * 1.25, 6),
        cache_write_1h=round(input_ * 2, 6),
        long_prompt_above=long_above,
        long_prompt=long,
    )


PRICES: dict[str, Price] = {
    "claude-opus-5-5": _price(4.00, 20.00, 0.20),
    "claude-sonnet-5-5": _price(2.00, 10.00, 0.20),
    "claude-haiku-5-5": _price(0.10, 0.50, 0.01, long_above=100_000, long=_price(0.50, 2.50, 0.05)),
}


class Usage(BaseModel):
    """Tokens by type, from the API's own usage fields (never estimated).

    ``input_tokens`` is *uncached* input, as Anthropic reports it; the cache fields
    are separate (unlike LangChain's ``usage_metadata``, see ``usage_from_langchain``).
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0  # 5-minute cache writes
    cache_creation_1h_input_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            **{name: getattr(self, name) + getattr(other, name) for name in Usage.model_fields}
        )

    @property
    def prompt_tokens(self) -> int:
        """Every input token of the call: uncached, cache reads and cache writes."""
        return (
            self.input_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
            + self.cache_creation_1h_input_tokens
        )


class UnknownModelPriceError(KeyError):
    pass


def price_for(model: str, prompt_tokens: int = 0) -> Price:
    try:
        p = PRICES[model]
    except KeyError as exc:
        raise UnknownModelPriceError(
            f"no pinned price for {model!r}; add it to migrator.cost.PRICES"
        ) from exc
    if p.long_prompt is not None and p.long_prompt_above and prompt_tokens > p.long_prompt_above:
        return p.long_prompt
    return p


PER_MILLION = 1_000_000


def cost_usd(model: str, usage: Usage) -> float:
    """What ``usage`` on ``model`` costs, from the pinned table."""
    p = price_for(model, usage.prompt_tokens)
    return round(
        (
            usage.input_tokens * p.input
            + usage.output_tokens * p.output
            + usage.cache_read_input_tokens * p.cache_read
            + usage.cache_creation_input_tokens * p.cache_write_5m
            + usage.cache_creation_1h_input_tokens * p.cache_write_1h
        )
        / PER_MILLION,
        6,
    )


def _split_cost(model: str, usage: Usage) -> dict[str, float]:
    p = price_for(model, usage.prompt_tokens)
    return {
        "input": usage.input_tokens * p.input / PER_MILLION,
        "output": usage.output_tokens * p.output / PER_MILLION,
        "cache_read": usage.cache_read_input_tokens * p.cache_read / PER_MILLION,
        "cache_write": (
            usage.cache_creation_input_tokens * p.cache_write_5m
            + usage.cache_creation_1h_input_tokens * p.cache_write_1h
        )
        / PER_MILLION,
    }


def usage_from_langchain(usage_metadata: Mapping[str, Any] | None) -> Usage:
    """Anthropic's token counts from a LangChain ``AIMessage.usage_metadata``.

    langchain-anthropic folds the cache tokens into ``input_tokens``, and when the API
    returns the 5-minute/1-hour breakdown it copies it into ``input_token_details`` and
    sets ``cache_creation`` to 0 so nothing is counted twice. So: uncached input is
    ``input_tokens`` minus cache reads minus cache writes, and the cache writes are the
    two ``ephemeral_*`` keys when present, ``cache_creation`` otherwise.
    """
    if not usage_metadata:
        return Usage()
    details = dict(usage_metadata.get("input_token_details") or {})
    read = int(details.get("cache_read") or 0)
    write_5m = int(details.get("ephemeral_5m_input_tokens") or 0)
    write_1h = int(details.get("ephemeral_1h_input_tokens") or 0)
    if not (write_5m or write_1h):
        write_5m = int(details.get("cache_creation") or 0)
    total_in = int(usage_metadata.get("input_tokens") or 0)
    return Usage(
        input_tokens=max(total_in - read - write_5m - write_1h, 0),
        output_tokens=int(usage_metadata.get("output_tokens") or 0),
        cache_read_input_tokens=read,
        cache_creation_input_tokens=write_5m,
        cache_creation_1h_input_tokens=write_1h,
    )


# --------------------------------------------------------------------------- run cost

# A run whose cache reads stay at 0 after this many calls gets a scorecard warning.
CACHE_WARNING_AFTER_CALLS = 3


class RunCost(BaseModel):
    """The cost block of a scorecard: spend split by kind, and the caps it ran under."""

    total_usd: float
    output_usd: float
    input_usd: float
    cache_read_usd: float
    cache_write_usd: float
    cache_read_share: float | None  # cache reads / all input tokens; None with no calls
    model_calls: int
    models: list[str]  # the models that served the calls (from the responses)
    usage: Usage
    run_cap_usd: float
    month_cap_usd: float
    # Spend this month on this machine, from the ledger; None for a run with no calls.
    month_spent_usd: float | None = None
    stopped_by_cap: bool = False  # Repair stopped because the next call could pass a cap
    warnings: list[str] = []

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


class CallRecord(BaseModel):
    """One model call, as the run state and the ledger keep it."""

    model: str  # the model that served it
    requested_model: str
    usage: Usage
    cost_usd: float
    file: str | None = None
    attempt: int | None = None
    stop_reason: str | None = None
    duration_s: float = 0.0


def run_cost(
    calls: Iterable[CallRecord],
    run_cap_usd: float,
    month_cap_usd: float,
    *,
    month_spent_usd: float | None = None,
    stopped_by_cap: bool = False,
) -> RunCost:
    """The scorecard's cost block from the run's calls (``no_llm`` when there were none)."""
    rows = list(calls)
    if not rows:
        cost = RunCost.no_llm(run_cap_usd, month_cap_usd)
        return cost.model_copy(update={"stopped_by_cap": stopped_by_cap})
    split: dict[str, float] = defaultdict(float)
    usage = Usage()
    for row in rows:
        usage = usage + row.usage
        priced = row.model if row.model in PRICES else row.requested_model
        for kind, value in _split_cost(priced, row.usage).items():
            split[kind] += value
    warnings: list[str] = []
    if len(rows) >= CACHE_WARNING_AFTER_CALLS and usage.cache_read_input_tokens == 0:
        warnings.append(
            f"cache reads stayed at 0 over {len(rows)} calls: the cached prefix (tools and "
            "system prompt) is not being reused, so every call paid full input price"
        )
    mismatched = sorted(
        {f"{r.requested_model} -> {r.model}" for r in rows if r.model != r.requested_model}
    )
    if mismatched:
        warnings.append("served model differs from the one asked for: " + ", ".join(mismatched))
    return RunCost(
        total_usd=round(sum(split.values()), 6),
        output_usd=round(split["output"], 6),
        input_usd=round(split["input"], 6),
        cache_read_usd=round(split["cache_read"], 6),
        cache_write_usd=round(split["cache_write"], 6),
        cache_read_share=round(usage.cache_read_input_tokens / usage.prompt_tokens, 4)
        if usage.prompt_tokens
        else None,
        model_calls=len(rows),
        models=sorted({r.model for r in rows}),
        usage=usage,
        run_cap_usd=run_cap_usd,
        month_cap_usd=month_cap_usd,
        month_spent_usd=month_spent_usd,
        stopped_by_cap=stopped_by_cap,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- ledger


def default_ledger_path() -> Path:
    """``~/.config/migrator/ledger.jsonl``, or ``$MIGRATOR_LEDGER``."""
    override = os.environ.get("MIGRATOR_LEDGER")
    if override:
        return Path(override).expanduser()
    return Path("~/.config/migrator/ledger.jsonl").expanduser()


def _month(at: str) -> str:
    return at[:7]  # "2026-11"


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class LedgerRow(BaseModel):
    at: str
    run_id: str
    case: str | None = None
    file: str | None = None
    attempt: int | None = None
    model: str
    requested_model: str
    usage: Usage
    cost_usd: float


class Ledger:
    """The per-machine ledger: one JSON line per model call."""

    def __init__(self, path: Path | None = None):
        self.path = path or default_ledger_path()

    def append(self, row: LedgerRow) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(row.model_dump_json() + "\n")

    def rows(self) -> list[LedgerRow]:
        if not self.path.is_file():
            return []
        out: list[LedgerRow] = []
        for line in self.path.read_text("utf-8").splitlines():
            if line.strip():
                out.append(LedgerRow.model_validate_json(line))
        return out

    def month_spent(self, at: str | None = None) -> float:
        month = _month(at or now_utc())
        return round(sum(r.cost_usd for r in self.rows() if _month(r.at) == month), 6)

    def attempts(self, model: str) -> dict[tuple[str, str | None, int | None], float]:
        """Cost per attempt (run, file, attempt) for attempts whose first call used ``model``."""
        per: dict[tuple[str, str | None, int | None], float] = defaultdict(float)
        first: dict[tuple[str, str | None, int | None], str] = {}
        for r in self.rows():
            key = (r.run_id, r.file, r.attempt)
            first.setdefault(key, r.requested_model)
            per[key] += r.cost_usd
        return {k: v for k, v in per.items() if first[k] == model}


# --------------------------------------------------------------------------- the cap


class CostCapError(RuntimeError):
    """The next model call could pass a cap, so it was not sent."""

    def __init__(self, message: str, *, worst_case_usd: float, cap: str):
        super().__init__(message)
        self.worst_case_usd = worst_case_usd
        self.cap = cap


# Characters per token for the pre-call estimate. Claude's tokenizers give roughly 3-4
# characters per token for English and code (Haiku 5.5's counts about 30% more tokens
# for the same text); 2.5 over-counts on purpose, so the worst case stays a bound.
CHARS_PER_TOKEN = 2.5


def estimate_tokens(payload: object) -> int:
    """A deliberately high token estimate for a request, from its serialised size."""
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def worst_case_usd(model: str, input_tokens: int, max_tokens: int) -> float:
    """The most one call can cost: every input token written to the 5-minute cache
    (the dearest input rate) and ``max_tokens`` of output."""
    p = price_for(model, input_tokens)
    return round((input_tokens * p.cache_write_5m + max_tokens * p.output) / PER_MILLION, 6)


class CostGuard:
    """The hard cap: checks each call's worst case against the run and month caps."""

    def __init__(self, run_cap_usd: float, month_cap_usd: float, ledger: Ledger):
        if not (math.isfinite(run_cap_usd) and run_cap_usd > 0):
            raise ValueError("the run cap must be a positive number (there is no unlimited)")
        if not (math.isfinite(month_cap_usd) and month_cap_usd > 0):
            raise ValueError("the month cap must be a positive number (there is no unlimited)")
        self.run_cap_usd = run_cap_usd
        self.month_cap_usd = month_cap_usd
        self.ledger = ledger

    def check(self, model: str, input_tokens: int, max_tokens: int, run_spent_usd: float) -> float:
        """Raise ``CostCapError`` if the call could pass a cap; else return its worst case."""
        worst = worst_case_usd(model, input_tokens, max_tokens)
        if run_spent_usd + worst > self.run_cap_usd:
            raise CostCapError(
                f"the next call ({model}, worst case ${worst:.2f}) could take this run past "
                f"its ${self.run_cap_usd:.2f} cap (spent ${run_spent_usd:.2f})",
                worst_case_usd=worst,
                cap="run",
            )
        month = self.ledger.month_spent()
        if month + worst > self.month_cap_usd:
            raise CostCapError(
                f"the next call ({model}, worst case ${worst:.2f}) could take this month "
                f"past its ${self.month_cap_usd:.2f} cap (spent ${month:.2f} on this machine)",
                worst_case_usd=worst,
                cap="month",
            )
        return worst


# --------------------------------------------------------------------------- pre-flight


class PlannedExperiment(BaseModel):
    configuration: str
    uses_llm: bool
    runs: int  # cases x repeats still to run
    max_cost_usd: float | None  # --max-cost, required for LLM configurations
    attempt_models: list[str] = []
    month_cap_usd: float | None = None


class PreflightResult(BaseModel):
    ok: bool
    estimated_usd: float | None
    reason: str


class CostPreflight(Protocol):
    def check(self, plan: PlannedExperiment) -> PreflightResult:
        """Estimate an experiment's cost before it starts; refuse it over the caps."""
        ...


class NoLedgerPreflight:
    """M2's pre-flight, kept for rules-only callers: anything that calls a model is refused."""

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
            reason="no cost ledger, so the cost of LLM runs cannot be estimated",
        )


# Until the ledger has real attempts, the estimate uses ticket #12's guesses: about
# $0.20 per attempt on Opus 5.5 at low effort, and a fixture run of about 8 failing
# files x 1.7 attempts. Other models scale the Opus guess by their output price.
PRIOR_OPUS_ATTEMPT_USD = 0.20
PRIOR_ATTEMPTS_PER_RUN = 14
MIN_ATTEMPTS_FOR_AVERAGE = 5


def prior_attempt_usd(model: str) -> float:
    return round(
        PRIOR_OPUS_ATTEMPT_USD * price_for(model).output / PRICES["claude-opus-5-5"].output, 6
    )


class LedgerPreflight:
    """Estimates from the ledger's average cost per attempt (or the prior without one)."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def estimate(self, plan: PlannedExperiment) -> tuple[float, str]:
        model = plan.attempt_models[0] if plan.attempt_models else "claude-opus-5-5"
        attempts = self.ledger.attempts(model)
        if len(attempts) >= MIN_ATTEMPTS_FOR_AVERAGE:
            per_attempt = sum(attempts.values()) / len(attempts)
            runs_seen = {k[0] for k in attempts}
            per_run = len(attempts) / len(runs_seen)
            basis = f"ledger: {len(attempts)} attempts on {model}"
        else:
            per_attempt = prior_attempt_usd(model)
            per_run = PRIOR_ATTEMPTS_PER_RUN
            basis = f"prior (ledger has {len(attempts)} attempts on {model})"
        estimate = round(plan.runs * per_run * per_attempt, 4)
        return estimate, (
            f"{plan.runs} runs x {per_run:.1f} attempts x ${per_attempt:.3f} per attempt "
            f"= ${estimate:.2f} ({basis})"
        )

    def check(self, plan: PlannedExperiment) -> PreflightResult:
        if not plan.uses_llm:
            return PreflightResult(ok=True, estimated_usd=0.0, reason="rules only: no model calls")
        if plan.max_cost_usd is None:
            return PreflightResult(
                ok=False,
                estimated_usd=None,
                reason="an experiment that calls a model must pass --max-cost",
            )
        estimate, how = self.estimate(plan)
        if estimate > plan.max_cost_usd:
            return PreflightResult(
                ok=False,
                estimated_usd=estimate,
                reason=f"estimated {how}, over --max-cost ${plan.max_cost_usd:.2f}",
            )
        if plan.month_cap_usd is not None:
            left = round(plan.month_cap_usd - self.ledger.month_spent(), 4)
            if estimate > left:
                return PreflightResult(
                    ok=False,
                    estimated_usd=estimate,
                    reason=f"estimated {how}, more than the ${left:.2f} left of this month's "
                    f"${plan.month_cap_usd:.2f} cap",
                )
        return PreflightResult(ok=True, estimated_usd=estimate, reason=f"estimated {how}")
