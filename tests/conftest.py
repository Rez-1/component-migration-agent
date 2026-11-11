"""Shared test helpers: a fake command runner and paths to the repo's own data."""

from __future__ import annotations

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


class FakeRunner:
    """A CommandRunner that records commands and answers them from a handler."""

    def __init__(self, handler: Handler | None = None):
        self.handler = handler or (lambda _cmd, _cwd: (0, ""))
        self.commands: list[str] = []

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
