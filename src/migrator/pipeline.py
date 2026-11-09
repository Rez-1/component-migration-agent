"""One run, stage by stage: Scan -> Pre-check -> Rules -> Verify -> Report.

Each stage is a plain function; this module only wires them together (from M3 a
LangGraph graph takes this role and adds Repair and Review). M1 supports dry runs: the
whole run happens in a throwaway copy and the target repo is never touched.
"""

from __future__ import annotations

import re
import secrets
import shutil
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from migrator import __version__
from migrator.checks import CheatingReport, CheckInput, read_files, read_test_rules, run_checks
from migrator.config import (
    CaseConfig,
    ConfigError,
    RepoConfig,
    ResolvedRepoConfig,
    TrapList,
    load_traps,
    read_package_json,
    resolve_repo_config,
)
from migrator.configuration import BASELINE, Configuration, ensure_runnable
from migrator.cost import RunCost
from migrator.execs import CommandRunner, DeadlineRunner, LocalRunner
from migrator.migrations import MigrationSpec
from migrator.report import (
    ReportInput,
    RunMeta,
    Scorecard,
    build_scorecard,
    render_scorecard,
    write_json,
)
from migrator.rules import RulesInput, RulesResult, ToolsError, apply_rules, ensure_tools
from migrator.scan import ScanInput, UsageReport, scan
from migrator.scan.render import render_usage_report
from migrator.verify import PrecheckInput, VerifyInput, VerifyResult, precheck, verify
from migrator.workspace import create_dry_run_workspace

StageCallback = Callable[[str, str], None]  # (stage, message)


class RunError(RuntimeError):
    """The run cannot start: wrong repo, missing lockfile, no usages..."""


class RunOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo: Path
    spec: MigrationSpec
    run_dir: Path
    case: CaseConfig | None = None
    traps: Path | None = None
    keep_workspace: bool = False
    tools_cache: Path | None = None
    configuration: Configuration = BASELINE
    ceiling_s: float | None = None  # hard wall-clock ceiling for the whole run
    run_id: str | None = None  # default: the run folder's name


class RunResult(BaseModel):
    run_id: str
    run_dir: Path
    usage: UsageReport
    scorecard: Scorecard
    workspace: Path | None  # kept only with keep_workspace


def new_run_id() -> str:
    return f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-{secrets.token_hex(2)[:3]}"


def _major(version: str) -> int | None:
    m = re.search(r"\d+", version)
    return int(m.group()) if m else None


def check_detection(repo: Path, spec: MigrationSpec) -> None:
    """Refuse a repo that is not on the spec's old version or misses a precondition."""
    package = read_package_json(repo)
    deps: dict[str, str] = {}
    for section in ("dependencies", "devDependencies"):
        value = package.get(section)
        if isinstance(value, dict):
            deps.update({str(k): str(v) for k, v in value.items()})
    found = [p for p in spec.detection.packages if p in deps]
    if not found:
        raise RunError(
            f"{repo} does not depend on {' or '.join(spec.detection.packages)}, "
            f"so it is not on {spec.from_}"
        )
    for name in found:
        if _major(deps[name]) != spec.detection.major:
            raise RunError(f"{name} is {deps[name]}, not major version {spec.detection.major}")
    for pre in spec.preconditions:
        version = deps.get(pre.package)
        major = _major(version) if version else None
        if major is None or major < pre.min_major:
            raise RunError(f"{spec.id} needs {pre.package} >= {pre.min_major} (found {version})")


def resolve_config(repo: Path, spec: MigrationSpec, case: CaseConfig | None) -> ResolvedRepoConfig:
    override: RepoConfig | None = case.repo if case else None
    try:
        config = resolve_repo_config(repo, override, spec.source_globs, spec.exclude)
    except ConfigError as exc:
        raise RunError(str(exc)) from exc
    if case is not None:
        config = config.model_copy(update={"runner": case.runner})
    return config


def run_scan(repo: Path, spec: MigrationSpec, config: ResolvedRepoConfig) -> UsageReport:
    return scan(
        ScanInput(repo=repo, spec=spec, source_globs=config.source_globs, exclude=config.exclude)
    )


def write_usage_report(report: UsageReport, out_dir: Path) -> None:
    write_json(report, out_dir / "usage-report.json")
    (out_dir / "usage-report.md").write_text(render_usage_report(report), "utf-8")


def _tool_version(runner: CommandRunner, tool: str, cwd: Path) -> str | None:
    result = runner.run([tool, "--version"], cwd, timeout_s=30)
    return result.output.strip().removeprefix("v") if result.ok else None


def dry_run(
    opts: RunOptions,
    runner: CommandRunner | None = None,
    on_stage: StageCallback | None = None,
) -> RunResult:
    """A full run in a throwaway copy of the target repo; the repo itself is untouched."""
    configuration = opts.configuration
    ensure_runnable(configuration)
    runner = runner or LocalRunner()
    if opts.ceiling_s is not None:
        runner = DeadlineRunner(runner, opts.ceiling_s)
    say = on_stage or (lambda _stage, _msg: None)
    started = time.monotonic()
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    timings: dict[str, float] = {}
    repo = opts.repo.resolve()
    spec = configuration.apply_to(opts.spec)
    run_dir = opts.run_dir
    run_id = opts.run_id or run_dir.name
    logs = run_dir / "logs"

    def timed(stage: str, t0: float) -> None:
        timings[stage] = round(time.monotonic() - t0, 2)

    # Scan (on the repo itself: it only reads).
    t0 = time.monotonic()
    check_detection(repo, spec)
    config = resolve_config(repo, spec, opts.case)
    say("Scan", f"scanning {repo.name}")
    usage = run_scan(repo, spec, config)
    if not usage.affected_files():
        raise RunError(f"{repo} has no usages of {spec.from_} in {', '.join(config.source_globs)}")
    run_dir.mkdir(parents=True, exist_ok=True)
    write_usage_report(usage, run_dir)
    say("Scan", f"{usage.totals.affected_files} affected files, {usage.totals.old_usages} usages")
    timed("scan", t0)

    traps: TrapList | None = None
    traps_path = opts.traps or (opts.case.traps_path() if opts.case else None)
    if traps_path is not None:
        traps = load_traps(traps_path)

    parent = Path(tempfile.mkdtemp(prefix=f"migrator-{run_id}-"))
    workspace = create_dry_run_workspace(repo, parent / "workspace")
    node_version = _tool_version(runner, "node", workspace)
    npm_version = _tool_version(runner, config.package_manager, workspace)
    rules: RulesResult | None = None
    verified: VerifyResult | None = None
    final_usage: UsageReport | None = None
    cheating: CheatingReport | None = None
    # What the Pre-check verifies: the untouched workspace, for the cheating checks.
    untouched = read_files(workspace)
    try:
        t0 = time.monotonic()
        say("Pre-check", "installing and verifying the untouched workspace")
        pre = precheck(PrecheckInput(workspace=workspace, config=config, log_dir=logs), runner)
        timed("precheck", t0)
        say("Pre-check", pre.status if pre.status == "ok" else f"rejected: {pre.reason}")

        if pre.status == "ok":
            t0 = time.monotonic()
            say("Rules", "running the rule steps")
            try:
                tools = ensure_tools(spec, runner, opts.tools_cache)
            except ToolsError as exc:
                rules = RulesResult(
                    status="rules_failure", reason=str(exc), steps=[], changed_files=[]
                )
            else:
                rules = apply_rules(
                    RulesInput(
                        workspace=workspace,
                        spec=spec,
                        config=config,
                        affected_files=usage.affected_files(),
                        tools_dir=tools,
                        log_dir=logs,
                    ),
                    runner,
                )
            timed("rules", t0)
            say(
                "Rules",
                f"{len(rules.changed_files)} files changed"
                if rules.status == "ok"
                else f"Rules failure: {rules.reason}",
            )

        if rules is not None and rules.status == "ok":
            t0 = time.monotonic()
            say("Verify", "type-check, lint, tests")
            verified = verify(
                VerifyInput(
                    workspace=workspace,
                    commands=config.verify,
                    runner=config.runner,
                    log_dir=logs,
                    label="verify",
                    pre_existing=pre.pre_existing_failures,
                ),
                runner,
            )
            final_usage = run_scan(workspace, spec, config)
            timed("verify", t0)
            # Without the repair loop (M3) the final workspace is the one after Rules.
            after_rules = read_files(workspace)
            cheating = run_checks(
                CheckInput(
                    before=untouched,
                    after_rules=after_rules,
                    final=after_rules,
                    test_rules=read_test_rules(workspace),
                    precheck_totals=pre.test_totals,
                    final_totals=verified.test_totals,
                )
            )
            say(
                "Checks",
                f"{len(cheating.hits)} cheating-check hits, {len(cheating.notes)} "
                "Rules-layer notes",
            )
            say(
                "Verify",
                f"{len(verified.failures)} failures in {len(verified.failing_files())} files",
            )

        t0 = time.monotonic()
        meta = RunMeta(
            run_id=run_id,
            started_at=started_at,
            finished_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            duration_s=round(time.monotonic() - started, 1),
            migrator_version=__version__,
            node_version=node_version,
            npm_version=npm_version,
            timings_s=timings,
        )
        card = build_scorecard(
            ReportInput(
                usage=usage,
                precheck=pre,
                rules=rules,
                verify=verified,
                final_usage=final_usage,
                traps=traps,
                configuration=configuration.name,
                configuration_digest=configuration.digest(),
                cheating=cheating,
                cost=RunCost.no_llm(
                    configuration.cost.max_run_usd, configuration.cost.max_month_usd
                ),
                case=opts.case.id if opts.case else (traps.case if traps else None),
                meta=meta,
            )
        )
        write_json(card, run_dir / "scorecard.json")
        (run_dir / "scorecard.md").write_text(render_scorecard(card), "utf-8")
        say("Report", f"written to {run_dir}")
    finally:
        if not opts.keep_workspace:
            shutil.rmtree(parent, ignore_errors=True)
    return RunResult(
        run_id=run_id,
        run_dir=run_dir,
        usage=usage,
        scorecard=card,
        workspace=workspace if opts.keep_workspace else None,
    )
