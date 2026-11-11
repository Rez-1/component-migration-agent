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
from migrator.scoring import Evidence
from tests.test_evals import OPUS, FakeRuns, _plan
from tests.test_scoring import card_input  # noqa: F401


class OkPreflight:
    def check(self, plan: object) -> PreflightResult:
        return PreflightResult(ok=True, estimated_usd=0.0, reason="test")


class TogetherRuns(FakeRuns):
    """Every run waits at a barrier: the experiment only finishes if they run at once."""

    def __init__(self, base: Evidence, outcomes: list[str], parties: int):
        super().__init__(base, outcomes)
        self.barrier = threading.Barrier(parties, timeout=10)
        self.lock = threading.Lock()

    def __call__(self, opts: RunOptions, runner: CommandRunner | None) -> RunResult:
        self.barrier.wait()  # raises BrokenBarrierError if the runs were sequential
        with self.lock:
            return super().__call__(opts, runner)


def test_repeat_runs_run_at_the_same_time_and_split_the_budget(
    tmp_path: Path,
    card_input: Evidence,  # noqa: F811
) -> None:
    runs = TogetherRuns(card_input, ["dirty", "dirty"], parties=2)
    out = run_experiment(
        _plan(tmp_path, OPUS, max_cost_usd=6.0, parallel=2), run=runs, preflight=OkPreflight()
    )
    assert (out.scored, out.errors) == (2, 0)
    # Each run of the group gets its share, so together they can't pass the budget.
    assert [o.max_run_usd for o in runs.calls] == [3.0, 3.0]
    assert len({o.run_id for o in runs.calls}) == 2


def test_one_at_a_time_keeps_the_old_cap(
    tmp_path: Path,
    card_input: Evidence,  # noqa: F811
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


def test_a_cached_precheck_gives_the_same_scorecard_without_rerunning(
    tmp_path: Path, monkeypatch: object, spec: object
) -> None:
    """Speed-up 2: the second run clones the cached install and reuses the Pre-check."""
    import pytest

    from migrator.pipeline import start_run
    from migrator.scoring import stable_view
    from tests.conftest import FakeRunner
    from tests.fakes import FakeToolchain, ScriptedChatModel, factory_for, make_mini_repo
    from tests.test_graph import GOOD, configuration

    mp = pytest.MonkeyPatch()
    mp.setenv("MIGRATOR_CACHE_DIR", str(tmp_path / "cache"))
    try:
        repo = make_mini_repo(tmp_path / "repo")
        cards, commands = [], []
        for n in (1, 2):
            runner = FakeRunner(FakeToolchain())
            result = start_run(
                RunOptions.model_validate(
                    {
                        "repo": repo,
                        "spec": spec,
                        "run_dir": tmp_path / f"run{n}",
                        "configuration": configuration(),
                        "tools_cache": tmp_path / "tools",
                        "run_id": f"r{n}",
                        "precheck_cache": True,
                    }
                ),
                runner,
                model_factory=factory_for(ScriptedChatModel(script=GOOD)),
                ledger=Ledger(tmp_path / f"ledger{n}.jsonl"),
            )
            assert isinstance(result, RunResult)
            cards.append(stable_view(result.scorecard))
            commands.append(runner.commands)
        assert cards[0] == cards[1]
        first_install = commands[0].index(
            next(c for c in commands[0] if " ci" in c or "install" in c)
        )
        assert first_install >= 0
        # The second run's commands start after the Pre-check: no install before Rules.
        precheck_part = commands[1][
            : commands[1].index(next(c for c in commands[1] if "codemod" in c))
        ]
        assert not any("--version" in c or c.startswith("npm ci") for c in precheck_part)
        assert (tmp_path / "run2" / "logs" / "precheck-from-cache.json").is_file()
    finally:
        mp.undo()


def test_incremental_typecheck_flags_each_tsc_and_leaves_other_commands_alone() -> None:
    """Speed-up 5: each tsc gets --incremental and a build-info file of its own."""
    from migrator.verify import incremental_typecheck

    two = "node_modules/.bin/tsc -p ./ && node_modules/.bin/tsc --noEmit -p src/ElectronBackend"
    assert incremental_typecheck(two, two) == (
        "node_modules/.bin/tsc --incremental --tsBuildInfoFile .migrator/tsbuildinfo-1 -p ./ && "
        "node_modules/.bin/tsc --incremental --tsBuildInfoFile .migrator/tsbuildinfo-2 "
        "--noEmit -p src/ElectronBackend"
    )
    assert incremental_typecheck("npm run typecheck", "npm run typecheck tsc --noEmit") == (
        "npm run typecheck -- --incremental --tsBuildInfoFile .migrator/tsbuildinfo-1"
    )
    # A script that runs tsc twice, or no tsc at all, is left as it is.
    assert incremental_typecheck("yarn check", "yarn check tsc -p a && tsc -p b") == "yarn check"
    assert incremental_typecheck("yarn vue-tsc", "yarn vue-tsc vue-tsc --noEmit") == "yarn vue-tsc"
