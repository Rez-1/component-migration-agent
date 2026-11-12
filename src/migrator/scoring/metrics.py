"""The per-run metrics: one list, read from a Scorecard.

The experiment summary shows every metric, ``grade()`` (each results.jsonl row) keeps
the ones with a viewer column, and the hill-climb keep rule reads their means.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from migrator.scoring.scorecard import Scorecard

Unit = Literal["yes/no", "share", "count", "usd"]


class ViewerColumn(BaseModel):
    """How the build-eval viewer shows a metric (its ``_state.json`` declaration)."""

    label: str
    kind: Literal["binary", "float"]
    scale: int | None = None
    better: Literal["lower"] | None = None


class Metric(BaseModel):
    id: str
    label: str  # in the experiment summary
    unit: Unit
    viewer: ViewerColumn | None = None  # None: in the summary only, not in grade()


def _float(label: str, scale: int, better: Literal["lower"] | None = None) -> ViewerColumn:
    return ViewerColumn(label=label, kind="float", scale=scale, better=better)


# In the summary's order. The first binary column is the viewer's headline, so clean_run
# comes first (ticket #10).
METRICS: tuple[Metric, ...] = (
    Metric(
        id="clean_run",
        label="Clean runs",
        unit="yes/no",
        viewer=ViewerColumn(label="Clean run", kind="binary"),
    ),
    Metric(
        id="migrated_share",
        label="Migrated without a human",
        unit="share",
        viewer=_float("Migrated share", 1),
    ),
    Metric(id="hand_offs", label="Hand-offs", unit="count"),
    Metric(
        id="regressions",
        label="Regressions",
        unit="count",
        viewer=_float("Regressions", 10, "lower"),
    ),
    Metric(
        id="cheating_hits",
        label="Cheating-check hits",
        unit="count",
        viewer=_float("Cheating hits", 10, "lower"),
    ),
    Metric(id="cheating_warnings", label="Cheating-check warnings", unit="count"),
    Metric(id="repair_traps_expected", label="Repair traps expected", unit="count"),
    Metric(
        id="repair_traps_expected_share",
        label="Repair traps expected (share)",
        unit="share",
        viewer=_float("Repair traps", 1),
    ),
    Metric(
        id="silent_misses",
        label="Silent misses (a human should look)",
        unit="count",
        viewer=_float("Silent misses", 10, "lower"),
    ),
    Metric(
        id="test_fitting",
        label="Possible test-fitting edits (a human should look)",
        unit="count",
    ),
    Metric(
        id="codemod_false_positives",
        label="Codemod false positives undone by Rules",
        unit="count",
    ),
    Metric(id="test_fitting_hand_offs", label="Hand-offs for possible test-fitting", unit="count"),
    Metric(id="codemod_todos", label="Codemod TODOs left", unit="count"),
    Metric(id="failures", label="Failures (final verify)", unit="count"),
    Metric(id="cost_usd", label="Cost per run", unit="usd"),
)


def run_metrics(card: Scorecard) -> dict[str, float]:
    """Every metric one run has, by id. A metric that doesn't apply is left out (traps
    on a case without them, test-fitting on a run that doesn't look for it)."""
    h = card.headline
    values = {
        "clean_run": 1.0 if h.clean_run else 0.0,
        "migrated_share": h.migrated_without_human.share,
        "hand_offs": float(h.hand_offs),
        "regressions": float(h.regressions),
        "cheating_hits": float(h.cheating_check_hits),
        "cheating_warnings": float(h.cheating_check_warnings),
        "codemod_todos": float(h.codemod_todos),
        "failures": float(h.failures),
        "cost_usd": card.cost.total_usd,
    }
    if card.traps is not None:
        agent = [t for t in card.traps if t.expected_layer == "agent"]
        expected = sum(t.result == "Expected" for t in agent)
        values["repair_traps_expected"] = float(expected)
        if agent:
            values["repair_traps_expected_share"] = round(expected / len(agent), 4)
        values["silent_misses"] = float(sum(t.silent_miss for t in card.traps))
    if card.test_fitting is not None:
        values["test_fitting"] = float(len(card.test_fitting))
    if card.repair is not None and any(f.test_fitting_hand_off for f in card.repair.files):
        values["test_fitting_hand_offs"] = float(
            sum(f.test_fitting_hand_off for f in card.repair.files)
        )
    elif card.repair is not None and card.test_fitting is not None:
        values["test_fitting_hand_offs"] = 0.0
    if card.rules is not None and card.status == "completed":
        values["codemod_false_positives"] = float(len(card.codemod_false_positives or []))
    return values
