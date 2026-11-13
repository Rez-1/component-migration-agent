"""How one file's repair ends: kept, handed off or not attempted, and why.

``end_file`` decides; it changes no file. The run's file-end node applies what it
returns (rolls back originals, so a set-aside patch or a cost-capped one is not in
the workspace the next file is repaired in) and saves the conversation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from migrator.cost import CallRecord
from migrator.repair.guardrails import added_escape_hatches
from migrator.repair.prompt import describe_failure
from migrator.repair.records import FileRepair
from migrator.repair.reviewer import Review
from migrator.repair.tools import SessionState
from migrator.review_aids import test_fitting_flags
from migrator.verify import Failure

# The test-fitting reviewer (M6 option D) on one flagged patch: (record, flag, model) ->
# its review, or None when it could not answer (the flag then decides).
Reviewer = Callable[[FileRepair, str, str], Review | None]


@dataclass(frozen=True)
class FileFailures:
    """The known failures when this file's repair started, and now."""

    at_start: list[Failure]
    now: list[Failure]


@dataclass(frozen=True)
class RepairWorkspace:
    """The workspace as end_file reads it: its folder and the Start of Repair."""

    root: Path
    start_of_repair: Mapping[str, str]

    def text(self, rel: str) -> str:
        return (self.root / rel).read_text("utf-8")


@dataclass(frozen=True)
class EndPolicy:
    cheating_hand_off: bool  # real use: a passing patch with an escape hatch is handed off
    test_fitting_hand_off: bool  # M6: a passing patch that fits the test goes to a human
    reviewer_model: str | None  # M6 option D: a reviewer looks at each flagged patch first


@dataclass
class FileOutcome:
    """How the file ends (``record.outcome`` and ``record.reason``), and what to apply."""

    record: FileRepair
    review_call: CallRecord | None = None  # the reviewer's call, to count in the run
    roll_back: dict[str, str] = field(default_factory=dict)  # write these originals back
    restart_failures: bool = False  # known failures go back to those at the file's start
    notes: list[str] = field(default_factory=list)  # for the run's log

    @property
    def handed_off(self) -> bool:
        return self.record.outcome == "Handed off"


def end_file(
    file: SessionState,
    failures: FileFailures,
    workspace: RepairWorkspace,
    policy: EndPolicy,
    reviewer: Reviewer,
) -> FileOutcome:
    """How ``file``'s repair ends. A cost-capped repair is rolled back (no half-done
    patch lands); a handed-off patch is set aside until Review, so the next files are
    repaired without it (a broken patch must not fail their tests)."""
    out = FileOutcome(record=file.record.model_copy(deep=True))
    record = out.record
    if file.ended == "cost_cap":
        record.touched = []
        record.patch_lines = {}
        out.roll_back, out.restart_failures = dict(file.originals), True
    elif (
        file.ended == "passed"
        and policy.cheating_hand_off
        and (hits := escape_hatches(record, workspace))
    ):  # in real use a cheating-check hit is a hand-off, not a migrated file
        record.outcome = "Handed off"
        record.reason = "cheating check: " + "; ".join(hits)
    if (
        file.ended == "passed"
        and record.outcome == "Migrated by agent"
        and policy.test_fitting_hand_off
    ):
        _test_fitting(out, failures.at_start, workspace, policy.reviewer_model, reviewer)
    if out.handed_off and file.originals:
        record.failures_at_hand_off = [
            describe_failure(f, record.path) for f in failures.now if f.file == record.path
        ]
        record.originals = dict(file.originals)
        record.set_aside = {rel: workspace.text(rel) for rel in file.originals}
        out.roll_back, out.restart_failures = dict(file.originals), True
    return out


def escape_hatches(record: FileRepair, workspace: RepairWorkspace) -> list[str]:
    """``file: hatch, ...`` for each touched file the patch added an escape hatch to."""
    return [
        f"{rel}: {', '.join(found)}"
        for rel in record.touched
        if (
            found := added_escape_hatches(
                rel, workspace.start_of_repair.get(rel, ""), workspace.text(rel)
            )
        )
    ]


def _test_fitting(
    out: FileOutcome,
    at_start: list[Failure],
    workspace: RepairWorkspace,
    model: str | None,
    reviewer: Reviewer,
) -> None:
    """M6: a passing patch that changes what a failing test looks at (accessibility
    props, the rendered element) goes to a human instead of counting as migrated,
    unless the reviewer finds the change is what v5 requires."""
    record = out.record
    current = {rel: workspace.text(rel) for rel in record.touched}
    why = test_fitting_reason(
        record.path, record.touched, workspace.start_of_repair, current, at_start
    )
    if why is not None and model is not None:
        review = reviewer(record, why, model)
        if review is not None:
            out.review_call = review.call
            record.reviewed_by = review.model
            record.review_verdict = review.verdict
            record.review_reason = review.reason
            if review.verdict == "v5_required":
                out.notes.append(f"{record.path}: flagged, reviewed as v5_required")
                why = None  # stays migrated; the review is a note for a human
    if why is not None:
        record.outcome = "Handed off"
        record.test_fitting_hand_off = True
        record.reason = why + (
            f" (reviewed by {record.reviewed_by}: {record.review_reason})"
            if record.reviewed_by
            else ""
        )


def test_fitting_reason(
    path: str,
    touched: list[str],
    after_rules: Mapping[str, str],
    current: Mapping[str, str],
    start_failures: list[Failure],
) -> str | None:
    """The hand-off reason when a passing patch for a file that failed a test changed
    accessibility props or the rendered element (M6), else None."""
    flags = test_fitting_flags(
        dict(after_rules),
        dict(current),
        [(path, touched)],
        {f.file for f in start_failures if f.source == "test" and f.file},
    )
    if not flags:
        return None
    return "possible test-fitting: " + "; ".join(
        f"{fl.file}: {', '.join(fl.lines[:3])}" for fl in flags
    )
