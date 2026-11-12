"""The scoring rules: one run's evidence in, its Scorecard out. No files, no commands."""

from __future__ import annotations

from collections import Counter
from typing import Any

from migrator.checks import Layer
from migrator.config import Trap
from migrator.repair.records import RepairReport
from migrator.scoring.evidence import AgentChanges, Evidence, MigratorChanges
from migrator.scoring.scorecard import (
    OUTCOMES,
    AttemptSummary,
    CommandSummary,
    CoverageSummary,
    FileRepairSummary,
    FileResult,
    Headline,
    Outcome,
    PrecheckSummary,
    RepairSummary,
    RulesSummary,
    RunStatus,
    Scorecard,
    Share,
    StepSummary,
    TrapCheck,
    TrapCounts,
    TrapResult,
    TrapResultName,
    VerifySummary,
)
from migrator.verify import Failure

# --------------------------------------------------------------------------- traps


def _failures_for_check(check: str, trap: Trap, failures: list[Failure]) -> list[Failure]:
    """Failures that show a trap's check firing: a type error in its file, or its test."""
    if check == "typecheck":
        return [f for f in failures if f.source == "typecheck" and f.file == trap.location.file]
    if check == "lint":
        return [f for f in failures if f.source == "lint" and f.file == trap.location.file]
    if check == "leftovers":  # M7: what is left of the old version, in the trap's file
        return [f for f in failures if f.source == "migration" and f.file == trap.location.file]
    # A suite that failed to run (a crash on import) never ran the trap's test either,
    # so it counts as the check firing. So does a test bundle that didn't compile
    # (Karma, M7): no spec ran at all.
    unbuilt = [f for f in failures if f.ran_no_spec]
    if unbuilt:
        return unbuilt
    return [f for f in failures if f.matches_test_check(check)]


def _describe(f: Failure) -> str:
    if f.source == "test":
        return f"test {f.test_name}: {f.message}"
    where = f"{f.file}:{f.line}" if f.line else (f.file or "(no file)")
    return f"{f.source} {f.code or ''} {where}: {f.message}".replace("  ", " ")


def _score_trap(
    trap: Trap,
    failures: list[Failure],
    layers: dict[str, Layer],
    handed_off: set[str],
    rules_ok: bool,
    rules_changed: set[str],
    rules_stage: bool = True,
) -> TrapResult:
    """One trap's result. A rules trap counts as handled when the Rules stage changed its
    file and its check stays quiet (a later agent edit to the same file doesn't undo
    that); with no Rules stage, a rules trap the agent handled is Other layer. A human
    trap is Expected when its file was handed off, even though its check still fires
    at the final verify."""
    file = trap.location.file
    checks: list[TrapCheck] = []
    evidence: list[str] = []
    for check in trap.checks():
        found = _failures_for_check(check, trap, failures)
        checks.append(TrapCheck(check=check, fired=bool(found)))
        evidence.extend(_describe(f) for f in found)
    caught = any(c.fired for c in checks)
    result: TrapResultName
    if trap.expected_layer == "visual-only":
        result = "Not scored"
    elif trap.expected_layer == "rules" and rules_stage:
        handled = rules_ok and file in rules_changed and not caught
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


# --------------------------------------------------------------------------- outcomes


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


def score(evidence: Evidence) -> Scorecard:
    """The Scorecard of one finished workspace."""
    ev = evidence
    if isinstance(ev.changes, AgentChanges):
        return _score(ev, MigratorChanges(rules=None), ev.changes)
    return _score(ev, ev.changes, None)


def _score(ev: Evidence, ch: MigratorChanges, agent: AgentChanges | None) -> Scorecard:
    """The scoring rules. ``agent`` is set for a workspace with no Rules stage; ``ch`` is
    then empty (no Rules, no repair, no review aids)."""
    affected = ev.usage.affected_files()
    failures = ev.verify.failures if ev.verify else []
    rules_changed = set(ch.rules.changed_files) if ch.rules else set()
    layers: dict[str, Layer] = {p: "rules" for p in rules_changed}
    layers.update(ch.later_layers or {})
    repair = ch.repair
    records = {f.path: f for f in repair.files} if repair else {}
    handed_off: list[str] = list(repair.review_list) if repair else []
    unfinished: dict[str, str] = {}
    if agent is None:
        rules_ok = ch.rules is not None and ch.rules.status == "ok"
        before = ch.rules_verify or ev.verify
        failing_before = {f.file for f in before.failures if f.file} if before else set()
        changed_by_run: set[str] = set()
        changed = rules_changed
    else:
        # No Rules stage: everything the agent changed is layer Agent, its unfinished
        # files are its Hand-offs, and Regressions are counted against the Pre-check.
        rules_ok = True
        layers = dict.fromkeys(agent.changed_files, "agent")
        unfinished = {u.path: u.reason for u in agent.unfinished}
        handed_off = list(unfinished)
        failing_before = {f.file for f in ev.precheck.pre_existing_failures if f.file}
        changed_by_run = set(agent.changed_files)
        changed = changed_by_run
    cheating = ev.cheating
    hit_files = cheating.hit_files() if cheating else set()
    hits = cheating.hits if cheating else []

    if ev.precheck.status == "rejected":
        status: RunStatus = "rejected"
        reason = ev.precheck.reason
    elif not rules_ok:
        status, reason = "rules_failure", ch.rules.reason if ch.rules else "Rules did not run"
    else:
        status, reason = "completed", None

    failing_files = sorted({f.file for f in failures if f.file})
    # A Regression: a file with no failures before (after Rules, or at the Pre-check)
    # that fails at the final verify. A file the producer changed itself is not one: it
    # ends Unmigrated with its failures.
    regressions = sorted(
        p for p in failing_files if p not in failing_before and p not in changed_by_run
    )

    files: list[FileResult] = []
    for path in affected:
        file_failures = [f for f in failures if f.file == path]
        final = ev.final_usage.file(path) if ev.final_usage else None
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
        elif path in unfinished:
            outcome, note = "Handed off", unfinished[path]
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
    outside = [f for f in failures if f.file not in set(handed_off) or f.file is None]

    trap_results: list[TrapResult] | None = None
    trap_counts: TrapCounts | None = None
    if ev.traps is not None:
        trap_results = [
            _score_trap(
                t,
                failures,
                layers,
                set(handed_off),
                rules_ok and status == "completed",
                rules_changed,
                rules_stage=agent is None,
            )
            for t in ev.traps.traps
        ]
        tc = Counter(t.result for t in trap_results)
        trap_counts = TrapCounts(
            expected=tc["Expected"],
            other_layer=tc["Other layer"],
            missed=tc["Missed"],
            not_scored=tc["Not scored"],
            silent=sum(t.silent_miss for t in trap_results),
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
        hand_offs=len(set(handed_off)),
        regressions=len(regressions),
        cheating_check_hits=len(hits),
        cheating_check_warnings=len(cheating.warnings) if cheating else 0,
        codemod_todos=len(ch.rules.codemod_todos) if ch.rules else 0,
        traps=trap_counts,
    )
    pre = ev.precheck
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
        migration=ev.usage.migration,
        target_repo=ev.usage.target_repo,
        configuration=ev.configuration,
        configuration_digest=ev.configuration_digest,
        case=ev.case,
        status=status,
        reason=reason,
        headline=headline,
        files=files,
        changed_not_affected=sorted(changed - set(affected)),
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
            status=ch.rules.status,
            reason=ch.rules.reason,
            steps=[
                StepSummary(
                    kind=s.kind,
                    name=s.name,
                    status=s.status,
                    changed_files=s.changed_files,
                    detail=s.detail,
                )
                for s in ch.rules.steps
            ],
            changed_files=ch.rules.changed_files,
            codemod_todos=ch.rules.codemod_todos,
        )
        if ch.rules
        else None,
        verify=VerifySummary(
            commands=_commands(ev.verify.commands),
            failures=ev.verify.failures,
            pre_existing_excluded=len(ev.verify.pre_existing),
            test_totals=ev.verify.test_totals,
        )
        if ev.verify
        else None,
        traps=trap_results,
        cheating=cheating,
        repair=_repair_summary(repair, files) if repair else None,
        regressions=regressions,
        regressions_against="Verify after Rules" if agent is None else "Pre-check",
        handed_off=handed_off,
        coverage=coverage,
        snapshots_to_review=ch.snapshots_to_review,
        repeated_edits=ch.repeated_edits,
        test_fitting=ch.test_fitting,
        codemod_false_positives=(ch.rules.false_positives or None) if ch.rules else None,
        visual=ch.visual,
        cost=ev.cost,
        meta=ev.meta,
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
