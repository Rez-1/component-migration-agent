"""Cost: the pinned USD price table, the ledger, the hard cap and the pre-flight.

Everything is in USD at the providers' own list prices, with no exchange rate in the
code (ticket #12). Cost is always derived from recorded tokens and the model that
served them, never from an assumed flat rate.

- **Price table** (``PRICES``): built from the model table (``migrator/models.toml``
  and the user's own), with the date it was checked. A model with no price is refused.
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
- **Budget** (``Budget``): one Run's Cost caps, spend so far and Reservation. It
  reserves the Run's worst case before Repair (in a book shared by every run in the
  process, so parallel runs can't pass the month cap together), checks every model
  call through the hard cap, and releases the Reservation when the run ends.
- **Pre-flight** (``LedgerPreflight``): before an experiment starts, its cost is
  estimated from the ledger's average cost per attempt, and it is refused if the
  estimate exceeds ``--max-cost`` or what is left of the month.
"""

from __future__ import annotations

import json
import math
import os
import threading
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, model_serializer

from migrator.model_table import ModelTable, model_table


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


def _prices(table: ModelTable) -> dict[str, Price]:
    """The price table, by model ref and by full ``provider:model`` id."""
    out: dict[str, Price] = {}
    for card in table.cards.values():
        long = card.long_prompt
        price = _price(
            card.price.input,
            card.price.output,
            card.price.cache_read,
            long_above=long.above if long else None,
            long=_price(long.input, long.output, long.cache_read) if long else None,
        )
        out[card.ref] = out[card.id] = price
    return out


# The model table's prices (migrator/models.toml, plus the user's own table). A model
# with no price can't be capped, so it is refused before any call.
PRICES: dict[str, Price] = _prices(model_table())
PRICES_CHECKED = model_table().checked


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
        p = PRICES[model] if model in PRICES else _prices(model_table())[model]
    except KeyError as exc:
        raise UnknownModelPriceError(
            f"no price for {model!r}; add it to the model table (migrator/models.toml or "
            "~/.config/migrator/models.toml)"
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


def usage_from_iteration(entry: Mapping[str, Any]) -> Usage:
    """One entry of the raw ``usage.iterations`` list (Anthropic's own field names)."""
    creation = dict(entry.get("cache_creation") or {})
    write_5m = int(creation.get("ephemeral_5m_input_tokens") or 0)
    write_1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
    if not (write_5m or write_1h):
        write_5m = int(entry.get("cache_creation_input_tokens") or 0)
    return Usage(
        input_tokens=int(entry.get("input_tokens") or 0),
        output_tokens=int(entry.get("output_tokens") or 0),
        cache_read_input_tokens=int(entry.get("cache_read_input_tokens") or 0),
        cache_creation_input_tokens=write_5m,
        cache_creation_1h_input_tokens=write_1h,
    )


class Iterations(BaseModel):
    """A response's ``usage.iterations`` split into the executor's and the advisor's part."""

    executor: Usage | None  # None when the response listed no ``message`` iterations
    advisor: list[tuple[str, Usage]]  # (advisor model, usage), one per consultation


def split_iterations(response_metadata: Mapping[str, Any] | None) -> Iterations | None:
    """The advisor's consultations, from the raw usage langchain-anthropic copies into
    ``response_metadata["usage"]`` (it is not in ``usage_metadata``). None when the
    response has no advisor iterations, so ordinary calls keep the M3 accounting.

    Each iteration is priced at its own model: an advisor's tokens bill at the advisor's
    rates, and the executor's own tokens are the ``message`` iterations."""
    usage = (response_metadata or {}).get("usage")
    if not isinstance(usage, Mapping):
        return None
    entries = [e for e in usage.get("iterations") or [] if isinstance(e, Mapping)]
    advisor = [
        (str(e.get("model") or ""), usage_from_iteration(e))
        for e in entries
        if e.get("type") == "advisor_message"
    ]
    if not advisor:
        return None
    messages = [usage_from_iteration(e) for e in entries if e.get("type") == "message"]
    executor = sum(messages, Usage()) if messages else None
    return Iterations(executor=executor, advisor=advisor)


# --------------------------------------------------------------------------- run cost

# A run whose cache reads stay at 0 after this many calls gets a scorecard warning.
CACHE_WARNING_AFTER_CALLS = 3


class ModelCost(BaseModel):
    """One model's share of a run: its calls (for an advisor, its consultations) and cost."""

    model: str
    calls: int
    cost_usd: float


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
    # Cost per model (M5: cascades and the advisor mix models). Left out of the JSON when
    # empty, so a run with no model calls serialises exactly as before.
    by_model: list[ModelCost] = []

    @model_serializer(mode="wrap")
    def _drop_empty_by_model(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not data.get("by_model"):
            data.pop("by_model", None)
        return data

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
    # The advisor's consultations inside this call (M5), priced at the advisor's rates
    # and included in ``cost_usd``.
    advisor_model: str | None = None
    advisor_usage: Usage | None = None
    advisor_calls: int = 0
    advisor_cost_usd: float = 0.0


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
    per_model: dict[str, list[float]] = {}
    for row in rows:
        usage = usage + row.usage
        priced = row.model if row.model in PRICES else row.requested_model
        for kind, value in _split_cost(priced, row.usage).items():
            split[kind] += value
        mine = per_model.setdefault(row.model, [0, 0.0])
        mine[0] += 1
        mine[1] += row.cost_usd - row.advisor_cost_usd
        if row.advisor_model and row.advisor_usage is not None:
            usage = usage + row.advisor_usage
            for kind, value in _split_cost(row.advisor_model, row.advisor_usage).items():
                split[kind] += value
            theirs = per_model.setdefault(row.advisor_model, [0, 0.0])
            theirs[0] += row.advisor_calls
            theirs[1] += row.advisor_cost_usd
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
        models=sorted(per_model),
        usage=usage,
        run_cap_usd=run_cap_usd,
        month_cap_usd=month_cap_usd,
        month_spent_usd=month_spent_usd,
        stopped_by_cap=stopped_by_cap,
        warnings=warnings,
        by_model=[
            ModelCost(model=m, calls=int(v[0]), cost_usd=round(v[1], 6))
            for m, v in sorted(per_model.items())
        ],
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


_LEDGER_LOCK = threading.Lock()


class Ledger:
    """The per-machine ledger: one JSON line per model call."""

    def __init__(self, path: Path | None = None):
        self.path = path or default_ledger_path()

    def append(self, row: LedgerRow) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER_LOCK, self.path.open("a", encoding="utf-8") as fh:
            fh.write(row.model_dump_json() + "\n")

    def rows(self) -> list[LedgerRow]:
        if not self.path.is_file():
            return []
        out: list[LedgerRow] = []
        for line in self.path.read_text("utf-8").splitlines():
            if line.strip():
                out.append(LedgerRow.model_validate_json(line))
        return out

    def repair_rows(self) -> list[LedgerRow]:
        """Rows of repair runs: not the reference judge's (run id ``judge:...``, M6), so
        cost-per-attempt estimates only average repair attempts."""
        return [r for r in self.rows() if not r.run_id.startswith("judge:")]

    def month_spent(self, at: str | None = None) -> float:
        month = _month(at or now_utc())
        return round(sum(r.cost_usd for r in self.rows() if _month(r.at) == month), 6)

    def attempts(self, model: str) -> dict[tuple[str, str | None, int | None], float]:
        """Cost per attempt (run, file, attempt) for attempts whose first call used ``model``."""
        per: dict[tuple[str, str | None, int | None], float] = defaultdict(float)
        first: dict[tuple[str, str | None, int | None], str] = {}
        for r in self.repair_rows():
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

    def check(
        self,
        model: str,
        input_tokens: int,
        max_tokens: int,
        run_spent_usd: float,
        *,
        extra_worst_usd: float = 0.0,
    ) -> float:
        """Raise ``CostCapError`` if the call could pass a cap; else return its worst case.

        ``extra_worst_usd`` is spend the call can cause on another model (the advisor's
        consultations), added to the call's own worst case."""
        worst = round(worst_case_usd(model, input_tokens, max_tokens) + extra_worst_usd, 6)
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


# --------------------------------------------------------------------------- the budget

# Runs must finish (M6), also when several run at once in one process (parallel repeat
# runs): each run's Reservation is held in this shared book until the run ends, and a
# run may only reserve what the month cap leaves after the other runs' outstanding
# Reservations (what each has reserved, less what it has already spent, which
# month_spent counts). Only the Budget touches it.
_RESERVED: dict[str, float] = {}
_RESERVE_LOCK = threading.Lock()


class RunCaps(BaseModel):
    """One Run's Cost caps, and what its Reservation is made of.

    ``stop_usd`` is the hard stop: a lower per-call limit a Configuration may set (M6,
    $2). ``reserve_attempt_usd`` is the worst case set aside per Attempt; None reserves
    nothing."""

    model_config = ConfigDict(frozen=True)

    run_usd: float
    month_usd: float
    stop_usd: float | None = None
    reserve_attempt_usd: float | None = None
    max_attempts: int = 3

    @property
    def call_cap_usd(self) -> float:
        """What the check before each model call stops at: the run cap, or the lower
        hard stop."""
        return min(self.run_usd, self.stop_usd) if self.stop_usd is not None else self.run_usd


class Reservation(BaseModel):
    """What one ``Budget.reserve`` asked for, and whether the shared book took it."""

    held: bool
    files: int  # the files reserved for (failing Test files cost nothing)
    added_usd: float  # their worst case: files x attempts x reserve per attempt
    total_usd: float  # the Run's whole Reservation with them
    available_usd: float  # what the run cap and the month left had room for


class Budget:
    """One Run's money: its Cost caps, its spend so far and its Reservation.

    It keeps nothing between steps: each step builds it again from the checkpointed
    state (the run's recorded spend and ``reserved_usd``), and its only lasting part is
    the run's entry in the shared book. ``pipeline.start_run`` and ``resume_run`` open
    it and release it in their ``finally``, so a run that crashes, times out or pauses
    never leaves a Reservation behind."""

    def __init__(
        self,
        run_id: str,
        caps: RunCaps,
        ledger: Ledger,
        *,
        spent_usd: float = 0.0,
        reserved_usd: float | None = None,
    ):
        self.run_id = run_id
        self.caps = caps
        self.ledger = ledger
        self.spent_usd = spent_usd
        self.reserved_usd = reserved_usd
        self._guard = CostGuard(caps.call_cap_usd, caps.month_usd, ledger)

    def check(
        self, model: str, input_tokens: int, max_tokens: int, *, extra_worst_usd: float = 0.0
    ) -> float:
        """Before a model call: raise ``CostCapError`` if its worst case could pass a
        cap, else return the worst case. ``extra_worst_usd`` is spend the call can cause
        on another model (the advisor's consultations)."""
        return self._guard.check(
            model, input_tokens, max_tokens, self.spent_usd, extra_worst_usd=extra_worst_usd
        )

    def reserve(self, files: Collection[str]) -> Reservation | None:
        """Add the worst case of ``files`` to the Reservation, if the run cap
        and the month (less other runs' Reservations) have room: the first pass reserves
        for its queue, the recheck tops up for the files it adds. None when the caps
        reserve nothing. The new total counts this run's spend twice against the month:
        on the safe side."""
        per = self.caps.reserve_attempt_usd
        if per is None:
            return None
        added = round(len(files) * self.caps.max_attempts * per, 2)
        total = round((self.reserved_usd or 0.0) + added, 2)
        held, available = self._book(total, need=total)
        if held:
            self.reserved_usd = total
        return Reservation(
            held=held, files=len(files), added_usd=added, total_usd=total, available_usd=available
        )

    def reopen(self) -> bool:
        """On resume: hold the recorded Reservation again, less what is already spent,
        so a resumed run keeps the guarantee of a fresh one. False when the month has
        no room left for it (nothing is held then)."""
        if not self.reserved_usd:
            return True
        need = max(0.0, round(self.reserved_usd - self.spent_usd, 6))
        return self._book(self.reserved_usd, need=need)[0]

    def release(self) -> None:
        """End this run's Reservation."""
        with _RESERVE_LOCK:
            _RESERVED.pop(self.run_id, None)

    def _book(self, total: float, *, need: float) -> tuple[bool, float]:
        """Hold ``total`` for this run if ``need`` fits; (held, what was available)."""
        with _RESERVE_LOCK:
            month = _month(now_utc())
            spent_by: dict[str, float] = defaultdict(float)
            for r in self.ledger.rows():
                if _month(r.at) == month:
                    spent_by[r.run_id] += r.cost_usd
            others = sum(
                max(0.0, usd - spent_by.get(rid, 0.0))
                for rid, usd in _RESERVED.items()
                if rid != self.run_id
            )
            month_left = self.caps.month_usd - sum(spent_by.values()) - others
            available = round(min(self.caps.run_usd, month_left), 2)
            if need > available:
                return False, available
            _RESERVED[self.run_id] = total
            return True, available


# --------------------------------------------------------------------------- pre-flight


class PlannedExperiment(BaseModel):
    configuration: str
    uses_llm: bool
    runs: int  # cases x repeats still to run
    max_cost_usd: float | None  # --max-cost, required for LLM configurations
    attempt_models: list[str] = []
    month_cap_usd: float | None = None
    advisor_model: str | None = None  # the advisor tool's model, if the configuration has one


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
# The advisor's consultations, until the ledger has some: tokens one consultation reads
# (about a fixture conversation) and writes (advice is short; max_tokens bounds it).
ADVISOR_PRIOR_INPUT = 12_000
ADVISOR_PRIOR_OUTPUT = 1_500
# Without ledger data, a guess at how a run's attempts fall on attempt 1, 2 and 3.
PRIOR_POSITION_SHARE = (0.7, 0.2, 0.1)


def prior_attempt_usd(model: str) -> float:
    return round(
        PRIOR_OPUS_ATTEMPT_USD * price_for(model).output / PRICES["claude-opus-5-5"].output, 6
    )


class LedgerPreflight:
    """Estimates from the ledger's average cost per attempt (or the prior without one)."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def estimate(self, plan: PlannedExperiment) -> tuple[float, str]:
        if len(set(plan.attempt_models)) > 1:
            return self.estimate_mixed(plan)
        model = plan.attempt_models[0] if plan.attempt_models else "claude-opus-5-5"
        attempts = self.ledger.attempts(model)
        if len(attempts) >= MIN_ATTEMPTS_FOR_AVERAGE:
            per_attempt = sum(attempts.values()) / len(attempts)
            runs_seen = {k[0] for k in attempts}
            per_run = len(attempts) / len(runs_seen)
            basis = f"ledger: {len(attempts)} attempts on {model}"
        else:
            per_attempt, scaled = self.scaled_prior(model)
            counts, how = self.attempts_per_run()
            per_run = sum(counts) if scaled else PRIOR_ATTEMPTS_PER_RUN
            basis = (
                f"{scaled}; attempts per run from the {how}"
                if scaled
                else f"prior (ledger has {len(attempts)} attempts on {model})"
            )
        estimate = round(plan.runs * per_run * per_attempt, 4)
        return estimate, (
            f"{plan.runs} runs x {per_run:.1f} attempts x ${per_attempt:.3f} per attempt "
            f"= ${estimate:.2f} ({basis})"
        )

    def scaled_prior(self, model: str) -> tuple[float, str | None]:
        """Cost per attempt for a model the ledger has too few attempts on: the measured
        average of the model with the most attempts, scaled by the output price ratio
        (output dominates an attempt's cost), else ticket #12's prior. Returns the cost
        and how it was derived (None for the plain prior)."""
        best: tuple[int, str, float] | None = None
        for other in {r.requested_model for r in self.ledger.rows()} - {model}:
            if other not in PRICES:
                continue
            attempts = self.ledger.attempts(other)
            if len(attempts) >= MIN_ATTEMPTS_FOR_AVERAGE and (
                best is None or len(attempts) > best[0]
            ):
                best = (len(attempts), other, sum(attempts.values()) / len(attempts))
        if best is None:
            return prior_attempt_usd(model), None
        n, other, each = best
        ratio = price_for(model).output / price_for(other).output
        return round(each * ratio, 6), (
            f"scaled from {n} attempts on {other} by the output price ratio {ratio:.2f}"
        )

    def attempts_per_run(self) -> tuple[list[float], str]:
        """Mean attempts per run at each attempt number (1, 2, 3, ...), over every run in
        the ledger whatever its model; the prior split of ticket #12's guess without one."""
        per: dict[tuple[str, str | None, int | None], None] = {}
        for r in self.ledger.repair_rows():
            per.setdefault((r.run_id, r.file, r.attempt), None)
        runs = {k[0] for k in per}
        if len(per) < MIN_ATTEMPTS_FOR_AVERAGE or not runs:
            return [PRIOR_ATTEMPTS_PER_RUN * s for s in PRIOR_POSITION_SHARE], "prior"
        top = max((k[2] or 1) for k in per)
        counts = [0.0] * top
        for _run, _file, attempt in per:
            counts[(attempt or 1) - 1] += 1
        return [c / len(runs) for c in counts], f"ledger: {len(runs)} runs"

    def estimate_mixed(self, plan: PlannedExperiment) -> tuple[float, str]:
        """A configuration whose attempts use different models (a cascade): attempts at
        position k are priced at attempt k's model. Each model's cost per attempt is its
        ledger average (or the prior); escalated attempts start with a cold cache, which
        the average of mostly-first attempts already includes."""
        per_run, basis = self.attempts_per_run()
        parts: list[str] = []
        total = 0.0
        for k, model in enumerate(plan.attempt_models, 1):
            n = per_run[k - 1] if k <= len(per_run) else 0.0
            attempts = self.ledger.attempts(model)
            if len(attempts) >= MIN_ATTEMPTS_FOR_AVERAGE:
                each = sum(attempts.values()) / len(attempts)
            else:
                each, _ = self.scaled_prior(model)
            total += n * each
            parts.append(f"attempt {k} {model}: {n:.1f} x ${each:.3f}")
        estimate = round(plan.runs * total, 4)
        return estimate, (
            f"{plan.runs} runs x ({'; '.join(parts)}) = ${estimate:.2f} "
            f"(attempts per run from the {basis})"
        )

    def estimate_with_advisor(self, plan: PlannedExperiment) -> tuple[float, str]:
        """``estimate`` plus, with an advisor, one consultation per attempt priced as a
        guess (``ADVISOR_PRIOR_INPUT`` tokens read, ``ADVISOR_PRIOR_OUTPUT`` written, no
        cache). Replace the guess with measured rows after the first advisor run."""
        estimate, how = self.estimate(plan)
        if plan.advisor_model is None:
            return estimate, how
        counts, _ = self.attempts_per_run()
        attempts = sum(counts[: len(plan.attempt_models)])
        p = price_for(plan.advisor_model)
        each = (ADVISOR_PRIOR_INPUT * p.input + ADVISOR_PRIOR_OUTPUT * p.output) / PER_MILLION
        extra = round(plan.runs * attempts * each, 4)
        return round(estimate + extra, 4), (
            f"{how}; advisor {plan.advisor_model} +${extra:.2f} (a guess: one consultation "
            "per attempt, "
            f"{ADVISOR_PRIOR_INPUT} tokens in, {ADVISOR_PRIOR_OUTPUT} out, ${each:.3f} each)"
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
        estimate, how = self.estimate_with_advisor(plan)
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
