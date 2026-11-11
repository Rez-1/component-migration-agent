"""migrator spec new / spec check (M7)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from migrator.cli import app
from migrator.migrations import MIGRATIONS_DIR
from migrator.spec_tools import Check, SpecToolError, check_spec, new_spec

MUI = MIGRATIONS_DIR / "mui-4-to-5"


def failures(checks: list[Check]) -> list[str]:
    return [f"{c.name}: {c.detail}" for c in checks if c.status == "fail"]


@pytest.fixture
def mui_copy(tmp_path: Path) -> Path:
    folder = tmp_path / "mui-4-to-5"
    shutil.copytree(MUI, folder, ignore=shutil.ignore_patterns("node_modules"))
    return folder


def edit(folder: Path, old: str, new: str) -> None:
    toml = folder / "migration.toml"
    text = toml.read_text("utf-8")
    assert old in text
    toml.write_text(text.replace(old, new, 1), "utf-8")


def test_the_shipped_mui_spec_passes() -> None:
    checks = check_spec(MUI)
    assert failures(checks) == [] and not [c for c in checks if c.status == "warn"]
    split = next(c for c in checks if c.name == "guide split")
    assert "204 sections" in split.detail


def test_a_new_spec_is_a_commented_template_that_fails_until_filled(tmp_path: Path) -> None:
    folder = new_spec("lib-1-to-2", "lib@1", "lib@2", "Some Library", root=tmp_path)
    text = (folder / "migration.toml").read_text("utf-8")
    assert 'id = "lib@1->lib@2"' in text and 'library_name = "Some Library"' in text
    assert (folder / "guide" / "SOURCE.md").is_file()
    assert (folder / "tools" / "package.json").is_file()
    fails = failures(check_spec(folder))
    assert fails and fails[0].startswith("placeholders: still TODO: from_version")
    with pytest.raises(SpecToolError, match="already exists"):
        new_spec("lib-1-to-2", "lib@1", "lib@2", "Some Library", root=tmp_path)
    with pytest.raises(SpecToolError, match="lower-case"):
        new_spec("Lib_1", "lib@1", "lib@2", "x", root=tmp_path)
    with pytest.raises(SpecToolError, match="library@major"):
        new_spec("lib-x", "lib1", "lib@2", "x", root=tmp_path)


def test_loose_pins_a_bad_guide_pin_and_missing_files_fail(mui_copy: Path) -> None:
    edit(mui_copy, '"@mui/icons-material" = "5.18.0"', '"@mui/icons-material" = "^5.18.0"')
    edit(mui_copy, 'commit = "6b50143dcfc2aad56a37c9f2e1f14256e9a65c4e"', 'commit = "6b50143"')
    (mui_copy / "guide" / "troubleshooting.md").unlink()
    fails = failures(check_spec(mui_copy))
    assert "pins: not exact versions: @mui/icons-material@^5.18.0" in fails
    assert any(f.startswith("guide files: missing in") for f in fails)


def test_a_codemod_whose_tool_is_not_pinned_fails(mui_copy: Path) -> None:
    edit(mui_copy, 'tool = "mui-codemod"', 'tool = "other-tool"')
    assert any("names tool 'other-tool'" in f for f in failures(check_spec(mui_copy)))
    (mui_copy / "tools" / "package-lock.json").unlink()
    assert any(
        "needs package.json and package-lock.json" in f for f in failures(check_spec(mui_copy))
    )


def test_a_wrong_heading_level_finds_no_sections(mui_copy: Path) -> None:
    edit(mui_copy, "section_level = 2 ", "section_level = 5 ")
    edit(mui_copy, "change_level = 3 ", "change_level = 6 ")
    assert any(f.startswith("guide split: no sections") for f in failures(check_spec(mui_copy)))


def test_a_schema_error_is_reported_by_field(mui_copy: Path) -> None:
    edit(mui_copy, 'kind = "format"', 'kind = "reformat"')
    [fail] = failures(check_spec(mui_copy))
    assert fail.startswith("schema: rule_steps.")


def test_the_network_checks_ask_github_and_npm(mui_copy: Path) -> None:
    asked: list[str] = []

    def fetch(url: str) -> int:
        asked.append(url)
        return 404 if url.endswith("/5.0.0-alpha.177") else 200

    fails = failures(check_spec(mui_copy, network=True, fetch=fetch))
    assert asked[0].startswith("https://api.github.com/repos/mui/material-ui/commits/6b50143")
    assert "pins: npm answered 404 for @mui/lab@5.0.0-alpha.177" in fails


def test_the_cli_exits_non_zero_on_a_failing_spec(tmp_path: Path) -> None:
    runner = CliRunner()
    made = runner.invoke(
        app,
        [
            "spec",
            "new",
            "lib-1-to-2",
            "--from",
            "lib@1",
            "--to",
            "lib@2",
            "--library",
            "Lib",
            "--root",
            str(tmp_path),
        ],
    )
    assert made.exit_code == 0, made.output
    checked = runner.invoke(app, ["spec", "check", "lib-1-to-2", "--root", str(tmp_path)])
    assert checked.exit_code == 1 and "placeholders" in checked.output
    ok = runner.invoke(app, ["spec", "check", "mui-4-to-5"])
    assert ok.exit_code == 0 and "0 failed" in ok.output
