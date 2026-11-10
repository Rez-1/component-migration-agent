"""Speed-up 1 (M6): repeat runs in parallel, with the budget and reservations intact."""

from __future__ import annotations

import threading
from pathlib import Path

from migrator.cost import (
    Ledger,
    LedgerRow,
    PreflightResult,
    Usage,
    now_utc,
    release_run,
    reserve_run,
)
from migrator.evals import run_experiment
from migrator.execs import CommandRunner
from migrator.pipeline import RunOptions, RunResult
from migrator.report import ReportInput
from tests.test_evals import OPUS, FakeRuns, _plan
from tests.test_report import card_input  # noqa: F401


class OkPreflight:
    def check(self, plan: object) -> PreflightResult:
        return PreflightResult(ok=True, estimated_usd=0.0, reason="test")


class TogetherRuns(FakeRuns):
    """Every run waits at a barrier: the experiment only finishes if they run at once."""

    def __init__(self, base: ReportInput, outcomes: list[str], parties: int):
        super().__init__(base, outcomes)
        self.barrier = threading.Barrier(parties, timeout=10)
        self.lock = threading.Lock()

    def __call__(self, opts: RunOptions, runner: CommandRunner | None) -> RunResult:
        self.barrier.wait()  # raises BrokenBarrierError if the runs were sequential
        with self.lock:
            return super().__call__(opts, runner)


def test_repeat_runs_run_at_the_same_time_and_split_the_budget(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    runs = TogetherRuns(card_input, ["dirty", "dirty"], parties=2)
    out = run_experiment(
        _plan(tmp_path, OPUS, max_cost_usd=6.0, parallel=2), run=runs, preflight=OkPreflight()
    )
    assert (out.scored, out.errors) == (2, 0)
    # Each run of the group gets its share, so together they can't pass the budget.
    assert sorted(o.max_run_usd for o in runs.calls) == [3.0, 3.0]
    assert len({o.run_id for o in runs.calls}) == 2


def test_one_at_a_time_keeps_the_old_cap(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    runs = FakeRuns(card_input, ["dirty", "dirty"])
    run_experiment(
        _plan(tmp_path, OPUS, max_cost_usd=6.0, parallel=1), run=runs, preflight=OkPreflight()
    )
    assert [o.max_run_usd for o in runs.calls] == [5.0, 5.0]  # min(run cap, what's left)


def test_reservations_of_running_runs_count_against_the_month(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ok_a, _ = reserve_run("a", 6.0, 8.0, 10.0, ledger)
    ok_b, available = reserve_run("b", 6.0, 8.0, 10.0, ledger)
    assert ok_a and not ok_b and available == 4.0
    # What a run has spent counts once: in the ledger, not again in its reservation.
    ledger.append(
        LedgerRow(at=now_utc(), run_id="a", model="m", requested_model="m", usage=Usage(),
                  cost_usd=2.0)
    )  # fmt: skip
    assert reserve_run("b", 4.5, 8.0, 10.0, ledger)[0] is False  # 10 - 2 spent - 4 left of a
    release_run("a")
    assert reserve_run("b", 6.0, 8.0, 10.0, ledger)[0] is True  # 10 - 2 spent
    release_run("b")
