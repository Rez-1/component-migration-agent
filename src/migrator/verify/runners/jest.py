"""Jest and Vitest: both write the same JSON report (Vitest's ``--reporter=json``)."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from migrator.execs import CommandResult
from migrator.verify.commands import real_path, with_args
from migrator.verify.parsers import Failure, jest_suite_files, parse_jest_json
from migrator.verify.runners.base import Planned, Skipped, TestReport, TestRun, TestRunner


class _JestReport(TestRunner):
    """What Jest and Vitest share: the report and how it is read."""

    config_lists_tests = True
    updates_snapshots = True
    # A Narrow verify whose report is missing: which test files count as run.
    ran_unreported: ClassVar[list[str] | None] = None

    def report_file(self, log_dir: Path, label: str) -> Path:
        return (log_dir / f"{label}-{self.name}.json").resolve()

    def read(self, result: CommandResult, run: TestRun, report: Path | None) -> TestReport:
        if report is None or not report.is_file():
            return TestReport(ran=self.ran_unreported if run.narrow else None)
        root = str(run.workspace.resolve())
        text = report.read_text("utf-8")
        failures, totals = parse_jest_json(text, root, lambda p: real_path(run.workspace, p))
        return TestReport(
            failures=failures,
            totals=totals,
            ran=jest_suite_files(text, root) if run.narrow else None,
            parsed_with=f"{self.name} json",
        )

    def snapshot_failures(self, text: str, workspace: str) -> list[Failure]:
        failures, _ = parse_jest_json(text, workspace, lambda p: True)
        return failures


class Jest(_JestReport):
    name = "jest"
    config_files = ("jest.config.js", "jest.config.cjs", "jest.config.mjs", "jest.config.ts")
    # The report didn't say which tests ran: assume none were (their known failures stay).
    ran_unreported: ClassVar[list[str] | None] = []

    def plan(self, command: str, run: TestRun) -> Planned | Skipped:
        report = self.report_file(run.log_dir, run.label)
        args = ["--json", f"--outputFile={report}", "--testLocationInResults"]
        if run.related_to is not None:
            args += ["--passWithNoTests", "--findRelatedTests", *run.related_to]
        if run.coverage_dir is not None:
            args += [
                "--coverage",
                "--coverageReporters=json-summary",
                f"--coverageDirectory={run.coverage_dir.resolve()}",
            ]
        return Planned(command=with_args(command, args), report=report)

    def snapshot_command(self, command: str, test_files: list[str], report: Path) -> str:
        args = ["--ci=false", "-u", "--json", f"--outputFile={report}",
                "--runTestsByPath", *test_files]  # fmt: skip
        return with_args(command, args)


class Vitest(_JestReport):
    name = "vitest"
    config_files = (
        "vitest.config.ts",
        "vitest.config.js",
        "vitest.config.mts",
        "vite.config.ts",
        "vite.config.js",
    )

    def plan(self, command: str, run: TestRun) -> Planned | Skipped:
        # A Narrow verify runs every test: there is no `vitest related` yet.
        report = self.report_file(run.log_dir, run.label)
        args = ["--reporter=json", f"--outputFile={report}"]
        if run.coverage_dir is not None:
            args += [
                "--coverage.enabled=true",
                "--coverage.reporter=json-summary",
                f"--coverage.reportsDirectory={run.coverage_dir.resolve()}",
            ]
        return Planned(command=with_args(command, args), report=report)

    def snapshot_command(self, command: str, test_files: list[str], report: Path) -> str:
        return with_args(command, ["-u", "--reporter=json", f"--outputFile={report}", *test_files])
