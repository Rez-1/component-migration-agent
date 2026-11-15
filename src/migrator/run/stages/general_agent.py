"""The general agent's stage (M8): Claude Code on the Pre-checked workspace, in place
of Rules, Repair and Review.

The Start of Repair is the untouched workspace, so every later change is the agent's
layer, codemods it chose to run included. The agent's cost goes into the ledger like
any model call, so the month cap counts it. When the agent changed package.json or the
lockfile, the Migrator's workspace is installed again in the sandbox (the agent's own
install was for this machine), then the run goes on to the same final Verify.
"""

from __future__ import annotations

from typing import Any

from migrator.cost import LedgerRow, now_utc
from migrator.general_agent import AgentRun, run_general_agent
from migrator.rules import ToolsError, ensure_tools
from migrator.run.context import RunContext
from migrator.run.state import RunState
from migrator.verify import install


class GeneralAgentState(RunState, total=False):
    """The run state of a general-agent run: the Migrator's keys, plus its record."""

    general_agent: dict[str, Any] | None  # general_agent: AgentRun


def general_agent_node(ctx: RunContext, state: GeneralAgentState) -> GeneralAgentState:
    d = ctx.deps
    settings = d.configuration.general_agent
    workspace = ctx.workspace(state)
    ctx.files.save_start_of_repair(ctx.files.untouched())
    spent = d.ledger.month_spent()
    # The per-run stop, never more than the run's cap (an experiment's --max-cost lowers it).
    budget = min(d.caps.stop_usd or d.caps.run_usd, d.caps.run_usd)
    if spent + budget > d.caps.month_usd:
        raise RuntimeError(
            f"the month cap (${d.caps.month_usd:.2f}) has ${d.caps.month_usd - spent:.2f} left, "
            f"less than this run's stop (${budget:.2f})"
        )
    try:
        tools = ensure_tools(d.spec, d.runner, d.tools_cache) if d.spec.tools else None
    except ToolsError as exc:
        raise RuntimeError(f"the pinned tools could not be installed: {exc}") from exc
    run = run_general_agent(
        settings=settings,
        spec=d.spec,
        config=d.config,
        workspace=workspace,
        run_id=state["run_id"],
        run_dir=ctx.files.folder,
        tools_dir=tools,
        budget_usd=budget,
        say=d.say,
    )
    calls = run.calls()
    for call in calls:
        d.ledger.append(
            LedgerRow(
                at=now_utc(),
                run_id=state["run_id"],
                case=d.case.id if d.case else None,
                model=call.model,
                requested_model=call.requested_model,
                usage=call.usage,
                cost_usd=call.cost_usd,
            )
        )
    (ctx.files.folder / "general-agent").mkdir(parents=True, exist_ok=True)
    (ctx.files.folder / "general-agent" / "run.json").write_text(
        run.model_dump_json(indent=2) + "\n", "utf-8"
    )
    if run.status != "ok":
        raise RuntimeError(f"the general agent did not run: {run.reason}")
    if run.agent is not None and not run.agent.audit.clean:
        found = run.agent.audit
        d.say(
            "General agent",
            f"AUDIT: {found.unsandboxed_requests} unsandboxed requests, file tools outside its "
            f"folder: {', '.join(found.outside_writes) or 'none'} (see general-agent/run.json)",
        )
    run = _reinstall(ctx, state, run)
    return {
        "general_agent": run.model_dump(mode="json"),
        "calls": [*(state.get("calls") or []), *(c.model_dump(mode="json") for c in calls)],
    }


def _reinstall(ctx: RunContext, state: GeneralAgentState, run: AgentRun) -> AgentRun:
    """Install the Migrator's workspace again when the agent changed its packages."""
    d = ctx.deps
    back = run.copied_back
    changed = set(back.all) if back else set()
    if not changed & {"package.json", d.config.lockfile}:
        return run
    workspace = ctx.workspace(state)
    frozen = d.config.lockfile in changed
    d.say("General agent", "the agent changed its packages: installing them again in the sandbox")
    log = ctx.files.logs / "general-agent-reinstall.log"
    result = install(d.runner, workspace, d.config, frozen=frozen, log_file=log)
    if not result.ok and frozen:
        # The agent left the lockfile out of step with package.json: update it, as
        # the Migrator's own install step does after changing package.json.
        result = install(d.runner, workspace, d.config, frozen=False, log_file=log)
    return run.model_copy(update={"reinstall": f"`{result.command}` exited {result.exit_code}"})
