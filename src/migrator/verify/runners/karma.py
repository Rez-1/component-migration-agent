"""Karma + Jasmine (Angular's default Test runner, M7); the wrapper config and its
report's parser are in ``migrator.verify.karma``."""

from __future__ import annotations

from pathlib import Path

from migrator.execs import CommandResult
from migrator.verify.commands import real_path, with_args
from migrator.verify.karma import (
    KARMA_CONFIGS,
    find_karma_config,
    parse_karma_json,
    spec_files_for,
    write_wrapper,
)
from migrator.verify.parsers import NO_SPEC_RAN, Failure
from migrator.verify.runners.base import Planned, Skipped, TestReport, TestRun, TestRunner
from migrator.workspace import list_files

SPEC_GLOBS = ["src/**/*.spec.ts", "projects/**/*.spec.ts"]


class Karma(TestRunner):
    name = "karma"
    config_files = KARMA_CONFIGS
    # The test entry point Angular's CLI generates (*.spec.ts already match the default
    # test names, so the config is not read for globs).
    entry_points = ("src/test.ts", "src/test-setup.ts")
    needs_browser = True  # the tests run in Chrome headless

    def report_file(self, log_dir: Path, label: str) -> Path:
        return (log_dir / f"{label}-karma.json").resolve()

    def plan(self, command: str, run: TestRun) -> Planned | Skipped:
        ws = run.workspace
        config = find_karma_config(ws)
        if config is None:
            failure = Failure(source="test", file=None, message="no karma.conf.js in the repo")
            return Skipped(why="no karma config", failures=[failure])
        wrapper, report = write_wrapper(ws, config, run.log_dir, run.label)
        args = [f"--karma-config={wrapper}", "--watch=false", "--browsers=MigratorChromeHeadless"]
        if run.related_to is not None:
            specs = spec_files_for(run.related_to, lambda p: (ws / p).is_file())
            if not specs:  # nothing tests these files: nothing to run
                return Skipped(why="no spec for these files", ran=[])
            args += [f"--include={s}" for s in specs]
        return Planned(command=with_args(command, args), report=report)

    def read(self, result: CommandResult, run: TestRun, report: Path | None) -> TestReport:
        ws = run.workspace
        read = TestReport()
        if report is not None and report.is_file():
            spec_sources = [
                (rel, (ws / rel).read_text("utf-8", errors="replace"))
                for rel in list_files(ws, SPEC_GLOBS, [])
            ]
            failures, totals = parse_karma_json(
                report.read_text("utf-8"),
                str(ws.resolve()),
                lambda p: real_path(ws, p),
                spec_sources,
            )
            # Karma reports only the failing specs as having run (a known gap).
            ran = sorted({f.test_file for f in failures if f.test_file}) if run.narrow else None
            read = TestReport(failures=failures, totals=totals, ran=ran, parsed_with="karma json")
        if not result.ok and not read.failures and "load error" in result.output:
            # The test bundle didn't compile (M7): Karma ran no spec. The cause is in the
            # type-check's failures; this says why the tests can't tell anything yet.
            failure = Failure(
                source="test",
                file=None,
                message="the test bundle didn't compile, so no spec ran (fix the build "
                "errors first)",
                test_name=NO_SPEC_RAN,
            )
            read = read.model_copy(
                update={"failures": [failure], "parsed_with": "karma load error"}
            )
        return read
