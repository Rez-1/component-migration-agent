"""Shared test helpers: a fake command runner and paths to the repo's own data."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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
