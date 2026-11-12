"""The repair queue: plan it, take the next file, and recheck (M7)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from migrator.checks import FileSet, find_test_files, import_graph, read_test_rules
from migrator.cost import Budget, Reservation, RunCaps
from migrator.repair.records import FileRepair, RepairReport
from migrator.repair.shared import SharedCause, find_shared_causes
from migrator.run.context import RunContext
from migrator.run.state import RunState, dump_failures, failures_of
from migrator.verify import VerifyResult


def not_attempted(report: RepairReport, paths: list[str]) -> None:
    """Files the cost cap left no room for: they end Unmigrated, untried."""
    for path in paths:
        report.files.append(
            FileRepair(path=path, outcome="Unmigrated", reason="cost cap: not attempted")
        )


def repair_order(failing: list[str], files: FileSet) -> list[str]:
    """Failing files in repair order: a file before the files that (transitively)
    import it; otherwise non-component modules (``.ts``: themes, utilities) before
    components (``.tsx``), then by path. A shared module such as ``theme.ts`` reaches
    many screens through the app shell, so fixing it first stops its failures being
    charged to (and handed off from) the screens' repairs."""
    importers = import_graph(files)
    reach: dict[str, set[str]] = {}

    def importers_of(path: str) -> set[str]:
        if path not in reach:
            seen: set[str] = set()
            stack = list(importers.get(path, ()))
            while stack:
                p = stack.pop()
                if p not in seen:
                    seen.add(p)
                    stack.extend(importers.get(p, ()))
            reach[path] = seen
        return reach[path]

    remaining = sorted(failing, key=lambda p: (p.endswith((".tsx", ".jsx")), p))
    ordered: list[str] = []
    while remaining:
        for p in remaining:
            # p can go now unless another remaining file is imported by p (directly or not)
            if not any(p in importers_of(q) for q in remaining if q != p):
                ordered.append(p)
                remaining.remove(p)
                break
        else:  # an import cycle: take the first in the tie order
            ordered.append(remaining.pop(0))
    return ordered


@dataclass(frozen=True)
class ReservationOutcome:
    """What reserving a queue's worst case came to. ``unreserved``: the caps set no
    reserve per attempt (or there is nothing to repair), so nothing is held."""

    status: Literal["unreserved", "held", "refused"]
    reservation: Reservation | None = None


def reserve_queue(budget: Budget, order: list[str], tests: Mapping[str, str]) -> ReservationOutcome:
    """Reserve the worst case of repairing ``order`` before its first call (M6: runs
    must finish). Failing test files are handed off without a model call, so they cost
    nothing. The first pass and the recheck's top-up share the run's caps."""
    held = budget.reserve([p for p in order if p not in tests]) if order else None
    if held is None:
        return ReservationOutcome("unreserved")
    return ReservationOutcome("held" if held.held else "refused", held)


def plan_repair_node(ctx: RunContext, state: RunState) -> RunState:
    result = VerifyResult.model_validate(state["verify"])
    after = ctx.files.start_of_repair()
    tests = find_test_files(
        ctx.files.untouched(), after.keys(), read_test_rules(ctx.workspace(state))
    )
    if not ctx.deps.repair_on:
        return {"test_files": tests, "queue": [], "review_queue": []}
    order, causes = _order(ctx, result, after, tests)
    updates: RunState = {
        "test_files": tests,
        "queue": order,
        "review_queue": [],
        "messages": [],
        "shared_causes": [c.model_dump(mode="json") for c in causes],
    }
    held = reserve_queue(ctx.budget(state), order, tests).reservation
    if held is not None:
        report = ctx.report(state)
        report.reserved_usd = held.total_usd
        if held.held:
            ctx.deps.say("Repair", _reserved(held))
        else:
            report.stopped_by_cost_cap = True
            report.cost_cap_reason = _repair_did_not_start(held, ctx.deps.caps)
            ctx.deps.say("Repair", report.cost_cap_reason)
        updates["repair"] = report.model_dump(mode="json")
    return updates


def _order(
    ctx: RunContext, result: VerifyResult, after: FileSet, tests: dict[str, str]
) -> tuple[list[str], list[SharedCause]]:
    """The failing files in repair order, a shared cause's definition first (M6)."""
    d = ctx.deps
    order = repair_order([p for p in result.failing_files() if p in after], after)
    causes: list[SharedCause] = []
    if d.configuration.repair.shared_causes:
        causes = find_shared_causes(result.failures, after, tests)
        sources = [c.source for c in causes if c.source in after]
        order = [*dict.fromkeys(sources), *[p for p in order if p not in sources]]
        for c in causes:
            d.say(
                "Repair",
                f"shared cause: {c.code} on {c.symbol} from {c.source} in "
                f"{len(c.callers)} files; repairing {c.source} first",
            )
    d.say("Repair", f"{len(order)} failing files to repair: {', '.join(order) or 'none'}")
    return order, causes


def _reserved(held: Reservation) -> str:
    return f"reserved ${held.total_usd:.2f} of ${held.available_usd:.2f} available"


def _repair_did_not_start(held: Reservation, caps: RunCaps) -> str:
    capped = (
        f", ${held.total_usd:.2f} at most, what the run can spend"
        if held.total_usd < held.added_usd
        else ""
    )
    return (
        f"the worst case ({held.files} files x {caps.max_attempts} attempts x "
        f"${caps.reserve_attempt_usd:.2f} = ${held.added_usd:.2f}{capped}) is more "
        f"than the ${held.available_usd:.2f} available (run cap "
        f"${caps.run_usd:.2f}, less what this month and other running runs have "
        "spent or reserved), so repair did not start"
    )


def next_file_node(ctx: RunContext, state: RunState) -> RunState:
    report = ctx.report(state)
    queue = list(state.get("queue") or [])
    if report.stopped_by_cost_cap and queue:
        not_attempted(report, queue)
        ctx.deps.say("Repair", f"cost cap: {len(queue)} files not attempted")
        return {"queue": [], "repair": report.model_dump(mode="json")}
    if ctx.deps.configuration.repair.shared_causes and queue:
        # After a shared definition was repaired, only callers that still fail stay.
        known = {f.file for f in failures_of(state.get("known_failures"))}
        sources = {c["source"] for c in state.get("shared_causes") or []}
        kept = [p for p in queue if p in known or p in sources]
        if kept != queue:
            gone = [p for p in queue if p not in kept]
            ctx.deps.say("Repair", f"no longer failing, skipped: {', '.join(gone)}")
            return {"queue": kept}
    return {}


def route_next_file(ctx: RunContext, state: RunState) -> str:
    if needs_recheck(ctx, state):
        return "recheck"
    return "start_file" if state.get("queue") else "commit_agent"


def needs_recheck(ctx: RunContext, state: RunState) -> bool:
    """The Verify after Rules ran no spec (a Karma bundle that didn't compile hides
    every test) and repair changed something: check the whole project once more, as
    soon as the type-check is clean (the bundle compiles, so the specs run), or when
    the queue is done. Before that, a spec that fails only because it never ran
    would be charged to the next file's patch as a new failure."""
    if state.get("rechecked") or not ctx.deps.repair_on or not state.get("verify"):
        return False
    first = VerifyResult.model_validate(state["verify"])
    if not any(f.ran_no_spec for f in first.failures):
        return False
    report = ctx.report(state)
    if report.stopped_by_cost_cap or not any(f.touched for f in report.files):
        return False
    known = failures_of(state.get("known_failures"))
    return not state.get("queue") or not any(f.source == "typecheck" for f in known)


def recheck_node(ctx: RunContext, state: RunState) -> RunState:
    """M7: the failures the first Verify couldn't see. Files that fail only now join
    the queue for one more pass; the worst case is reserved first, like the first."""
    d = ctx.deps
    d.say("Verify", "recheck: the first verify ran no spec; type-check, lint, tests")
    result = ctx.checker(state).check("recheck")
    report = ctx.report(state)
    tried = {f.path for f in report.files}
    after = ctx.files.start_of_repair()
    failing = set(result.failing_files())
    queued = list(state.get("queue") or [])
    kept = [p for p in queued if p in failing]  # a queued file may pass by now
    new = [p for p in sorted(failing) if p in after and p not in tried and p not in kept]
    updates: RunState = {
        "rechecked": True,
        "known_failures": dump_failures(result.failures),
        "queue": kept,
    }
    if gone := [p for p in queued if p not in kept]:
        d.say("Repair", f"recheck: no longer failing, skipped: {', '.join(gone)}")
    if not new:
        d.say("Repair", "recheck: no new failing files")
        return updates
    order = repair_order(new, after)
    # The top-up stays under the same run cap as the first pass's Reservation.
    out = reserve_queue(ctx.budget(state), order, state.get("test_files") or {})
    if out.status == "refused" and (held := out.reservation) is not None:
        d.say(
            "Repair",
            f"recheck: {len(order)} new failing files, but the worst case "
            f"(${held.total_usd:.2f} in all) is more than the "
            f"${held.available_usd:.2f} available; not attempted",
        )
        not_attempted(report, order)
        updates["repair"] = report.model_dump(mode="json")
        return updates
    if out.status == "held" and out.reservation is not None:
        report.reserved_usd = out.reservation.total_usd
        updates["repair"] = report.model_dump(mode="json")
    d.say("Repair", f"recheck: {len(order)} new failing files: {', '.join(order)}")
    updates["queue"] = [*kept, *order]
    return updates


def route_recheck(ctx: RunContext, state: RunState) -> str:
    return "start_file" if state.get("queue") else "commit_agent"
