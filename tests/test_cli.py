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


def test_migrate_without_dry_run_is_not_implemented_yet() -> None:
    result = runner.invoke(app, ["migrate", str(FIXTURE), "--from", "mui@4", "--to", "mui@5"])
    assert result.exit_code == 2
    assert "only --dry-run" in result.output


def test_unknown_migration() -> None:
    result = runner.invoke(
        app, ["migrate", str(FIXTURE), "--from", "mui@5", "--to", "mui@6", "--dry-run"]
    )
    assert result.exit_code == 2
    assert "no migration from mui@5 to mui@6" in result.output
