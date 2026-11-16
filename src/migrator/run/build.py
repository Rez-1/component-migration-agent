"""The run graph's wiring: its nodes, edges and routes, in run order.

    Scan -> Pre-check -> Rules -> commit_rules -> Verify -> plan_repair
         -> next_file -> start_file -> agent <-> tools -> file_end -> next_file ...
            (once, a recheck when the Verify after Rules ran no spec)
         -> commit_agent -> prepare_review <-> review (one interrupt per hand-off)
         -> commit_review -> final_verify -> Report

Each node is a plain function ``(ctx, state) -> changed keys`` in ``stages/``, bound
here to the run's RunContext; each route is one too. Timing is one wrapper, applied
here to the nodes that are timed. LangGraph checkpoints the state after every node, so
Rules runs once even across a pause and resume (the codemods are not idempotent), and
a paused run resumes by node name and state key: both are pinned by
``tests/test_graph_shape.py``.

Repair's limits are edges, not prompt text: an attempt ends when the agent calls
``run_verify`` (or at 15 tool calls, which hands the file off), a file gets at most its
configured attempts, and the cost cap ends Repair for every remaining file (they end
Unmigrated, and the run still goes through Review and Report, so there is always a
Scorecard). The commit nodes commit a real run's stage once (they look for their own
commit first) and pass a dry run through unchanged.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from langgraph.graph import END, START, StateGraph

from migrator.run.context import RunContext
from migrator.run.stages import (
    commits,
    file_loop,
    general_agent,
    prepare,
    queue,
    report,
    review,
    verify,
)
from migrator.run.state import RunState

RECURSION_LIMIT = 10_000

Node = Callable[[RunContext, RunState], RunState]
Route = Callable[[RunContext, RunState], str]


class BoundNode(Protocol):
    def __call__(self, state: RunState) -> RunState: ...


class BoundAgentNode(Protocol):
    def __call__(
        self, state: general_agent.GeneralAgentState
    ) -> general_agent.GeneralAgentState: ...


def _bind(ctx: RunContext, node: Node, timed: str | None = None) -> BoundNode:
    """``node`` over ``ctx``; with ``timed``, its wall time is added to that timing."""

    def run(state: RunState) -> RunState:
        t0 = time.monotonic()
        out = node(ctx, state)
        if timed is None or not out:  # a node that did nothing took no time
            return out
        timings = dict(state.get("timings") or {})
        timings[timed] = round(timings.get(timed, 0.0) + time.monotonic() - t0, 2)
        return {**out, "timings": timings}

    return run


def _route(ctx: RunContext, route: Route) -> Callable[[RunState], str]:
    def pick(state: RunState) -> str:
        return route(ctx, state)

    pick.__name__ = route.__name__  # the branch's name, as traces show it
    return pick


def build(ctx: RunContext) -> StateGraph[RunState]:
    g: StateGraph[RunState] = StateGraph(RunState)
    g.add_node("scan", _bind(ctx, prepare.scan_node, "scan"))
    g.add_node("precheck", _bind(ctx, prepare.precheck_node, "precheck"))
    g.add_node("rules", _bind(ctx, prepare.rules_node, "rules"))
    g.add_node("commit_rules", _bind(ctx, commits.commit_rules_node))
    g.add_node("verify", _bind(ctx, verify.verify_node, "verify"))
    g.add_node("plan_repair", _bind(ctx, queue.plan_repair_node))
    g.add_node("next_file", _bind(ctx, queue.next_file_node))
    g.add_node("recheck", _bind(ctx, queue.recheck_node, "recheck"))
    g.add_node("start_file", _bind(ctx, file_loop.start_file_node))
    g.add_node("agent", _bind(ctx, file_loop.agent_node, "repair"))
    g.add_node("tools", _bind(ctx, file_loop.tools_node, "repair"))
    g.add_node("file_end", _bind(ctx, file_loop.file_end_node))
    g.add_node("commit_agent", _bind(ctx, commits.commit_agent_node))
    g.add_node("prepare_review", _bind(ctx, review.prepare_review_node))
    g.add_node("review", _bind(ctx, review.review_node))
    g.add_node("commit_review", _bind(ctx, commits.commit_review_node))
    g.add_node("final_verify", _bind(ctx, verify.final_verify_node, "final_verify"))
    g.add_node("report", _bind(ctx, report.report_node))

    g.add_edge(START, "scan")
    g.add_edge("scan", "precheck")
    g.add_conditional_edges("precheck", _route(ctx, prepare.route_precheck), ["rules", "report"])
    g.add_conditional_edges("rules", _route(ctx, prepare.route_rules), ["commit_rules", "report"])
    g.add_edge("commit_rules", "verify")
    g.add_edge("verify", "plan_repair")
    g.add_edge("plan_repair", "next_file")
    g.add_conditional_edges(
        "next_file", _route(ctx, queue.route_next_file), ["start_file", "recheck", "commit_agent"]
    )
    g.add_conditional_edges(
        "recheck", _route(ctx, queue.route_recheck), ["start_file", "commit_agent"]
    )
    g.add_conditional_edges(
        "start_file", _route(ctx, file_loop.route_start_file), ["agent", "file_end"]
    )
    g.add_conditional_edges("agent", _route(ctx, file_loop.route_agent), ["tools", "file_end"])
    g.add_conditional_edges("tools", _route(ctx, file_loop.route_tools), ["agent", "file_end"])
    g.add_edge("file_end", "next_file")
    g.add_edge("commit_agent", "prepare_review")
    g.add_conditional_edges(
        "prepare_review", _route(ctx, review.route_prepare_review), ["review", "commit_review"]
    )
    g.add_edge("review", "prepare_review")
    g.add_edge("commit_review", "final_verify")
    g.add_edge("final_verify", "report")
    g.add_edge("report", END)
    return g


def build_general_agent(ctx: RunContext) -> StateGraph[general_agent.GeneralAgentState]:
    """M8's general agent in place of Rules, Repair and Review:

        Scan -> Pre-check -> general_agent -> final_verify -> Report

    The other nodes are the Migrator's own. A general-agent run never pauses (it is
    only run as a dry run in evals), so this graph's shape is not pinned for resume."""
    g: StateGraph[general_agent.GeneralAgentState] = StateGraph(general_agent.GeneralAgentState)
    g.add_node("scan", _bind_agent(ctx, prepare.scan_node, "scan"))
    g.add_node("precheck", _bind_agent(ctx, prepare.precheck_node, "precheck"))
    g.add_node(
        "general_agent",
        _bind_agent(ctx, general_agent.general_agent_node, "general_agent"),  # type: ignore[arg-type]
    )
    g.add_node("final_verify", _bind_agent(ctx, verify.final_verify_node, "final_verify"))
    g.add_node("report", _bind_agent(ctx, report.report_node))
    g.add_edge(START, "scan")
    g.add_edge("scan", "precheck")
    g.add_conditional_edges("precheck", _route(ctx, _after_precheck), ["general_agent", "report"])
    g.add_edge("general_agent", "final_verify")
    g.add_edge("final_verify", "report")
    g.add_edge("report", END)
    return g


def _bind_agent(ctx: RunContext, node: Node, timed: str | None = None) -> BoundAgentNode:
    """``_bind`` for the general agent's graph: LangGraph hands a node only the keys of
    the state type it is annotated with, and Report must see ``general_agent``."""
    inner = _bind(ctx, node, timed)

    def run(state: general_agent.GeneralAgentState) -> general_agent.GeneralAgentState:
        return inner(state)  # type: ignore[return-value]

    return run


def _after_precheck(_ctx: RunContext, state: RunState) -> str:
    pre = state.get("precheck") or {}
    return "general_agent" if pre.get("status") == "ok" else "report"


def builder_for(ctx: RunContext) -> StateGraph[RunState]:
    """The run's graph: the Migrator's, or the general agent's (M8)."""
    if ctx.deps.configuration.general_agent.enabled:
        return build_general_agent(ctx)  # type: ignore[return-value]
    return build(ctx)
