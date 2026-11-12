"""M7: a Karma bundle that didn't compile hides every spec, so the failures it hid are
checked once more after repair, and the files that fail only then get a pass."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import migrator.verify.checker as checker
from migrator.checks import read_files
from migrator.config import VerifyCommands
from migrator.cost import Budget, Ledger, LedgerRow, Reservation, RunCaps, Usage, now_utc
from migrator.repair.records import FileRepair, RepairReport
from migrator.run.context import RunContext
from migrator.run.stages import queue
from migrator.run.state import RunState
from migrator.verify import VerifyResult
from migrator.verify.parsers import Failure

BUILD = Failure(source="test", file=None, message="no spec ran", test_name="(build)")
TYPE = Failure(source="typecheck", file="src/app/list.component.ts", message="TS2322")
SPEC = Failure(
    source="test",
    file="src/app/search.component.ts",
    message="Expected undefined",
    test_file="src/app/search.component.spec.ts",
    test_name="labels the field",
)


class Graph(RunContext):
    """The run context with its file-system helpers replaced."""

    def __init__(self, tmp: Path, reserve: float | None = 0.15, run_cap: float = 8.0):
        self.said: list[str] = []
        self.files = SimpleNamespace(  # type: ignore[assignment]
            logs=tmp, start_of_repair=self.after_rules, untouched=self.untouched
        )
        self.d = self.deps = SimpleNamespace(  # type: ignore[assignment]
            repair_on=True,
            say=lambda stage, text: self.said.append(text),
            config=SimpleNamespace(verify=VerifyCommands(), runner="karma", leftovers=None),
            configuration=SimpleNamespace(repair=SimpleNamespace(shared_causes=False)),
            caps=RunCaps(run_usd=run_cap, month_usd=50.0, reserve_attempt_usd=reserve),
            ledger=Ledger(tmp / "ledger.jsonl"),
            runner=None,
        )
        self.tmp = tmp

    def workspace(self, state: Any) -> Path:
        return self.tmp

    def untouched(self) -> dict[str, str]:
        return {}

    def after_rules(self) -> dict[str, str]:
        return {
            "src/app/list.component.ts": "",
            "src/app/search.component.ts": "",
            "src/app/a.component.scss": "",
            "src/app/b.component.scss": "",
        }


def state(first: list[Failure], tried: list[FileRepair], **extra: Any) -> RunState:
    report = RepairReport(enabled=True, files=tried, reserved_usd=1.35)
    return cast(
        RunState,
        {
            "run_id": "recheck-test",
            "precheck": {"status": "ok"},
            "verify": VerifyResult(commands=[], failures=first).model_dump(mode="json"),
            "repair": report.model_dump(mode="json"),
            "test_files": {},
            "timings": {},
            **extra,
        },
    )


def fixed(path: str = "src/app/list.component.ts") -> FileRepair:
    return FileRepair(path=path, outcome="Migrated by agent", touched=[path])


def test_a_recheck_only_when_no_spec_ran_and_repair_changed_something(tmp_path: Path) -> None:
    g = Graph(tmp_path)
    assert queue.needs_recheck(g, state([BUILD, TYPE], [fixed()]))
    assert not queue.needs_recheck(g, state([TYPE, SPEC], [fixed()]))  # the specs ran
    assert not queue.needs_recheck(g, state([BUILD, TYPE], []))  # nothing changed
    assert not queue.needs_recheck(g, state([BUILD, TYPE], [fixed()], rechecked=True))  # once
    assert queue.route_next_file(g, state([BUILD, TYPE], [fixed()])) == "recheck"
    assert queue.route_next_file(g, state([TYPE, SPEC], [fixed()])) == "commit_agent"


def test_the_recheck_comes_as_soon_as_the_build_compiles(tmp_path: Path) -> None:
    g = Graph(tmp_path)
    queued = ["src/app/confirm.component.scss"]
    # the type-check still fails: the specs can't run yet, so repair goes on
    still = state([BUILD, TYPE], [fixed()], queue=queued, known_failures=[TYPE.model_dump()])
    assert not queue.needs_recheck(g, still)
    assert queue.route_next_file(g, still) == "start_file"
    # the build compiles: check every spec before the next file's repair is charged
    clean = state([BUILD, TYPE], [fixed()], queue=queued, known_failures=[])
    assert queue.route_next_file(g, clean) == "recheck"


def test_the_recheck_keeps_queued_files_that_still_fail_and_drops_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    still = Failure(source="migration", file="src/app/a.component.scss", message="stale rule")
    monkeypatch.setattr(
        checker, "verify", lambda inp, runner: VerifyResult(commands=[], failures=[still, SPEC])
    )
    g = Graph(tmp_path, reserve=None)  # no Reservation: this test is about the queue
    queued = ["src/app/b.component.scss", "src/app/a.component.scss"]
    out = queue.recheck_node(g, state([BUILD, TYPE], [fixed()], queue=queued))
    assert out["queue"] == ["src/app/a.component.scss", "src/app/search.component.ts"]


def test_the_files_that_fail_only_now_are_queued_and_reserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        checker, "verify", lambda inp, runner: VerifyResult(commands=[], failures=[SPEC])
    )
    g = Graph(tmp_path)
    out = queue.recheck_node(g, state([BUILD, TYPE], [fixed()]))
    assert out["rechecked"] and out["queue"] == ["src/app/search.component.ts"]
    assert RepairReport.model_validate(out["repair"]).reserved_usd == 1.8  # 1.35 + 3 x 0.15
    assert queue.route_recheck(g, out) == "start_file"
    # The top-up is held in the shared book: another run has $50 - $1.80 of the month.
    other = Budget("other", RunCaps(run_usd=99, month_usd=50, reserve_attempt_usd=20), g.d.ledger)
    assert other.reserve(["x"]) == Reservation(
        held=False, files=1, added_usd=60.0, total_usd=60.0, available_usd=48.2
    )
    Budget("recheck-test", g.d.caps, g.d.ledger).release()  # start_run's finally, here


def test_a_file_already_tried_is_not_queued_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        checker, "verify", lambda inp, runner: VerifyResult(commands=[], failures=[SPEC])
    )
    tried = [fixed(), FileRepair(path="src/app/search.component.ts", outcome="Handed off")]
    out = queue.recheck_node(Graph(tmp_path), state([BUILD, TYPE], tried))
    assert out["rechecked"] and out["queue"] == []


def test_new_files_over_the_cap_are_left_unmigrated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        checker, "verify", lambda inp, runner: VerifyResult(commands=[], failures=[SPEC])
    )
    g = Graph(tmp_path)
    g.d.ledger.append(
        LedgerRow(at=now_utc(), run_id="earlier", model="m", requested_model="m", usage=Usage(),
                  cost_usd=49.0)
    )  # fmt: skip
    out = queue.recheck_node(g, state([BUILD, TYPE], [fixed()]))  # $1.80 > $50 - $49 of the month
    assert out["queue"] == []
    files = RepairReport.model_validate(out["repair"]).files
    assert files[-1].path == "src/app/search.component.ts" and files[-1].outcome == "Unmigrated"


def test_the_top_up_stops_at_what_the_run_can_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        checker, "verify", lambda inp, runner: VerifyResult(commands=[], failures=[SPEC])
    )
    g = Graph(tmp_path, run_cap=1.5)
    out = queue.recheck_node(
        g, state([BUILD, TYPE], [fixed()])
    )  # $1.80 asked, the run stops at $1.50
    assert out["queue"] == ["src/app/search.component.ts"]
    assert RepairReport.model_validate(out["repair"]).reserved_usd == 1.5
    Budget("recheck-test", g.d.caps, g.d.ledger).release()


def test_build_output_is_not_read_as_source(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("x", "utf-8")
    for d in ("dist/app", ".angular/cache"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "vendor.js").write_text("// @ts-ignore", "utf-8")
    assert list(read_files(tmp_path)) == ["src/a.ts"]
