"""The Scorecard: the measured results of one run (the schema Scoring fills).

Everything outside ``meta`` is deterministic for the same evidence, so CI can compare a
Baseline run with a committed expected scorecard (``stable_view``). Times, versions
and the run id live in ``meta``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from migrator.checks import CheatingReport, Layer
from migrator.cost import RunCost
from migrator.false_positives import CodemodFalsePositive
from migrator.rules import CodemodTodo
from migrator.verify import Failure, TestTotals
from migrator.visual.compare import VisualReport
from migrator.workspace import StageCommit

# 2: cheating checks, cost block, configuration digest (M2).
# 3: the repair block, Regressions against the Verify after Rules, a clean run ignores
#    handed-off files, cost warnings and the cost-cap flag (M3).
SCHEMA_VERSION = 3

Outcome = Literal[
    "Migrated by rules", "Migrated by agent", "Migrated by human", "Handed off", "Unmigrated"
]
OUTCOMES: tuple[Outcome, ...] = (
    "Migrated by rules",
    "Migrated by agent",
    "Migrated by human",
    "Handed off",
    "Unmigrated",
)
TrapResultName = Literal["Expected", "Other layer", "Missed", "Not scored"]
RunStatus = Literal["completed", "rejected", "rules_failure"]


class Share(BaseModel):
    count: int
    total: int
    share: float


class TrapCounts(BaseModel):
    expected: int
    other_layer: int
    missed: int
    not_scored: int
    # Missed traps whose checks all pass at the final verify (see TrapResult.silent_miss).
    # Defaults to 0 so scorecards written before it existed still load.
    silent: int = 0


class Headline(BaseModel):
    clean_run: bool
    failures: int
    failing_files: int
    migrated_without_human: Share
    outcomes: dict[str, int]
    hand_offs: int
    regressions: int
    cheating_check_hits: int
    cheating_check_warnings: int
    codemod_todos: int
    traps: TrapCounts | None


class FileResult(BaseModel):
    path: str
    outcome: Outcome
    layer: Layer | None
    failures: int
    old_usages_left: int
    note: str = ""


class CoverageSummary(BaseModel):
    """Test coverage of the files migrated without a human (M6), measured once at the
    Pre-check: covered means a test ran at least one of the file's functions."""

    covered: list[str]
    not_covered: list[str]


class SnapshotUpdate(BaseModel):
    """A snapshot file the Migrator itself updated (never the repair agent), because the
    only failures of its test file were snapshot mismatches (M6). A human reviews each."""

    test_file: str
    snapshot_file: str | None
    tests: list[str]
    stage: str  # "verify" (after Rules) or "final"


class RepeatedEdit(BaseModel):
    """A hint (M6): one line the later layers (the repair agent, a human) added to, or
    removed from, 3 or more files (``+ line`` / ``- line``). It may belong in one shared
    place, or be right in every file, as on OpossumUI, where the developers made the
    same one-line fix in each caller. Never a failure."""

    line: str
    files: list[str]


class TestFittingFlag(BaseModel):
    """A possible fit to a test (M6): the agent changed accessibility props or the
    rendered element in a patch for a file that failed a test. Behaviour the test sees
    changed, which is fine when v5 needs it and wrong when it only makes an outdated
    test pass (OpossumUI: ``describeChild`` added so a v4 ``title`` test passes). It
    blocks nothing; a human checks it. No model call."""

    file: str  # the file the edit is in
    repaired_for: str  # the failing file whose repair made it
    lines: list[str]  # the flagged added (+) and removed (-) lines


class StepSummary(BaseModel):
    kind: str
    name: str
    status: str
    changed_files: list[str]
    detail: str


class CommandSummary(BaseModel):
    name: str
    command: str
    exit_code: int
    failures: int
    parsed_with: str


class PrecheckSummary(BaseModel):
    status: str
    reason: str | None
    commands: list[CommandSummary]
    pre_existing_failures: list[Failure]
    test_totals: TestTotals | None


class RulesSummary(BaseModel):
    status: str
    reason: str | None
    steps: list[StepSummary]
    changed_files: list[str]
    codemod_todos: list[CodemodTodo]


class VerifySummary(BaseModel):
    commands: list[CommandSummary]
    failures: list[Failure]
    pre_existing_excluded: int
    test_totals: TestTotals | None


class TrapCheck(BaseModel):
    check: str
    fired: bool


class TrapResult(BaseModel):
    id: str
    title: str
    expected_layer: str
    file: str
    result: TrapResultName
    checks: list[TrapCheck]
    evidence: list[str]

    @property
    def silent_miss(self) -> bool:
        """A Silent miss: a Missed agent or human trap whose checks all pass at the final
        verify. Verify can't show it: either the trap is still in the code and no check
        covers it, or it was fixed somewhere the scorer doesn't look (another file).
        Only a human reading the diff can tell which, so it is counted on its own."""
        return (
            self.result == "Missed"
            and self.expected_layer in ("agent", "human")
            and not any(c.fired for c in self.checks)
        )


class AttemptSummary(BaseModel):
    number: int
    model: str
    tool_calls: int
    result: str | None
    failures_left: int | None
    new_failures_elsewhere: int
    note: str | None


class FileRepairSummary(BaseModel):
    path: str
    outcome: Outcome
    reason: str | None
    attempts: list[AttemptSummary]
    tool_calls: int
    touched: list[str]
    patch_lines: dict[str, int]
    edits_applied: int
    edits_rejected: dict[str, int]
    review: str | None
    conversation: str | None
    parse_warnings: int = 0  # prompt v2's apply_edit warnings (M5)
    suggested_test_change: str | None = None  # prompt v3: for a human, never applied (M6)
    test_fitting_hand_off: bool = False  # handed off because the test-fitting flag fired
    reviewed_by: str | None = None  # the reviewer model on a flagged patch (M6 option D)
    review_verdict: str | None = None
    review_reason: str | None = None


class RepairSummary(BaseModel):
    files: list[FileRepairSummary]
    review_list: list[str]
    attempts: int
    tool_calls: int
    edits_rejected: dict[str, int]
    stopped_by_cost_cap: bool
    cost_cap_reason: str | None
    human_changed: list[str]
    reserved_usd: float | None = None


class RunMeta(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_s: float
    migrator_version: str
    node_version: str | None
    npm_version: str | None
    timings_s: dict[str, float]
    # Where commands ran, and a real run's branch and stage commits (M4). In meta, so
    # the stable view (and the committed expected scorecard) does not change.
    sandbox: str | None = None
    branch: str | None = None
    base_branch: str | None = None
    commits: list[StageCommit] = []
    # Provider features the configuration asked for and a model doesn't declare, turned
    # off before the run (M7, migrator.model_table). Empty for Claude.
    features_off: list[str] = []


class Scorecard(BaseModel):
    schema_version: int = SCHEMA_VERSION
    migration: str
    target_repo: str
    configuration: str
    configuration_digest: str | None
    case: str | None
    status: RunStatus
    reason: str | None
    headline: Headline
    files: list[FileResult]
    changed_not_affected: list[str]
    precheck: PrecheckSummary
    rules: RulesSummary | None
    verify: VerifySummary | None
    traps: list[TrapResult] | None
    cheating: CheatingReport | None  # None when the run stopped before Verify
    # Schema 3 fields default, so schema-2 scorecards (M2 experiments) still load.
    repair: RepairSummary | None = None  # None when repair is off (the Baseline)
    regressions: list[str] = []
    # M6 sections; None (and left out of the stable view) on runs that don't use them.
    coverage: CoverageSummary | None = None
    snapshots_to_review: list[SnapshotUpdate] | None = None
    repeated_edits: list[RepeatedEdit] | None = None
    test_fitting: list[TestFittingFlag] | None = None
    # Codemod changes to the repo's own components that Rules undid (M6); None: none.
    codemod_false_positives: list[CodemodFalsePositive] | None = None
    # M7: screenshots compared (migrator.visual). Visual changes to review, never a
    # verdict; None when the repo has no [visual] section.
    visual: VisualReport | None = None
    cost: RunCost
    meta: RunMeta


def stable_view(scorecard: Scorecard | dict[str, Any]) -> dict[str, Any]:
    """The deterministic part of a scorecard: everything but ``meta`` and ``visual`` (M7:
    screenshots depend on Docker and the browser image, so they are not part of it)."""
    data = (
        scorecard.model_dump(mode="json") if isinstance(scorecard, Scorecard) else dict(scorecard)
    )
    data.pop("meta", None)
    data.pop("visual", None)
    for key in _M6_KEYS:
        if data.get(key) is None:
            data.pop(key, None)
    return data


_M6_KEYS = (
    "coverage",
    "snapshots_to_review",
    "repeated_edits",
    "test_fitting",
    "codemod_false_positives",
)
