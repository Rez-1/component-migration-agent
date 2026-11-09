from __future__ import annotations

import json
from pathlib import Path

from migrator.config import ResolvedRepoConfig, VerifyCommands
from migrator.verify import PrecheckInput, VerifyInput, precheck, verify
from migrator.verify.parsers import (
    Failure,
    parse_eslint_json,
    parse_eslint_stylish,
    parse_jest_json,
    parse_tsc,
    subject_candidates,
)
from tests.conftest import DATA, FakeRunner

FIXTURE_SOURCES = {
    "src/screens/Search.tsx",
    "src/screens/Settings.tsx",
    "src/screens/AccountDialog.tsx",
    "src/screens/ProfileCard.tsx",
    "src/screens/ResponsiveNav.tsx",
}


def test_tsc_output_from_the_baseline() -> None:
    failures = parse_tsc((DATA / "tsc-baseline.txt").read_text())
    assert len(failures) == 8
    assert len({f.file for f in failures}) == 6
    first = failures[0]
    assert (first.file, first.line, first.column, first.code) == (
        "src/screens/Dashboard.tsx",
        12,
        16,
        "TS2362",
    )
    overload = next(f for f in failures if f.file == "src/screens/Notifications.tsx")
    assert overload.message.startswith("No overload matches this call. Overload 1 of 2")


def test_tsc_strips_the_workspace_path_and_global_errors() -> None:
    out = (
        "/ws/src/a.ts(1,2): error TS1005: ';' expected.\n"
        "error TS5058: The specified path does not exist.\n"
    )
    failures = parse_tsc(out, "/ws")
    assert failures[0].file == "src/a.ts"
    assert failures[1].file is None and failures[1].code == "TS5058"


def test_eslint_json_errors_and_warnings() -> None:
    report = json.dumps(
        [
            {
                "filePath": "/ws/src/a.tsx",
                "messages": [
                    {
                        "ruleId": "no-unused-vars",
                        "severity": 2,
                        "message": "'x' unused",
                        "line": 3,
                        "column": 7,
                    },
                    {
                        "ruleId": "eqeqeq",
                        "severity": 1,
                        "message": "Expected '==='",
                        "line": 4,
                        "column": 1,
                    },
                ],
            },
            {"filePath": "/ws/src/b.tsx", "messages": []},
        ]
    )
    errors = parse_eslint_json(report, "/ws")
    assert [(f.file, f.line, f.code) for f in errors] == [("src/a.tsx", 3, "no-unused-vars")]
    assert len(parse_eslint_json(report, "/ws", include_warnings=True)) == 2


def test_eslint_stylish_fallback() -> None:
    out = (
        "\n/ws/src/a.tsx\n"
        "  3:7  error    'x' is assigned but never used  @typescript-eslint/no-unused-vars\n"
        "  4:1  warning  Unexpected console statement            no-console\n"
        "\n✖ 2 problems (1 error, 1 warning)\n"
    )
    failures = parse_eslint_stylish(out, "/ws")
    assert [(f.file, f.line, f.code) for f in failures] == [
        ("src/a.tsx", 3, "@typescript-eslint/no-unused-vars")
    ]


def test_subject_candidates() -> None:
    assert (
        subject_candidates("src/screens/__tests__/Search.test.tsx")[0] == "src/screens/Search.tsx"
    )
    assert "src/util.ts" in subject_candidates("src/util.spec.ts")


def test_jest_json_from_the_baseline() -> None:
    failures, totals = parse_jest_json(
        (DATA / "jest-baseline.json").read_text(), "/WS", lambda p: p in FIXTURE_SOURCES
    )
    assert len(failures) == 7
    assert (totals.tests_total, totals.tests_failed, totals.suites_failed) == (19, 7, 5)
    assert totals.tests_skipped == 0 and totals.snapshots_total == 0
    card = next(f for f in failures if f.test_file == "src/screens/__tests__/ProfileCard.test.tsx")
    assert card.file == "src/screens/ProfileCard.tsx"
    assert card.test_name == "ProfileCard › shows the name, role, email and initials"
    assert card.message == "TypeError: theme.spacing is not a function"
    assert "/WS" not in card.message


def test_jest_suite_that_fails_to_run() -> None:
    report = {
        "numTotalTests": 0,
        "numFailedTestSuites": 1,
        "numTotalTestSuites": 1,
        "testResults": [
            {
                "name": "/ws/src/a.test.ts",
                "status": "failed",
                "message": "  ● Test suite failed to run\n\n    SyntaxError",
                "assertionResults": [],
            }
        ],
    }
    failures, totals = parse_jest_json(json.dumps(report), "/ws", lambda p: p == "src/a.ts")
    assert [(f.file, f.test_name) for f in failures] == [("src/a.ts", "(suite)")]
    assert totals.suites_failed == 1


def _config(**verify: str) -> ResolvedRepoConfig:
    return ResolvedRepoConfig(
        package_manager="npm",
        lockfile="package-lock.json",
        node=None,
        install_flags=[],
        source_globs=["src/**/*.ts"],
        exclude=[],
        runner=None,
        verify=VerifyCommands(**verify),
    )


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text(
        '{"scripts": {"typecheck": "tsc", "lint": "eslint src"}}'
    )
    (tmp_path / "package-lock.json").write_text("{}")
    return tmp_path


def test_verify_excludes_pre_existing_failures(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    tsc = (
        "src/a.ts(3,1): error TS2322: Type 'x' is not assignable.\n"
        "src/b.ts(1,1): error TS2304: Cannot find name 'y'.\n"
    )
    runner = FakeRunner(lambda cmd, _cwd: (2, tsc) if "typecheck" in cmd else (0, ""))
    old = Failure(
        source="typecheck",
        file="src/a.ts",
        line=1,
        code="TS2322",
        message="Type 'x' is not assignable.",
    )
    result = verify(
        VerifyInput(
            workspace=ws,
            commands=VerifyCommands(typecheck="npm run typecheck"),
            runner=None,
            log_dir=tmp_path / "logs",
            pre_existing=[old],
        ),
        runner,
    )
    assert [f.file for f in result.failures] == ["src/b.ts"]
    assert [f.file for f in result.pre_existing] == ["src/a.ts"]
    assert result.failing_files() == ["src/b.ts"]


def test_a_failing_command_without_parseable_output_is_still_a_failure(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    runner = FakeRunner(lambda _cmd, _cwd: (1, "Segmentation fault"))
    result = verify(
        VerifyInput(
            workspace=ws,
            commands=VerifyCommands(test="npm test"),
            runner="jest",
            log_dir=tmp_path / "logs",
        ),
        runner,
    )
    assert len(result.failures) == 1
    assert result.failures[0].file is None
    assert "--json" in runner.commands[0] and " -- " in runner.commands[0]


def test_lint_gets_the_json_formatter_when_the_script_runs_eslint(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    runner = FakeRunner()
    verify(
        VerifyInput(
            workspace=ws,
            commands=VerifyCommands(lint="npm run lint"),
            runner=None,
            log_dir=tmp_path / "logs",
        ),
        runner,
    )
    assert runner.commands[0].startswith("npm run lint -- -f json -o ")


def test_precheck_rejects_a_repo_whose_type_check_fails(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    tsc = "src/a.ts(3,1): error TS2322: Type 'x' is not assignable.\n"
    runner = FakeRunner(lambda cmd, _cwd: (2, tsc) if "typecheck" in cmd else (0, ""))
    result = precheck(
        PrecheckInput(
            workspace=ws, config=_config(typecheck="npm run typecheck"), log_dir=tmp_path / "l"
        ),
        runner,
    )
    assert result.status == "rejected"
    assert "type-check already fails" in (result.reason or "")
    assert runner.commands[0] == "npm ci --no-audit --no-fund"


def test_precheck_records_lint_failures_as_pre_existing(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    lint = "\n/x/src/a.ts\n  1:1  error  bad  no-bad\n"
    runner = FakeRunner(lambda cmd, _cwd: (1, lint) if "lint" in cmd else (0, ""))
    result = precheck(
        PrecheckInput(
            workspace=ws,
            config=_config(typecheck="npm run typecheck", lint="npm run lint"),
            log_dir=tmp_path / "l",
        ),
        runner,
    )
    assert result.status == "ok"
    assert [f.code for f in result.pre_existing_failures] == ["no-bad"]


def test_precheck_rejects_when_install_fails(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    runner = FakeRunner(lambda cmd, _cwd: (1, "ERESOLVE") if cmd.startswith("npm ci") else (0, ""))
    result = precheck(PrecheckInput(workspace=ws, config=_config(), log_dir=tmp_path / "l"), runner)
    assert result.status == "rejected"
    assert result.verify is None
