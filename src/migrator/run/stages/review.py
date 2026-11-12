"""Review: one hand-off per pause (prepare review -> review, looped)."""

from __future__ import annotations

from pathlib import Path

from langgraph.types import interrupt

from migrator.checks import read_files
from migrator.repair.context import unified_diff
from migrator.repair.prompt import describe_failure
from migrator.repair.records import FileRepair, ReviewAnswer
from migrator.repair.tools import RepairSession, SessionState, failure_key
from migrator.review import ReviewPayload
from migrator.run.context import RunContext
from migrator.run.files import slug
from migrator.run.state import RunState, dump_failures, failures_of
from migrator.workspace import hash_file


def code_hashes(workspace: Path) -> dict[str, str]:
    """Hashes of the workspace's code files (the same set the cheating checks read)."""
    return {p: hash_file(workspace / p) for p in sorted(read_files(workspace))}


def prepare_review_node(ctx: RunContext, state: RunState) -> RunState:
    queue = list(state.get("review_queue") or [])
    if not queue:
        return {"review": None}
    path = queue[0]
    report = ctx.report(state)
    record = report.record(path) or FileRepair(path=path)
    workspace = ctx.workspace(state)
    after = ctx.files.start_of_repair()
    known = failures_of(state.get("known_failures"))
    failures = [describe_failure(f, path) for f in known if f.file == path]
    updates: RunState = {}
    if record.set_aside and not record.restored_for_review:
        # Put the patch back for the human to see (and edit); Revert removes it.
        for rel, text in record.set_aside.items():
            (workspace / rel).write_text(text, "utf-8")
        record.restored_for_review = True
        failures = record.failures_at_hand_off
        updates["repair"] = report.model_dump(mode="json")
    diff = "".join(
        unified_diff(rel, after.get(rel), (workspace / rel).read_text("utf-8"))
        for rel in record.touched
        if (workspace / rel).is_file()
    )
    attempts = [
        f"attempt {a.number} ({a.model}, {a.tool_calls} tool calls): {a.result or '—'}"
        + (f", {a.failures_left} failures left" if a.failures_left is not None else "")
        + (f' — "{a.note}"' if a.note else "")
        for a in record.attempts
    ]
    payload = ReviewPayload(
        path=path,
        reason=record.reason or "handed off",
        attempts=attempts,
        failures=failures,
        diff=diff,
        workspace=str(workspace),
        hashes=code_hashes(workspace),
        remaining=len(queue) - 1,
    )
    return {**updates, "review": payload.model_dump(mode="json")}


def route_prepare_review(ctx: RunContext, state: RunState) -> str:
    return "review" if state.get("review") else "commit_review"


def review_node(ctx: RunContext, state: RunState) -> RunState:
    # Nothing before interrupt(): on resume this node starts again from here.
    payload = ReviewPayload.model_validate(state["review"])
    answer = interrupt(payload.model_dump(mode="json"), response_schema=ReviewAnswer)
    if isinstance(answer, dict):
        answer = ReviewAnswer.model_validate(answer)
    d = ctx.deps
    workspace = ctx.workspace(state)
    report = ctx.report(state)
    record = report.record(payload.path)
    if record is None:
        raise RuntimeError(f"no repair record for {payload.path}")
    now = code_hashes(workspace)
    changed = sorted(
        p for p in now.keys() | payload.hashes.keys() if now.get(p) != payload.hashes.get(p)
    )
    for rel in changed:
        if rel not in report.human_changed:
            report.human_changed.append(rel)
    known = failures_of(state.get("known_failures"))
    queue = list(state.get("review_queue") or [])
    record.review = answer.choice
    updates: RunState = {}
    if answer.choice == "revert":
        after = ctx.files.start_of_repair()
        for rel in record.touched:
            if rel in changed:
                continue  # a human changed it while paused: theirs wins
            before = record.originals.get(rel, after.get(rel))
            if before is not None:
                (workspace / rel).write_text(before, "utf-8")
        record.touched = [rel for rel in record.touched if rel in changed]
        queue.pop(0)
    elif answer.choice == "keep":
        queue.pop(0)
    else:  # edit: the human changed files; check the file again with the narrow verify
        assert d.templates is not None and d.retriever is not None
        after_rules = ctx.files.start_of_repair()
        session = RepairSession(
            SessionState(
                path=payload.path,
                baseline_keys=[failure_key(f) for f in known if f.file != payload.path],
                record=record.model_copy(update={"touched": sorted({*record.touched, *changed})}),
            ),
            workspace=workspace,
            after_rules=after_rules,
            test_files=state.get("test_files") or {},
            known_failures=known,
            checker=ctx.checker(state, after_rules),
            templates=d.templates,
            retriever=d.retriever,
            link_base=d.spec.guide.link_base,
        )
        left, elsewhere, _ran = session.narrow_verify(f"review-{slug(payload.path)}")
        known = session.known_failures
        if not left and not elsewhere:
            record.migrated_by_human = True
            queue.pop(0)
            d.say("Review", f"{payload.path}: fixed by a human")
        else:
            d.say(
                "Review",
                f"{payload.path}: still {len(left) + len(elsewhere)} failures after the edit",
            )
    updates.update(
        {
            "repair": report.model_dump(mode="json"),
            "review_queue": queue,
            "known_failures": dump_failures(known),
            "review": None,
        }
    )
    return updates
