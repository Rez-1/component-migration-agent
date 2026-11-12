"""Report: the run's Scoring evidence, its Scorecard and PR body, then cleanup."""

from __future__ import annotations

import shutil
from functools import partial
from pathlib import Path

from migrator.report import render_pr_body, render_scorecard, write_json
from migrator.run.context import RunContext
from migrator.run.evidence import EVIDENCE_FILE, evidence_from_run, write_evidence
from migrator.run.stages.prepare import visual_setup
from migrator.run.state import RunState
from migrator.scoring import score
from migrator.visual.check import reference_capture, visual_report
from migrator.visual.compare import VisualReport
from migrator.workspace import remove_worktree


def report_node(ctx: RunContext, state: RunState) -> RunState:
    d = ctx.deps
    run_dir = ctx.files.folder
    evidence = evidence_from_run(state, ctx.files, d, partial(_visual, ctx, state))
    write_evidence(evidence, run_dir / EVIDENCE_FILE)  # before Scoring: see #17
    card = score(evidence)
    write_json(card, run_dir / "scorecard.json")
    (run_dir / "scorecard.md").write_text(render_scorecard(card), "utf-8")
    # The PR body, rendered from the same JSON; written for every run, opened as a PR
    # only by the separate `migrator pr --open` step.
    (run_dir / "pr-body.md").write_text(render_pr_body(card), "utf-8")
    d.say("Report", f"written to {run_dir}")
    _clean_up(ctx, state)  # here until #26 makes it a node of its own
    return {"scorecard_path": str(run_dir / "scorecard.json")}


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


def _clean_up(ctx: RunContext, state: RunState) -> None:
    """Remove a dry run's workspace, or a real run's worktree when it made no commit
    (the branch stays when it has commits), unless the run keeps its workspace."""
    d = ctx.deps
    ws = state.get("workspace")
    if ws and not d.keep_workspace:
        if d.worktree is None:
            shutil.rmtree(Path(ws).parent, ignore_errors=True)
        elif remove_worktree(d.worktree):
            d.say("Report", f"nothing was committed, so {d.worktree.branch} was removed")
