"""Scan, Pre-check (with its per-case cache) and Rules."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from migrator.checks import read_files
from migrator.execs import CommandRunner, node_image
from migrator.precheck_cache import (
    CachedPrecheck,
    PrecheckCache,
    cache_key,
    clone_tree,
    restore_logs,
)
from migrator.repair.records import RepairReport
from migrator.report import write_json
from migrator.rules import RulesInput, RulesResult, ToolsError, apply_rules, ensure_tools
from migrator.run.context import RunContext
from migrator.run.state import RunState, now
from migrator.scan import ScanInput, UsageReport, scan
from migrator.scan.render import render_usage_report
from migrator.verify import PrecheckInput, PrecheckResult, precheck
from migrator.visual.check import VisualSetup, capture_workspace
from migrator.workspace import create_dry_run_workspace


def scan_node(ctx: RunContext, state: RunState) -> RunState:
    """Scan the target repo for the migration's old usages into the run folder; the
    repair report and the call list start empty."""
    d = ctx.deps
    d.say("Scan", f"scanning {d.repo.name}")
    usage = scan(
        ScanInput(
            repo=d.repo,
            spec=d.spec,
            source_globs=d.config.source_globs,
            exclude=d.config.exclude,
        )
    )
    run_dir = ctx.files.folder
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(usage, run_dir / "usage-report.json")
    (run_dir / "usage-report.md").write_text(render_usage_report(usage), "utf-8")
    d.say(
        "Scan",
        f"{usage.totals.affected_files} affected files, {usage.totals.old_usages} usages",
    )
    return {
        "usage_path": str(run_dir / "usage-report.json"),
        "config": d.config.model_dump(mode="json"),
        "repair": RepairReport(enabled=d.configuration.repair.enabled).model_dump(mode="json"),
        "calls": [],
    }


def precheck_node(ctx: RunContext, state: RunState) -> RunState:
    """Make the workspace (a real run's worktree, or a new copy for a dry run),
    install and verify it untouched, and take the visual check's before capture."""
    d = ctx.deps
    if d.worktree is not None:  # a real run: the worktree on the migration branch
        workspace = d.worktree.workspace
        node_version, npm_version, pre = run_precheck(ctx, workspace)
    else:
        workspace = Path(tempfile.mkdtemp(prefix=f"migrator-{state['run_id']}-")) / "workspace"
        if d.precheck_cache is not None:
            node_version, npm_version, pre = cached_precheck(ctx, d.precheck_cache, workspace)
        else:
            create_dry_run_workspace(d.repo, workspace)
            node_version, npm_version, pre = run_precheck(ctx, workspace)
    d.say("Pre-check", pre.status if pre.status == "ok" else f"rejected: {pre.reason}")
    visual = visual_setup(ctx)
    before = (
        capture_workspace(visual, workspace, ctx.files.folder / "visual" / "before")
        if visual is not None and pre.status == "ok"
        else None
    )
    return {
        "visual_before": before,
        "workspace": str(workspace),
        "node_version": node_version,
        "npm_version": npm_version,
        "precheck": pre.model_dump(mode="json"),
    }


def cached_precheck(
    ctx: RunContext, cache: PrecheckCache, workspace: Path
) -> tuple[str | None, str | None, PrecheckResult]:
    """Speed-up 2 (M6): one install and Pre-check per case, cloned into each dry run's
    ``workspace``. Only a Pre-check that passed is cached."""
    d = ctx.deps
    untouched = ctx.files.untouched_path
    key = cache_key(d.repo, d.config, where(ctx))
    with cache.locked(key):
        hit = cache.get(key)
        if hit is None:
            create_dry_run_workspace(d.repo, workspace)
            node_version, npm_version, pre = run_precheck(ctx, workspace)
            if pre.status == "ok":
                cached = CachedPrecheck(
                    precheck=pre, node_version=node_version, npm_version=npm_version
                )
                cache.put(key, workspace, ctx.files.logs, cached, untouched)
            return node_version, npm_version, pre
        d.say("Pre-check", "reusing this case's cached install and Pre-check")
        clone_tree(cache.workspace(key), workspace)
        restore_logs(cache, key, ctx.files.logs)
        untouched.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache.entry(key) / "untouched.json", untouched)
        return hit.node_version, hit.npm_version, hit.precheck


def visual_setup(ctx: RunContext) -> VisualSetup | None:
    """The run's visual check (M7); None when the repo has no [visual] section."""
    d = ctx.deps
    cfg = d.config.visual
    if cfg is None:
        return None
    return VisualSetup(
        cfg=cfg.model_copy(update={"hide": [*d.spec.visual_hide, *cfg.hide]}),
        sandbox=d.sandbox,
        runner=d.runner,
        tools_cache=d.tools_cache,
        say=d.say,
    )


def where(ctx: RunContext) -> str:
    """Where commands run, as part of the Pre-check cache key."""
    d = ctx.deps
    if d.sandbox != "docker":
        return "local"
    return f"docker:{node_image(d.config.node)}"


def _tool_version(runner: CommandRunner, tool: str, cwd: Path) -> str | None:
    result = runner.run([tool, "--version"], cwd, timeout_s=30)
    return result.output.strip().removeprefix("v") if result.ok else None


def run_precheck(ctx: RunContext, workspace: Path) -> tuple[str | None, str | None, PrecheckResult]:
    """Install and verify the untouched workspace (the Pre-check itself)."""
    d = ctx.deps
    node_version = _tool_version(d.runner, "node", workspace)
    npm_version = _tool_version(d.runner, d.config.package_manager, workspace)
    # What the Pre-check verifies: the untouched workspace, for the cheating checks.
    ctx.files.save_untouched(read_files(workspace))
    d.say("Pre-check", "installing and verifying the untouched workspace")
    pre = precheck(
        PrecheckInput(workspace=workspace, config=d.config, log_dir=ctx.files.logs), d.runner
    )
    return node_version, npm_version, pre


def rules_node(ctx: RunContext, state: RunState) -> RunState:
    """Run the rule steps, once: a marker refuses a second start on the same
    workspace. The workspace after them is saved as the Start of Repair."""
    d = ctx.deps
    if state.get("rules_done"):
        return {}
    marker = ctx.files.rules_marker
    if marker.exists():
        raise RuntimeError(
            "the Rules stage was interrupted part-way in this run; the codemods are not "
            "idempotent, so it cannot run again on this workspace. Start a new run."
        )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(now(), "utf-8")
    workspace = ctx.workspace(state)
    d.say("Rules", "running the rule steps")
    rules = run_rules(ctx, workspace, Path(state["usage_path"]))
    d.say(
        "Rules",
        f"{len(rules.changed_files)} files changed"
        if rules.status == "ok"
        else f"Rules failure: {rules.reason}",
    )
    ctx.files.save_start_of_repair(read_files(workspace))
    return {"rules": rules.model_dump(mode="json"), "rules_done": True}


def run_rules(ctx: RunContext, workspace: Path, usage_path: Path) -> RulesResult:
    """The migration spec's rule steps on the scan's Affected files; a Rules failure
    when the pinned codemod tools can't be installed."""
    d = ctx.deps
    usage = UsageReport.model_validate_json(usage_path.read_text("utf-8"))
    try:
        tools = ensure_tools(d.spec, d.runner, d.tools_cache) if d.spec.tools else None
    except ToolsError as exc:
        return RulesResult(status="rules_failure", reason=str(exc), steps=[], changed_files=[])
    rules_input = RulesInput(
        workspace=workspace,
        spec=d.spec,
        config=d.config,
        affected_files=usage.affected_files(),
        tools_dir=tools,
        log_dir=ctx.files.logs,
    )
    return apply_rules(rules_input, d.runner)


def route_precheck(ctx: RunContext, state: RunState) -> str:
    pre = state.get("precheck") or {}
    return "rules" if pre.get("status") == "ok" else "report"


def route_rules(ctx: RunContext, state: RunState) -> str:
    rules = state.get("rules") or {}
    return "commit_rules" if rules.get("status") == "ok" else "report"
