"""The Test runner adapters (#18), each through ``verify()`` with a fake command runner
that answers with recorded real output:

- ``jest-baseline.json``: Jest's ``--json`` report on the MUI fixture;
- ``runners/vitest-report.json``: Vitest 3.2.4's JSON reporter on a two-file project,
  one failing test and one file that fails to import;
- ``runners/karma-report.json``: the wrapper reporter's JSON from the Angular fixture's
  Pre-check in Docker, with one spec made to fail;
- ``runners/karma-load-error.txt``: ``ng test``'s output after the Angular fixture's
  Rules in Docker, when the test bundle didn't compile.

The workspace path in them is ``/WS``.
"""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path

import pytest

from migrator.checks import read_test_rules
from migrator.config import Runner, VerifyCommands
from migrator.verify import VerifyInput, VerifyResult, verify
from migrator.verify.parsers import Failure
from migrator.verify.runners import ADAPTERS, adapter_for
from tests.conftest import DATA, REPO_ROOT, FakeRunner

RUNNERS = DATA / "runners"
ANGULAR = REPO_ROOT / "fixtures" / "angular15-app"


def _recorded(name: Path, ws: Path) -> str:
    return name.read_text("utf-8").replace("/WS", str(ws.resolve()))


def _verify(
    ws: Path,
    log_dir: Path,
    runner_name: Runner | None,
    fake: FakeRunner,
    related_to: list[str] | None = None,
) -> VerifyResult:
    return verify(
        VerifyInput(
            workspace=ws,
            commands=VerifyCommands(test="npm test"),
            runner=runner_name,
            log_dir=log_dir,
            label="verify",
            related_to=related_to,
        ),
        fake,
    )


def _reporting(report: str | None, code: int = 1, output: str = "") -> FakeRunner:
    """A test command that writes ``report`` to its ``--outputFile`` (if any)."""

    def handler(command: str, _cwd: Path) -> tuple[int, str]:
        out = next(
            (a.split("=", 1)[1] for a in shlex.split(command) if a.startswith("--outputFile=")),
            None,
        )
        if report is not None and out is not None:
            Path(out).write_text(report, "utf-8")
        return code, output

    return FakeRunner(handler)


def _node_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "src" / "__tests__").mkdir(parents=True)
    (ws / "package.json").write_text('{"scripts": {"test": "jest"}}')
    return ws


# --------------------------------------------------------------------------- Jest


def test_jest_reads_its_json_report(tmp_path: Path) -> None:
    ws = _node_workspace(tmp_path)
    (ws / "src/screens").mkdir()
    (ws / "src/screens/Search.tsx").write_text("")
    fake = _reporting(_recorded(DATA / "jest-baseline.json", ws))
    result = _verify(ws, tmp_path / "logs", "jest", fake)
    [command] = fake.commands
    assert command.startswith("npm test -- --json --outputFile=")
    assert command.endswith("/logs/verify-jest.json --testLocationInResults")
    assert result.command("test").parsed_with == "jest json"  # type: ignore[union-attr]
    assert result.test_totals is not None and result.test_totals.tests_failed == 7
    assert len(result.failures) == 7 and result.test_files_run is None
    search = [f for f in result.failures if f.test_file == "src/screens/__tests__/Search.test.tsx"]
    assert search and {f.file for f in search} == {"src/screens/Search.tsx"}


def test_a_narrow_jest_run_finds_the_related_tests_and_says_which_ran(tmp_path: Path) -> None:
    ws = _node_workspace(tmp_path)
    fake = _reporting(_recorded(DATA / "jest-baseline.json", ws))
    result = _verify(ws, tmp_path / "logs", "jest", fake, ["src/a.tsx"])
    assert fake.commands[0].endswith(
        "--testLocationInResults --passWithNoTests --findRelatedTests src/a.tsx"
    )
    assert result.test_files_run is not None
    assert "src/screens/__tests__/Dashboard.test.tsx" in result.test_files_run


def test_a_narrow_jest_run_without_a_report_ran_no_test(tmp_path: Path) -> None:
    """Jest didn't say which tests ran: assume none, so their known failures stay."""
    ws = _node_workspace(tmp_path)
    result = _verify(ws, tmp_path / "logs", "jest", _reporting(None), ["src/a.tsx"])
    assert result.test_files_run == []
    assert result.command("test").parsed_with == "exit code"  # type: ignore[union-attr]
    assert len(result.failures) == 1 and result.failures[0].file is None
    full = _verify(ws, tmp_path / "logs", "jest", _reporting(None))
    assert full.test_files_run is None


# --------------------------------------------------------------------------- Vitest


def test_vitest_reads_its_json_report(tmp_path: Path) -> None:
    ws = _node_workspace(tmp_path)
    (ws / "src/sum.js").write_text("")
    fake = _reporting(_recorded(RUNNERS / "vitest-report.json", ws))
    result = _verify(ws, tmp_path / "logs", "vitest", fake)
    [command] = fake.commands
    assert command.startswith("npm test -- --reporter=json --outputFile=")
    assert command.endswith("/logs/verify-vitest.json")
    assert result.command("test").parsed_with == "vitest json"  # type: ignore[union-attr]
    by_name = {f.test_name: f for f in result.failures}
    assert set(by_name) == {"(suite)", "sum › adds negatives"}
    assert by_name["(suite)"].whole_suite_failed
    assert by_name["(suite)"].test_file == "src/__tests__/broken.test.js"
    assert "Cannot find module '../missing.js'" in by_name["(suite)"].message
    assert by_name["sum › adds negatives"].file == "src/sum.js"
    assert result.test_totals is not None and result.test_totals.tests_total == 2


def test_a_narrow_vitest_run_runs_every_test(tmp_path: Path) -> None:
    """A known gap, kept as it is: no ``vitest related`` yet, so every test runs."""
    ws = _node_workspace(tmp_path)
    fake = _reporting(_recorded(RUNNERS / "vitest-report.json", ws))
    result = _verify(ws, tmp_path / "logs", "vitest", fake, ["src/sum.js"])
    assert "src/sum.js" not in fake.commands[0]
    assert result.test_files_run == ["src/__tests__/broken.test.js", "src/__tests__/sum.test.js"]
    missing = _verify(ws, tmp_path / "logs", "vitest", _reporting(None), ["src/sum.js"])
    assert missing.test_files_run is None


# --------------------------------------------------------------------------- Karma


@pytest.fixture
def angular(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    shutil.copytree(ANGULAR, ws)
    return ws


def _karma(logs: Path) -> FakeRunner:
    """``ng test`` with the wrapper config: its reporter writes the recorded report."""

    def handler(_command: str, _cwd: Path) -> tuple[int, str]:
        report = (RUNNERS / "karma-report.json").read_text("utf-8")
        (logs / "verify-karma.json").write_text(report, "utf-8")
        return 1, ""

    return FakeRunner(handler)


def test_karma_reads_the_wrapper_reporters_json(tmp_path: Path, angular: Path) -> None:
    logs = tmp_path / "logs"
    fake = _karma(logs)
    result = _verify(angular, logs, "karma", fake)
    [command] = fake.commands
    assert command == (
        f"npm test -- --karma-config={(logs / 'verify-karma.conf.cjs').resolve()} "
        "--watch=false --browsers=MigratorChromeHeadless"
    )
    assert result.command("test").parsed_with == "karma json"  # type: ignore[union-attr]
    [failure] = result.failures
    assert failure.test_name == "AppComponent › shows the app name in the toolbar"
    assert (failure.test_file, failure.line) == ("src/app/app.component.spec.ts", 20)
    assert failure.file == "src/app/app.component.ts"
    assert failure.message.startswith("Expected 'TriageIssues")
    assert result.test_totals is not None
    assert (result.test_totals.tests_total, result.test_totals.tests_failed) == (30, 1)


def test_a_narrow_karma_run_includes_the_specs_and_lists_the_failing_ones(
    tmp_path: Path, angular: Path
) -> None:
    logs = tmp_path / "logs"
    fake = _karma(logs)
    result = _verify(angular, logs, "karma", fake, ["src/app/app.component.html"])
    assert fake.commands[0].endswith("--include=src/app/app.component.spec.ts")
    # A known gap, kept as it is: only the failing specs count as run.
    assert result.test_files_run == ["src/app/app.component.spec.ts"]


def test_a_narrow_karma_run_with_no_spec_runs_nothing(tmp_path: Path, angular: Path) -> None:
    fake = FakeRunner()
    result = _verify(angular, tmp_path / "logs", "karma", fake, ["src/styles.scss"])
    assert fake.commands == []
    assert result.command("test").parsed_with == "not run: no spec for these files"  # type: ignore[union-attr]
    assert result.failures == [] and result.test_files_run == []


def test_a_karma_load_error_is_one_failure_saying_no_spec_ran(
    tmp_path: Path, angular: Path
) -> None:
    output = _recorded(RUNNERS / "karma-load-error.txt", angular)
    result = _verify(angular, tmp_path / "logs", "karma", _reporting(None, 1, output))
    assert result.command("test").parsed_with == "karma load error"  # type: ignore[union-attr]
    [failure] = result.failures
    assert failure.ran_no_spec and failure.test_name == "(build)" and failure.file is None


def test_karma_without_a_config_is_a_failure_and_runs_nothing(tmp_path: Path) -> None:
    ws = _node_workspace(tmp_path)
    fake = FakeRunner()
    result = _verify(ws, tmp_path / "logs", "karma", fake)
    assert fake.commands == []
    assert [f.message for f in result.failures] == ["no karma.conf.js in the repo"]


# --------------------------------------------------------------------------- exit code


def test_with_no_known_runner_only_the_exit_code_counts(tmp_path: Path) -> None:
    ws = _node_workspace(tmp_path)
    fake = _reporting(None, 1, "1 test failed")
    result = _verify(ws, tmp_path / "logs", None, fake, ["src/a.ts"])
    assert fake.commands == ["npm test"]
    assert result.command("test").parsed_with == "exit code"  # type: ignore[union-attr]
    assert [f.message for f in result.failures] == [
        "`npm test` exited 1 without failures the Migrator could parse"
    ]
    assert result.test_files_run is None
    assert _verify(ws, tmp_path / "logs", None, _reporting(None, 0)).failures == []


# --------------------------------------------------------------------------- facts


def test_the_lookup_and_each_runners_facts() -> None:
    assert [a.name for a in ADAPTERS] == ["jest", "vitest", "karma"]
    assert adapter_for(None).name == "exit code"
    assert [a.name for a in ADAPTERS if a.needs_browser] == ["karma"]
    assert [a.name for a in ADAPTERS if a.updates_snapshots] == ["jest", "vitest"]
    assert not adapter_for(None).updates_snapshots and not adapter_for(None).config_files


def test_test_file_rules_ask_every_runner(tmp_path: Path) -> None:
    """A repo with Karma's config and a Vitest config: both, and Karma's entry point,
    belong to the tests, whichever runner was selected."""
    (tmp_path / "src").mkdir()
    (tmp_path / "karma.conf.js").write_text("module.exports = () => {};\n")
    (tmp_path / "src/test.ts").write_text("")
    (tmp_path / "vite.config.ts").write_text(
        "export default { test: { include: ['src/**/*.it.ts'] } };\n"
    )
    rules = read_test_rules(tmp_path)
    assert rules.setup_files == ["karma.conf.js", "src/test.ts", "vite.config.ts"]
    assert rules.test_globs == ["src/**/*.it.ts"]
    (tmp_path / "karma.conf.js").unlink()  # the entry point counts only with its config
    assert read_test_rules(tmp_path).setup_files == ["vite.config.ts"]


# --------------------------------------------------------------------------- Failure


def test_a_failure_answers_named_questions() -> None:
    test = Failure(
        source="test",
        file="src/a.ts",
        message="x",
        test_file="src/a.test.ts",
        test_name="Search › clears the field",
    )
    assert test.matches_test_check("src/a.test.ts › clears the field")
    assert test.matches_test_check("src/a.test.ts › Search › clears the field")
    assert not test.matches_test_check("src/b.test.ts › clears the field")
    assert not test.matches_test_check("src/a.test.ts › clears")
    suite = test.model_copy(update={"test_name": "(suite)"})
    assert suite.whole_suite_failed and suite.matches_test_check("src/a.test.ts › anything")
    assert not test.whole_suite_failed and not test.ran_no_spec
    unnamed = Failure(source="test", file=None, message="no karma.conf.js in the repo")
    assert unnamed.test_title == "(suite)" and test.test_title == "Search › clears the field"
    lint = Failure(source="lint", file=None, message="x", test_name="(build)")
    assert not lint.ran_no_spec
