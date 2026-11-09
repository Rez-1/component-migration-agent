from __future__ import annotations

import json
from pathlib import Path

from migrator.config import ResolvedRepoConfig, VerifyCommands
from migrator.migrations import DependencyMapEntry, MigrationSpec
from migrator.rules import (
    RulesInput,
    apply_dependency_map,
    apply_rules,
    find_codemod_todos,
    parse_jscodeshift,
)
from migrator.workspace import record_install
from tests.conftest import FakeRunner

JSCODESHIFT = """\
Executing command: jscodeshift --transform preset-safe.js src/a.tsx src/b.tsx
Processing 2 files...
 OKK /ws/src/a.tsx
 NOC /ws/src/b.tsx
 ERR /ws/tsconfig.json Transformation error (Missing semicolon. (1:5))
Results:
"""


def test_parse_jscodeshift() -> None:
    lines = parse_jscodeshift(JSCODESHIFT)
    assert [p for p, _ in lines["OKK"]] == ["/ws/src/a.tsx"]
    assert [p for p, _ in lines["NOC"]] == ["/ws/src/b.tsx"]
    assert lines["ERR"][0][1].startswith("Transformation error")


def test_dependency_map_replaces_in_the_same_section() -> None:
    package: dict[str, object] = {
        "dependencies": {"react": "17.0.2", "@material-ui/core": "4.12.4"},
        "devDependencies": {"@material-ui/icons": "4.11.3", "jest": "29"},
    }
    notes = apply_dependency_map(
        package,
        [
            DependencyMapEntry(
                old="@material-ui/core",
                new={"@mui/material": "5.18.0", "@emotion/react": "11.14.0"},
            ),
            DependencyMapEntry(old="@material-ui/icons", new={"@mui/icons-material": "5.18.0"}),
            DependencyMapEntry(old="@material-ui/lab", new={"@mui/lab": "5.0.0-alpha.177"}),
        ],
    )
    assert package["dependencies"] == {
        "@emotion/react": "11.14.0",
        "@mui/material": "5.18.0",
        "react": "17.0.2",
    }
    assert package["devDependencies"] == {"@mui/icons-material": "5.18.0", "jest": "29"}
    assert "-@material-ui/core" in notes and "+@mui/lab@5.0.0-alpha.177" not in notes


def test_codemod_todos_are_only_the_new_marker_comments(tmp_path: Path) -> None:
    before = {"src/a.tsx": b"// TODO: old one\nconst a = 1;\n"}
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.tsx").write_text(
        "// TODO: old one\n/* FIXME checkout https://mui.com/x */\nconst a = 1; // plain\n"
    )
    todos = find_codemod_todos(before, tmp_path, ["src/a.tsx"], ["FIXME", "TODO"])
    assert [(t.line, t.text) for t in todos] == [(2, "/* FIXME checkout https://mui.com/x */")]


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "node_modules").mkdir()
    (ws / "src/a.tsx").write_text("import Button from '@material-ui/core/Button';\n")
    (ws / "src/b.tsx").write_text("export const b = 1;\n")
    (ws / "package.json").write_text(
        json.dumps({"dependencies": {"@material-ui/core": "4.12.4", "react": "17.0.2"}}, indent=2)
    )
    (ws / "package-lock.json").write_text("{}")
    record_install(ws, "package-lock.json")  # as the Pre-check leaves it
    return ws


def _config() -> ResolvedRepoConfig:
    return ResolvedRepoConfig(
        package_manager="npm",
        lockfile="package-lock.json",
        node=None,
        install_flags=[],
        source_globs=["src/**/*.tsx"],
        exclude=[],
        runner="jest",
        verify=VerifyCommands(),
    )


def _input(ws: Path, spec: MigrationSpec) -> RulesInput:
    return RulesInput(
        workspace=ws,
        spec=spec,
        config=_config(),
        affected_files=["src/a.tsx"],
        tools_dir=ws.parent / "tools",
        log_dir=ws.parent / "logs",
    )


def test_rule_steps_in_order_with_changes_found_by_hashing(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    ws = _workspace(tmp_path)

    def handler(cmd: str, cwd: Path) -> tuple[int, str]:
        if "v5.0.0/preset-safe" in cmd:
            assert cmd.endswith("src/a.tsx -- --verbose=2 --fail-on-error")
            (cwd / "src/a.tsx").write_text(
                "// FIXME: codemod could not migrate this\n"
                "import Button from '@mui/material/Button';\n"
            )
            return 0, " OKK src/a.tsx\n"
        if "codemod.js" in cmd:
            return 0, " NOC src/a.tsx\n"
        if cmd.startswith("npm install"):
            (cwd / "package-lock.json").write_text('{"v": 5}')
        return 0, ""

    runner = FakeRunner(handler)
    result = apply_rules(_input(ws, spec), runner)

    assert result.status == "ok", result.reason
    steps = {s.name: s for s in result.steps}
    assert result.steps[0].status == "skipped"  # first install: the Pre-check already did it
    assert result.steps[-1].status == "ok"
    assert steps["preset-safe"].changed_files == ["src/a.tsx"]
    assert steps["variant-prop"].changed_files == []
    assert steps["format"].status == "skipped"  # no Prettier or ESLint in package.json
    assert steps["dependencies"].changed_files == ["package.json"]
    assert result.steps[-1].changed_files == ["package-lock.json"]
    assert result.changed_files == ["package-lock.json", "package.json", "src/a.tsx"]
    assert [t.file for t in result.codemod_todos] == ["src/a.tsx"]
    package = json.loads((ws / "package.json").read_text())
    assert "@material-ui/core" not in package["dependencies"]
    assert package["dependencies"]["@mui/material"] == "5.18.0"
    # After the dependency bump the lockfile is out of date: a normal install, not npm ci.
    assert runner.commands[-1] == "npm install --no-audit --no-fund"
    assert sum("codemod.js" in c for c in runner.commands) == 4


def test_a_codemod_error_is_a_rules_failure(tmp_path: Path, spec: MigrationSpec) -> None:
    ws = _workspace(tmp_path)
    runner = FakeRunner(
        lambda cmd, _cwd: (
            (0, " ERR src/a.tsx Transformation error (Unexpected token)\n")
            if "codemod.js" in cmd
            else (0, "")
        )
    )
    result = apply_rules(_input(ws, spec), runner)
    assert result.status == "rules_failure"
    assert "preset-safe" in (result.reason or "")
    assert [s.name for s in result.steps] == ["install", "preset-safe"]


def test_a_codemod_that_processes_nothing_is_a_rules_failure(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    ws = _workspace(tmp_path)
    runner = FakeRunner(lambda _cmd, _cwd: (0, "Transform 'v5.0.0/preset-safe' not found"))
    result = apply_rules(_input(ws, spec), runner)
    assert result.status == "rules_failure"
    assert "processed no files" in (result.reason or "")


def test_a_failed_install_is_a_rules_failure(tmp_path: Path, spec: MigrationSpec) -> None:
    ws = _workspace(tmp_path)
    runner = FakeRunner(
        lambda cmd, _cwd: (
            (1, "ERESOLVE") if cmd.startswith("npm install") else (0, " NOC src/a.tsx")
        )
    )
    result = apply_rules(_input(ws, spec), runner)
    assert result.status == "rules_failure"
    assert result.steps[-1].kind == "install"
