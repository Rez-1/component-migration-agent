"""One failing file's repair: start file -> agent <-> tools -> file end."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from migrator.cost import CallRecord, CostCapError
from migrator.repair.context import local_imports
from migrator.repair.guardrails import added_escape_hatches
from migrator.repair.prompt import describe_failure, first_message, system_prompt
from migrator.repair.records import AttemptRecord, FileRepair
from migrator.repair.retriever import render_section
from migrator.repair.reviewer import (
    Review,
    failing_tests_of,
    patch_diff,
    read_tests,
    review_patch,
    review_prompt,
)
from migrator.repair.reviewer import default_model as default_review_model
from migrator.repair.shared import SharedCause, shared_cause_section
from migrator.repair.tools import RepairSession, SessionState, failure_key
from migrator.review_aids import test_fitting_flags
from migrator.run.context import RunContext
from migrator.run.state import RunState, dump_failures, failures_of
from migrator.scan import UsageReport
from migrator.verify import Failure

MAX_TOOL_CALLS = 15
NUDGE = (
    "Your reply had no tool call. End this attempt with `run_verify` (with a one-line "
    "note), or call `hand_off` if a human must make this fix."
)


def attempt_model(ctx: RunContext, attempt: int) -> str:
    models = ctx.deps.configuration.repair.attempt_models
    return models[min(attempt, len(models)) - 1]


def start_file_node(ctx: RunContext, state: RunState) -> RunState:
    d = ctx.deps
    assert d.templates is not None and d.retriever is not None
    queue = list(state.get("queue") or [])
    path = queue.pop(0)
    workspace = ctx.workspace(state)
    after = ctx.files.start_of_repair()
    tests = state.get("test_files") or {}
    known = failures_of(state.get("known_failures"))
    mine = [f for f in known if f.file == path]
    causes = [SharedCause.model_validate(c) for c in state.get("shared_causes") or []]
    owned = [c for c in causes if c.source == path]
    calling = [c for c in causes if path in c.callers and c.source != path]
    target_keys: list[tuple[str, str]] = []
    for c in owned:
        still = [f for f in known if (f.file, f.code) in c.failure_keys()]
        mine += [f for f in still if f not in mine]
        target_keys += [(str(f.file), str(f.code)) for f in still]
    first_model = d.configuration.repair.attempt_models[0]
    record = FileRepair(path=path, attempts=[AttemptRecord(number=1, model=first_model)])
    session = SessionState(
        path=path,
        max_attempts=d.configuration.repair.max_attempts,
        allowed_imports=[p for p in local_imports(path, after) if p not in tests],
        baseline_keys=[failure_key(f) for f in known],
        record=record,
        target_keys=sorted(set(target_keys)),
    )
    d.say("Repair", f"{path}: {len(mine)} failures")
    if path in tests:
        session.ended = "handed_off"
        record.outcome = "Handed off"
        record.reason = (
            f"the failure is in a Test file ({tests[path]}), which only a human may change"
        )
        record.attempts = []
        return {
            "queue": queue,
            "current": session.model_dump(mode="json"),
            "messages": [],
            "file_start_failures": state.get("known_failures") or [],
        }
    usage = UsageReport.model_validate_json(Path(state["usage_path"]).read_text("utf-8"))
    file_usages = usage.file(path)
    symbols = [u.symbol.split(".")[0] for u in file_usages.old_usages] if file_usages else []
    text = first_message(
        d.templates,
        d.spec,
        d.retriever,
        path=path,
        max_attempts=session.max_attempts,
        failures=mine,
        untouched=ctx.files.untouched().get(path),
        after_rules=(workspace / path).read_text("utf-8"),
        files={
            **after,
            **{p: (workspace / p).read_text("utf-8") for p in after if (workspace / p).is_file()},
        },
        test_files=tests,
        symbols=list(dict.fromkeys(s for s in symbols if s != "*")),
    )
    if owned or calling:
        sections = [shared_cause_section(c, path) for c in [*owned, *calling]]
        text += "\n\n### Shared cause\n\n" + "\n\n".join(sections)
    return {
        "queue": queue,
        "current": session.model_dump(mode="json"),
        "messages": [HumanMessage(content=text)],
        "file_start_failures": state.get("known_failures") or [],
    }


def route_start_file(ctx: RunContext, state: RunState) -> str:
    current = state.get("current") or {}
    return "file_end" if current.get("ended") else "agent"


def agent_node(ctx: RunContext, state: RunState) -> RunState:
    d = ctx.deps
    assert d.model is not None and d.templates is not None
    session = SessionState.model_validate(state["current"])
    report = ctx.report(state)
    calls = [CallRecord.model_validate(c) for c in state.get("calls") or []]
    model = attempt_model(ctx, session.attempt)
    record = session.record
    if not record.attempts or record.attempts[-1].number != session.attempt:
        record.attempts.append(AttemptRecord(number=session.attempt, model=model))
    system = system_prompt(d.templates, d.spec, max_attempts=session.max_attempts)
    messages = list(state.get("messages") or [])
    try:
        message, call = d.model.call(
            model,
            system,
            messages,
            budget=ctx.budget(state),
            file=session.path,
            attempt=session.attempt,
        )
    except CostCapError as exc:
        session.ended = "cost_cap"
        record.outcome = "Unmigrated"
        record.reason = f"cost cap: {exc}"
        record.attempts[-1].result = "cost_cap"
        report.stopped_by_cost_cap = True
        report.cost_cap_reason = str(exc)
        d.say("Repair", f"cost cap reached: {exc}")
        return {
            "current": session.model_dump(mode="json"),
            "repair": report.model_dump(mode="json"),
        }
    record.attempts[-1].stop_reason = call.stop_reason
    if call.stop_reason == "refusal":
        session.ended = "handed_off"
        record.outcome = "Handed off"
        record.reason = "the model declined the request (refusal)"
        record.attempts[-1].result = "handed_off"
    return {
        "current": session.model_dump(mode="json"),
        "messages": [*messages, message],
        "calls": [*[c.model_dump(mode="json") for c in calls], call.model_dump(mode="json")],
    }


def route_agent(ctx: RunContext, state: RunState) -> str:
    current = state.get("current") or {}
    return "file_end" if current.get("ended") else "tools"


def tools_node(ctx: RunContext, state: RunState) -> RunState:
    d = ctx.deps
    assert d.tools is not None and d.templates is not None and d.retriever is not None
    session_state = SessionState.model_validate(state["current"])
    messages = list(state.get("messages") or [])
    last = messages[-1] if messages else None
    known = failures_of(state.get("known_failures"))
    after = ctx.files.start_of_repair()
    session = RepairSession(
        session_state,
        workspace=ctx.workspace(state),
        after_rules=after,
        test_files=state.get("test_files") or {},
        known_failures=known,
        checker=ctx.checker(state, after),
        templates=d.templates,
        retriever=d.retriever,
        link_base=d.spec.guide.link_base,
    )
    d.tools.session = session
    new: list[BaseMessage] = []
    try:
        calls = last.tool_calls if isinstance(last, AIMessage) else []
        if not calls:
            # No tool call (text only, or cut off): nudge, and count it against the budget.
            session_state.tool_calls += 1
            session.current_attempt.tool_calls += 1
            new.append(HumanMessage(content=NUDGE))
        for call in calls:
            if session_state.ended is not None:
                new.append(
                    ToolMessage(
                        content="Not run: this file's repair has ended.",
                        tool_call_id=call["id"] or "",
                        name=call["name"],
                        status="error",
                    )
                )
                continue
            attempt_before = session_state.attempt
            session_state.tool_calls += 1
            session.current_attempt.tool_calls += 1
            new.append(d.tools.invoke(call))
            if session_state.ended is None and session_state.attempt != attempt_before:
                # run_verify failed and a new attempt starts: later calls are its own
                session.record.attempts.append(
                    AttemptRecord(
                        number=session_state.attempt,
                        model=attempt_model(ctx, session_state.attempt),
                    )
                )
        if session_state.ended is None and session_state.tool_calls >= MAX_TOOL_CALLS:
            session.hand_off(
                f"tool-call budget used: {MAX_TOOL_CALLS} calls in attempt "
                f"{session_state.attempt} without passing run_verify"
            )
    finally:
        d.tools.session = None
    return {
        "current": session_state.model_dump(mode="json"),
        "messages": [*messages, *new],
        "known_failures": dump_failures(session.known_failures),
    }


def route_tools(ctx: RunContext, state: RunState) -> str:
    current = state.get("current") or {}
    return "file_end" if current.get("ended") else "agent"


def review_flagged(
    ctx: RunContext, state: RunState, record: FileRepair, flagged: str, model: str
) -> Review | None:
    """The test-fitting reviewer on one flagged patch (M6 option D); None when its
    call doesn't fit the caps or fails (the flag then decides, as without it)."""
    d = ctx.deps
    workspace = ctx.workspace(state)
    after = ctx.files.start_of_repair()
    current = {rel: (workspace / rel).read_text("utf-8") for rel in record.touched}
    failures = failing_tests_of(record.path, failures_of(state.get("file_start_failures")))
    tests = read_tests(workspace, failures)
    lines = flagged.removeprefix("possible test-fitting: ").split("; ")
    query = " ".join([*re.findall(r"[A-Z][A-Za-z]+|aria-\w+|describeChild", " ".join(lines))])
    guide = (
        [render_section(doc, d.spec.guide.link_base) for doc in d.retriever.rank(query, k=2)]
        if d.retriever is not None and query
        else []
    )
    prompt = review_prompt(
        record.path, patch_diff(record.touched, after, current), lines, failures, tests, guide
    )
    try:
        return review_patch(
            prompt,
            model=model,
            budget=ctx.budget(state),
            case=d.case.id if d.case else None,
            path=record.path,
            factory=d.reviewer_factory or default_review_model,
        )
    except Exception as exc:  # the flag still decides: a hand-off
        d.say("Repair", f"{record.path}: the reviewer could not answer ({exc})")
        return None


def file_end_node(ctx: RunContext, state: RunState) -> RunState:
    d = ctx.deps
    session = SessionState.model_validate(state["current"])
    record = session.record
    report = ctx.report(state)
    workspace = ctx.workspace(state)
    review_queue = list(state.get("review_queue") or [])
    updates: RunState = {}
    if session.ended == "cost_cap":
        # No half-done patch lands: put the file back as this repair found it.
        for rel, text in session.originals.items():
            (workspace / rel).write_text(text, "utf-8")
        record.touched = []
        record.patch_lines = {}
        updates["known_failures"] = state.get("file_start_failures") or []
    elif session.ended == "passed" and d.mode == "cli":
        after = ctx.files.start_of_repair()
        hits = [
            f"{rel}: {', '.join(found)}"
            for rel in record.touched
            if (
                found := added_escape_hatches(
                    rel, after.get(rel, ""), (workspace / rel).read_text("utf-8")
                )
            )
        ]
        if hits:  # in real use a cheating-check hit is a hand-off, not a migrated file
            record.outcome = "Handed off"
            record.reason = "cheating check: " + "; ".join(hits)
    if (
        session.ended == "passed"
        and record.outcome == "Migrated by agent"
        and d.configuration.repair.test_fitting_hand_off
    ):
        # M6: a passing patch that changes what a failing test looks at (accessibility
        # props, the rendered element) goes to a human instead of counting as migrated.
        why = test_fitting_reason(
            record.path,
            record.touched,
            ctx.files.start_of_repair(),
            {rel: (workspace / rel).read_text("utf-8") for rel in record.touched},
            failures_of(state.get("file_start_failures")),
        )
        reviewer = d.configuration.repair.reviewer_model
        if why is not None and reviewer is not None:
            review = review_flagged(ctx, state, record, why, reviewer)
            if review is not None:
                updates["calls"] = [
                    *(state.get("calls") or []),
                    review.call.model_dump(mode="json"),
                ]
                record.reviewed_by = review.model
                record.review_verdict = review.verdict
                record.review_reason = review.reason
                if review.verdict == "v5_required":
                    d.say("Repair", f"{record.path}: flagged, reviewed as v5_required")
                    why = None  # stays migrated; the review is a note for a human
        if why is not None:
            record.outcome = "Handed off"
            record.test_fitting_hand_off = True
            record.reason = why + (
                f" (reviewed by {record.reviewed_by}: {record.review_reason})"
                if record.reviewed_by
                else ""
            )
    if record.outcome == "Handed off":
        review_queue.append(record.path)
        report.review_list.append(record.path)
        if session.originals:
            # Set the patch aside until Review: the next files are repaired in a
            # workspace without it (a broken patch must not fail their tests).
            known = failures_of(state.get("known_failures"))
            record.failures_at_hand_off = [
                describe_failure(f, record.path) for f in known if f.file == record.path
            ]
            record.originals = dict(session.originals)
            record.set_aside = {
                rel: (workspace / rel).read_text("utf-8") for rel in session.originals
            }
            for rel, text in session.originals.items():
                (workspace / rel).write_text(text, "utf-8")
            updates["known_failures"] = state.get("file_start_failures") or []
    messages = list(state.get("messages") or [])
    if messages:
        record.conversation = ctx.files.save_conversation(record.path, messages)
    report.files.append(record)
    d.say(
        "Repair",
        f"{record.path}: {record.outcome}" + (f" ({record.reason})" if record.reason else ""),
    )
    return {
        **updates,
        "current": None,
        "messages": [],
        "repair": report.model_dump(mode="json"),
        "review_queue": review_queue,
    }


def test_fitting_reason(
    path: str,
    touched: list[str],
    after_rules: Mapping[str, str],
    current: Mapping[str, str],
    start_failures: list[Failure],
) -> str | None:
    """The hand-off reason when a passing patch for a file that failed a test changed
    accessibility props or the rendered element (M6), else None."""
    flags = test_fitting_flags(
        dict(after_rules),
        dict(current),
        [(path, touched)],
        {f.file for f in start_failures if f.source == "test" and f.file},
    )
    if not flags:
        return None
    return "possible test-fitting: " + "; ".join(
        f"{fl.file}: {', '.join(fl.lines[:3])}" for fl in flags
    )
