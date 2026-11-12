"""Report: the run's Scoring evidence, its Scorecard and PR body, then cleanup."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from migrator import __version__
from migrator.checks import CheatingReport, Layer, read_files
from migrator.cost import CallRecord, run_cost
from migrator.report import render_pr_body, render_scorecard, write_json
from migrator.review_aids import repeated_edits, test_fitting_flags
from migrator.rules import RulesResult
from migrator.run.context import RunContext
from migrator.run.stages.prepare import visual_setup
from migrator.run.stages.verify import final_layers, migrator_snapshots
from migrator.run.state import RunState
from migrator.scan import UsageReport
from migrator.scoring import Evidence, MigratorChanges, RunMeta, SnapshotUpdate, score
from migrator.verify import PrecheckResult, VerifyResult
from migrator.visual.check import reference_capture, visual_report
from migrator.visual.compare import VisualReport
from migrator.workspace import StageCommit, remove_worktree

# The run's Scoring evidence, in its run folder: written before the Scorecard is built,
# so a run can be scored again later (issue #17's replay gate).
EVIDENCE_FILE = "report-input.json"
# Whole file texts a repair record keeps for Review; Scoring never reads them, and the
# evidence file must not copy the target repo's source.
_FILE_TEXTS = ("set_aside", "originals", "failures_at_hand_off")


def write_evidence(evidence: Evidence, path: Path) -> None:
    """``evidence`` as JSON, without the repair records' file texts."""
    data = evidence.model_dump(mode="json")
    for record in (data["changes"].get("repair") or {}).get("files") or []:
        for key in _FILE_TEXTS:
            record.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def _visual(ctx: RunContext, state: RunState, finished: bool) -> VisualReport | None:
    """The visual check's report (M7); against the reference PR only in an eval."""
    d = ctx.deps
    setup = visual_setup(ctx)
    if setup is None:
        return None
    case = d.case if d.mode == "eval" else None
    return visual_report(
        setup,
        state.get("visual_before"),
        ctx.workspace(state) if finished else None,
        ctx.files.folder / "visual",
        lambda: reference_capture(setup, case, d.config) if case is not None else None,
    )


def report_node(ctx: RunContext, state: RunState) -> RunState:
    d = ctx.deps
    run_dir = ctx.files.folder
    usage = UsageReport.model_validate_json(Path(state["usage_path"]).read_text("utf-8"))
    pre = PrecheckResult.model_validate(state["precheck"])
    rules = RulesResult.model_validate(state["rules"]) if state.get("rules") else None
    post_rules = VerifyResult.model_validate(state["verify"]) if state.get("verify") else None
    final = VerifyResult.model_validate(state["final"]) if state.get("final") else None
    final_usage = (
        UsageReport.model_validate_json(Path(fp).read_text("utf-8"))
        if (fp := state.get("final_usage_path"))
        else None
    )
    report = ctx.report(state)
    calls = [CallRecord.model_validate(c) for c in state.get("calls") or []]
    timings = dict(state.get("timings") or {})
    if calls:
        timings["model"] = round(sum(c.duration_s for c in calls), 2)
    started = datetime.strptime(state["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    finished = datetime.now(UTC)
    meta = RunMeta(
        run_id=state["run_id"],
        started_at=state["started_at"],
        finished_at=finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        duration_s=round((finished - started).total_seconds(), 1),
        migrator_version=__version__,
        node_version=state.get("node_version"),
        npm_version=state.get("npm_version"),
        timings_s=timings,
        sandbox=d.sandbox,
        branch=d.worktree.branch if d.worktree else None,
        base_branch=d.worktree.base_branch if d.worktree else None,
        commits=[StageCommit.model_validate(c) for c in state.get("commits") or []],
        features_off=d.configuration.feature_notes(),
    )
    layers: dict[str, Layer] | None = None
    if state.get("workspace") and rules is not None and rules.status == "ok" and final is not None:
        layers = final_layers(
            ctx.files.start_of_repair(),
            read_files(ctx.workspace(state)),
            report,
            migrator_snapshots(state),
        )
    visual = _visual(
        ctx,
        state,
        finished=bool(state.get("workspace"))
        and rules is not None
        and rules.status == "ok"
        and final is not None,
    )
    cost = run_cost(
        calls,
        d.caps.run_usd,
        d.caps.month_usd,
        month_spent_usd=d.ledger.month_spent() if calls else None,
        stopped_by_cap=report.stopped_by_cost_cap,
    )
    evidence = Evidence(
        usage=usage,
        precheck=pre,
        verify=final,
        final_usage=final_usage,
        traps=d.traps,
        configuration=d.configuration.name,
        configuration_digest=d.configuration.digest(),
        cheating=CheatingReport.model_validate(state["cheating"])
        if state.get("cheating")
        else None,
        cost=cost,
        case=d.case.id if d.case else (d.traps.case if d.traps else None),
        meta=meta,
        changes=MigratorChanges(
            rules=rules,
            rules_verify=post_rules,
            repair=report if d.configuration.repair.enabled else None,
            later_layers=layers,
            repeated_edits=repeated_edits(
                ctx.files.start_of_repair(), read_files(ctx.workspace(state)), layers
            )
            if layers is not None and d.configuration.repair.shared_causes
            else None,
            test_fitting=test_fitting_flags(
                ctx.files.start_of_repair(),
                read_files(ctx.workspace(state)),
                [(f.path, f.touched) for f in report.files if f.touched],
                {f.file for f in post_rules.failures if f.source == "test" and f.file},
            )
            if layers is not None and post_rules is not None and d.configuration.repair.enabled
            else None,
            snapshots_to_review=[
                SnapshotUpdate.model_validate(r) for r in state.get("snapshot_updates") or []
            ]
            if d.config.update_snapshots
            else None,
            visual=visual,
        ),
    )
    write_evidence(evidence, run_dir / EVIDENCE_FILE)  # before Scoring: see #17
    card = score(evidence)
    write_json(card, run_dir / "scorecard.json")
    (run_dir / "scorecard.md").write_text(render_scorecard(card), "utf-8")
    # The PR body, rendered from the same JSON; written for every run, opened as a PR
    # only by the separate `migrator pr --open` step.
    (run_dir / "pr-body.md").write_text(render_pr_body(card), "utf-8")
    d.say("Report", f"written to {run_dir}")
    ws = state.get("workspace")
    if ws and not d.keep_workspace:
        if d.worktree is None:
            shutil.rmtree(Path(ws).parent, ignore_errors=True)
        elif remove_worktree(d.worktree):  # the branch stays when it has commits
            d.say("Report", f"nothing was committed, so {d.worktree.branch} was removed")
    return {"scorecard_path": str(run_dir / "scorecard.json")}
