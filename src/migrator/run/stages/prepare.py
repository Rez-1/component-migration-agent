"""Scan, Pre-check (with its per-case cache) and Rules."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from migrator.checks import read_files
from migrator.execs import CommandRunner, node_image
from migrator.precheck_cache import CachedPrecheck, cache_key, clone_tree, restore_logs
from migrator.repair.records import RepairReport
from migrator.report import write_json
from migrator.rules import RulesInput, RulesResult, ToolsError, apply_rules, ensure_tools
from migrator.run.context import RunContext
from migrator.run.stages.visual import visual_capture
from migrator.run.state import RunState, now
from migrator.scan import ScanInput, UsageReport, scan
from migrator.scan.render import render_usage_report
from migrator.verify import PrecheckInput, PrecheckResult, precheck
from migrator.workspace import create_dry_run_workspace


def scan_node(ctx: RunContext, state: RunState) -> RunState:
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
    d = ctx.deps
    if d.worktree is not None:
        workspace = d.worktree.workspace  # a real run: the worktree on the migration branch
    else:
        parent = Path(tempfile.mkdtemp(prefix=f"migrator-{state['run_id']}-"))
        workspace = parent / "workspace"
    untouched = ctx.files.untouched_path
    if d.precheck_cache is not None and d.worktree is None:
        # Speed-up 2 (M6): one install and Pre-check per case, cloned into each run.
        cache = d.precheck_cache
        key = cache_key(d.repo, d.config, where(ctx))
        with cache.locked(key):
            hit = cache.get(key)
            if hit is None:
                create_dry_run_workspace(d.repo, workspace)
                node_version, npm_version, pre = run_precheck(ctx, workspace)
                if pre.status == "ok":
                    cache.put(
                        key,
                        workspace,
                        ctx.files.logs,
                        CachedPrecheck(
                            precheck=pre,
                            node_version=node_version,
                            npm_version=npm_version,
                        ),
                        untouched,
                    )
            else:
                d.say("Pre-check", "reusing this case's cached install and Pre-check")
                clone_tree(cache.workspace(key), workspace)
                restore_logs(cache, key, ctx.files.logs)
                untouched.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cache.entry(key) / "untouched.json", untouched)
                node_version, npm_version, pre = hit.node_version, hit.npm_version, hit.precheck
    else:
        if d.worktree is None:
            create_dry_run_workspace(d.repo, workspace)
        node_version, npm_version, pre = run_precheck(ctx, workspace)
    d.say("Pre-check", pre.status if pre.status == "ok" else f"rejected: {pre.reason}")
    before = visual_capture(ctx, workspace, "before") if pre.status == "ok" else None
    return {
        "visual_before": before,
        "workspace": str(workspace),
        "node_version": node_version,
        "npm_version": npm_version,
        "precheck": pre.model_dump(mode="json"),
    }


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
    usage = UsageReport.model_validate_json(Path(state["usage_path"]).read_text("utf-8"))
    d.say("Rules", "running the rule steps")
    try:
        tools = ensure_tools(d.spec, d.runner, d.tools_cache) if d.spec.tools else None
    except ToolsError as exc:
        rules = RulesResult(status="rules_failure", reason=str(exc), steps=[], changed_files=[])
    else:
        rules = apply_rules(
            RulesInput(
                workspace=workspace,
                spec=d.spec,
                config=d.config,
                affected_files=usage.affected_files(),
                tools_dir=tools,
                log_dir=ctx.files.logs,
            ),
            d.runner,
        )
    d.say(
        "Rules",
        f"{len(rules.changed_files)} files changed"
        if rules.status == "ok"
        else f"Rules failure: {rules.reason}",
    )
    ctx.files.save_start_of_repair(read_files(workspace))
    return {"rules": rules.model_dump(mode="json"), "rules_done": True}


def route_precheck(ctx: RunContext, state: RunState) -> str:
    pre = state.get("precheck") or {}
    return "rules" if pre.get("status") == "ok" else "report"


def route_rules(ctx: RunContext, state: RunState) -> str:
    rules = state.get("rules") or {}
    return "commit_rules" if rules.get("status") == "ok" else "report"
