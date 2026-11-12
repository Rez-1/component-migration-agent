"""A finished run's Scoring evidence, built from its state and run folder.

Scoring takes ``Evidence`` and never sees the run state; this is the one place that
turns one into the other. Each input is read once: the scans, the Start of Repair,
the final workspace and the ledger.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from migrator import __version__
from migrator.checks import CheatingReport, FileSet, read_files
from migrator.cost import CallRecord, run_cost
from migrator.repair.records import RepairReport
from migrator.review_aids import repeated_edits, test_fitting_flags
from migrator.rules import RulesResult
from migrator.run.context import RunDeps
from migrator.run.files import RunFiles
from migrator.run.stages.verify import final_layers, migrator_snapshots
from migrator.run.state import RunState
from migrator.scan import UsageReport
from migrator.scoring import Evidence, MigratorChanges, RunMeta, SnapshotUpdate
from migrator.verify import PrecheckResult, VerifyResult
from migrator.visual.compare import VisualReport
from migrator.workspace import StageCommit

# The run's Scoring evidence, in its run folder: written before the Scorecard is built,
# so a run can be scored again later (issue #17's replay gate).
EVIDENCE_FILE = "report-input.json"
# Whole file texts a repair record keeps for Review; Scoring never reads them, and the
# evidence file must not copy the target repo's source.
_FILE_TEXTS = ("set_aside", "originals", "failures_at_hand_off")

# The visual check's report, given whether the run finished (reached its final verify).
VisualCheck = Callable[[bool], VisualReport | None]


def write_evidence(evidence: Evidence, path: Path) -> None:
    """``evidence`` as JSON, without the repair records' file texts."""
    data = evidence.model_dump(mode="json")
    for record in (data["changes"].get("repair") or {}).get("files") or []:
        for key in _FILE_TEXTS:
            record.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def _usage(path: str) -> UsageReport:
    return UsageReport.model_validate_json(Path(path).read_text("utf-8"))


def evidence_from_run(
    state: RunState, files: RunFiles, deps: RunDeps, visual: VisualCheck
) -> Evidence:
    """The run's Evidence. ``visual`` runs the after capture: it is called after the
    run's end time is taken and its files are read, since the capture builds the app."""
    rules = RulesResult.model_validate(state["rules"]) if state.get("rules") else None
    final = VerifyResult.model_validate(state["final"]) if state.get("final") else None
    report = RepairReport.model_validate(
        state.get("repair") or {"enabled": deps.configuration.repair.enabled}
    )
    calls = [CallRecord.model_validate(c) for c in state.get("calls") or []]
    meta = run_meta(state, deps, calls)
    ws = state.get("workspace")
    finished = bool(ws) and rules is not None and rules.status == "ok" and final is not None
    # The Start of Repair and the final files: who changed what after Rules.
    layers = (files.start_of_repair(), read_files(Path(str(ws)))) if finished else None
    visual_report = visual(finished)
    cost = run_cost(
        calls,
        deps.caps.run_usd,
        deps.caps.month_usd,
        month_spent_usd=deps.ledger.month_spent() if calls else None,
        stopped_by_cap=report.stopped_by_cost_cap,
    )
    return Evidence(
        usage=_usage(state["usage_path"]),
        precheck=PrecheckResult.model_validate(state["precheck"]),
        verify=final,
        final_usage=_usage(fp) if (fp := state.get("final_usage_path")) else None,
        traps=deps.traps,
        configuration=deps.configuration.name,
        configuration_digest=deps.configuration.digest(),
        cheating=CheatingReport.model_validate(state["cheating"])
        if state.get("cheating")
        else None,
        cost=cost,
        case=deps.case.id if deps.case else (deps.traps.case if deps.traps else None),
        meta=meta,
        changes=migrator_changes(state, deps, rules, report, layers, visual_report),
    )


def run_meta(state: RunState, deps: RunDeps, calls: list[CallRecord]) -> RunMeta:
    """When the run started and finished, where it ran, its timings and commits."""
    timings = dict(state.get("timings") or {})
    if calls:
        timings["model"] = round(sum(c.duration_s for c in calls), 2)
    started = datetime.strptime(state["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    finished = datetime.now(UTC)
    return RunMeta(
        run_id=state["run_id"],
        started_at=state["started_at"],
        finished_at=finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        duration_s=round((finished - started).total_seconds(), 1),
        migrator_version=__version__,
        node_version=state.get("node_version"),
        npm_version=state.get("npm_version"),
        timings_s=timings,
        sandbox=deps.sandbox,
        branch=deps.worktree.branch if deps.worktree else None,
        base_branch=deps.worktree.base_branch if deps.worktree else None,
        commits=[StageCommit.model_validate(c) for c in state.get("commits") or []],
        features_off=deps.configuration.feature_notes(),
    )


def migrator_changes(
    state: RunState,
    deps: RunDeps,
    rules: RulesResult | None,
    report: RepairReport,
    workspace: tuple[FileSet, FileSet] | None,
    visual: VisualReport | None,
) -> MigratorChanges:
    """What Rules, Repair and Review did, who changed each file after Rules, and the
    aids for a human reviewer. ``workspace``: the Start of Repair and the final files,
    for a run that finished (reached its final verify); None for one that did not."""
    post_rules = VerifyResult.model_validate(state["verify"]) if state.get("verify") else None
    repair = deps.configuration.repair
    changes = MigratorChanges(
        rules=rules,
        rules_verify=post_rules,
        repair=report if repair.enabled else None,
        snapshots_to_review=[
            SnapshotUpdate.model_validate(r) for r in state.get("snapshot_updates") or []
        ]
        if deps.config.update_snapshots
        else None,
        visual=visual,
    )
    if workspace is None:
        return changes
    start, now = workspace
    changes.later_layers = layers = final_layers(start, now, report, migrator_snapshots(state))
    if repair.shared_causes:
        changes.repeated_edits = repeated_edits(start, now, layers)
    if post_rules is not None and repair.enabled:
        changes.test_fitting = test_fitting_flags(
            start,
            now,
            [(f.path, f.touched) for f in report.files if f.touched],
            {f.file for f in post_rules.failures if f.source == "test" and f.file},
        )
    return changes
