"""The Checker (#18): one run's Verify after the Pre-check, with a fake command runner."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from migrator.config import LeftoverCheck, ResolvedRepoConfig, VerifyCommands
from migrator.verify.checker import Checker
from migrator.verify.parsers import Failure
from tests.conftest import FakeRunner

TODO = "TODO(mdc-migration)"
AFTER_RULES = {"src/a.scss": f"/* {TODO}: internal classes */\n.x .mat-form-field-wrapper {{\n}}\n"}
OLD_TEST = Failure(
    source="test",
    file="src/old.ts",
    message="Error: was failing before",
    test_file="src/old.test.ts",
    test_name="old",
)


def _jest(command: str, cwd: Path) -> tuple[int, str]:
    """A Jest that fails ``src/old.test.ts`` and ``src/new.test.ts``'s one test each."""
    argv = shlex.split(command)
    out = next(a.split("=", 1)[1] for a in argv if a.startswith("--outputFile="))
    suites = [
        {
            "name": str(cwd / f"src/{name}.test.ts"),
            "status": "failed",
            "message": "",
            "assertionResults": [
                {
                    "status": "failed",
                    "title": name,
                    "ancestorTitles": [],
                    "failureMessages": [f"Error: {name} fails"],
                }
            ],
        }
        for name in ("old", "new")
    ]
    Path(out).write_text(json.dumps({"testResults": suites}))
    return 1, ""


def _checker(tmp_path: Path, runner: FakeRunner, leftovers: LeftoverCheck | None = None) -> Checker:
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "package.json").write_text("{}")
    config = ResolvedRepoConfig(
        package_manager="npm",
        lockfile="package-lock.json",
        node=None,
        install_flags=[],
        source_globs=["src/**/*.ts"],
        exclude=[],
        runner="jest",
        verify=VerifyCommands(test="npm test"),
        leftovers=leftovers,
    )

    def after_rules() -> dict[str, str]:
        if leftovers is None or not leftovers.todo_markers:
            raise AssertionError("the after-Rules snapshot is read only for stale rules")
        return AFTER_RULES

    return Checker(
        workspace=ws,
        config=config,
        pre_existing=[OLD_TEST],
        after_rules=after_rules,
        runner=runner,
        log_dir=tmp_path / "logs",
    )


@pytest.mark.parametrize("label", ["verify", "recheck", "final"])
def test_a_check_is_named_by_its_label_and_runs_every_test(tmp_path: Path, label: str) -> None:
    runner = FakeRunner(_jest)
    result = _checker(tmp_path, runner).check(label)
    [command] = runner.commands
    assert f"/logs/{label}-jest.json" in command
    assert "--findRelatedTests" not in command
    assert result.command("test") is not None
    assert result.command("test").log == f"{label}-test.log"  # type: ignore[union-attr]
    assert (tmp_path / "logs" / f"{label}-test.log").is_file()


def test_every_check_passes_the_pre_existing_failures_along(tmp_path: Path) -> None:
    checker = _checker(tmp_path, FakeRunner(_jest))
    for result in (checker.check("verify"), checker.narrow("repair-a", ["src/new.ts"])):
        assert [f.test_name for f in result.failures] == ["new"]
        assert [f.key() for f in result.pre_existing] == [OLD_TEST.key()]


def test_a_narrow_verify_runs_only_the_related_tests(tmp_path: Path) -> None:
    runner = FakeRunner(_jest)
    result = _checker(tmp_path, runner).narrow("repair-src-a-ts-a1", ["src/a.ts", "src/b.ts"])
    [command] = runner.commands
    assert "/logs/repair-src-a-ts-a1-jest.json" in command
    assert command.endswith("--passWithNoTests --findRelatedTests src/a.ts src/b.ts")
    assert result.test_files_run == ["src/new.test.ts", "src/old.test.ts"]


def test_the_leftovers_check_gets_the_stale_rules_from_the_after_rules_snapshot(
    tmp_path: Path,
) -> None:
    check = LeftoverCheck(old_modules=[], todo_markers=[TODO], source_globs=["src/**/*.scss"])
    checker = _checker(tmp_path, FakeRunner(_jest), leftovers=check)
    assert checker.stale_rules == [("src/a.scss", ".x .mat-form-field-wrapper {")]
    (checker.workspace / "src/a.scss").write_text(".x .mat-form-field-wrapper {\n}\n")
    for result in (checker.check("final"), checker.narrow("repair-a", ["src/a.ts"])):
        assert [f.code for f in result.failures if f.source == "migration"] == ["stale-rule"]


def test_a_snapshot_update_reruns_the_snapshot_only_test_files(tmp_path: Path) -> None:
    runner = FakeRunner(_jest)
    checker = _checker(tmp_path, runner)
    snap = Failure(
        source="test",
        file="src/new.ts",
        message="expect(received).toMatchSnapshot()",
        test_file="src/new.test.ts",
        test_name="new",
    )
    first = checker.check("verify").model_copy(update={"failures": [snap]})
    result, run = checker.update_snapshots("final", first, dict)
    assert run is not None and run.log == "final-snapshots-update.log"
    assert runner.commands[-1].endswith("--runTestsByPath src/new.test.ts")
    assert result.failures == [snap]  # the fake still fails it: kept
