"""The run graph's shape, pinned (#27, Q4 and Q15).

A paused run resumes from its checkpoint by node name, state key and edge, so a change
to any of them strands every run paused before it. The lists below were recorded from
the graph as it was before graph.py became the run package; change them only on purpose
(and say what happens to paused runs).
"""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph.state import CompiledStateGraph

from migrator.graph import RunGraph

NODES = [
    "__end__",
    "__start__",
    "agent",
    "commit_agent",
    "commit_review",
    "commit_rules",
    "file_end",
    "final_verify",
    "next_file",
    "plan_repair",
    "precheck",
    "prepare_review",
    "recheck",
    "report",
    "review",
    "rules",
    "scan",
    "start_file",
    "tools",
    "verify",
]

# (source, target, conditional)
EDGES = [
    ("__start__", "scan", False),
    ("agent", "file_end", True),
    ("agent", "tools", True),
    ("commit_agent", "prepare_review", False),
    ("commit_review", "final_verify", False),
    ("commit_rules", "verify", False),
    ("file_end", "next_file", False),
    ("final_verify", "report", False),
    ("next_file", "commit_agent", True),
    ("next_file", "recheck", True),
    ("next_file", "start_file", True),
    ("plan_repair", "next_file", False),
    ("precheck", "report", True),
    ("precheck", "rules", True),
    ("prepare_review", "commit_review", True),
    ("prepare_review", "review", True),
    ("recheck", "commit_agent", True),
    ("recheck", "start_file", True),
    ("report", "__end__", False),
    ("review", "prepare_review", False),
    ("rules", "commit_rules", True),
    ("rules", "report", True),
    ("scan", "precheck", False),
    ("start_file", "agent", True),
    ("start_file", "file_end", True),
    ("tools", "agent", True),
    ("tools", "file_end", True),
    ("verify", "plan_repair", False),
]

STATE_KEYS = [
    "calls",
    "cheating",
    "commits",
    "config",
    "current",
    "file_start_failures",
    "final",
    "final_usage_path",
    "known_failures",
    "messages",
    "node_version",
    "npm_version",
    "precheck",
    "queue",
    "rechecked",
    "repair",
    "review",
    "review_queue",
    "rules",
    "rules_done",
    "run_dir",
    "run_id",
    "scorecard_path",
    "shared_causes",
    "snapshot_updates",
    "started_at",
    "test_files",
    "timings",
    "usage_path",
    "verify",
    "visual_before",
    "workspace",
]


def compiled() -> CompiledStateGraph[Any, Any, Any, Any]:
    """The run graph, compiled without a checkpointer; building it runs no node."""
    return RunGraph(cast(Any, None)).build().compile()


def test_the_node_names_are_pinned() -> None:
    assert sorted(compiled().get_graph().nodes) == NODES


def test_the_edges_are_pinned() -> None:
    edges = compiled().get_graph().edges
    assert sorted((e.source, e.target, e.conditional) for e in edges) == EDGES


def test_the_state_keys_are_pinned() -> None:
    channels = set(compiled().channels)
    branches = {f"branch:to:{n}" for n in NODES if not n.startswith("__")}
    assert sorted(channels - branches - {"__pregel_tasks", "__start__"}) == STATE_KEYS
    assert branches <= channels  # every node's trigger channel, as checkpoints name it
