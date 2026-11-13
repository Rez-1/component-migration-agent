"""Verify after Rules, the final Verify, and the snapshot policy (M6)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from migrator.checks import (
    CheatingReport,
    CheckInput,
    FileSet,
    Layer,
    read_files,
    read_test_rules,
    run_checks,
)
from migrator.repair.records import RepairReport
from migrator.report import write_json
from migrator.run.context import RunContext
from migrator.run.state import RunState, dump_failures
from migrator.scan import ScanInput, scan
from migrator.scoring import SnapshotUpdate
from migrator.verify import PrecheckResult, VerifyResult
from migrator.workspace import hash_file


def verify_node(ctx: RunContext, state: RunState) -> RunState:
    """The Verify after Rules. With the snapshot policy, snapshot-only failures are
    rewritten and the Start of Repair is saved again to include them."""
    d = ctx.deps
    d.say("Verify", "type-check, lint, tests")
    result = ctx.checker(state).check("verify")
    d.say("Verify", f"{len(result.failures)} failures in {len(result.failing_files())} files")
    updates: list[dict[str, Any]] = []
    if d.config.update_snapshots:
        result, updates = update_snapshots(ctx, state, result, "verify")
        if updates:
            # The Migrator's own change, before repair: part of the Rules layer.
            ctx.files.save_start_of_repair(read_files(ctx.workspace(state)))
    return {
        "verify": result.model_dump(mode="json"),
        "known_failures": dump_failures(result.failures),
        "snapshot_updates": updates,
    }


def update_snapshots(
    ctx: RunContext, state: RunState, result: VerifyResult, stage: str
) -> tuple[VerifyResult, list[dict[str, Any]]]:
    """The snapshot policy (M6): rewrite snapshot-only failures, list each one."""
    d = ctx.deps
    workspace = ctx.workspace(state)
    result, run = ctx.checker(state).update_snapshots(
        stage, result, lambda: snapshot_hashes(workspace)
    )
    if run is None:
        return result, []
    snaps = run.changed_files
    updates = [
        SnapshotUpdate(
            test_file=t,
            snapshot_file=next((s for s in snaps if snapshot_belongs(s, t)), None),
            tests=names,
            stage=stage,
        ).model_dump(mode="json")
        for t, names in run.updated.items()
    ]
    d.say(
        "Verify",
        f"snapshots: updated {len(updates)} test files whose only failures were "
        f"snapshot mismatches ({len(snaps)} snapshot files changed), for a human to review",
    )
    return result, updates


def final_verify_node(ctx: RunContext, state: RunState) -> RunState:
    """The final verify (with the snapshot policy), the rescan, the final
    files saved for scoring, and the cheating checks."""
    d = ctx.deps
    workspace = ctx.workspace(state)
    report = ctx.report(state)
    final = final_check(ctx, state, report)
    final_snapshots: list[dict[str, Any]] = []
    if d.config.update_snapshots:
        final, final_snapshots = update_snapshots(ctx, state, final, "final")
    final_usage = scan(
        ScanInput(
            repo=workspace,
            spec=d.spec,
            source_globs=d.config.source_globs,
            exclude=d.config.exclude,
        )
    )
    write_json(final_usage, ctx.files.final_usage_path)
    final_files = read_files(workspace)
    ctx.files.save_final(final_files)
    start = ctx.files.start_of_repair()
    layers = final_layers(start, final_files, report, migrator_snapshots(state, final_snapshots))
    cheating = cheating_checks(ctx, state, final, start, final_files, layers)
    d.say("Checks", f"{len(cheating.hits)} cheating-check hits, {len(cheating.notes)} notes")
    d.say("Verify", f"{len(final.failures)} failures in {len(final.failing_files())} files")
    return {
        "final": final.model_dump(mode="json"),
        "final_usage_path": str(ctx.files.final_usage_path),
        "cheating": cheating.model_dump(mode="json"),
        "snapshot_updates": [*(state.get("snapshot_updates") or []), *final_snapshots],
    }


def final_check(ctx: RunContext, state: RunState, report: RepairReport) -> VerifyResult:
    """The final verify: the Verify after Rules again when nothing changed since."""
    repaired = any(f.touched for f in report.files) or bool(report.human_changed)
    if state.get("verify") and not repaired:
        return VerifyResult.model_validate(state["verify"])
    ctx.deps.say("Verify", "final: type-check, lint, tests")
    return ctx.checker(state).check("final")


def cheating_checks(
    ctx: RunContext,
    state: RunState,
    final: VerifyResult,
    start: FileSet,
    final_files: FileSet,
    layers: dict[str, Layer],
) -> CheatingReport:
    """The cheating checks on the final workspace, against the untouched one and the
    Start of Repair; ``layers``: who changed each file after Rules."""
    pre = PrecheckResult.model_validate(state["precheck"])
    rules_verify = VerifyResult.model_validate(state["verify"]) if state.get("verify") else None
    return run_checks(
        CheckInput(
            before=ctx.files.untouched(),
            after_rules=start,
            final=final_files,
            later_layers=layers,
            test_rules=read_test_rules(ctx.workspace(state)),
            precheck_totals=pre.test_totals,
            final_totals=final.test_totals,
            rules_totals=rules_verify.test_totals if rules_verify else None,
        )
    )


def migrator_snapshots(state: RunState, extra: list[dict[str, Any]] | None = None) -> set[str]:
    """Snapshot files the Migrator itself rewrote (never the agent's layer)."""
    rows = [*(state.get("snapshot_updates") or []), *(extra or [])]
    return {str(r["snapshot_file"]) for r in rows if r.get("snapshot_file")}


def final_layers(
    after_rules: FileSet,
    final: FileSet,
    report: RepairReport,
    migrator_snapshots: set[str] | None = None,
) -> dict[str, Layer]:
    """Who changed each file after the Rules stage: the human (at Review) or the agent.
    Snapshot files the Migrator itself rewrote at the final verify (the snapshot policy,
    M6) count as the Rules layer: deterministic, and listed for a human to review."""
    human = set(report.human_changed)
    ours = migrator_snapshots or set()
    layers: dict[str, Layer] = {}
    for path in after_rules.keys() | final.keys():
        if after_rules.get(path) != final.get(path):
            layers[path] = "rules" if path in ours else "human" if path in human else "agent"
    return layers


def snapshot_hashes(workspace: Path) -> dict[str, str]:
    """sha256 of every snapshot file in the workspace (not in node_modules)."""
    out: dict[str, str] = {}
    for folder, dirs, files in workspace.walk():
        dirs[:] = [x for x in dirs if x not in ("node_modules", ".git")]
        for name in files:
            if name.endswith(".snap"):
                path = folder / name
                out[path.relative_to(workspace).as_posix()] = hash_file(path)
    return out


def snapshot_belongs(snapshot: str, test_file: str) -> bool:
    """``a/__snapshots__/B.test.tsx.snap`` belongs to ``a/B.test.tsx``."""
    snap, test = PurePosixPath(snapshot), PurePosixPath(test_file)
    return snap.name == f"{test.name}.snap" and snap.parent.parent == test.parent
