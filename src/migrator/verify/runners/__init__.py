"""The Test runner adapters (Jest, Vitest, Karma, and exit code only for a repo with no
known runner), and the one lookup from a runner's name to its adapter.

``migrate.toml`` and ``case.toml`` name the runner as a string; ``adapter_for`` is the
only place that turns it into behaviour. No other module compares runner names.
"""

from __future__ import annotations

from migrator.config import Runner
from migrator.verify.runners.base import (
    ExitCode,
    Planned,
    Skipped,
    TestReport,
    TestRun,
    TestRunner,
)
from migrator.verify.runners.jest import Jest, Vitest
from migrator.verify.runners.karma import Karma

__all__ = [
    "ADAPTERS",
    "Planned",
    "Skipped",
    "TestReport",
    "TestRun",
    "TestRunner",
    "adapter_for",
]

_BY_NAME: dict[Runner, TestRunner] = {"jest": Jest(), "vitest": Vitest(), "karma": Karma()}
_EXIT_CODE = ExitCode()
# Every known runner's adapter; the test-file rules ask all of them, not only the
# selected one, so a Test file is never missed because the runner was guessed wrong.
ADAPTERS: tuple[TestRunner, ...] = tuple(_BY_NAME.values())


def adapter_for(runner: Runner | None) -> TestRunner:
    """The adapter for the runner a repo config names; exit code only for none."""
    return _EXIT_CODE if runner is None else _BY_NAME[runner]
