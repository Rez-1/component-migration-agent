"""The Budget (#19): one Run's Cost caps, spend and Reservation, and its release."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import migrator.graph as graph
import migrator.verify.checker as checker
from migrator.cost import (
    Budget,
    CostCapError,
    Ledger,
    LedgerRow,
    Reservation,
    RunCaps,
    Usage,
    now_utc,
)
from migrator.migrations import MigrationSpec
from migrator.pipeline import PausedRun, RunResult, resume_run
from migrator.repair.records import RepairReport
from migrator.verify import VerifyResult
from tests.test_graph import GOOD, Recorder, configuration, run
from tests.test_recheck import BUILD, SPEC, TYPE, Graph, state

CAPS = RunCaps(run_usd=8.0, month_usd=10.0, reserve_attempt_usd=0.5, max_attempts=3)


def held_by_others(ledger: Ledger) -> float:
    """What the shared book holds for running runs, less what they have spent: a probe
    run with room for everything else is refused, and says what was left."""
    probe = Budget("probe", RunCaps(run_usd=2e6, month_usd=1e6, reserve_attempt_usd=1e6), ledger)
    out = probe.reserve(["x"])
    assert out is not None and not out.held
    return round(1e6 - ledger.month_spent() - float(out.available_usd), 2)


def spend(ledger: Ledger, run_id: str, usd: float) -> None:
    ledger.append(
        LedgerRow(at=now_utc(), run_id=run_id, model="m", requested_model="m", usage=Usage(),
                  cost_usd=usd)
    )  # fmt: skip


def test_reserve_then_top_up_then_release(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    budget = Budget("a", CAPS, ledger)
    first = budget.reserve(["x", "y"])  # 2 files x 3 attempts x $0.50
    assert first is not None and first.held and first.total_usd == 3.0
    assert budget.reserved_usd == 3.0 and held_by_others(ledger) == 3.0
    # The recheck tops up from the recorded Reservation (a new step, a new Budget).
    again = Budget("a", CAPS, ledger, reserved_usd=3.0).reserve(["z"])
    assert again is not None and again.held and (again.added_usd, again.total_usd) == (1.5, 4.5)
    assert held_by_others(ledger) == 4.5
    budget.release()
    assert held_by_others(ledger) == 0.0


def test_a_reservation_over_the_month_is_refused_and_holds_nothing(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    spend(ledger, "earlier", 6.0)  # the month counts other runs' spend
    budget = Budget("a", CAPS, ledger, reserved_usd=3.0)
    out = budget.reserve(["x"])  # $3 + $1.50 > $10 - $6
    assert out is not None and not out.held and out.available_usd == 4.0
    assert budget.reserved_usd == 3.0 and held_by_others(ledger) == 0.0
    # ... and other runs' Reservations.
    assert Budget("b", CAPS, ledger).reserve(["x", "y"]).held  # type: ignore[union-attr]
    out = Budget("a", CAPS, ledger).reserve(["x"])  # $1.50 > $10 - $6 - $3
    assert out is not None and not out.held and out.available_usd == 1.0
    Budget("b", CAPS, ledger).release()


def test_never_reserve_more_than_the_run_can_spend(tmp_path: Path) -> None:
    """Codecharta: 34 files x 3 attempts x $0.15 = $15.30, under an $8 run cap and a $2
    hard stop. The $2 stop would end the run first, so $2 is reserved and repair starts."""
    ledger = Ledger(tmp_path / "ledger.jsonl")
    caps = RunCaps(run_usd=8.0, month_usd=20.0, stop_usd=2.0, reserve_attempt_usd=0.15)
    out = Budget("a", caps, ledger).reserve([f"f{n}" for n in range(34)])
    assert out == Reservation(held=True, files=34, added_usd=15.3, total_usd=2.0, available_usd=8.0)
    assert held_by_others(ledger) == 2.0
    # Without a hard stop, the run cap: the recheck's top-up stops there too.
    out = Budget("a", CAPS, ledger, reserved_usd=6.0).reserve(["x", "y"])
    assert out is not None and out.held and out.total_usd == 8.0
    Budget("a", caps, ledger).release()


def test_no_reservation_without_a_reserve_per_attempt(tmp_path: Path) -> None:
    budget = Budget("a", RunCaps(run_usd=8.0, month_usd=10.0), Ledger(tmp_path / "l.jsonl"))
    assert budget.reserve(["x"]) is None


def test_each_call_is_checked_against_the_hard_stop(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    caps = CAPS.model_copy(update={"stop_usd": 2.0})
    worst = Budget("a", caps, ledger).check("claude-opus-5-5", 10_000, 16_000)
    with pytest.raises(CostCapError, match=r"\$2\.00 cap"):  # not the $8 run cap
        Budget("a", caps, ledger, spent_usd=2.0 - worst / 2).check(
            "claude-opus-5-5", 10_000, 16_000
        )


def test_resume_reserves_again_less_what_was_spent(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    spend(ledger, "a", 1.0)
    assert Budget("a", CAPS, ledger, spent_usd=1.0, reserved_usd=4.5).reopen()
    assert held_by_others(ledger) == 3.5  # $4.50 held, $1 of it already in the ledger
    Budget("a", CAPS, ledger).release()
    # A month with no room for the $3.50 still to come holds nothing.
    spend(ledger, "earlier", 6.0)
    assert not Budget("a", CAPS, ledger, spent_usd=1.0, reserved_usd=4.5).reopen()
    assert held_by_others(ledger) == 0.0


# --------------------------------------------------------------------------- the graph


class FirstPass(Graph):
    """test_recheck's graph, with what the first pass reads."""

    def untouched(self, state: Any) -> dict[str, str]:
        return self.after_rules(state)


def test_the_first_pass_reserves_its_queue_through_the_budget(tmp_path: Path) -> None:
    g = FirstPass(tmp_path)
    first = state([TYPE, SPEC], [], repair=RepairReport(enabled=True).model_dump(mode="json"))
    out = g.plan_repair_node(first)
    assert out["queue"] == ["src/app/list.component.ts", "src/app/search.component.ts"]
    report = RepairReport.model_validate(out["repair"])
    assert report.reserved_usd == 0.9 and not report.stopped_by_cost_cap  # 2 x 3 x $0.15
    assert held_by_others(g.d.ledger) == 0.9
    Budget("recheck-test", g.d.caps, g.d.ledger).release()
    # No room in the month: repair does not start, and every queued file ends not attempted.
    g = FirstPass(tmp_path)
    spend(g.d.ledger, "earlier", 49.5)
    out = g.plan_repair_node(first)
    report = RepairReport.model_validate(out["repair"])
    assert report.stopped_by_cost_cap and "so repair did not start" in str(report.cost_cap_reason)
    assert held_by_others(g.d.ledger) == 0.0
    ended = g.next_file_node({**first, **out})
    files = RepairReport.model_validate(ended["repair"]).files
    assert [f.reason for f in files] == ["cost cap: not attempted"] * 2


def test_the_recheck_tops_up_through_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        checker, "verify", lambda inp, runner: VerifyResult(commands=[], failures=[SPEC])
    )
    g = Graph(tmp_path)
    Budget("recheck-test", g.d.caps, g.d.ledger).reserve(["a", "b", "c"])  # the first $1.35
    g.recheck_node(state([BUILD, TYPE], []))
    assert held_by_others(g.d.ledger) == 1.8
    Budget("recheck-test", g.d.caps, g.d.ledger).release()


def test_a_run_that_crashes_leaves_no_reservation_behind(
    tmp_path: Path, spec: MigrationSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    seen: list[float] = []

    def crash(self: graph.RunGraph, state: Any) -> Any:
        seen.append(held_by_others(ledger))
        raise RuntimeError("the sandbox went away")

    monkeypatch.setattr(graph.RunGraph, "final_verify_node", crash)
    with pytest.raises(RuntimeError, match="sandbox"):
        run(tmp_path, spec, GOOD, config=configuration(reserve_attempt_usd=0.5))
    assert seen and seen[0] > 0  # the run held a Reservation when it crashed
    assert held_by_others(ledger) == 0.0


def test_a_paused_run_releases_and_its_resume_reserves_again(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    config = configuration(reserve_attempt_usd=0.5)
    paused, _, _, runner = run(
        tmp_path, spec, GOOD, config=config, reviewer=Recorder([None]), mode="cli"
    )
    assert isinstance(paused, PausedRun)
    assert held_by_others(ledger) == 0.0  # paused: nothing held while no one is running it

    class Probe(Recorder):
        def review(self, payload: Any) -> Any:
            seen.append(held_by_others(ledger))
            return super().review(payload)

    seen: list[float] = []
    done = resume_run(tmp_path / "run", reviewer=Probe(["revert"]), runner=runner, ledger=ledger)
    assert isinstance(done, RunResult)
    card = done.scorecard
    assert card.repair is not None
    reserved = card.repair.reserved_usd
    assert reserved and seen == [round(reserved - card.cost.total_usd, 2)]
    assert held_by_others(ledger) == 0.0
