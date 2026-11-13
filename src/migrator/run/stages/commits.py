"""A real run's stage commits, after Rules, Repair and Review, and their messages."""

from __future__ import annotations

from migrator.cost import CallRecord
from migrator.repair.records import RepairReport
from migrator.report import usd
from migrator.rules import RulesResult
from migrator.run.context import RunContext
from migrator.run.state import RunState
from migrator.workspace import StageCommit, StageName, commit_stage


def commit_rules_node(ctx: RunContext, state: RunState) -> RunState:
    return commit(ctx, state, "rules")


def commit_agent_node(ctx: RunContext, state: RunState) -> RunState:
    return commit(ctx, state, "agent")


def commit_review_node(ctx: RunContext, state: RunState) -> RunState:
    return commit(ctx, state, "review")


def commit(ctx: RunContext, state: RunState, stage: StageName) -> RunState:
    """Commit one stage's changes on a real run's branch, once (a no-op for dry runs)."""
    d = ctx.deps
    if d.worktree is None:
        return {}
    commits = [StageCommit.model_validate(c) for c in state.get("commits") or []]
    if any(c.stage == stage for c in commits):
        return {}
    title, body = commit_message(ctx, stage, state)
    made = commit_stage(d.worktree, run_id=state["run_id"], stage=stage, title=title, body=body)
    if made is None:
        d.say("Commit", f"{stage}: nothing changed, no commit")
        return {}
    d.say("Commit", f"{made.sha[:8]} {made.title} ({len(made.files)} files)")
    return {
        "commits": [*[c.model_dump(mode="json") for c in commits], made.model_dump(mode="json")]
    }


def commit_message(ctx: RunContext, stage: StageName, state: RunState) -> tuple[str, str]:
    migration = f"{ctx.deps.spec.from_} to {ctx.deps.spec.to}"
    if stage == "rules":
        return f"Migrate {migration}: Rules (codemods and dependency map)", rules_commit_body(
            RulesResult.model_validate(state["rules"])
        )
    report = ctx.report(state)
    if stage == "agent":
        fixed = [f for f in report.files if f.outcome == "Migrated by agent"]
        calls = [CallRecord.model_validate(c) for c in state.get("calls") or []]
        return (
            f"Migrate {migration}: repair agent fixes in {len(fixed)} files",
            agent_commit_body(report, calls),
        )
    return f"Migrate {migration}: changes made at Review", review_commit_body(report)


def rules_commit_body(rules: RulesResult) -> str:
    lines = ["The deterministic layer, no model: the migration spec's rule steps, in order.", ""]
    for step in rules.steps:
        if step.status == "skipped":
            continue
        label = step.kind if step.name == step.kind else f"{step.kind} {step.name}"
        lines.append(f"- {label}: {step.detail}")
    todos = len(rules.codemod_todos)
    lines += [
        "",
        f"Codemod TODOs left: {todos}" + (" (listed in the PR body)." if todos else "."),
    ]
    return "\n".join(lines)


def agent_commit_body(report: RepairReport, calls: list[CallRecord]) -> str:
    fixed = [f for f in report.files if f.outcome == "Migrated by agent"]
    lines = [
        "Fixed by the repair agent; each passed the narrow verify (type-check, lint on the",
        "file, related tests):",
        "",
    ]
    for f in fixed:
        models = ", ".join(dict.fromkeys(a.model for a in f.attempts))
        others = [p for p in f.touched if p != f.path]
        lines.append(
            f"- {f.path}: {len(f.attempts)} attempt{'s' if len(f.attempts) != 1 else ''} ({models})"
            + (f", also {', '.join(others)}" if others else "")
        )
    handed = [f for f in report.files if f.outcome == "Handed off"]
    if handed:
        lines += ["", "Handed off to Review (not in this commit):"]
        lines += [f"- {f.path}: {f.reason or 'handed off'}" for f in handed]
    unmigrated = [f for f in report.files if f.outcome == "Unmigrated"]
    if unmigrated:
        lines += ["", "Unmigrated:"] + [f"- {f.path}: {f.reason or ''}" for f in unmigrated]
    cost = sum(c.cost_usd for c in calls)
    lines += ["", f"{len(calls)} model calls, {usd(cost)}."]
    return "\n".join(lines)


def review_commit_body(report: RepairReport) -> str:
    lines = ["Decided by a human at Review:", ""]
    for f in report.files:
        if f.migrated_by_human:
            lines.append(f"- {f.path}: edited by a human; passes the narrow verify")
        elif f.review == "keep":
            lines.append(f"- {f.path}: the repair agent's patch kept; still handed off")
    reviewed = {f.path for f in report.files if f.migrated_by_human or f.review == "keep"}
    others = [p for p in report.human_changed if p not in reviewed]
    if others:
        lines += ["", "Also changed by the human: " + ", ".join(others)]
    return "\n".join(lines)
