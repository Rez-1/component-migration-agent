from __future__ import annotations

from pathlib import Path

from migrator.migrations import MigrationSpec
from migrator.scan import ScanInput, scan
from migrator.scan.parser import dialect_for, parse_file
from migrator.scan.render import render_usage_report
from migrator.scan.teams import Teams, load_teams, parse_codeowners
from tests.conftest import FIXTURE

OLD = lambda m: m.startswith("@material-ui/")  # noqa: E731

SNIPPET = b"""\
import React from 'react';
import Button from '@material-ui/core/Button';
import { makeStyles, Theme } from '@material-ui/core/styles';
import type { GridProps } from '@material-ui/core';
import { Link as MuiLink, type TypographyProps } from '@material-ui/core';
import * as Icons from '@material-ui/icons';
export { Paper } from '@material-ui/core';

const useStyles = makeStyles((theme: Theme) => ({ root: { padding: theme.spacing(1) } }));

export function App(): JSX.Element {
  const classes = useStyles();
  // TODO: tidy up
  return (
    <div className={classes.root}>
      <Button color="primary">Go</Button>
      <MuiLink href="#">Home</MuiLink>
      <Icons.Add />
    </div>
  );
}
"""


def test_parser_finds_imports_jsx_and_calls() -> None:
    parsed = parse_file(SNIPPET, "src/App.tsx", OLD)
    got = [(u.kind, u.symbol, u.local_name, u.type_only) for u in parsed.usages]
    assert got == [
        ("import", "Button", "Button", False),
        ("import", "makeStyles", "makeStyles", False),
        ("import", "Theme", "Theme", False),
        ("import", "GridProps", "GridProps", True),
        ("import", "Link", "MuiLink", False),
        ("import", "TypographyProps", "TypographyProps", True),
        ("import", "*", "Icons", False),
        ("import", "Paper", "Paper", False),
        ("call", "makeStyles", "makeStyles", False),
        ("jsx", "Button", "Button", False),
        ("jsx", "Link", "MuiLink", False),
        ("jsx", "Add", "Icons.Add", False),
    ]
    button = parsed.usages[0]
    assert (button.line, button.column, button.module) == (2, 8, "@material-ui/core/Button")
    assert [c.text for c in parsed.comments] == ["// TODO: tidy up"]
    assert not parsed.has_syntax_errors


def test_parser_ignores_other_modules_and_local_names() -> None:
    src = b"import { useState } from 'react';\nconst Button = () => null;\nconst x = <Button />;\n"
    assert parse_file(src, "a.tsx", OLD).usages == []


def test_ts_files_use_the_typescript_grammar() -> None:
    assert dialect_for("src/theme.ts") == "ts"
    assert dialect_for("src/App.tsx") == "tsx"
    src = (
        b"import { fade } from '@material-ui/core/styles';\nconst n = <number>x; fade('#fff', 1);\n"
    )
    parsed = parse_file(src, "src/a.ts", OLD)
    assert not parsed.has_syntax_errors
    assert [u.kind for u in parsed.usages] == ["import", "call"]


def test_codeowners_last_match_wins() -> None:
    teams = Teams(
        parse_codeowners(
            "# comment\n/src/ @platform\n/src/screens/Dash* @insights\n*.md @docs\nlib/ @lib\n"
        )
    )
    assert teams.team_for("src/screens/Dashboard.tsx") == "@insights"
    assert teams.team_for("src/screens/Other.tsx") == "@platform"
    assert teams.team_for("docs/deep/README.md") == "@docs"
    assert teams.team_for("packages/lib/x.ts") == "@lib"
    assert teams.team_for("other/x.ts") == "(unowned)"


def test_teams_fall_back_to_top_level_folders(tmp_path: Path) -> None:
    teams = load_teams(tmp_path)
    assert teams.source == "folder"
    assert teams.team_for("app/x.ts") == "app/"
    assert teams.team_for("x.ts") == "(root)"


def _scan(repo: Path, spec: MigrationSpec):  # type: ignore[no-untyped-def]
    return scan(
        ScanInput(repo=repo, spec=spec, source_globs=["src/**/*.ts", "src/**/*.tsx"], exclude=[])
    )


def test_scan_small_repo(tmp_path: Path, spec: MigrationSpec) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/App.tsx").write_bytes(SNIPPET)
    (tmp_path / "src/New.tsx").write_text("import Button from '@mui/material/Button';\n")
    (tmp_path / "src/plain.ts").write_text("export const x = 1;\n")
    report = _scan(tmp_path, spec)
    t = report.totals
    assert (t.files_scanned, t.affected_files, t.old_usages, t.new_usages) == (3, 1, 12, 1)
    assert report.affected_files() == ["src/App.tsx"]
    # Button's "Remove span and label" has no ✅, so the <Button> element counts for repair;
    # import statements never do.
    app = report.file("src/App.tsx")
    assert app is not None
    assert "v5-component-changes#button/remove-span-and-label" in app.expected_repair
    assert t.expected_repair + t.expected_by_codemods == t.old_usages
    assert report.by_team[0].source == "folder"


def test_scan_fixture_is_deterministic(spec: MigrationSpec) -> None:
    first = _scan(FIXTURE, spec)
    second = _scan(FIXTURE, spec)
    assert first.model_dump(exclude={"meta"}) == second.model_dump(exclude={"meta"})
    assert first.totals.affected_files == 12
    assert first.totals.new_usages == 0
    teams = {t.team: t.affected_files for t in first.by_team}
    assert teams == {
        "@team-platform": 5,
        "@team-insights": 2,
        "@team-accounts": 3,
        "@team-discovery": 2,
    }


def test_usage_report_markdown(spec: MigrationSpec) -> None:
    md = render_usage_report(_scan(FIXTURE, spec))
    assert md.startswith("# Usage report: mui4-fixture-app")
    assert "**12 affected files" in md
    assert "| @team-accounts | 3 |" in md
    assert "## Most-used symbols" in md
