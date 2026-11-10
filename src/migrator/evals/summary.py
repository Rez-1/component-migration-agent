"""The experiment summary: an experiment's scorecards aggregated, with mean and spread.

Every number is recomputed from the raw per-run rows (``results.jsonl``) and the runs'
scorecards, never from an aggregate field. With 2 runs the spread is shown as both
values next to the mean; with 3 or more, as the mean and the range (ticket #10). Cost
per clean run is total cost / clean runs, and undefined ("—") when there are none.

JSON is the source of truth (``experiment-summary.json``); the markdown is rendered
from it. Times, dates and run ids live in ``meta``, so the rest is deterministic for a
deterministic configuration and can be committed and compared.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, SerializerFunctionWrapHandler, model_serializer

from migrator.cost import ModelCost
from migrator.evals import (
    EvalError,
    Manifest,
    ResultRow,
    read_errors,
    read_manifest,
    read_rows,
)
from migrator.report import Scorecard, is_silent_miss, usd

SCHEMA_VERSION = 1

Unit = Literal["yes/no", "share", "count", "usd"]


class MetricSummary(BaseModel):
    id: str
    label: str
    unit: Unit
    values: list[float]  # one per scored run, in (case, rep) order
    mean: float | None
    min: float | None
    max: float | None
    baseline_mean: float | None = None
    change: float | None = None  # mean - baseline_mean


class TrapAcrossRuns(BaseModel):
    id: str
    title: str
    expected_layer: str
    case: str
    results: list[str]  # one per run of that case


class RunRef(BaseModel):
    case: str
    rep: int
    scorecard: str


class CostSummary(BaseModel):
    total_usd: float
    per_run_usd: float | None
    per_clean_run_usd: float | None  # None when no run was clean: never divide by zero
    clean_runs: int
    # Cost per model over the scored runs (M5: cascades, the advisor); left out of the
    # JSON when no run called a model, so a rules-only summary is unchanged.
    by_model: list[ModelCost] = []

    @model_serializer(mode="wrap")
    def _drop_empty_by_model(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not data.get("by_model"):
            data.pop("by_model", None)
        return data


class Comparison(BaseModel):
    experiment: str
    configuration: str
    runs: int
    clean_runs: int


class SummaryMeta(BaseModel):
    created_at: str
    experiment_created_at: str
    run_ids: list[str]
    time_per_run_s: list[float]
    mean_time_s: float | None
    baseline_mean_time_s: float | None
    migrator_version: str


class ExperimentSummary(BaseModel):
    schema_version: int = SCHEMA_VERSION
    experiment: str
    split: str
    configuration: str
    configuration_digest: str
    cases: list[str]
    repeats: int
    runs_planned: int
    runs_scored: int
    runs_not_scored: dict[str, int]  # failure class -> count (errors.jsonl, latest per run)
    runs: list[RunRef]
    clean_runs: int
    metrics: list[MetricSummary]
    cost: CostSummary
    traps: list[TrapAcrossRuns]
    against: Comparison | None
    meta: SummaryMeta | None = None  # None in a committed (stable) summary


METRIC_LABELS: list[tuple[str, str, Unit]] = [
    ("clean_run", "Clean runs", "yes/no"),
    ("migrated_share", "Migrated without a human", "share"),
    ("hand_offs", "Hand-offs", "count"),
    ("regressions", "Regressions", "count"),
    ("cheating_hits", "Cheating-check hits", "count"),
    ("cheating_warnings", "Cheating-check warnings", "count"),
    ("repair_traps_expected", "Repair traps expected", "count"),
    ("silent_misses", "Silent misses (a human should look)", "count"),
    ("test_fitting", "Possible test-fitting edits (a human should look)", "count"),
    ("codemod_todos", "Codemod TODOs left", "count"),
    ("failures", "Failures (final verify)", "count"),
    ("cost_usd", "Cost per run", "usd"),
]


def _per_run_values(row: ResultRow, card: Scorecard) -> dict[str, float]:
    h = card.headline
    agent_expected = (
        sum(t.result == "Expected" for t in card.traps if t.expected_layer == "agent")
        if card.traps is not None
        else None
    )
    values = {
        # Headline numbers come from the row's grade, the rest from the scorecard.
        "clean_run": row.grade["clean_run"],
        "migrated_share": row.grade["migrated_share"],
        "hand_offs": float(h.hand_offs),
        "regressions": row.grade["regressions"],
        "cheating_hits": row.grade["cheating_hits"],
        "cheating_warnings": float(h.cheating_check_warnings),
        "codemod_todos": float(h.codemod_todos),
        "failures": float(h.failures),
        "cost_usd": row.cost_usd,
    }
    if agent_expected is not None:
        values["repair_traps_expected"] = float(agent_expected)
    if card.traps is not None:
        values["silent_misses"] = float(sum(is_silent_miss(t) for t in card.traps))
    if card.test_fitting is not None:
        values["test_fitting"] = float(len(card.test_fitting))
    return values


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _load(variant: Path) -> tuple[Manifest, list[ResultRow], list[Scorecard]]:
    manifest = read_manifest(variant)
    rows = sorted(read_rows(variant), key=lambda r: (manifest.cases.index(r.prompt_id), r.rep))
    flow = variant.parent
    cards = [
        Scorecard.model_validate_json((flow / str(r.meta["scorecard"])).read_text("utf-8"))
        for r in rows
    ]
    for row, card in zip(rows, cards, strict=True):
        if card.headline.clean_run != bool(row.grade["clean_run"]):
            raise EvalError(f"{row.prompt_id} rep {row.rep}: results row and scorecard disagree")
    return manifest, rows, cards


def _by_model(cards: list[Scorecard]) -> list[ModelCost]:
    totals: dict[str, list[float]] = {}
    for card in cards:
        for m in card.cost.by_model:
            t = totals.setdefault(m.model, [0, 0.0])
            t[0] += m.calls
            t[1] += m.cost_usd
    return [
        ModelCost(model=m, calls=int(v[0]), cost_usd=round(v[1], 6))
        for m, v in sorted(totals.items())
    ]


def build_summary(
    variant: Path, against: Path | None = None, created_at: str = ""
) -> ExperimentSummary:
    manifest, rows, cards = _load(variant)
    if not rows:
        raise EvalError(f"{manifest.experiment} has no scored runs yet")
    scored = {(r.prompt_id, r.rep) for r in rows}
    latest: dict[tuple[str, int], str] = {}
    for err in read_errors(variant):
        if (err.prompt_id, err.rep) not in scored:
            latest[(err.prompt_id, err.rep)] = err.failure_class
    per_run = [_per_run_values(r, c) for r, c in zip(rows, cards, strict=True)]

    base: ExperimentSummary | None = None
    if against is not None and against.resolve() != variant.resolve():
        base = build_summary(against, None, created_at)
    base_means = {m.id: m.mean for m in base.metrics} if base else {}

    metrics: list[MetricSummary] = []
    for metric_id, label, unit in METRIC_LABELS:
        values = [v[metric_id] for v in per_run if metric_id in v]
        if not values:
            continue
        mean = _mean(values)
        bmean = base_means.get(metric_id)
        metrics.append(
            MetricSummary(
                id=metric_id,
                label=label,
                unit=unit,
                values=values,
                mean=mean,
                min=min(values),
                max=max(values),
                baseline_mean=bmean,
                change=round(mean - bmean, 4) if mean is not None and bmean is not None else None,
            )
        )

    clean = sum(int(r.grade["clean_run"]) for r in rows)
    total = round(sum(r.cost_usd for r in rows), 6)
    traps: list[TrapAcrossRuns] = []
    for case_id in manifest.cases:
        case_cards = [c for r, c in zip(rows, cards, strict=True) if r.prompt_id == case_id]
        if not case_cards or case_cards[0].traps is None:
            continue
        for i, trap in enumerate(case_cards[0].traps):
            traps.append(
                TrapAcrossRuns(
                    id=trap.id,
                    title=trap.title,
                    expected_layer=trap.expected_layer,
                    case=case_id,
                    results=[c.traps[i].result if c.traps else "—" for c in case_cards],
                )
            )
    times = [r.latency_s for r in rows]
    return ExperimentSummary(
        experiment=manifest.experiment,
        split=manifest.split,
        configuration=manifest.configuration,
        configuration_digest=manifest.configuration_digest,
        cases=manifest.cases,
        repeats=manifest.repeats,
        runs_planned=len(manifest.cases) * manifest.repeats,
        runs_scored=len(rows),
        runs_not_scored=dict(sorted(Counter(latest.values()).items())),
        runs=[
            RunRef(case=r.prompt_id, rep=r.rep, scorecard=str(r.meta["scorecard"])) for r in rows
        ],
        clean_runs=clean,
        metrics=metrics,
        cost=CostSummary(
            total_usd=total,
            per_run_usd=round(total / len(rows), 6),
            per_clean_run_usd=round(total / clean, 6) if clean else None,
            clean_runs=clean,
            by_model=_by_model(cards),
        ),
        traps=traps,
        against=Comparison(
            experiment=base.experiment,
            configuration=base.configuration,
            runs=base.runs_scored,
            clean_runs=base.clean_runs,
        )
        if base
        else None,
        meta=SummaryMeta(
            created_at=created_at,
            experiment_created_at=manifest.created_at,
            run_ids=[str(r.meta["run_id"]) for r in rows],
            time_per_run_s=times,
            mean_time_s=_mean(times),
            baseline_mean_time_s=base.meta.mean_time_s if base and base.meta else None,
            migrator_version=manifest.migrator_version,
        ),
    )


def stable_view(summary: ExperimentSummary | dict[str, Any]) -> dict[str, Any]:
    """The deterministic part of a summary: everything but ``meta``."""
    data = (
        summary.model_dump(mode="json") if isinstance(summary, ExperimentSummary) else dict(summary)
    )
    data.pop("meta", None)
    return data


# --------------------------------------------------------------------------- markdown


def _fmt(value: float | None, unit: Unit) -> str:
    if value is None:
        return "—"
    if unit == "yes/no":
        return "yes" if value >= 1 else "no"
    if unit == "share":
        return f"{round(value * 100)}%"
    if unit == "usd":
        return usd(value)
    return f"{value:g}"


def _spread(m: MetricSummary) -> str:
    """Both values for 2 runs (or 1), the range from 3 runs on."""
    if len(m.values) <= 2:
        return " / ".join(_fmt(v, m.unit) for v in m.values)
    return f"{_fmt(m.min, m.unit)} to {_fmt(m.max, m.unit)}"


def _mean_cell(m: MetricSummary, runs: int) -> str:
    if m.unit == "yes/no":
        return f"{int(sum(m.values))} of {runs}"
    if m.mean is None:
        return "—"
    if m.unit == "share":
        return f"{round(m.mean * 100)}%"
    return _fmt(m.mean, m.unit)


def _change(m: MetricSummary, s: ExperimentSummary) -> str:
    if m.change is None:
        return ""
    if m.unit == "yes/no" and s.against is not None:
        diff = s.clean_runs - s.against.clean_runs
        return f"{diff:+d}" if diff else "0"
    if m.unit == "share":
        return f"{round(m.change * 100):+d} pts" if round(m.change * 100) else "0"
    if m.change == 0:
        return "0"
    return (
        f"{m.change:+g}"
        if m.unit != "usd"
        else f"{'+' if m.change > 0 else '−'}{usd(abs(m.change))}"
    )


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d}"


def render_summary(s: ExperimentSummary, *, stable: bool = False) -> str:
    """The experiment summary as markdown; ``stable`` leaves out dates and times."""
    runs = s.runs_scored
    by_id = {m.id: m for m in s.metrics}
    share = by_id["migrated_share"]
    base_name = s.against.configuration if s.against else None
    vs = f" vs {_fmt(share.baseline_mean, 'share')} {base_name}" if s.against else ""
    clean_vs = f" vs {s.against.clean_runs} of {s.against.runs}" if s.against else ""
    per_clean = (
        usd(s.cost.per_clean_run_usd)
        if s.cost.per_clean_run_usd is not None
        else "— (no clean runs)"
    )
    cases = ", ".join(s.cases)
    meta = None if stable else s.meta
    when = f"{meta.created_at[:10]} · " if meta else ""
    lines = [
        f"# Experiment summary: {s.configuration}"
        + (f" vs {base_name}" if base_name else "")
        + f" · {s.split} split",
        "",
        f"{when}{len(s.cases)} case{'s' if len(s.cases) != 1 else ''} ({cases}) × "
        f"{s.repeats} run{'s' if s.repeats != 1 else ''} · configuration "
        f"`{s.configuration}` ({s.configuration_digest}) · "
        f"experiment `{s.experiment}` · total {usd(s.cost.total_usd)}",
        "",
        f"**Migrated without a human: {_mean_cell(share, runs)} (runs: {_spread(share)}){vs}. "
        f"Clean runs: {s.clean_runs} of {runs}{clean_vs}.** Cost per clean run: {per_clean} "
        f"(cost per run: {usd(s.cost.per_run_usd)}).",
        "",
    ]
    if len(s.cost.by_model) > 1:
        parts = "; ".join(
            f"{m.model} {usd(m.cost_usd)} over {m.calls} calls" for m in s.cost.by_model
        )
        lines += [f"Cost by model: {parts}.", ""]
    if s.runs_planned != s.runs_scored:
        not_scored = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in s.runs_not_scored.items())
        lines += [
            f"**{s.runs_scored} of {s.runs_planned} runs scored**"
            + (f"; not scored: {not_scored}" if not_scored else "; the rest have not run yet")
            + ". Runs that were not scored are left out of every number below.",
            "",
        ]
    head = f"| Metric | {s.configuration} ({'run 1 / run 2' if runs == 2 else 'runs'}) | Mean |"
    sep = "|---|---|---|"
    if s.against:
        head += f" {base_name} (mean) | Change |"
        sep += "---|---|"
    lines += [head, sep]
    for m in s.metrics:
        label = m.label
        if m.id == "repair_traps_expected" and s.traps and len(s.cases) == 1:
            label += f" (of {sum(t.expected_layer == 'agent' for t in s.traps)})"
        row = f"| {label} | {_spread(m)} | {_mean_cell(m, runs)} |"
        if s.against:
            if m.unit == "yes/no":
                row += f" {s.against.clean_runs} of {s.against.runs} | {_change(m, s)} |"
            else:
                row += f" {_fmt(m.baseline_mean, m.unit)} | {_change(m, s)} |"
        lines.append(row)
    if meta is not None:
        secs = meta.time_per_run_s
        times = (
            " / ".join(_duration(x) for x in secs)
            if runs <= 2
            else f"{_duration(min(secs))} to {_duration(max(secs))}"
        )
        row = f"| Time per run | {times} | {_duration(meta.mean_time_s)} |"
        if s.against:
            row += f" {_duration(meta.baseline_mean_time_s)} | |"
        lines.append(row)
    spread_note = {
        1: "One run, so there is no spread yet (the brief asks for 2 runs per case).",
        2: "With 2 runs, the spread is shown as both values, not a standard deviation.",
    }.get(runs, "The spread is the range over the runs (min to max), not a standard deviation.")
    lines += ["", spread_note]
    if s.traps:
        lines += ["", "## Traps across runs", ""]
        multi = len(s.cases) > 1
        cols = " | ".join(f"Run {i + 1}" for i in range(s.repeats))
        lines += [
            ("| Case " if multi else "") + f"| Trap | Expected layer | {cols} |",
            ("|---" if multi else "") + "|---|---|" + "---|" * s.repeats,
        ]
        for t in s.traps:
            results = " | ".join(t.results + ["—"] * (s.repeats - len(t.results)))
            lines.append(
                (f"| {t.case} " if multi else "")
                + f"| {t.title} (`{t.id}`) | {t.expected_layer} | {results} |"
            )
        counts = Counter(r for t in s.traps for r in t.results)
        lines += [
            "",
            "Over all runs: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) + ".",
        ]
    lines += [
        "",
        "Scorecards: " + ", ".join(f"`{r.scorecard}`" for r in s.runs) + "."
        if meta is not None
        else "Source: `experiment-summary.json` (this file is rendered from it).",
    ]
    return "\n".join(lines) + "\n"


def write_summary(summary: ExperimentSummary, out_dir: Path, *, stable: bool = False) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = stable_view(summary) if stable else summary.model_dump(mode="json")
    (out_dir / "experiment-summary.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8"
    )
    md = out_dir / "experiment-summary.md"
    md.write_text(render_summary(summary, stable=stable), "utf-8")
    return md
