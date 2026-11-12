"""Shared test helpers: a fake command runner and paths to the repo's own data."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from migrator.execs import CommandResult, display

if TYPE_CHECKING:
    from migrator.migrations import MigrationSpec

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "fixtures" / "mui4-app"
FIXTURE_CASE = REPO_ROOT / "evals" / "cases" / "fixture-mui4"
DATA = Path(__file__).parent / "data"

Handler = Callable[[str, Path], tuple[int, str]]


# Every FakeRunner made during the current test, for the command-line gate below.
_RUNNERS: list[FakeRunner] = []


class FakeRunner:
    """A CommandRunner that records commands and answers them from a handler."""

    def __init__(self, handler: Handler | None = None):
        self.handler = handler or (lambda _cmd, _cwd: (0, ""))
        self.commands: list[str] = []
        _RUNNERS.append(self)

    def run(
        self,
        command: str | Sequence[str],
        cwd: Path,
        *,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        log_file: Path | None = None,
    ) -> CommandResult:
        text = display(command)
        self.commands.append(text)
        code, output = self.handler(text, cwd)
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text(output, "utf-8")
        return CommandResult(
            command=text, cwd=str(cwd), exit_code=code, output=output, duration_s=0.0
        )


@pytest.fixture(scope="session")
def spec() -> MigrationSpec:
    from migrator.migrations import find_spec

    return find_spec("mui@4", "mui@5")


@pytest.fixture(autouse=True)
def _capture_scoring_goldens(request: pytest.FixtureRequest) -> Iterator[None]:
    """With MIGRATOR_CAPTURE_SCORING set, save every run this test made as a Scoring
    golden candidate (tests/scoring_goldens.py). Off by default."""
    yield
    out = os.environ.get("MIGRATOR_CAPTURE_SCORING")
    tmp = getattr(request.node, "funcargs", {}).get("tmp_path")
    if not out or tmp is None:
        return
    from tests.scoring_goldens import save_golden

    name = re.sub(r"[^A-Za-z0-9_-]+", "-", request.node.name).strip("-")
    for n, evidence in enumerate(sorted(tmp.rglob("report-input.json"))):
        if (evidence.parent / "scorecard.json").is_file():
            save_golden(evidence.parent, Path(out) / f"{name}-{n}", {"<tmp>": tmp})


# --------------------------------------------------------------------------- command gate

COMMANDS_FILE = DATA / "fake-commands.json"


def _normalised(command: str, paths: dict[str, Path]) -> str:
    pairs = {}
    for name, p in paths.items():
        for raw in (str(p), str(p.resolve())):
            pairs[raw] = name
            pairs[raw.removeprefix("/private")] = name
    for raw in sorted(pairs, key=len, reverse=True):
        command = command.replace(raw, pairs[raw])
    return command


@pytest.fixture(autouse=True)
def _command_gate(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    """The gate for refactors that must not change what a run executes (issue #18): every
    command line a test's FakeRunners were asked to run, compared with the ones recorded
    in ``tests/data/fake-commands.json``. A test not in that file is not checked.
    ``MIGRATOR_RECORD_COMMANDS=1 uv run pytest ...`` records the tests it runs instead.
    Machine paths (the test's temp folders, this checkout, the home folder) are
    replaced by placeholders."""
    _RUNNERS.clear()
    yield
    commands = [c for r in _RUNNERS for c in r.commands]
    _RUNNERS.clear()
    if not commands:
        return
    paths = {"<basetemp>": tmp_path_factory.getbasetemp(), "<repo>": REPO_ROOT}
    tmp = getattr(request.node, "funcargs", {}).get("tmp_path")
    if tmp is not None:
        paths["<tmp>"] = tmp
    paths["<home>"] = Path.home()
    seen = [_normalised(c, paths) for c in commands]
    recorded = json.loads(COMMANDS_FILE.read_text("utf-8")) if COMMANDS_FILE.is_file() else {}
    key = request.node.nodeid
    if os.environ.get("MIGRATOR_RECORD_COMMANDS"):
        recorded[key] = seen
        text = json.dumps(dict(sorted(recorded.items())), indent=1, ensure_ascii=False)
        COMMANDS_FILE.write_text(text + "\n", "utf-8")
    elif key in recorded:
        assert seen == recorded[key], f"{key} ran different commands than recorded"
