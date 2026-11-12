"""One failing file's repair: start file -> agent <-> tools -> file end."""

from __future__ import annotations

import re
from functools import partial
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolCall, ToolMessage

from migrator.checks import FileSet
from migrator.cost import CallRecord, CostCapError
from migrator.repair.context import local_imports
from migrator.repair.outcome import EndPolicy, FileFailures, RepairWorkspace, end_file
from migrator.repair.prompt import first_message, system_prompt
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
from migrator.repair.tools import RepairSession, RepairTools, SessionState, failure_key
from migrator.run.context import RunContext
from migrator.run.state import RunState, dump_failures, failures_of
from migrator.scan import UsageReport

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
    session = ctx.repair_session(state, SessionState.model_validate(state["current"]))
    messages = list(state.get("messages") or [])
    last = messages[-1] if messages else None
    calls = last.tool_calls if isinstance(last, AIMessage) else []
    with ctx.tools_for(session) as tools:
        new = run_tool_calls(ctx, session, tools, calls)
    return {
        "current": session.state.model_dump(mode="json"),
        "messages": [*messages, *new],
        "known_failures": dump_failures(session.known_failures),
    }


def run_tool_calls(
    ctx: RunContext, session: RepairSession, tools: RepairTools, calls: list[ToolCall]
) -> list[BaseMessage]:
    """The model's tool calls, one at a time, and their results. Calls after the
    file's repair ended are not run; the tool-call budget hands the file off."""
    file = session.state
    new: list[BaseMessage] = []
    if not calls:
        # No tool call (text only, or cut off): nudge, and count it against the budget.
        file.tool_calls += 1
        session.current_attempt.tool_calls += 1
        new.append(HumanMessage(content=NUDGE))
    for call in calls:
        if file.ended is not None:
            new.append(
                ToolMessage(
                    content="Not run: this file's repair has ended.",
                    tool_call_id=call["id"] or "",
                    name=call["name"],
                    status="error",
                )
            )
            continue
        attempt_before = file.attempt
        file.tool_calls += 1
        session.current_attempt.tool_calls += 1
        new.append(tools.invoke(call))
        if file.ended is None and file.attempt != attempt_before:
            # run_verify failed and a new attempt starts: later calls are its own
            session.record.attempts.append(
                AttemptRecord(number=file.attempt, model=attempt_model(ctx, file.attempt))
            )
    if file.ended is None and file.tool_calls >= MAX_TOOL_CALLS:
        session.hand_off(
            f"tool-call budget used: {MAX_TOOL_CALLS} calls in attempt "
            f"{file.attempt} without passing run_verify"
        )
    return new


def route_tools(ctx: RunContext, state: RunState) -> str:
    current = state.get("current") or {}
    return "file_end" if current.get("ended") else "agent"


def review_flagged(
    ctx: RunContext,
    state: RunState,
    start: FileSet,
    record: FileRepair,
    flagged: str,
    model: str,
) -> Review | None:
    """The test-fitting reviewer on one flagged patch (M6 option D); None when its
    call doesn't fit the caps or fails (the flag then decides, as without it)."""
    d = ctx.deps
    workspace = ctx.workspace(state)
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
        record.path, patch_diff(record.touched, start, current), lines, failures, tests, guide
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
    start = ctx.files.start_of_repair()
    workspace = ctx.workspace(state)
    out = end_file(
        SessionState.model_validate(state["current"]),
        FileFailures(
            at_start=failures_of(state.get("file_start_failures")),
            now=failures_of(state.get("known_failures")),
        ),
        RepairWorkspace(workspace, start),
        EndPolicy(
            cheating_hand_off=d.mode == "cli",
            test_fitting_hand_off=d.configuration.repair.test_fitting_hand_off,
            reviewer_model=d.configuration.repair.reviewer_model,
        ),
        partial(review_flagged, ctx, state, start),
    )
    for rel, text in out.roll_back.items():
        (workspace / rel).write_text(text, "utf-8")
    record = out.record
    if messages := list(state.get("messages") or []):
        record.conversation = ctx.files.save_conversation(record.path, messages)
    report = ctx.report(state)
    report.files.append(record)
    review_queue = list(state.get("review_queue") or [])
    if out.handed_off:
        review_queue.append(record.path)
        report.review_list.append(record.path)
    for note in out.notes:
        d.say("Repair", note)
    reason = f" ({record.reason})" if record.reason else ""
    d.say("Repair", f"{record.path}: {record.outcome}{reason}")
    updates: RunState = {
        "current": None,
        "messages": [],
        "repair": report.model_dump(mode="json"),
        "review_queue": review_queue,
    }
    if out.restart_failures:
        updates["known_failures"] = state.get("file_start_failures") or []
    if out.review_call is not None:
        updates["calls"] = [*(state.get("calls") or []), out.review_call.model_dump(mode="json")]
    return updates
