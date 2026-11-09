from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from migrator.cli import app
from tests.conftest import FIXTURE, FIXTURE_CASE

runner = CliRunner()


def test_scan_writes_the_usage_report(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["scan", str(FIXTURE), "--case", str(FIXTURE_CASE / "case.toml"), "--out", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "12 affected files" in result.output
    report = json.loads((tmp_path / "usage-report.json").read_text())
    assert report["schema_version"] == 1
    assert report["totals"]["affected_files"] == 12
    assert (tmp_path / "usage-report.md").read_text().startswith("# Usage report")


def test_scan_refuses_a_repo_not_on_the_old_version(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies": {"@mui/material": "5.18.0"}}')
    (tmp_path / "package-lock.json").write_text("{}")
    result = runner.invoke(app, ["scan", str(tmp_path), "--out", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "not on mui@4" in result.output


def test_a_real_run_refuses_a_folder_inside_another_git_repo() -> None:
    # The fixture is a folder of this repository, not a repo of its own.
    result = runner.invoke(
        app, ["migrate", str(FIXTURE), "--from", "mui@4", "--to", "mui@5", "--sandbox", "local"]
    )
    assert result.exit_code == 2
    assert "inside the git repo" in " ".join(result.output.split())


def test_unknown_migration() -> None:
    result = runner.invoke(
        app, ["migrate", str(FIXTURE), "--from", "mui@5", "--to", "mui@6", "--dry-run"]
    )
    assert result.exit_code == 2
    assert "no migration from mui@5 to mui@6" in result.output


MIGRATE = ["migrate", str(FIXTURE), "--from", "mui@4", "--to", "mui@5", "--dry-run"]


def test_migrate_with_a_model_needs_max_cost_outside_a_terminal() -> None:
    result = runner.invoke(
        app,
        [*MIGRATE, "--config", "opus-low"],
    )
    assert result.exit_code == 2
    assert "pass --max-cost" in result.output


def test_max_cost_can_never_be_unlimited() -> None:
    for value in ("0", "-1", "inf", "nan"):
        result = runner.invoke(
            app,
            [*MIGRATE, "--config", "opus-low", "--max-cost", value],
        )
        assert result.exit_code == 2, value
        assert "no unlimited" in result.output


def test_resume_an_unknown_run(tmp_path: Path) -> None:
    result = runner.invoke(app, ["resume", str(tmp_path / "nope")])
    assert result.exit_code == 2
    assert "no run" in result.output
