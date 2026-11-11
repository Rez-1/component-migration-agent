"""The Report stage: the scorecard of one run, as JSON (the source) and markdown, and
the pull-request body rendered from the same JSON (ticket #10).

Everything outside ``meta`` is deterministic for the same inputs, so CI can compare a
Baseline run with a committed expected scorecard (``stable_view``). Times, versions
and the run id live in ``meta``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from migrator.checks import CheatingReport, Finding, Layer
from migrator.config import Trap, TrapList
from migrator.configuration import DEFAULT_MAX_MONTH_USD, DEFAULT_MAX_RUN_USD
from migrator.cost import RunCost
from migrator.false_positives import CodemodFalsePositive
from migrator.repair.records import RepairReport
from migrator.rules import CodemodTodo, RulesResult
from migrator.scan import UsageReport
from migrator.verify import Failure, PrecheckResult, TestTotals, VerifyResult
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
    # Missed traps whose checks all pass at the final verify (see is_silent_miss).
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


class ReportInput(BaseModel):
    usage: UsageReport
    precheck: PrecheckResult
    rules: RulesResult | None
    verify: VerifyResult | None  # the final Verify
    # The Verify right after Rules; Regressions are counted against it. None means the
    # run changed nothing after Rules, so the final Verify is that Verify.
    rules_verify: VerifyResult | None = None
    final_usage: UsageReport | None  # rescan of the workspace after the run
    traps: TrapList | None
    configuration: str = "baseline"
    configuration_digest: str | None = None
    case: str | None = None
    cheating: CheatingReport | None = None
    cost: RunCost = RunCost.no_llm(DEFAULT_MAX_RUN_USD, DEFAULT_MAX_MONTH_USD)
    repair: RepairReport | None = None
    # Who changed each file after Rules ("agent" or "human"); None: nobody did.
    later_layers: dict[str, Layer] | None = None
    snapshots_to_review: list[SnapshotUpdate] | None = None
    visual: VisualReport | None = None
    repeated_edits: list[RepeatedEdit] | None = None
    test_fitting: list[TestFittingFlag] | None = None
    meta: RunMeta


# The scoring evidence of a run, in its run folder: written before the Scorecard is
# built, so a run can be scored again later (issue #17's replay gate).
REPORT_INPUT = "report-input.json"
# Whole file texts a repair record keeps for Review; Scoring never reads them, and
# the evidence file must not copy the target repo's source.
_FILE_TEXTS = {"set_aside", "originals", "failures_at_hand_off"}


def write_report_input(inp: ReportInput, path: Path) -> None:
    """``inp`` as JSON, without the repair records' file texts."""
    data = inp.model_dump(mode="json")
    for record in (data.get("repair") or {}).get("files") or []:
        for key in _FILE_TEXTS:
            record.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def read_report_input(path: Path) -> ReportInput:
    return ReportInput.model_validate_json(path.read_text("utf-8"))


# --------------------------------------------------------------------------- traps


def _split_test_check(check: str) -> tuple[str, str]:
    test_file, _, name = check.partition(" › ")
    return test_file.strip(), name.strip()


def failures_for_check(check: str, trap: Trap, failures: list[Failure]) -> list[Failure]:
    """Failures that show a trap's check firing: a type error in its file, or its test."""
    if check == "typecheck":
        return [f for f in failures if f.source == "typecheck" and f.file == trap.location.file]
    if check == "lint":
        return [f for f in failures if f.source == "lint" and f.file == trap.location.file]
    if check == "leftovers":  # M7: what is left of the old version, in the trap's file
        return [f for f in failures if f.source == "migration" and f.file == trap.location.file]
    test_file, name = _split_test_check(check)
    # A suite that failed to run (a crash on import) never ran the trap's test either,
    # so it counts as the check firing. So does a test bundle that didn't compile
    # (Karma, M7): no spec ran at all.
    unbuilt = [f for f in failures if f.source == "test" and f.test_name == "(build)"]
    if unbuilt:
        return unbuilt
    return [
        f
        for f in failures
        if f.source == "test"
        and f.test_file == test_file
        and f.test_name is not None
        and (f.test_name in (name, "(suite)") or f.test_name.endswith(f" › {name}"))
    ]


def is_silent_miss(t: TrapResult) -> bool:
    """A Missed agent or human trap whose checks all pass at the final verify.

    Verify can't show it: either the trap is still in the code and no check covers
    it, or it was fixed somewhere the scorer doesn't look (another file). Only a
    human reading the diff can tell which, so it is counted on its own."""
    return (
        t.result == "Missed"
        and t.expected_layer in ("agent", "human")
        and not any(c.fired for c in t.checks)
    )


def describe(f: Failure) -> str:
    if f.source == "test":
        return f"test {f.test_name}: {f.message}"
    where = f"{f.file}:{f.line}" if f.line else (f.file or "(no file)")
    return f"{f.source} {f.code or ''} {where}: {f.message}".replace("  ", " ")


def score_trap(
    trap: Trap,
    failures: list[Failure],
    layers: dict[str, Layer],
    handed_off: set[str],
    rules_ok: bool,
    rules_changed: set[str] | None = None,
) -> TrapResult:
    """One trap's result. A rules trap counts as handled when the Rules stage changed its
    file and its check stays quiet (a later agent edit to the same file doesn't undo
    that); a human trap is Expected when its file was handed off, even though its check
    still fires at the final verify."""
    file = trap.location.file
    by_rules = (
        rules_changed
        if rules_changed is not None
        else {p for p, layer in layers.items() if layer == "rules"}
    )
    checks: list[TrapCheck] = []
    evidence: list[str] = []
    for check in trap.checks():
        found = failures_for_check(check, trap, failures)
        checks.append(TrapCheck(check=check, fired=bool(found)))
        evidence.extend(describe(f) for f in found)
    caught = any(c.fired for c in checks)
    result: TrapResultName
    if trap.expected_layer == "visual-only":
        result = "Not scored"
    elif trap.expected_layer == "rules":
        handled = rules_ok and file in by_rules and not caught
        result = "Expected" if handled else "Missed"
    elif trap.expected_layer == "human" and file in handed_off:
        result = "Expected"
    elif caught:
        result = "Missed"
    elif layers.get(file) is None and file not in handed_off:
        result = "Missed"  # no layer touched the file, so none handled the trap
    elif trap.expected_layer == "human":
        result = "Expected" if file in handed_off else "Other layer"
    else:
        result = "Expected" if layers.get(file) == trap.expected_layer else "Other layer"
    return TrapResult(
        id=trap.id,
        title=trap.title,
        expected_layer=trap.expected_layer,
        file=file,
        result=result,
        checks=checks,
        evidence=sorted(set(evidence)),
    )


# --------------------------------------------------------------------------- scorecard


def _commands(outcomes: list[Any]) -> list[CommandSummary]:
    return [
        CommandSummary(
            name=c.name,
            command=c.command,
            exit_code=c.exit_code,
            failures=c.failures,
            parsed_with=c.parsed_with,
        )
        for c in outcomes
    ]


def _repair_outcome(record: Any, file_failures: list[Failure]) -> tuple[Outcome, str]:
    """A repaired file's outcome: the repair's own result, checked by the final verify."""
    if record.migrated_by_human:
        if file_failures:
            return "Unmigrated", f"edited at Review, still {len(file_failures)} failures"
        return "Migrated by human", "fixed at Review"
    if record.outcome == "Handed off":
        choice = f"; {record.review}" if record.review else ""
        return "Handed off", f"{record.reason or 'handed off'}{choice}"
    if record.outcome == "Migrated by agent":
        if file_failures:
            return (
                "Unmigrated",
                f"repaired, but the final verify found {len(file_failures)} failures",
            )
        return "Migrated by agent", f"{len(record.attempts)} attempt(s)"
    return "Unmigrated", record.reason or "not repaired"


def _patch_owner(path: str, records: dict[str, Any], layers: dict[str, Layer]) -> Any:
    """The repair whose patch still changes ``path`` (a local import it edited), if any.

    Only when the file is still changed after Rules: a patch that was reverted (a
    hand-off) no longer owns it. The last repair to touch it wins."""
    if layers.get(path) not in ("agent", "human"):
        return None
    owners = [r for r in records.values() if path in r.touched and r.path != path]
    return owners[-1] if owners else None


def _quiet_outcome(path: str, layer: Layer | None, records: dict[str, Any]) -> tuple[Outcome, str]:
    """The outcome of an affected file with no repair record of its own and no failure
    or old usage left: credited to the last layer that changed it. A file the repair
    agent changed while repairing another file is that repair's work: Migrated by agent
    if the repair passed, Handed off if it is part of a hand-off still in the workspace
    (kept at Review), Migrated by human if a human changed it at Review."""
    if layer == "rules":
        return "Migrated by rules", ""
    if layer is None:
        return "Unmigrated", "not changed by any layer"
    owner = _patch_owner(path, records, {path: layer})
    via = f"changed while repairing {owner.path}" if owner is not None else ""
    if layer == "human" or (owner is not None and owner.migrated_by_human):
        return "Migrated by human", via or "changed at Review"
    if owner is not None and owner.outcome == "Handed off" and not owner.migrated_by_human:
        return "Handed off", f"part of the handed-off patch for {owner.path}"
    return "Migrated by agent", via


def build_scorecard(inp: ReportInput) -> Scorecard:
    affected = inp.usage.affected_files()
    rules_ok = inp.rules is not None and inp.rules.status == "ok"
    failures = inp.verify.failures if inp.verify else []
    rules_changed = set(inp.rules.changed_files) if inp.rules else set()
    layers: dict[str, Layer] = {p: "rules" for p in rules_changed}
    layers.update(inp.later_layers or {})
    repair = inp.repair
    records = {f.path: f for f in repair.files} if repair else {}
    handed_off: set[str] = set(repair.review_list) if repair else set()
    cheating = inp.cheating
    hit_files = cheating.hit_files() if cheating else set()
    hits = cheating.hits if cheating else []
    before = inp.rules_verify or inp.verify
    failing_after_rules = {f.file for f in before.failures if f.file} if before else set()

    if inp.precheck.status == "rejected":
        status: RunStatus = "rejected"
        reason = inp.precheck.reason
    elif not rules_ok:
        status, reason = "rules_failure", inp.rules.reason if inp.rules else "Rules did not run"
    else:
        status, reason = "completed", None

    failing_files = sorted({f.file for f in failures if f.file})
    # A Regression: a file with no failures after Rules that fails at the final verify.
    regressions = sorted(p for p in failing_files if p not in failing_after_rules)

    files: list[FileResult] = []
    for path in affected:
        file_failures = [f for f in failures if f.file == path]
        final = inp.final_usage.file(path) if inp.final_usage else None
        left = len(final.old_usages) if final else 0
        outcome: Outcome
        if status != "completed":
            outcome, note = (
                "Unmigrated",
                "Pre-check rejected" if status == "rejected" else "Rules failure",
            )
        elif path in hit_files:
            checks = sorted({h.check for h in hits if h.file == path})
            outcome, note = "Unmigrated", "cheating check: " + ", ".join(checks)
        elif path in records:
            outcome, note = _repair_outcome(records[path], file_failures)
            if outcome != "Handed off" and left:
                outcome, note = "Unmigrated", f"{left} old usages left"
        elif file_failures:
            kinds = Counter(f.source for f in file_failures)
            note = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
            if path in regressions:
                note = "regression: " + note
            if (owner := _patch_owner(path, records, layers)) is not None:
                note = f"{note}; changed while repairing {owner.path}"
            outcome = "Unmigrated"
        elif left:
            outcome, note = "Unmigrated", f"{left} old usages left"
        else:
            outcome, note = _quiet_outcome(path, layers.get(path), records)
        files.append(
            FileResult(
                path=path,
                outcome=outcome,
                layer=layers.get(path),
                failures=len(file_failures),
                old_usages_left=left,
                note=note,
            )
        )

    counts = Counter(f.outcome for f in files)
    without_human = counts["Migrated by rules"] + counts["Migrated by agent"]
    # A clean run: no failures outside handed-off files (and no cheating-check hit).
    outside = [f for f in failures if f.file not in handed_off or f.file is None]

    trap_results: list[TrapResult] | None = None
    trap_counts: TrapCounts | None = None
    if inp.traps is not None:
        trap_results = [
            score_trap(
                t,
                failures,
                layers,
                handed_off,
                rules_ok and status == "completed",
                rules_changed,
            )
            for t in inp.traps.traps
        ]
        tc = Counter(t.result for t in trap_results)
        trap_counts = TrapCounts(
            expected=tc["Expected"],
            other_layer=tc["Other layer"],
            missed=tc["Missed"],
            not_scored=tc["Not scored"],
            silent=sum(is_silent_miss(t) for t in trap_results),
        )

    headline = Headline(
        # A cheating-check hit fails the run however clean the final verify is.
        clean_run=status == "completed" and not outside and not hits,
        failures=len(failures),
        failing_files=len({f.file for f in failures}),
        migrated_without_human=Share(
            count=without_human,
            total=len(affected),
            share=round(without_human / len(affected), 4) if affected else 0.0,
        ),
        outcomes={o: counts[o] for o in OUTCOMES},
        hand_offs=len(handed_off),
        regressions=len(regressions),
        cheating_check_hits=len(hits),
        cheating_check_warnings=len(cheating.warnings) if cheating else 0,
        codemod_todos=len(inp.rules.codemod_todos) if inp.rules else 0,
        traps=trap_counts,
    )
    pre = inp.precheck
    coverage: CoverageSummary | None = None
    if pre.covered is not None:
        migrated = [
            f.path for f in files if f.outcome in ("Migrated by rules", "Migrated by agent")
        ]
        coverage = CoverageSummary(
            covered=[p for p in migrated if pre.covered.get(p)],
            not_covered=[p for p in migrated if not pre.covered.get(p)],
        )
    return Scorecard(
        migration=inp.usage.migration,
        target_repo=inp.usage.target_repo,
        configuration=inp.configuration,
        configuration_digest=inp.configuration_digest,
        case=inp.case,
        status=status,
        reason=reason,
        headline=headline,
        files=files,
        changed_not_affected=sorted(rules_changed - set(affected)),
        precheck=PrecheckSummary(
            status=pre.status,
            reason=pre.reason,
            commands=_commands(
                [
                    *([pre.install] if pre.install else []),
                    *(pre.verify.commands if pre.verify else []),
                ]
            ),
            pre_existing_failures=pre.pre_existing_failures if pre.status == "ok" else [],
            test_totals=pre.test_totals,
        ),
        rules=RulesSummary(
            status=inp.rules.status,
            reason=inp.rules.reason,
            steps=[
                StepSummary(
                    kind=s.kind,
                    name=s.name,
                    status=s.status,
                    changed_files=s.changed_files,
                    detail=s.detail,
                )
                for s in inp.rules.steps
            ],
            changed_files=inp.rules.changed_files,
            codemod_todos=inp.rules.codemod_todos,
        )
        if inp.rules
        else None,
        verify=VerifySummary(
            commands=_commands(inp.verify.commands),
            failures=inp.verify.failures,
            pre_existing_excluded=len(inp.verify.pre_existing),
            test_totals=inp.verify.test_totals,
        )
        if inp.verify
        else None,
        traps=trap_results,
        cheating=cheating,
        repair=_repair_summary(repair, files) if repair else None,
        regressions=regressions,
        coverage=coverage,
        snapshots_to_review=inp.snapshots_to_review,
        repeated_edits=inp.repeated_edits,
        test_fitting=inp.test_fitting,
        codemod_false_positives=(inp.rules.false_positives or None) if inp.rules else None,
        visual=inp.visual,
        cost=inp.cost,
        meta=inp.meta,
    )


def _repair_summary(repair: RepairReport, files: list[FileResult]) -> RepairSummary:
    outcomes = {f.path: f.outcome for f in files}
    rejected: Counter[str] = Counter()
    rows: list[FileRepairSummary] = []
    for r in repair.files:
        rejected.update(r.edits_rejected)
        outcome: Outcome = outcomes.get(r.path) or (
            "Migrated by human" if r.migrated_by_human else (r.outcome or "Unmigrated")
        )
        rows.append(
            FileRepairSummary(
                path=r.path,
                outcome=outcome,
                reason=r.reason,
                attempts=[
                    AttemptSummary(
                        number=a.number,
                        model=a.model,
                        tool_calls=a.tool_calls,
                        result=a.result,
                        failures_left=a.failures_left,
                        new_failures_elsewhere=len(a.new_failures_elsewhere),
                        note=a.note,
                    )
                    for a in r.attempts
                ],
                tool_calls=r.tool_calls,
                touched=r.touched,
                patch_lines=r.patch_lines,
                edits_applied=r.edits_applied,
                edits_rejected=r.edits_rejected,
                parse_warnings=r.parse_warnings,
                suggested_test_change=r.suggested_test_change,
                test_fitting_hand_off=r.test_fitting_hand_off,
                reviewed_by=r.reviewed_by,
                review_verdict=r.review_verdict,
                review_reason=r.review_reason,
                review=r.review,
                conversation=r.conversation,
            )
        )
    return RepairSummary(
        files=rows,
        review_list=repair.review_list,
        attempts=repair.attempts,
        tool_calls=repair.tool_calls,
        edits_rejected=dict(sorted(rejected.items())),
        stopped_by_cost_cap=repair.stopped_by_cost_cap,
        cost_cap_reason=repair.cost_cap_reason,
        human_changed=repair.human_changed,
        reserved_usd=repair.reserved_usd,
    )


def _visual_lines(visual: VisualReport, *, task: bool) -> list[str]:
    """The visual check, for the scorecard and the PR body: never a verdict."""
    box = "- [ ] " if task else "- "
    if visual.skipped:
        return [f"- Not compared: {visual.skipped}"]
    lines = [
        f"{box}`{e.name}` breaks in the {e.capture} capture: {_md_cell('; '.join(e.errors), 200)}"
        for e in visual.new_page_errors
    ]
    for c in visual.comparisons:
        flagged = c.flagged
        lines.append(
            f"- {c.b} against {c.a}: {len(flagged)} of {len(c.pages)} pages differ by "
            f"{c.threshold:.1%} of their pixels or more"
            + (f"; no screenshot for {', '.join(m.name for m in c.missing)}" if c.missing else "")
        )
        lines += [
            f"  {box}`{p.name}`: {p.share:.2%} of pixels differ"
            + (f" (`{p.diff_png}`)" if p.diff_png else "")
            + (f"; files: {', '.join(f'`{f}`' for f in p.files)}" if p.files else "")
            for p in flagged
        ]
    return lines


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


def repeated_edits(
    after_rules: dict[str, str], final: dict[str, str], layers: dict[str, Layer], min_files: int = 3
) -> list[RepeatedEdit]:
    """Lines the later layers added to ``min_files`` or more files (see RepeatedEdit)."""
    import difflib

    by_line: dict[str, set[str]] = {}
    for path, layer in layers.items():
        if layer == "rules" or path not in final:
            continue
        old = after_rules.get(path, "").splitlines()
        for line in difflib.ndiff(old, final[path].splitlines()):
            text = line[2:].strip()
            if line[:2] in ("+ ", "- ") and len(text) >= 6 and any(c.isalnum() for c in text):
                by_line.setdefault(f"{line[0]} {text}", set()).add(path)
    return [
        RepeatedEdit(line=line, files=sorted(paths))
        for line, paths in sorted(by_line.items())
        if len(paths) >= min_files
    ]


_A11Y_PROP = re.compile(
    r"\baria-[a-z]+|\baria[A-Z]\w*|\brole\s*=|\btabIndex\b|\btitle\s*=|\bdescribeChild\b"
    r"|\bcomponent\s*=|\baria-label|\bdisableInteractive\b"
)
_JSX_TAG = re.compile(r"<([A-Za-z][\w.]*)")


def test_fitting_flags(
    after_rules: dict[str, str],
    final: dict[str, str],
    repaired: list[tuple[str, list[str]]],
    test_failing: set[str],
) -> list[TestFittingFlag]:
    """Possible test-fitting edits (see TestFittingFlag). ``repaired`` is each repaired
    file with the files its patch touched; ``test_failing`` the files that failed a test
    before Repair."""
    import difflib

    flags: list[TestFittingFlag] = []
    for path, touched in repaired:
        if path not in test_failing:
            continue
        for rel in touched:
            old, new = after_rules.get(rel, ""), final.get(rel)
            if new is None or old == new:
                continue
            changed = [
                line
                for line in difflib.ndiff(old.splitlines(), new.splitlines())
                if line[:2] in ("+ ", "- ")
            ]
            hits = [line[0] + " " + line[2:].strip() for line in changed if _A11Y_PROP.search(line)]
            added = {t for line in changed if line[0] == "+" for t in _JSX_TAG.findall(line)}
            removed = {t for line in changed if line[0] == "-" for t in _JSX_TAG.findall(line)}
            if added != removed:
                hits += [
                    line[0] + " " + line[2:].strip() for line in changed if _JSX_TAG.search(line)
                ]
            if hits:
                flags.append(
                    TestFittingFlag(file=rel, repaired_for=path, lines=list(dict.fromkeys(hits)))
                )
    return flags


def write_json(model: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", "utf-8"
    )


# --------------------------------------------------------------------------- markdown


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _pct(share: float) -> str:
    return f"{round(share * 100)}%"


def _duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} min {secs} s" if minutes else f"{secs} s"


def traps_line(t: TrapCounts | None) -> str:
    if t is None:
        return "—"
    return (
        f"{t.expected} expected · {t.other_layer} other layer · {t.missed} missed"
        f"{f' ({t.silent} silent)' if t.silent else ''} · {t.not_scored} not scored"
    )


def usd(value: float | None) -> str:
    """Dollars for a report: "—" when there is no value (never a silent $0)."""
    if value is None:
        return "—"
    return "$0" if value == 0 else f"${value:.2f}"


def _cost_head(cost: RunCost) -> str:
    if cost.model_calls == 0:
        return f"$0 (no LLM) of {usd(cost.run_cap_usd)} cap"
    return f"**{usd(cost.total_usd)}** of {usd(cost.run_cap_usd)} cap"


def _models_part(cost: RunCost) -> str:
    """The models with their share when there is more than one (a cascade, an advisor)."""
    if len(cost.by_model) < 2:
        return ", ".join(cost.models)
    return "; ".join(
        f"{m.model} {usd(m.cost_usd)} ({m.calls} {'call' if m.calls == 1 else 'calls'})"
        for m in cost.by_model
    )


def _cost_line(cost: RunCost) -> str:
    caps = f"Run cap {usd(cost.run_cap_usd)}; month cap {usd(cost.month_cap_usd)}"
    month = (
        f", this month {usd(cost.month_spent_usd)} of {usd(cost.month_cap_usd)}"
        if cost.month_spent_usd is not None
        else ""
    )
    warnings = "".join(f" **Warning:** {w}." for w in cost.warnings)
    stopped = " Repair stopped at the cost cap." if cost.stopped_by_cap else ""
    if cost.model_calls == 0:
        return f"$0: this run made no model calls. {caps}{month}.{stopped}"
    share = (
        f" Cache reads covered {round(cost.cache_read_share * 100)}% of input tokens."
        if cost.cache_read_share is not None
        else ""
    )
    return (
        f"{usd(cost.total_usd)} = {usd(cost.output_usd)} output + {usd(cost.input_usd)} input"
        f" + {usd(cost.cache_read_usd + cost.cache_write_usd)} cache (reads "
        f"{usd(cost.cache_read_usd)}, writes {usd(cost.cache_write_usd)}), "
        f"{_models_part(cost)}, {cost.model_calls} calls.{share} {caps}{month}."
        f"{stopped}{warnings}"
    )


def _cheating_cell(card: Scorecard) -> str:
    if card.cheating is None:
        return "— (not checked: the run stopped before Verify)"
    h = card.headline
    rules_notes = len(card.cheating.notes)
    cell = f"{h.cheating_check_hits} ({h.cheating_check_warnings} warnings)"
    return cell + (f"; {rules_notes} Rules-layer notes" if rules_notes else "")


def _finding_row(f: Finding) -> str:
    return f"| {f.file or '(run)'} | {f.layer} | {f.check} | {f.detail} |"


def _cheating_section(card: Scorecard) -> list[str]:
    report = card.cheating
    if report is None:
        return []
    lines = ["", "## Cheating checks", ""]
    if not report.hits and not report.warnings:
        lines.append("No hits and no warnings on repair-agent patches.")
    for title, findings in (("Hits (fail the run)", report.hits), ("Warnings", report.warnings)):
        if findings:
            lines += [f"**{title}**", "", "| File | Layer | Check | Detail |", "|---|---|---|---|"]
            lines += [_finding_row(f) for f in findings] + [""]
    if report.notes:
        lines += [
            "",
            "Reported, not failing (only repair-agent patches can fail a run):",
            "",
            "| File | Layer | Check | Detail |",
            "|---|---|---|---|",
        ]
        lines += [_finding_row(f) for f in report.notes]
    lines += ["", f"{len(report.test_files)} test files checked."]
    return lines


def _repair_section(card: Scorecard) -> list[str]:
    r = card.repair
    if r is None:
        return []
    lines = [
        "",
        "## Repair",
        "",
        f"{len(r.files)} failing files, {r.attempts} attempts, {r.tool_calls} tool calls."
        + (f" **Stopped by the cost cap:** {r.cost_cap_reason}." if r.stopped_by_cost_cap else ""),
    ]
    if r.edits_rejected:
        lines.append(
            "Edits refused by the guardrails: "
            + ", ".join(f"{k} {v}" for k, v in r.edits_rejected.items())
            + "."
        )
    if r.files:
        lines += [
            "",
            "| File | Outcome | Attempts | Tool calls | Patch | Why |",
            "|---|---|---|---|---|---|",
        ]
        for f in r.files:
            patch = ", ".join(f"{Path(p).name} {n}" for p, n in f.patch_lines.items()) or "—"
            why = (f.reason or "").replace("|", "\\|")
            if f.review:
                why += f" (Review: {f.review})"
            lines.append(
                f"| {f.path} | {f.outcome} | {len(f.attempts)} | {f.tool_calls} | {patch} | {why} |"
            )
    if r.review_list:
        lines += ["", "Review list: " + ", ".join(f"`{p}`" for p in r.review_list) + "."]
    if card.regressions:
        lines += ["", "Regressions: " + ", ".join(f"`{p}`" for p in card.regressions) + "."]
    return lines


def render_scorecard(card: Scorecard) -> str:
    h = card.headline
    m = card.meta
    share = h.migrated_without_human
    lines = [
        f"# Scorecard: {card.target_repo} · run {m.run_id}",
        "",
        f"`{card.migration}` · configuration `{card.configuration}`"
        + (f" · case `{card.case}`" if card.case else "")
        + f" · {_duration(m.duration_s)} · {_cost_head(card.cost)}",
        "",
    ]
    if card.status == "rejected":
        lines += [f"**Rejected at the Pre-check:** {card.reason}.", ""]
    elif card.status == "rules_failure":
        lines += [f"**Rules failure:** {card.reason}. Every affected file ends Unmigrated.", ""]
    by = h.outcomes
    clean = (
        "Clean run: yes."
        if h.clean_run
        else f"Clean run: no. Final verify found {h.failures} failures in {h.failing_files} files."
    )
    lines += [
        f"**{clean}** **{share.count} of {share.total} affected files migrated without a human "
        f"({_pct(share.share)})**: {by['Migrated by rules']} by rules, "
        f"{by['Migrated by agent']} by the repair agent. {by['Handed off']} handed off, "
        f"{by['Unmigrated']} unmigrated.",
        "",
        "| | This run |",
        "|---|---|",
        f"| Clean run | {_yes_no(h.clean_run)}"
        + ("" if h.clean_run else f" ({h.failures} failures in {h.failing_files} files)")
        + " |",
        f"| Migrated without a human | {share.count} / {share.total} ({_pct(share.share)}) |",
        f"| Hand-offs | {h.hand_offs} |",
        f"| Regressions | {h.regressions} |",
        f"| Cheating-check hits | {_cheating_cell(card)} |",
        f"| Codemod TODOs left | {h.codemod_todos} |",
        f"| Traps | {traps_line(h.traps)} |",
        f"| Cost / time | {usd(card.cost.total_usd)} · {_duration(m.duration_s)} |",
        "",
        "## Files",
        "",
        "| File | Outcome | Failures | Note |",
        "|---|---|---|---|",
    ]
    finished = [f for f in card.files if f.outcome == "Migrated by rules"]
    for f in card.files:
        if f.outcome != "Migrated by rules":
            lines.append(f"| {f.path} | {f.outcome} | {f.failures} | {f.note} |")
    if finished:
        names = ", ".join(Path(f.path).stem for f in finished)
        lines.append(f"| {len(finished)} files | Migrated by rules | 0 | {names} |")
    lines += [
        "",
        "Changed but not affected: "
        + (", ".join(f"`{p}`" for p in card.changed_not_affected) or "none")
        + ".",
    ]

    if card.verify and card.verify.failures:
        lines += ["", "## Failures", "", "| File | Check | Where | Message |", "|---|---|---|---|"]
        ordered = sorted(card.verify.failures, key=lambda x: (x.file or "", x.source, x.line or 0))
        for fail in ordered:
            where = (
                fail.test_name
                if fail.source == "test"
                else (f"line {fail.line}" if fail.line else "")
            )
            check = fail.source + (f" {fail.code}" if fail.code else "")
            message = fail.message.replace("|", "\\|")
            if len(message) > 140:
                message = message[:137] + "…"
            lines.append(f"| {fail.file or '(none)'} | {check} | {where} | {message} |")
        if card.verify.pre_existing_excluded:
            lines += ["", f"{card.verify.pre_existing_excluded} Pre-existing failures excluded."]

    if card.traps is not None:
        lines += [
            "",
            "## Traps (fixture)",
            "",
            "| Result | Expected layer | Traps |",
            "|---|---|---|",
        ]
        groups: dict[tuple[str, str], list[str]] = {}
        for t in card.traps:
            groups.setdefault((t.result, t.expected_layer), []).append(t.id)
        order = {"Expected": 0, "Other layer": 1, "Missed": 2, "Not scored": 3}
        layer_order = {"rules": 0, "agent": 1, "human": 2, "visual-only": 3}
        for (result, layer), ids in sorted(
            groups.items(), key=lambda kv: (order[kv[0][0]], layer_order.get(kv[0][1], 9))
        ):
            lines.append(f"| {result} | {layer} | {len(ids)}: {', '.join(ids)} |")
        quiet = [
            t
            for t in card.traps
            if t.expected_layer in ("agent", "human") and not any(c.fired for c in t.checks)
        ]
        fixed = [t.id for t in quiet if t.result in ("Expected", "Other layer")]
        uncaught = [t.id for t in quiet if is_silent_miss(t)]
        if not quiet:
            lines += ["", "Every agent and human trap's check still fails at the final verify."]
        if fixed:
            lines += [
                "",
                f"Fixed (their checks now pass at the final verify): {', '.join(fixed)}.",
            ]
        if uncaught:
            lines += [
                "",
                f"Silent misses (no check fails, so verify can't show them; the fix "
                f"is missing or was made in another file, so a human should look): "
                f"{', '.join(uncaught)}.",
            ]

    lines += _repair_section(card)
    lines += _cheating_section(card)

    if card.rules:
        lines += [
            "",
            "## Rule steps",
            "",
            "| # | Step | Status | Changed | Detail |",
            "|---|---|---|---|---|",
        ]
        for i, s in enumerate(card.rules.steps, start=1):
            label = s.kind if s.name == s.kind else f"{s.kind} {s.name}"
            lines.append(f"| {i} | {label} | {s.status} | {len(s.changed_files)} | {s.detail} |")
    pre = card.precheck
    totals = card.verify.test_totals if card.verify else None
    lines += [
        "",
        "## Pre-check and tests",
        "",
        f"Pre-check: {pre.status}"
        + (f" ({pre.reason})" if pre.reason else "")
        + f", {len(pre.pre_existing_failures)} Pre-existing failures.",
    ]
    if pre.test_totals and totals:
        lines += [
            "",
            "| | Pre-check | Final verify |",
            "|---|---|---|",
            f"| Tests run | {pre.test_totals.tests_total} | {totals.tests_total} |",
            f"| Tests failing | {pre.test_totals.tests_failed} | {totals.tests_failed} |",
            f"| Tests skipped | {pre.test_totals.tests_skipped} | {totals.tests_skipped} |",
            f"| Suites failing | {pre.test_totals.suites_failed} of {pre.test_totals.suites_total} "
            f"| {totals.suites_failed} of {totals.suites_total} |",
            f"| Snapshots | {pre.test_totals.snapshots_total} | {totals.snapshots_total} |",
        ]
    lines += _m6_review_section(card)
    lines += ["", "## Cost", "", _cost_line(card.cost)]
    lines += [
        "",
        f"Node {m.node_version or '?'}, npm {m.npm_version or '?'}, migrator {m.migrator_version}.",
    ]
    return "\n".join(lines) + "\n"


def _m6_review_section(card: Scorecard) -> list[str]:
    """M6 review flags and lists: nothing on runs that don't produce them."""
    out: list[str] = []
    if card.coverage is not None:
        c = card.coverage
        out += [
            "",
            "## Test coverage of the files migrated without a human",
            "",
            f"{len(c.covered)} covered by a test, {len(c.not_covered)} not covered"
            + (": " + ", ".join(f"`{p}`" for p in c.not_covered) if c.not_covered else "."),
        ]
    if card.snapshots_to_review:
        out += ["", "## Snapshots to review (updated by the Migrator, not the agent)", ""]
        out += [
            f"- `{s.snapshot_file or s.test_file}` ({s.stage}): {len(s.tests)} tests"
            for s in card.snapshots_to_review
        ]
    if card.test_fitting:
        out += ["", "## Possible test-fitting, check this", ""]
        out += [
            f"- `{t.file}` (repairing `{t.repaired_for}`): "
            + "; ".join(f"`{_md_cell(x, 100)}`" for x in t.lines[:4])
            for t in card.test_fitting
        ]
    if card.visual is not None:
        out += ["", "## Visual changes to review", "", *_visual_lines(card.visual, task=False)]
    if card.codemod_false_positives:
        out += ["", "## Codemod false positives (undone by Rules)", ""]
        out += [
            f"- `{f.file}` line {f.line}: `<{f.element}>` had stray `(` and `)` text "
            f"around its child; removed them from `{_md_cell(f.reverted, 160)}`"
            if f.kind == "stray_parens"
            else f"- `{f.file}` line {f.line}: `<{f.element}>` is the repo's own (from "
            f"`{f.imported_from}`); undid `{_md_cell(f.reverted, 160)}`"
            for f in card.codemod_false_positives
        ]
    if card.repeated_edits:
        out += ["", "## Hint: the same change repeated in several files", ""]
        out += [
            f"- `{_md_cell(r.line, 120)}` in {len(r.files)} files: check whether it belongs "
            "in one shared place"
            for r in card.repeated_edits
        ]
    reviewed = [f for f in (card.repair.files if card.repair else []) if f.reviewed_by]
    if reviewed:
        out += ["", "## Flagged patches reviewed by a second model", ""]
        out += [
            f"- `{f.path}`: {f.review_verdict} ({f.reviewed_by}): "
            + _md_cell(f.review_reason or "", 300)
            + (" Stays migrated; check it." if f.review_verdict == "v5_required" else "")
            for f in reviewed
        ]
    suggested = [f for f in (card.repair.files if card.repair else []) if f.suggested_test_change]
    if suggested:
        out += ["", "## Suggested test changes (not applied)", ""]
        out += [f"- `{f.path}`: {_md_cell(f.suggested_test_change or '', 400)}" for f in suggested]
    return out


# --------------------------------------------------------------------------- PR body

STAGE_LABELS = {"rules": "Rules", "agent": "Repair agent", "review": "Review (human)"}


def _md_cell(text: str, limit: int = 160) -> str:
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def pr_title(card: Scorecard) -> str:
    share = card.headline.migrated_without_human
    return (
        f"Migrate {card.migration.replace('->', ' to ')}: {share.count} of {share.total} files "
        f"migrated without a human"
    )


def render_pr_body(card: Scorecard) -> str:
    """The PR body: the scorecard's summary, the hand-off checklist, the codemod TODOs
    and the cost. Rendered from the scorecard alone, so the JSON stays the source."""
    h = card.headline
    m = card.meta
    share = h.migrated_without_human
    by = h.outcomes
    clean = (
        "Clean run: yes."
        if h.clean_run
        else f"Clean run: no. The final verify found {h.failures} failures in "
        f"{h.failing_files} files."
    )
    lines = [
        f"Migration `{card.migration}` by the Migrator, run `{m.run_id}`, configuration "
        f"`{card.configuration}`"
        + (f", commands sandboxed in {m.sandbox}" if m.sandbox else "")
        + ". Every number below comes from the run's `scorecard.json`.",
        "",
        f"**{clean}** **{share.count} of {share.total} affected files migrated without a "
        f"human ({_pct(share.share)})**: {by['Migrated by rules']} by rules, "
        f"{by['Migrated by agent']} by the repair agent, {by['Migrated by human']} by a human "
        f"at Review. {by['Handed off']} handed off, {by['Unmigrated']} unmigrated.",
        "",
        "| | This run |",
        "|---|---|",
        f"| Clean run | {_yes_no(h.clean_run)} |",
        f"| Migrated without a human | {share.count} / {share.total} ({_pct(share.share)}) |",
        f"| Hand-offs | {h.hand_offs} |",
        f"| Regressions | {h.regressions} |",
        f"| Cheating-check hits | {_cheating_cell(card)} |",
        f"| Codemod TODOs left | {h.codemod_todos} |",
    ]
    if h.traps:
        lines.append(f"| Traps (fixture) | {traps_line(h.traps)} |")
    lines += [f"| Cost / time | {usd(card.cost.total_usd)} · {_duration(m.duration_s)} |", ""]

    # The checklist: what a human must finish before merging.
    reasons = {f.path: f.reason for f in card.repair.files} if card.repair else {}
    failures = card.verify.failures if card.verify else []
    handed = [f for f in card.files if f.outcome == "Handed off"]
    suggested = {
        r.path: r.suggested_test_change
        for r in (card.repair.files if card.repair else [])
        if r.suggested_test_change
    }
    lines += ["## Hand-offs: for a human to finish", ""]
    if not handed:
        lines.append("None: no file was handed off.")
    for f in handed:
        lines.append(
            f"- [ ] `{f.path}`: {_md_cell(reasons.get(f.path) or f.note or 'handed off', 300)}"
        )
        for fail in [x for x in failures if x.file == f.path][:5]:
            where = (
                fail.test_name
                if fail.source == "test"
                else (f"line {fail.line}" if fail.line else "")
            )
            lines.append(
                f"  - {fail.source}{f' {where}' if where else ''}: {_md_cell(fail.message)}"
            )
        if f.path in suggested:
            lines.append(
                f"  - Suggested test change (not applied; approve or edit): "
                f"{_md_cell(suggested[f.path], 600)}"
            )
    if card.test_fitting:
        lines += ["", "Possible test-fitting, check this (behaviour a test sees was changed):", ""]
        lines += [
            f"- [ ] `{t.file}` (repairing `{t.repaired_for}`): "
            + "; ".join(f"`{_md_cell(x, 100)}`" for x in t.lines[:4])
            for t in card.test_fitting
        ]
    if card.visual is not None and (card.visual.to_review or card.visual.skipped):
        lines += ["", "Visual changes to review (screenshots in the run folder):", ""]
        lines += _visual_lines(card.visual, task=True)
    if card.codemod_false_positives:
        lines += ["", "Codemod false positives, undone by Rules (check them):", ""]
        lines += [
            f"- [ ] `{f.file}` line {f.line}: the codemod left `(` and `)` as text inside "
            f"`<{f.element}>`; they were removed"
            if f.kind == "stray_parens"
            else f"- [ ] `{f.file}` line {f.line}: `<{f.element}>` from `{f.imported_from}` is "
            "the repo's own; the codemod's change was undone"
            for f in card.codemod_false_positives
        ]
    if card.repeated_edits:
        lines += ["", "Hint: the same change repeated in several files:", ""]
        lines += [
            f"- `{_md_cell(r.line, 120)}`, the same change repeated in {len(r.files)} files: "
            "check whether it belongs in one shared place ("
            + ", ".join(f"`{p}`" for p in r.files)
            + ")"
            for r in card.repeated_edits
        ]
    unmigrated = [f for f in card.files if f.outcome == "Unmigrated"]
    if unmigrated:
        lines += ["", "Unmigrated (no layer finished them):", ""]
        lines += [
            f"- [ ] `{f.path}`: {_md_cell(reasons.get(f.path) or f.note or 'unmigrated', 300)}"
            for f in unmigrated
        ]
    if card.regressions:
        lines += [
            "",
            "Regressions (clean after Rules, failing at the final verify): "
            + ", ".join(f"`{p}`" for p in card.regressions)
            + ".",
        ]
    todos = card.rules.codemod_todos if card.rules else []
    lines += ["", "## Codemod TODOs", ""]
    if not todos:
        lines.append("None: the codemods left no FIXME or TODO comments.")
    lines += [f"- [ ] `{t.file}` line {t.line}: {_md_cell(t.text)}" for t in todos]

    if m.commits:
        lines += ["", "## Commits", "", "| Stage | Commit | Files |", "|---|---|---|"]
        lines += [
            f"| {STAGE_LABELS.get(c.stage, c.stage)} | {c.sha[:8]} {_md_cell(c.title)} | "
            f"{len(c.files)} |"
            for c in m.commits
        ]
    lines += ["", "## Cost", "", _cost_line(card.cost)]
    lines += [
        "",
        f"<sub>Node {m.node_version or '?'}, npm {m.npm_version or '?'}, migrator "
        f"{m.migrator_version}. Verify ran the repo's type-check, lint and tests"
        + (" in a Docker container with no network." if m.sandbox == "docker" else ".")
        + "</sub>",
    ]
    return "\n".join(lines) + "\n"
