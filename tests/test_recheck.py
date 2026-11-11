"""M7: a Karma bundle that didn't compile hides every spec, so the failures it hid are
checked once more after repair, and the files that fail only then get a pass."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import migrator.graph as graph
from migrator.checks import read_files
from migrator.config import VerifyCommands
from migrator.cost import Ledger, release_run
from migrator.repair.records import FileRepair, RepairReport
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


class Graph(graph.RunGraph):
    """The run graph with its file-system helpers replaced."""

    def __init__(self, tmp: Path, reserve: float | None = 0.15, run_cap: float = 8.0):
        self.said: list[str] = []
        self.d = SimpleNamespace(  # type: ignore[assignment]
            repair_on=True,
            say=lambda stage, text: self.said.append(text),
            config=SimpleNamespace(verify=VerifyCommands(), runner="karma", leftovers=None),
            configuration=SimpleNamespace(
                cost=SimpleNamespace(reserve_attempt_usd=reserve),
                repair=SimpleNamespace(max_attempts=3),
            ),
            run_cap_usd=run_cap,
            month_cap_usd=50.0,
            ledger=Ledger(tmp / "ledger.jsonl"),
            runner=None,
        )
        self.tmp = tmp

    def workspace(self, state: Any) -> Path:
        return self.tmp

    def logs(self, state: Any) -> Path:
        return self.tmp

    def stale_rules(self, state: Any) -> list[tuple[str, str]]:
        return []

    def after_rules(self, state: Any) -> dict[str, str]:
        return {"src/app/list.component.ts": "", "src/app/search.component.ts": ""}


def state(first: list[Failure], tried: list[FileRepair], **extra: Any) -> graph.RunState:
    report = RepairReport(enabled=True, files=tried, reserved_usd=1.35)
    return cast(
        graph.RunState,
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


@pytest.fixture(autouse=True)
def _release() -> Any:
    yield
    release_run("recheck-test")


def test_a_recheck_only_when_no_spec_ran_and_repair_changed_something(tmp_path: Path) -> None:
    g = Graph(tmp_path)
    assert g.needs_recheck(state([BUILD, TYPE], [fixed()]))
    assert not g.needs_recheck(state([TYPE, SPEC], [fixed()]))  # the specs ran
    assert not g.needs_recheck(state([BUILD, TYPE], []))  # nothing changed
    assert not g.needs_recheck(state([BUILD, TYPE], [fixed()], rechecked=True))  # once
    assert g.route_next_file(state([BUILD, TYPE], [fixed()])) == "recheck"
    assert g.route_next_file(state([TYPE, SPEC], [fixed()])) == "commit_agent"


def test_the_files_that_fail_only_now_are_queued_and_reserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        graph, "verify", lambda inp, runner: VerifyResult(commands=[], failures=[SPEC])
    )
    g = Graph(tmp_path)
    out = g.recheck_node(state([BUILD, TYPE], [fixed()]))
    assert out["rechecked"] and out["queue"] == ["src/app/search.component.ts"]
    assert RepairReport.model_validate(out["repair"]).reserved_usd == 1.8  # 1.35 + 3 x 0.15
    assert g.route_recheck(out) == "start_file"


def test_a_file_already_tried_is_not_queued_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        graph, "verify", lambda inp, runner: VerifyResult(commands=[], failures=[SPEC])
    )
    tried = [fixed(), FileRepair(path="src/app/search.component.ts", outcome="Handed off")]
    out = Graph(tmp_path).recheck_node(state([BUILD, TYPE], tried))
    assert out["rechecked"] and "queue" not in out


def test_new_files_over_the_cap_are_left_unmigrated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        graph, "verify", lambda inp, runner: VerifyResult(commands=[], failures=[SPEC])
    )
    out = Graph(tmp_path, run_cap=1.5).recheck_node(state([BUILD, TYPE], [fixed()]))
    assert "queue" not in out
    files = RepairReport.model_validate(out["repair"]).files
    assert files[-1].path == "src/app/search.component.ts" and files[-1].outcome == "Unmigrated"


def test_build_output_is_not_read_as_source(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("x", "utf-8")
    for d in ("dist/app", ".angular/cache"):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / "vendor.js").write_text("// @ts-ignore", "utf-8")
    assert list(read_files(tmp_path)) == ["src/a.ts"]
