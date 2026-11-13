"""The run's graph state, and which stage writes each key.

LangGraph checkpoints this dict after every node and a paused run resumes from it, so
its keys (and the node names in ``build.py``) are fixed: ``tests/test_graph_shape.py``
pins them. Values are small and JSON-friendly; large artifacts are files in the run
folder (``RunFiles``) and the state holds their paths.

Start of Repair: the workspace as Repair begins, meaning the codemods' changes plus the
Migrator's own snapshot updates. Rules saves it, and Verify saves it again when it
rewrote snapshots; everything after it is the agent's (or a human's) layer. On disk it
keeps its old name, ``state/after-rules.json``, so older runs still load.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.messages import BaseMessage

from migrator.verify import Failure


class RunState(TypedDict, total=False):
    """The run's graph state. Each comment names the nodes that write the key."""

    run_id: str  # initial_state
    run_dir: str  # initial_state
    workspace: str | None  # initial_state (a real run's worktree), precheck
    started_at: str  # initial_state
    visual_before: dict[str, Any] | None  # precheck: the before capture, or why there is none
    timings: dict[str, float]  # every timed node, through build.py's wrapper
    config: dict[str, Any]  # scan: the ResolvedRepoConfig (no node reads it back)
    usage_path: str  # scan
    node_version: str | None  # precheck
    npm_version: str | None  # precheck
    precheck: dict[str, Any]  # precheck: PrecheckResult
    rules: dict[str, Any] | None  # rules: RulesResult
    rules_done: bool  # rules
    verify: dict[str, Any] | None  # verify: the Verify after Rules
    # verify, recheck, tools, file_end, review: the latest known failures (Failure)
    known_failures: list[dict[str, Any]]
    file_start_failures: list[dict[str, Any]]  # start_file: known when this file began
    test_files: dict[str, str]  # plan_repair
    queue: list[str]  # plan_repair, next_file, recheck, start_file: files still to repair
    current: dict[str, Any] | None  # start_file, agent, tools, file_end: SessionState
    messages: list[BaseMessage]  # plan_repair, start_file, agent, tools, file_end
    # scan, plan_repair, next_file, recheck, agent, file_end, prepare_review, review:
    # the RepairReport, read once and written back once by each of them
    repair: dict[str, Any]
    calls: list[dict[str, Any]]  # scan, agent, file_end: CallRecord, one per model call
    review_queue: list[str]  # plan_repair, file_end, review
    review: dict[str, Any] | None  # prepare_review, review: the hand-off's ReviewPayload
    final: dict[str, Any] | None  # final_verify: the final Verify
    final_usage_path: str | None  # final_verify
    cheating: dict[str, Any] | None  # final_verify: CheatingReport
    scorecard_path: str | None  # report
    commits: list[dict[str, Any]]  # commit_rules, commit_agent, commit_review: StageCommit
    snapshot_updates: list[dict[str, Any]]  # verify, final_verify: SnapshotUpdate
    shared_causes: list[dict[str, Any]]  # plan_repair: SharedCause, one per definition
    rechecked: bool  # recheck: the full verify after a first pass no spec could run in


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def initial_state(run_id: str, run_dir: Path) -> RunState:
    return {"run_id": run_id, "run_dir": str(run_dir), "started_at": now(), "timings": {}}


def failures_of(rows: list[dict[str, Any]] | None) -> list[Failure]:
    """Failures from their state rows (``known_failures``, ``file_start_failures``)."""
    return [Failure.model_validate(r) for r in rows or []]


def dump_failures(failures: list[Failure]) -> list[dict[str, Any]]:
    return [f.model_dump(mode="json") for f in failures]
