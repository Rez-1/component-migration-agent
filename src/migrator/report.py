"""The Report stage: the scorecard of one run, as JSON (the source) and markdown.

Everything outside ``meta`` is deterministic for the same inputs, so CI can compare a
Baseline run with a committed expected scorecard (``stable_view``). Times, versions
and the run id live in ``meta``.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from migrator.checks import CheatingReport, Finding, Layer
from migrator.config import Trap, TrapList
from migrator.configuration import DEFAULT_MAX_MONTH_USD, DEFAULT_MAX_RUN_USD
from migrator.cost import RunCost
from migrator.repair.records import RepairReport
from migrator.rules import CodemodTodo, RulesResult
from migrator.scan import UsageReport
from migrator.verify import Failure, PrecheckResult, TestTotals, VerifyResult

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


class RepairSummary(BaseModel):
    files: list[FileRepairSummary]
    review_list: list[str]
    attempts: int
    tool_calls: int
    edits_rejected: dict[str, int]
    stopped_by_cost_cap: bool
    cost_cap_reason: str | None
    human_changed: list[str]


class RunMeta(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    duration_s: float
    migrator_version: str
    node_version: str | None
    npm_version: str | None
    timings_s: dict[str, float]


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
    repair: RepairSummary | None  # None when repair is off (the Baseline)
    regressions: list[str]
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
    meta: RunMeta


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
    test_file, name = _split_test_check(check)
    # A suite that failed to run (a crash on import) never ran the trap's test either,
    # so it counts as the check firing.
    return [
        f
        for f in failures
        if f.source == "test"
        and f.test_file == test_file
        and f.test_name is not None
        and (f.test_name in (name, "(suite)") or f.test_name.endswith(f" › {name}"))
    ]


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
            outcome = "Unmigrated"
        elif left:
            outcome, note = "Unmigrated", f"{left} old usages left"
        else:
            outcome, note = (
                ("Migrated by rules" if layers.get(path) == "rules" else "Unmigrated"),
                "",
            )
            if outcome == "Unmigrated":
                note = "not changed by any layer"
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
    )


def stable_view(scorecard: Scorecard | dict[str, Any]) -> dict[str, Any]:
    """The deterministic part of a scorecard: everything but ``meta``."""
    data = (
        scorecard.model_dump(mode="json") if isinstance(scorecard, Scorecard) else dict(scorecard)
    )
    data.pop("meta", None)
    return data


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


def _traps_line(t: TrapCounts | None) -> str:
    if t is None:
        return "—"
    return (
        f"{t.expected} expected · {t.other_layer} other layer · {t.missed} missed · "
        f"{t.not_scored} not scored"
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
        f"{', '.join(cost.models)}, {cost.model_calls} calls.{share} {caps}{month}."
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
        f"| Traps | {_traps_line(h.traps)} |",
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
        uncaught = [
            t.id
            for t in card.traps
            if t.expected_layer in ("agent", "human") and not any(c.fired for c in t.checks)
        ]
        lines += [
            "",
            "Every agent and human trap was caught by verify."
            if not uncaught
            else f"Not caught by verify: {', '.join(uncaught)}.",
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
    lines += ["", "## Cost", "", _cost_line(card.cost)]
    lines += [
        "",
        f"Node {m.node_version or '?'}, npm {m.npm_version or '?'}, migrator {m.migrator_version}.",
    ]
    return "\n".join(lines) + "\n"
