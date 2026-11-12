"""What a test-runner adapter is: the one place a Test runner's conventions live.

An adapter builds the test command for a full, narrow or coverage run and says where
its report will be; reads the result into Failures, test totals and the test files
that ran; and states plain facts about the runner (its config files, its test entry
points, whether it needs a browser in the sandbox, whether it can update snapshots).
Only the test command goes through it; the type-check and lint are read elsewhere.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from migrator.execs import CommandResult
from migrator.verify.parsers import Failure, TestTotals


class TestRun(BaseModel):
    """One run of the test command: in which workspace, named how, covering what."""

    model_config = ConfigDict(frozen=True)

    workspace: Path
    log_dir: Path
    label: str
    # A Narrow verify: only the tests related to these files. None runs every test.
    related_to: list[str] | None = None
    # Also measure test coverage into this folder (the Pre-check, M6).
    coverage_dir: Path | None = None

    @property
    def narrow(self) -> bool:
        return self.related_to is not None


class Planned(BaseModel):
    """The test command to run, and the report file it will write (if any)."""

    command: str
    report: Path | None = None


class Skipped(BaseModel):
    """The test command is not run: why, the failures that stand for it, and which test
    files count as run (None: all)."""

    why: str
    failures: list[Failure] = []
    ran: list[str] | None = None


class TestReport(BaseModel):
    """What one run of the test command said."""

    failures: list[Failure] = []
    totals: TestTotals | None = None
    # The test files that ran: None for all of them. Only a Narrow verify asks.
    ran: list[str] | None = None
    parsed_with: str = "exit code"


class TestRunner:
    """A Test runner's adapter. The base reads nothing but the exit code."""

    __test__ = False  # not a pytest test class

    name: ClassVar[str] = "exit code"
    # Files that configure the runner; each belongs to the tests (a Test file).
    config_files: ClassVar[tuple[str, ...]] = ()
    # Whether its config files list test globs and setup files worth reading.
    config_lists_tests: ClassVar[bool] = False
    # Files the runner loads before the tests, Test files when a config file is there.
    entry_points: ClassVar[tuple[str, ...]] = ()
    needs_browser: ClassVar[bool] = False  # the sandbox needs Chromium (M7)
    updates_snapshots: ClassVar[bool] = False

    def report_file(self, log_dir: Path, label: str) -> Path | None:
        """Where this runner's report for the run labelled ``label`` goes."""
        return None

    def plan(self, command: str, run: TestRun) -> Planned | Skipped:
        """The repo's test command with this runner's arguments for ``run``."""
        return Planned(command=command)

    def read(self, result: CommandResult, run: TestRun, report: Path | None) -> TestReport:
        """The failures, totals and test files run from the command's report and output.
        A failing exit with no failures read is left to Verify, as for every command."""
        return TestReport()

    def snapshot_command(self, command: str, test_files: list[str], report: Path) -> str:
        """The test command that rewrites the snapshots of ``test_files`` (M6)."""
        raise NotImplementedError(f"{self.name} can't update snapshots")

    def snapshot_failures(self, text: str, workspace: str) -> list[Failure]:
        """The failures still in a snapshot update's report."""
        raise NotImplementedError(f"{self.name} can't update snapshots")


class ExitCode(TestRunner):
    """A repo with no known Test runner: its test command runs as it is, and only the
    exit code says whether it passed."""
