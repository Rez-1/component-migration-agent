"""Review: one hand-off per pause (prepare review -> review, looped)."""

from __future__ import annotations

from functools import partial

from langgraph.types import interrupt

from migrator.repair.context import unified_diff
from migrator.repair.prompt import describe_failure
from migrator.repair.records import FileRepair, ReviewAnswer
from migrator.repair.tools import SessionState, failure_key
from migrator.review import ReviewPayload, apply_answer, changed_files, code_hashes
from migrator.run.context import RunContext
from migrator.run.files import slug
from migrator.run.state import RunState, dump_failures, failures_of
from migrator.verify import Failure


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
    workspace = ctx.workspace(state)
    report = ctx.report(state)
    record = report.record(payload.path)
    if record is None:
        raise RuntimeError(f"no repair record for {payload.path}")
    changed = changed_files(payload.hashes, code_hashes(workspace))
    report.human_changed += [rel for rel in changed if rel not in report.human_changed]
    narrow = partial(_narrow_verify, ctx, state, record)
    result = apply_answer(payload, answer, record, changed, narrow)
    start = ctx.files.start_of_repair() if result.revert else {}
    for rel in result.revert:
        if (before := record.originals.get(rel, start.get(rel))) is not None:
            (workspace / rel).write_text(before, "utf-8")
    report.files[report.files.index(record)] = result.record
    if result.note:
        ctx.deps.say("Review", result.note)
    queue = list(state.get("review_queue") or [])
    if result.done:
        queue.pop(0)
    known = result.known_failures
    if known is None:
        known = failures_of(state.get("known_failures"))
    return {
        "repair": report.model_dump(mode="json"),
        "review_queue": queue,
        "known_failures": dump_failures(known),
        "review": None,
    }


def _narrow_verify(
    ctx: RunContext, state: RunState, record: FileRepair, touched: list[str]
) -> tuple[list[Failure], list[Failure], list[Failure]]:
    """The narrow verify of a human's edit to ``record``'s file, over ``touched``."""
    path = record.path
    known = failures_of(state.get("known_failures"))
    session = ctx.repair_session(
        state,
        SessionState(
            path=path,
            baseline_keys=[failure_key(f) for f in known if f.file != path],
            record=record.model_copy(update={"touched": touched}),
        ),
    )
    left, elsewhere, _ran = session.narrow_verify(f"review-{slug(path)}")
    return left, elsewhere, session.known_failures
