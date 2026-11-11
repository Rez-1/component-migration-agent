"""The Pre-check and Verify stages.

Verify runs the case's (or the repo's) type-check, lint and test commands in the
workspace and turns their output into Failures. The Pre-check is the same verification
on the untouched workspace: a repo whose type-check already fails is rejected, and
lint and test failures it finds are recorded as Pre-existing failures, which later
verifies exclude.
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from migrator.config import (
    VERIFY_ORDER,
    ResolvedRepoConfig,
    Runner,
    VerifyCommands,
    VerifyName,
    read_package_json,
)
from migrator.execs import CommandResult, CommandRunner
from migrator.verify.karma import (
    find_karma_config,
    parse_karma_json,
    spec_files_for,
    write_wrapper,
)
from migrator.verify.parsers import (
    Failure,
    TestTotals,
    jest_suite_files,
    parse_eslint_json,
    parse_eslint_stylish,
    parse_jest_json,
    parse_ng_build,
    parse_tsc,
)
from migrator.workspace import install_command, list_files, record_install

_INSTALL_LOCK = threading.Lock()

__all__ = [
    "CommandOutcome",
    "Failure",
    "PrecheckInput",
    "PrecheckResult",
    "TestTotals",
    "VerifyInput",
    "VerifyResult",
    "install",
    "precheck",
    "verify",
]


class CommandOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    command: str
    exit_code: int
    duration_s: float
    failures: int = 0
    parsed_with: str = ""
    log: str = ""


class VerifyInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace: Path
    commands: VerifyCommands
    runner: Runner | None
    log_dir: Path
    label: str = "verify"
    pre_existing: list[Failure] = []
    # Narrow verify (the repair agent's run_verify): run only the tests related to
    # these files (``jest --findRelatedTests``). None runs every test.
    related_to: list[str] | None = None
    # Also measure test coverage into this folder (the Pre-check, M6).
    coverage_dir: Path | None = None


class VerifyResult(BaseModel):
    commands: list[CommandOutcome]
    failures: list[Failure]  # charged to the run
    pre_existing: list[Failure] = []  # Pre-existing failures seen again, excluded
    test_totals: TestTotals | None = None
    # The test files that ran; None when every test ran (or the runner didn't say).
    test_files_run: list[str] | None = None

    def failing_files(self) -> list[str]:
        return sorted({f.file for f in self.failures if f.file is not None})

    def failures_in(self, path: str) -> list[Failure]:
        return [f for f in self.failures if f.file == path]

    def command(self, name: str) -> CommandOutcome | None:
        return next((c for c in self.commands if c.name == name), None)


def _script_body(workspace: Path, command: str) -> str:
    """The command plus the package.json script it runs, to see which tool it calls."""
    words = command.split()
    script = None
    if words[:2] == ["npm", "test"] or words[:2] in (["yarn", "test"], ["pnpm", "test"]):
        script = "test"
    elif len(words) >= 3 and words[1] == "run":
        script = words[2]
    elif len(words) >= 2 and words[0] == "yarn":
        script = words[1]
    body = command
    if script:
        scripts = read_package_json(workspace).get("scripts")
        if isinstance(scripts, dict):
            body += " " + str(scripts.get(script, ""))
    return body


_TSC = re.compile(r"(?<![\w./-])((?:[\w./-]*/)?tsc)(?=\s|$)")


def incremental_typecheck(command: str, body: str) -> str:
    """``command`` with each tsc run incrementally (M6 speed-up 5), each with its own
    build-info file under the workspace's ``.migrator/``. A tsc named in the command
    gets the flags in place; a package script that runs a single tsc gets them appended.
    Anything else is left as it is."""
    count = 0

    def flags(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{m.group(1)} --incremental --tsBuildInfoFile .migrator/tsbuildinfo-{count}"

    direct = _TSC.sub(flags, command)
    if count:
        return direct
    script = body[len(command) :]
    if len(_TSC.findall(script)) == 1:
        return with_args(command, ["--incremental", "--tsBuildInfoFile", ".migrator/tsbuildinfo-1"])
    return command


def real_path(root: Path, rel: str) -> str | None:
    """``rel`` as it is spelled on disk under ``root``, or None if there is no such file.
    macOS's file system ignores case, so asking whether ``month.tsx`` exists says yes when
    only ``Month.tsx`` does; the failure must be charged to ``Month.tsx``, the path every
    file list has (M6, wps: failures charged to ``month.tsx`` were never repaired)."""
    folder, parts = root, []
    for part in Path(rel).parts:
        try:
            names = [e.name for e in os.scandir(folder)]
        except OSError:
            return None
        match = (
            part if part in names else next((n for n in names if n.lower() == part.lower()), None)
        )
        if match is None:
            return None
        parts.append(match)
        folder = folder / match
    return "/".join(parts) if folder.is_file() else None


def with_args(command: str, args: list[str]) -> str:
    """Append arguments to a command; ``npm run``/``npm test`` need ``--`` first."""
    sep = " -- " if command.startswith("npm ") and " -- " not in command else " "
    return command + sep + " ".join(args)


def _run_one(
    name: VerifyName, command: str, inp: VerifyInput, runner: CommandRunner
) -> tuple[CommandOutcome, list[Failure], TestTotals | None, list[str] | None]:
    ws = inp.workspace
    root = str(ws.resolve())
    inp.log_dir.mkdir(parents=True, exist_ok=True)
    log = inp.log_dir / f"{inp.label}-{name}.log"
    body = _script_body(ws, command)
    json_out: Path | None = None
    run_command = command
    if name == "typecheck" and inp.commands.typecheck_incremental:
        run_command = incremental_typecheck(command, body)
    if name == "lint" and "eslint" in body:
        json_out = (inp.log_dir / f"{inp.label}-eslint.json").resolve()
        run_command = with_args(command, ["-f", "json", "-o", str(json_out)])
    elif name == "test" and inp.runner == "jest":
        json_out = (inp.log_dir / f"{inp.label}-jest.json").resolve()
        args = ["--json", f"--outputFile={json_out}", "--testLocationInResults"]
        if inp.related_to is not None:
            args += ["--passWithNoTests", "--findRelatedTests", *inp.related_to]
        if inp.coverage_dir is not None:
            args += [
                "--coverage",
                "--coverageReporters=json-summary",
                f"--coverageDirectory={inp.coverage_dir.resolve()}",
            ]
        run_command = with_args(command, args)
    elif name == "test" and inp.runner == "karma":
        karma_config = find_karma_config(ws)
        if karma_config is None:
            failure = Failure(source="test", file=None, message="no karma.conf.js in the repo")
            return _skipped(name, command, "no karma config"), [failure], None, None
        wrapper, json_out = write_wrapper(ws, karma_config, inp.log_dir, inp.label)
        args = [f"--karma-config={wrapper}", "--watch=false", "--browsers=MigratorChromeHeadless"]
        if inp.related_to is not None:
            specs = spec_files_for(inp.related_to, lambda p: (ws / p).is_file())
            if not specs:  # nothing tests these files: nothing to run
                return _skipped(name, command, "no spec for these files"), [], None, []
            args += [f"--include={s}" for s in specs]
        run_command = with_args(command, args)
    elif name == "test" and inp.runner == "vitest":
        # Vitest's JSON reporter writes the same shape as Jest's (not yet exercised by a case).
        json_out = (inp.log_dir / f"{inp.label}-vitest.json").resolve()
        args = ["--reporter=json", f"--outputFile={json_out}"]
        if inp.coverage_dir is not None:
            args += [
                "--coverage.enabled=true",
                "--coverage.reporter=json-summary",
                f"--coverage.reportsDirectory={inp.coverage_dir.resolve()}",
            ]
        run_command = with_args(command, args)
    if json_out is not None:
        json_out.unlink(missing_ok=True)

    result: CommandResult = runner.run(run_command, ws, log_file=log)
    failures: list[Failure] = []
    totals: TestTotals | None = None
    suites: list[str] | None = None
    parsed_with = "exit code"
    if name == "typecheck":
        failures, parsed_with = parse_tsc(result.output, root), "tsc"
        angular = parse_ng_build(result.output, root)
        if angular:  # an Angular build (`ng build`, ngc): its own format, templates too
            failures, parsed_with = [*failures, *angular], "ng build"
    elif name == "lint":
        warnings = not result.ok  # --max-warnings tripped: warnings count
        if json_out is not None and json_out.is_file():
            failures = parse_eslint_json(json_out.read_text("utf-8"), root, warnings)
            parsed_with = "eslint json"
        else:
            failures, parsed_with = (
                parse_eslint_stylish(result.output, root, warnings),
                "eslint text",
            )
    elif name == "test" and inp.runner == "karma" and json_out is not None and json_out.is_file():
        spec_sources = [
            (rel, (ws / rel).read_text("utf-8", errors="replace"))
            for rel in list_files(ws, ["src/**/*.spec.ts", "projects/**/*.spec.ts"], [])
        ]
        failures, totals = parse_karma_json(
            json_out.read_text("utf-8"), root, lambda p: real_path(ws, p), spec_sources
        )
        if inp.related_to is not None:
            suites = sorted({f.test_file for f in failures if f.test_file})
        parsed_with = "karma json"
    elif json_out is not None and json_out.is_file():
        text = json_out.read_text("utf-8")
        failures, totals = parse_jest_json(text, root, lambda p: real_path(ws, p))
        if inp.related_to is not None:
            suites = jest_suite_files(text, root)
        parsed_with = f"{inp.runner} json"

    if not result.ok and not failures:
        why = "timed out" if result.timed_out else f"exited {result.exit_code}"
        failures = [
            Failure(
                source=name,
                file=None,
                message=f"`{command}` {why} without failures the Migrator could parse",
            )
        ]
    outcome = CommandOutcome(
        name=name,
        command=command,
        exit_code=result.exit_code,
        duration_s=result.duration_s,
        failures=len(failures),
        parsed_with=parsed_with,
        log=log.name,
    )
    return outcome, failures, totals, suites


def _skipped(name: VerifyName, command: str, why: str) -> CommandOutcome:
    return CommandOutcome(
        name=name,
        command=command,
        exit_code=0,
        duration_s=0.0,
        failures=0,
        parsed_with=f"not run: {why}",
        log="",
    )


def _order(f: Failure) -> tuple[int, str, int, str, str, str]:
    return (
        VERIFY_ORDER.index(f.source),
        f.file or "",
        f.line or 0,
        f.test_file or "",
        f.test_name or "",
        f.message,
    )


def verify(inp: VerifyInput, runner: CommandRunner) -> VerifyResult:
    """Run every configured verify command, in order, and collect the Failures."""
    known = {f.key() for f in inp.pre_existing}
    outcomes: list[CommandOutcome] = []
    charged: list[Failure] = []
    seen_again: list[Failure] = []
    totals: TestTotals | None = None
    suites: list[str] | None = None
    for name in VERIFY_ORDER:
        command = getattr(inp.commands, name)
        if not command:
            continue
        outcome, failures, cmd_totals, cmd_suites = _run_one(name, command, inp, runner)
        outcomes.append(outcome)
        totals = cmd_totals or totals
        suites = cmd_suites if cmd_suites is not None else suites
        for failure in failures:
            (seen_again if failure.key() in known else charged).append(failure)
    return VerifyResult(
        commands=outcomes,
        # Sorted: Jest runs suites in parallel and reports them in finishing order.
        failures=sorted(charged, key=_order),
        pre_existing=sorted(seen_again, key=_order),
        test_totals=totals,
        test_files_run=suites,
    )


# --------------------------------------------------------------------------- pre-check


def install(
    runner: CommandRunner,
    workspace: Path,
    config: ResolvedRepoConfig,
    *,
    frozen: bool,
    log_file: Path,
) -> CommandResult:
    """Install the workspace's packages and record what was installed."""
    command = install_command(config.package_manager, frozen, config.install_flags)
    # One install at a time in this process: parallel runs share the package cache
    # volume, and yarn v1's cache is not safe for concurrent writers.
    with _INSTALL_LOCK:
        result = runner.run(command, workspace, env=config.install_env or None, log_file=log_file)
    if result.ok:
        record_install(workspace, config.lockfile)
    return result


class PrecheckInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace: Path
    config: ResolvedRepoConfig
    log_dir: Path


class PrecheckResult(BaseModel):
    status: Literal["ok", "rejected"]
    reason: str | None = None
    install: CommandOutcome | None = None
    verify: VerifyResult | None = None
    # With coverage on (M6): every file the coverage report lists, True when a test ran
    # code in it. None when coverage was not measured (or its report is missing).
    covered: dict[str, bool] | None = None

    @property
    def pre_existing_failures(self) -> list[Failure]:
        return self.verify.failures if self.verify else []

    @property
    def test_totals(self) -> TestTotals | None:
        return self.verify.test_totals if self.verify else None


def precheck(inp: PrecheckInput, runner: CommandRunner) -> PrecheckResult:
    """Install and verify the untouched workspace."""
    log = inp.log_dir / "precheck-install.log"
    result = install(runner, inp.workspace, inp.config, frozen=True, log_file=log)
    installed = CommandOutcome(
        name="install",
        command=result.command,
        exit_code=result.exit_code,
        duration_s=result.duration_s,
        log=log.name,
    )
    if not result.ok:
        return PrecheckResult(
            status="rejected",
            reason=f"installing the repo's packages failed (exit {result.exit_code}); "
            f"see {log.name}",
            install=installed,
        )
    coverage_dir = inp.log_dir / "coverage" if inp.config.coverage else None
    verified = verify(
        VerifyInput(
            workspace=inp.workspace,
            commands=inp.config.verify,
            runner=inp.config.runner,
            log_dir=inp.log_dir,
            label="precheck",
            coverage_dir=coverage_dir,
        ),
        runner,
    )
    covered = None
    if coverage_dir is not None:
        report = inp.log_dir / f"precheck-{inp.config.runner}.json"
        covered = read_coverage(coverage_dir, inp.workspace, report)
    type_errors = [f for f in verified.failures if f.source == "typecheck"]
    if type_errors:
        files = sorted({f.file or "(no file)" for f in type_errors})
        return PrecheckResult(
            status="rejected",
            reason=(
                f"the type-check already fails before any change ({len(type_errors)} "
                f"failures in {', '.join(files[:5])}{'…' if len(files) > 5 else ''})"
            ),
            install=installed,
            verify=verified,
            covered=covered,
        )
    return PrecheckResult(status="ok", install=installed, verify=verified, covered=covered)


def read_coverage(
    coverage_dir: Path, workspace: Path, runner_report: Path | None = None
) -> dict[str, bool] | None:
    """``coverage-summary.json`` (Jest's and Vitest's json-summary reporter) as
    repo-relative path -> covered. A file counts as covered when a test ran at least one
    of its functions (just importing it runs only module-level code), or, for a file
    without functions, at least one of its lines."""
    path = coverage_dir / "coverage-summary.json"
    root = workspace.resolve()
    if not path.is_file():
        # Vitest 4 with its JSON reporter puts the coverage in that report
        # (``coverageMap``, Istanbul's per-file counts) and wrote no summary (M6).
        if runner_report is None or not runner_report.is_file():
            return None
        cmap = json.loads(runner_report.read_text("utf-8")).get("coverageMap")
        if not isinstance(cmap, dict):
            return None
        return _covered_from_map(cmap, root)
    data = json.loads(path.read_text("utf-8"))
    out: dict[str, bool] = {}
    for key, summary in data.items():
        if key == "total" or not isinstance(summary, dict):
            continue
        try:
            rel = Path(key).resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        functions = summary.get("functions") or {}
        lines = summary.get("lines") or {}
        if functions.get("total", 0):
            out[rel] = functions.get("covered", 0) > 0
        else:
            out[rel] = lines.get("covered", 0) > 0
    return dict(sorted(out.items()))


def _covered_from_map(cmap: dict[str, object], root: Path) -> dict[str, bool]:
    """The same rule from an Istanbul coverage map: ``f`` counts calls per function,
    ``s`` per statement."""
    out: dict[str, bool] = {}
    for key, entry in cmap.items():
        if not isinstance(entry, dict):
            continue
        try:
            rel = Path(str(entry.get("path") or key)).resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        functions = list((entry.get("f") or {}).values())
        statements = list((entry.get("s") or {}).values())
        out[rel] = any(n > 0 for n in functions) if functions else any(n > 0 for n in statements)
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- snapshots (M6)

# A failed test whose message is a snapshot mismatch: Jest's matcher line, or Vitest's.
# Inline snapshots are left out: updating them rewrites the test file itself.
_SNAPSHOT_FAILURE = re.compile(r"\.toMatchSnapshot\(|Snapshot .+ mismatched")


def is_snapshot_failure(f: Failure) -> bool:
    return f.source == "test" and bool(_SNAPSHOT_FAILURE.search(f.message))


def snapshot_only_test_files(result: VerifyResult) -> list[str]:
    """Test files whose every charged failure is a snapshot mismatch."""
    by_file: dict[str, list[Failure]] = {}
    for f in result.failures:
        if f.source == "test" and f.test_file:
            by_file.setdefault(f.test_file, []).append(f)
    return sorted(t for t, fs in by_file.items() if all(is_snapshot_failure(f) for f in fs))


class SnapshotRun(BaseModel):
    """What one snapshot update did: the test files whose snapshots were rewritten and
    now pass, their failures (removed from the result), and the snapshot files changed."""

    updated: dict[str, list[str]]  # test file -> the snapshot tests it rewrote
    changed_files: list[str]  # snapshot files whose content changed
    log: str


def update_snapshots(
    inp: VerifyInput,
    result: VerifyResult,
    runner: CommandRunner,
    snapshot_hashes: Callable[[], dict[str, str]],
) -> tuple[VerifyResult, SnapshotRun | None]:
    """The snapshot policy (M6): for each test file whose only failures are snapshot
    mismatches, the Migrator itself (never the repair agent) re-runs it with the
    runner's update flag. A file that passes afterwards loses its failures from the
    result; each rewritten snapshot is listed for a human to review. Every other test
    failure stays."""
    files = snapshot_only_test_files(result)
    command = inp.commands.test
    if not files or not command or inp.runner not in ("jest", "vitest"):
        return result, None
    inp.log_dir.mkdir(parents=True, exist_ok=True)
    log = inp.log_dir / f"{inp.label}-snapshots-update.log"
    json_out = (inp.log_dir / f"{inp.label}-snapshots-update.json").resolve()
    json_out.unlink(missing_ok=True)
    if inp.runner == "jest":
        args = ["--ci=false", "-u", "--json", f"--outputFile={json_out}",
                "--runTestsByPath", *files]  # fmt: skip
    else:
        args = ["-u", "--reporter=json", f"--outputFile={json_out}", *files]
    before = snapshot_hashes()
    runner.run(with_args(command, args), inp.workspace, log_file=log)
    after = snapshot_hashes()
    changed = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    if not json_out.is_file():
        return result, SnapshotRun(updated={}, changed_files=changed, log=log.name)
    still, _ = parse_jest_json(
        json_out.read_text("utf-8"), str(inp.workspace.resolve()), lambda p: True
    )
    failing_now = {f.test_file for f in still}
    fixed = [t for t in files if t not in failing_now]
    updated = {
        t: sorted({f.test_name or "" for f in result.failures if f.test_file == t}) for t in fixed
    }
    kept = [f for f in result.failures if f.test_file not in fixed]
    return (
        result.model_copy(update={"failures": kept}),
        SnapshotRun(updated=updated, changed_files=changed, log=log.name),
    )
