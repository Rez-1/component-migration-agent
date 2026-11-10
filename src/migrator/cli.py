"""The ``migrator`` command line (Typer commands only; the work lives in the stages)."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from migrator.config import ConfigError, load_case
from migrator.configuration import (
    Configuration,
    ConfigurationError,
    ensure_runnable,
    find_configuration,
)
from migrator.cost import Ledger, LedgerPreflight, PlannedExperiment, default_ledger_path
from migrator.evals import (
    DEFAULT_CEILING_S,
    DEFAULT_REPEATS,
    EvalError,
    ExperimentPlan,
    RunEvent,
    Split,
    experiment_dir,
    load_cases,
    now,
    read_manifest,
    run_experiment,
)
from migrator.evals.hillclimb import (
    ClimbError,
    check_harness,
    keep_verdict,
    matching_baseline,
    read_state,
    record_round,
    sync_cases,
    write_state,
)
from migrator.evals.retrieval import RetrievalError
from migrator.evals.retrieval import measure as measure_retrieval
from migrator.evals.retrieval import render as render_retrieval
from migrator.evals.summary import build_summary, write_summary
from migrator.execs import LocalRunner, Sandbox, docker_available
from migrator.migrations import UnknownMigrationError, available_specs, find_spec
from migrator.pipeline import (
    PausedRun,
    RunError,
    RunOptions,
    RunResult,
    check_detection,
    find_run_dir,
    new_run_id,
    resolve_config,
    resume_run,
    run_scan,
    start_run,
    write_usage_report,
)
from migrator.pr import PrError, open_pr, plan_pr
from migrator.report import Scorecard, traps_line, usd
from migrator.review import AutoReviewer, Reviewer, RichReviewer
from migrator.tracing import describe, flush, install_redaction, tracing_settings
from migrator.workspace import RUN_FILES_DIR, run_files_ignored

app = typer.Typer(
    help="The Migrator: moves a target repo from one component-library version to the next.",
    no_args_is_help=True,
    add_completion=False,
)
eval_app = typer.Typer(
    help="Experiments over eval cases, and their summaries.", no_args_is_help=True
)
app.add_typer(eval_app, name="eval")
console = Console()
err = Console(stderr=True)

RepoArg = Annotated[
    Path, typer.Argument(exists=True, file_okay=False, resolve_path=True, help="The target repo.")
]
CaseOpt = Annotated[
    Path | None,
    typer.Option(
        "--case",
        exists=True,
        dir_okay=False,
        help="A case.toml: its [repo] table overrides migrate.toml; its traps are scored.",
    ),
]


def _fail(message: str) -> typer.Exit:
    err.print(f"[bold red]error:[/] {message}")
    return typer.Exit(code=2)


def _default_run_dir(run_id: str) -> Path:
    return Path.cwd() / "runs" / run_id


@app.command("scan")
def scan_command(
    repo: RepoArg,
    from_: Annotated[str, typer.Option("--from", help="Old version, such as mui@4.")] = "mui@4",
    to: Annotated[str, typer.Option("--to", help="New version, such as mui@5.")] = "mui@5",
    case: CaseOpt = None,
    out: Annotated[
        Path | None, typer.Option(help="Folder for usage-report.json and .md (default runs/<id>/).")
    ] = None,
) -> None:
    """Write the usage report for a target repo, before any change."""
    try:
        spec = find_spec(from_, to)
        case_config = load_case(case) if case else None
        check_detection(repo, spec)
        config = resolve_config(repo, spec, case_config)
        report = run_scan(repo, spec, config)
    except (UnknownMigrationError, RunError, ConfigError) as exc:
        raise _fail(str(exc)) from exc
    out_dir = out or _default_run_dir(f"scan-{new_run_id()}")
    write_usage_report(report, out_dir)
    t = report.totals
    console.print(
        f"[bold]{t.affected_files} affected files[/], {t.old_usages} usages of {from_}, "
        f"{t.new_usages} of {to} ({t.files_scanned} files scanned)."
    )
    console.print(
        f"Codemods expected to handle {t.expected_by_codemods} of {t.old_usages} usages; "
        f"{t.expected_repair} usages in {t.expected_repair_files} files may need repair."
    )
    table = Table("Team", "Affected files", "Usages", "Expected repair")
    for team in report.by_team:
        table.add_row(
            team.team,
            str(team.affected_files),
            str(team.usages),
            f"{team.expected_repair_usages} in {team.expected_repair_files} files",
        )
    console.print(table)
    console.print(f"Usage report: {out_dir / 'usage-report.md'}")


def _print_scorecard(card: Scorecard, run_dir: Path) -> None:
    h = card.headline
    share = h.migrated_without_human
    if card.status != "completed":
        console.print(f"[bold red]{card.status.replace('_', ' ')}:[/] {card.reason}")
    table = Table("", "This run", title=f"Scorecard · {card.configuration}")
    table.add_row(
        "Clean run",
        "[green]yes[/]"
        if h.clean_run
        else f"[red]no[/] ({h.failures} failures in {h.failing_files} files)",
    )
    table.add_row(
        "Migrated without a human", f"{share.count} / {share.total} ({round(share.share * 100)}%)"
    )
    for outcome, n in h.outcomes.items():
        if n:
            table.add_row(f"  {outcome}", str(n))
    table.add_row("Regressions", str(h.regressions))
    table.add_row("Codemod TODOs", str(h.codemod_todos))
    if h.traps:
        table.add_row("Traps", traps_line(h.traps))
    console.print(table)
    console.print(f"Scorecard: {run_dir / 'scorecard.md'}")


def _on_stage(stage: str, message: str) -> None:
    console.log(f"[bold]{stage}[/] {message}")


def _caps_confirmed_marker() -> Path:
    return default_ledger_path().parent / "caps-confirmed"


def confirm_caps_once(configuration: Configuration, run_cap: float) -> None:
    """The first LLM-using command on a machine shows the caps and asks once (#12).

    Non-interactive use must pass --max-cost (checked by the caller)."""
    marker = _caps_confirmed_marker()
    if marker.exists():
        return
    console.print(
        f"[bold]{configuration.name}[/] calls a model. Cost caps (USD, Anthropic's prices): "
        f"{usd(run_cap)} per run, {usd(configuration.cost.max_month_usd)} per month on this "
        f"machine (ledger: {default_ledger_path()}). The ledger only sees this machine: set a "
        "monthly spend limit in the Anthropic Console to cover every machine."
    )
    if not typer.confirm("Run with these caps?", default=False):
        raise typer.Exit(code=1)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(now(), "utf-8")


def _check_max_cost(max_cost: float | None) -> None:
    if max_cost is not None and not (math.isfinite(max_cost) and max_cost > 0):
        raise _fail("--max-cost must be a positive number of USD (there is no unlimited)")


def _finish_run(result: RunResult | PausedRun) -> None:
    if isinstance(result, PausedRun):
        console.print(
            f"Paused at the hand-off of [bold]{result.payload.path}[/]. Continue with: "
            f"[bold]migrator resume {result.run_dir}[/]"
        )
        return
    if result.workspace:
        console.print(f"Workspace kept at {result.workspace}")
    _print_scorecard(result.scorecard, result.run_dir)
    meta = result.scorecard.meta
    if result.branch:
        console.print(
            f"Branch [bold]{result.branch}[/] has {len(meta.commits)} commit(s) on top of "
            f"{meta.base_branch or 'the starting commit'}:"
        )
        for c in meta.commits:
            console.print(f"  {c.sha[:8]} {c.title}")
        console.print(
            f"PR body: {result.run_dir / 'pr-body.md'}. To push the branch and open a PR on "
            f"your own repo or fork: [bold]migrator pr {result.run_dir} --open[/] "
            "(without --open it shows what it would do)."
        )
    if result.scorecard.status != "completed":
        raise typer.Exit(code=1)


MaxCostOpt = Annotated[
    float | None,
    typer.Option(
        "--max-cost",
        help="USD cap for this run, replacing the configuration's run cap (never unlimited). "
        "Required when not run from a terminal.",
    ),
]


SandboxChoice = Annotated[
    str,
    typer.Option(
        "--sandbox",
        help="Where install, Verify and the repair agent's run_verify execute: docker (the "
        "pinned node image, no network during Verify), local (this machine, your "
        "permissions) or auto (Docker when it is running, else local with a warning).",
    ),
]


def _resolve_sandbox(choice: str, *, allow_auto: bool = True) -> Sandbox:
    if choice == "docker":
        return "docker"
    if choice == "local":
        return "local"
    if choice != "auto" or not allow_auto:
        raise _fail(f"--sandbox must be docker{', local or auto' if allow_auto else ' or local'}")
    if docker_available():
        return "docker"
    err.print(
        "[yellow]warning:[/] Docker is not running, so commands run on this machine with "
        "your permissions, including the tests that execute code the repair agent edited. "
        "Start Docker for the sandbox, or pass --sandbox local to choose this explicitly."
    )
    return "local"


def _print_tracing() -> None:
    line = describe(tracing_settings())
    if line:
        install_redaction()  # no absolute local paths leave this machine (M6)
        console.print(line + " Local paths are made relative before upload.")


@app.command("init")
def init_command(
    repo: Annotated[Path, typer.Argument(help="The target repo (default: this folder).")] = Path(),
    force: Annotated[bool, typer.Option(help="Overwrite an existing migrate.toml.")] = False,
    stdout: Annotated[
        bool, typer.Option("--stdout", help="Print the file instead of writing it.")
    ] = False,
) -> None:
    """Detect the repo's package manager, Node, test runner, verify commands and source
    globs, and write a commented migrate.toml to check. No LLM, no network."""
    from migrator.init import InitError, detect, render_migrate_toml, write_migrate_toml

    repo = repo.resolve()
    try:
        if stdout:
            result = detect(repo)
            print(render_migrate_toml(result), end="")
        else:
            path, result = write_migrate_toml(repo, force=force)
            console.print(f"Wrote {path}. Check every value before the first run.")
    except (InitError, ConfigError) as exc:
        raise _fail(str(exc)) from exc
    if result.todos:
        err.print(f"[bold]{len(result.todos)} TODO[/] (not detected, fill in by hand):")
        for todo in result.todos:
            err.print(f"  - {todo}")


@app.command("migrate")
def migrate_command(
    repo: RepoArg,
    from_: Annotated[str, typer.Option("--from", help="Old version, such as mui@4.")],
    to: Annotated[str, typer.Option("--to", help="New version, such as mui@5.")],
    dry_run_: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Run everything in a throwaway copy; the repo is untouched."
        ),
    ] = False,
    branch: Annotated[
        str | None,
        typer.Option(help="The branch a real run commits to (default migrate/<library>-v<N>)."),
    ] = None,
    sandbox: SandboxChoice = "auto",
    config: Annotated[
        str,
        typer.Option(
            help="A configuration name in evals/configs/ or a .toml path. The default, "
            "baseline, is rules only and calls no model."
        ),
    ] = "baseline",
    max_cost: MaxCostOpt = None,
    no_review: Annotated[
        bool, typer.Option("--no-review", help="Revert every hand-off instead of asking.")
    ] = False,
    case: CaseOpt = None,
    traps: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, help="A traps.yaml to score.")
    ] = None,
    run_dir: Annotated[
        Path | None,
        typer.Option(
            help="Where run files go (default <repo>/.migrator/runs/<run-id>/ for a real "
            "run, runs/<run-id>/ for a dry run)."
        ),
    ] = None,
    keep_workspace: Annotated[
        bool,
        typer.Option(help="Keep the workspace (a dry run's copy, a real run's worktree)."),
    ] = False,
    root: Annotated[
        Path | None, typer.Option(help="The folder holding evals/configs (default: here).")
    ] = None,
) -> None:
    """Migrate a target repo: Scan, Pre-check, Rules, Verify, Repair, Review, Report.

    A real run (the default) needs a clean git working tree. It works in a git worktree
    on a new branch and commits each stage there (Rules, the repair agent, edits at
    Review); your working tree is never touched. --dry-run uses a throwaway copy."""
    _check_max_cost(max_cost)
    try:
        spec = find_spec(from_, to)
        case_config = load_case(case) if case else None
        configuration = find_configuration(config, _repo_root(root) / "evals" / "configs")
        ensure_runnable(configuration)
    except (UnknownMigrationError, ConfigError, ConfigurationError) as exc:
        raise _fail(str(exc)) from exc
    if configuration.uses_llm:
        if max_cost is None and not sys.stdin.isatty():
            raise _fail(
                f"{configuration.name} calls a model: pass --max-cost when not in a terminal"
            )
        confirm_caps_once(configuration, max_cost or configuration.cost.max_run_usd)
    run_id = new_run_id()
    real = not dry_run_
    default_dir = repo / RUN_FILES_DIR / "runs" / run_id if real else _default_run_dir(run_id)
    target = (run_dir or default_dir).resolve()
    chosen = _resolve_sandbox(sandbox)
    opts = RunOptions(
        repo=repo,
        spec=spec,
        run_dir=target,
        case=case_config,
        traps=traps,
        keep_workspace=keep_workspace,
        configuration=configuration,
        run_id=run_id,
        max_run_usd=max_cost,
        mode="cli",
        sandbox=chosen,
        real=real,
        branch=branch,
    )
    console.print(
        f"Run [bold]{run_id}[/] · {'real run' if real else 'dry run'} · sandbox {chosen} · "
        f"configuration [bold]{configuration.name}[/]"
        + (
            f" · cost cap {usd(max_cost or configuration.cost.max_run_usd)} per run, "
            f"{usd(configuration.cost.max_month_usd)} per month"
            if configuration.uses_llm
            else " · rules only, no model calls"
        )
    )
    _print_tracing()
    reviewer: Reviewer = AutoReviewer() if no_review else RichReviewer(console)
    try:
        result = start_run(opts, on_stage=_on_stage, reviewer=reviewer)
    except (RunError, ConfigError) as exc:
        raise _fail(str(exc)) from exc
    finally:
        flush()
    if real and not run_files_ignored(repo):
        console.print(
            f"[yellow]Note:[/] git does not ignore {RUN_FILES_DIR}/ in {repo}. The run files "
            f"are never committed, but add `{RUN_FILES_DIR}/` to .gitignore (or "
            ".git/info/exclude) so they stay out of `git status`."
        )
    _finish_run(result)


@app.command("resume")
def resume_command(
    run_id: Annotated[str, typer.Argument(help="The run to continue (or its run folder).")],
    accept_changes: Annotated[
        bool,
        typer.Option(
            "--accept-changes",
            help="Continue although files changed while paused (they count as the human's).",
        ),
    ] = False,
    no_review: Annotated[
        bool, typer.Option("--no-review", help="Revert the remaining hand-offs.")
    ] = False,
) -> None:
    """Continue a run paused for review, from its checkpoint."""
    reviewer: Reviewer = AutoReviewer() if no_review else RichReviewer(console)
    try:
        run_folder = find_run_dir(run_id)
        result = resume_run(
            run_folder, reviewer=reviewer, accept_changes=accept_changes, on_stage=_on_stage
        )
    except RunError as exc:
        raise _fail(str(exc)) from exc
    finally:
        flush()
    _finish_run(result)


@app.command("pr")
def pr_command(
    run_id: Annotated[str, typer.Argument(help="A finished real run (its id or run folder).")],
    open_: Annotated[
        bool,
        typer.Option(
            "--open",
            help="Push the branch and open the PR with gh. Without it, only show what "
            "would happen.",
        ),
    ] = False,
    remote: Annotated[str, typer.Option(help="The git remote to push to.")] = "origin",
    base: Annotated[
        str | None, typer.Option(help="The PR's base branch (default: where the run started).")
    ] = None,
    draft: Annotated[bool, typer.Option(help="Open the PR as a draft.")] = False,
) -> None:
    """Open a pull request for a real run's branch, on your own repo or fork only.

    Refuses dry runs, eval runs, unfinished runs, non-GitHub remotes, and remotes whose
    owner is not the account `gh` is logged in as."""
    runner = LocalRunner()
    try:
        plan = plan_pr(find_run_dir(run_id), runner, remote=remote, base=base, draft=draft)
    except RunError as exc:
        raise _fail(str(exc)) from exc
    if not open_:
        for line in plan.describe():
            console.print(line, markup=False, highlight=False)
        console.print("Nothing was pushed. Add --open to do it.")
        return
    try:
        url = open_pr(plan, runner)
    except PrError as exc:
        raise _fail(str(exc)) from exc
    console.print(f"Opened {url}")


def _repo_root(root: Path | None) -> Path:
    return (root or Path.cwd()).resolve()


RootOpt = Annotated[
    Path | None,
    typer.Option(help="The repository root holding evals/ (default: the current folder)."),
]
ResultsOpt = Annotated[
    Path | None,
    typer.Option(help="Where experiments are written (default <root>/runs/evals, git-ignored)."),
]


# The judge shares M6's month cap (evals/configs/m6-*.toml).
M6_MONTH_CAP_USD = 50.0


@eval_app.command("run")
def eval_run(
    split: Annotated[str, typer.Option(help="dev or held-out.")] = "dev",
    config: Annotated[
        str, typer.Option(help="A configuration name in evals/configs/, or a .toml path.")
    ] = "baseline",
    case: Annotated[
        str | None, typer.Option(help="Run only this case (it must be in the split).")
    ] = None,
    repeats: Annotated[int, typer.Option(min=1, help="Runs per case.")] = DEFAULT_REPEATS,
    resume: Annotated[
        str | None, typer.Option(help="Continue an experiment, e.g. dev/baseline.")
    ] = None,
    max_cost: Annotated[
        float | None,
        typer.Option(
            "--max-cost",
            help="USD cap for the experiment; required for configurations that call a model.",
        ),
    ] = None,
    timeout_s: Annotated[
        float, typer.Option(help="Hard wall-clock ceiling per run, in seconds.")
    ] = DEFAULT_CEILING_S,
    sandbox: Annotated[
        str,
        typer.Option(
            "--sandbox",
            help="docker (default: the pinned node image per case, no network during "
            "Verify) or local (this machine).",
        ),
    ] = "docker",
    root: RootOpt = None,
    results_dir: ResultsOpt = None,
    cases_dir: Annotated[
        Path | None,
        typer.Option(
            help="Folder of cases (default <root>/evals/cases; M6's real repos are in "
            "<root>/evals/m6-cases)."
        ),
    ] = None,
    parallel: Annotated[
        int,
        typer.Option(
            min=1,
            max=4,
            help="Repeat runs of one case at the same time (each in its own workspace and "
            "container; 2 suits a 10-core machine).",
        ),
    ] = 2,
    precheck_cache: Annotated[
        bool,
        typer.Option(
            help="Reuse each case's install and Pre-check across runs (cached under "
            "~/.cache/migrator/precheck, keyed on the repo's files, config and Node image)."
        ),
    ] = True,
    run_container: Annotated[
        bool,
        typer.Option(
            help="One long-lived container per run, commands by docker exec, instead of a "
            "new container per command."
        ),
    ] = False,
) -> None:
    """Run an experiment: every case in a split under one configuration, N runs each."""
    base = _repo_root(root)
    results = (results_dir or base / "runs" / "evals").resolve()
    configs = base / "evals" / "configs"
    if split not in ("dev", "held-out"):
        raise _fail(f"--split must be dev or held-out, not {split!r}")
    split_name: Split = "dev" if split == "dev" else "held-out"
    try:
        configuration = find_configuration(config, configs)
        ensure_runnable(configuration)
        baseline = (
            find_configuration("baseline", configs)
            if (configs / "baseline.toml").is_file()
            else None
        )
        cases = load_cases((cases_dir or base / "evals" / "cases").resolve(), split_name, case)
        plan = ExperimentPlan(
            root=base,
            results_dir=results,
            split=split_name,
            configuration=configuration,
            cases=cases,
            repeats=repeats,
            resume=resume,
            baseline_configuration=baseline,
            max_cost_usd=max_cost,
            ceiling_s=timeout_s,
            sandbox=_resolve_sandbox(sandbox, allow_auto=False),
            parallel=parallel,
            precheck_cache=precheck_cache,
            run_container=run_container,
        )
    except (ConfigurationError, ConfigError, EvalError) as exc:
        raise _fail(str(exc)) from exc
    _check_max_cost(max_cost)
    console.print(
        f"[bold]{configuration.name}[/] on {len(cases)} {split} case(s) × {repeats} runs "
        f"· run cap {usd(configuration.cost.max_run_usd)}, month cap "
        f"{usd(configuration.cost.max_month_usd)}"
        + (f", experiment cap {usd(max_cost)}" if max_cost is not None else "")
        + f" · sandbox {plan.sandbox}"
    )
    if configuration.uses_llm:
        ledger = Ledger()
        _estimate, how = LedgerPreflight(ledger).estimate_with_advisor(
            PlannedExperiment(
                configuration=configuration.name,
                uses_llm=True,
                runs=len(cases) * repeats,
                max_cost_usd=max_cost,
                attempt_models=configuration.repair.attempt_models,
                advisor_model=(
                    configuration.repair.advisor.model if configuration.repair.advisor else None
                ),
            )
        )
        console.print(
            f"Estimated {how}. Spent this month on this machine: "
            f"{usd(ledger.month_spent())} (ledger {ledger.path})."
        )

    def on_event(event: RunEvent) -> None:
        label = f"{event.case} run {event.rep + 1}"
        if event.kind == "start":
            console.log(f"[bold]{label}[/] started")
        elif event.kind == "scored":
            console.log(f"[bold]{label}[/] scored: {event.message}")
        elif event.kind == "error":
            console.log(f"[bold red]{label} not scored[/]: {event.message}")
        elif event.kind == "skipped":
            console.log(f"{label} already scored, skipped")

    _print_tracing()
    try:
        outcome = run_experiment(plan, on_event=on_event)
    except (ConfigurationError, EvalError) as exc:
        raise _fail(str(exc)) from exc
    finally:
        flush()
    console.print(
        f"Experiment [bold]{outcome.experiment}[/]: {outcome.scored} runs scored, "
        f"{outcome.errors} not scored, {outcome.skipped} already done. "
        f"Results: {outcome.path / 'results.jsonl'}"
    )
    console.print(f"Next: migrator eval summary {outcome.experiment}")
    if outcome.errors:
        raise typer.Exit(code=1)


@eval_app.command("summary")
def eval_summary(
    experiment: Annotated[
        str, typer.Argument(help="An experiment id such as dev/baseline, or its folder.")
    ],
    against: Annotated[
        str | None,
        typer.Option(help="The Baseline experiment to compare with (default <split>/baseline)."),
    ] = None,
    out: Annotated[
        Path | None, typer.Option(help="Folder for the summary (default: the experiment's).")
    ] = None,
    stable: Annotated[
        bool,
        typer.Option(help="Leave out dates, times and run ids (for a committed summary)."),
    ] = False,
    root: RootOpt = None,
    results_dir: ResultsOpt = None,
) -> None:
    """Summarise an experiment's scorecards: mean and spread, traps, the Baseline."""
    base = _repo_root(root)
    results = (results_dir or base / "runs" / "evals").resolve()
    try:
        variant = experiment_dir(results, experiment)
        manifest = read_manifest(variant)
        if against is not None:
            against_dir: Path | None = experiment_dir(results, against)
        else:
            default = results / manifest.split / "baseline"
            against_dir = default if (default / "experiment.json").is_file() else None
        summary = build_summary(variant, against_dir, created_at=now())
    except EvalError as exc:
        raise _fail(str(exc)) from exc
    path = write_summary(summary, out or variant, stable=stable)
    share = next(m for m in summary.metrics if m.id == "migrated_share")
    per_clean = summary.cost.per_clean_run_usd
    console.print(
        f"[bold]{summary.experiment}[/] ({summary.configuration}): clean runs "
        f"{summary.clean_runs} of {summary.runs_scored}, migrated without a human "
        f"{round((share.mean or 0) * 100)}% (runs: "
        + ", ".join(f"{round(v * 100)}%" for v in share.values)
        + f"), cost per clean run {usd(per_clean) if per_clean is not None else '—'}"
        + (f"; compared with {summary.against.experiment}" if summary.against else "")
        + "."
    )
    console.print(f"Experiment summary: {path}")


DEFAULT_FLOW = Path(".claude") / "hillclimb" / "dev"


@eval_app.command("score-reference")
def eval_score_reference(
    experiment: Annotated[
        Path, typer.Argument(help="An experiment folder of real-repo runs, e.g. runs/m6/dev/v1.")
    ],
    max_cost: Annotated[
        float | None,
        typer.Option("--max-cost", help="USD cap for the judge calls; required unless --plan."),
    ] = None,
    plan: Annotated[
        bool, typer.Option("--plan", help="Only count the judge calls needed; call nothing.")
    ] = False,
    root: RootOpt = None,
    cases_dir: Annotated[Path | None, typer.Option(help="Default <root>/evals/m6-cases.")] = None,
) -> None:
    """Score each run of an experiment against its case's merged migration PR (M6)."""
    from migrator.cost import CostGuard, Ledger
    from migrator.evals import read_manifest, read_rows
    from migrator.evals.reference import (
        ClaudeJudge,
        JudgeCache,
        pending_judgements,
        read_run,
        render_reference_score,
        score_run,
    )
    from migrator.report import write_json

    base = _repo_root(root)
    variant = experiment.resolve()
    try:
        manifest = read_manifest(variant)
    except EvalError as exc:
        raise _fail(str(exc)) from exc
    folder = (cases_dir or base / "evals" / "m6-cases").resolve()
    cases = {c.id: c for c in (load_case(p) for p in sorted(folder.glob("*/case.toml")))}
    cache = JudgeCache(variant.parent.parent / "judge-cache")
    rows = read_rows(variant)
    todo = []
    for row in rows:
        case = cases.get(row.prompt_id)
        if case is None or case.upstream is None:
            raise _fail(f"{row.prompt_id} is not a real-repo case in {folder}")
        run_dir = variant / "runs" / f"{row.prompt_id}_rep{row.rep}"
        todo.append((case, run_dir, read_run(run_dir)))
    needed = sum(
        pending_judgements(c, [r for cc, _d, r in todo if cc.id == c.id], cache)
        for c in {c.id: c for c, _d, _r in todo}.values()
    )
    console.print(
        f"{manifest.experiment}: {len(todo)} runs, {needed} judge calls needed "
        f"(not cached), on claude-opus-5-5 at low effort"
    )
    if plan or not todo:
        return
    if needed and max_cost is None:
        raise _fail("judge calls cost money: pass --max-cost")
    _check_max_cost(max_cost)
    ledger = Ledger()
    guard = CostGuard(max_cost or 0.01, M6_MONTH_CAP_USD, ledger)
    for case, run_dir, inputs in todo:
        judge = ClaudeJudge(case.id, guard, ledger)
        score = score_run(case, inputs, judge, cache)
        write_json(score, run_dir / "reference-score.json")
        (run_dir / "reference-score.md").write_text(render_reference_score(score), "utf-8")
        guard.run_cap_usd = max(0.01, round(guard.run_cap_usd - judge.spent, 6))
        c = score.counts
        console.print(
            f"{run_dir.name}: matches {c['matches']}, other valid {c['other valid fix']}, "
            f"wrong {c['wrong']}, untouched {c['untouched']}, out of scope "
            f"{c['out of scope']}; silent misses {score.silent_misses}; judge "
            f"{score.judge_calls} calls ${score.judge_cost_usd:.2f}"
        )


@eval_app.command("climb")
def eval_climb(
    config: Annotated[
        str, typer.Option(help="The round's configuration: a name in evals/configs/ or a path.")
    ],
    max_cost: Annotated[
        float | None,
        typer.Option("--max-cost", help="USD cap for the round (required to call a model)."),
    ] = None,
    repeats: Annotated[int, typer.Option(min=1, help="Runs per dev case.")] = DEFAULT_REPEATS,
    approved: Annotated[
        bool,
        typer.Option(
            "--approved",
            help="The user approved this round (needed while approve_each_round is on).",
        ),
    ] = False,
    approve_harness: Annotated[
        bool,
        typer.Option(
            "--approve-harness",
            help="Record the current harness digest (the user's step after reviewing it).",
        ),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Check the gates and print the scope; run nothing.")
    ] = False,
    resume: Annotated[
        str | None, typer.Option(help="Continue a round's experiment, e.g. dev/v4.")
    ] = None,
    sandbox: Annotated[str, typer.Option("--sandbox", help="docker (default) or local.")] = (
        "docker"
    ),
    timeout_s: Annotated[
        float, typer.Option(help="Hard wall-clock ceiling per run, in seconds.")
    ] = DEFAULT_CEILING_S,
    flow: Annotated[
        Path | None, typer.Option(help="The hillclimb flow folder (default .claude/hillclimb/dev).")
    ] = None,
    root: RootOpt = None,
) -> None:
    """One hill-climbing round on the dev split: the gates, the experiment, its summary
    and the keep-rule verdict against the best round (directional, n = the dev cases)."""
    base = _repo_root(root)
    flow_dir = (flow or base / DEFAULT_FLOW).resolve()
    configs = base / "evals" / "configs"
    try:
        state = read_state(flow_dir)
        note = check_harness(base, state, approve=approve_harness)
        if note:
            write_state(flow_dir, state)
            console.print(note)
        cases = load_cases(base / "evals" / "cases", "dev")
        changed = sync_cases(state, cases)
        configuration = find_configuration(config, configs)
        ensure_runnable(configuration)
    except (ClimbError, ConfigurationError, ConfigError, EvalError) as exc:
        raise _fail(str(exc)) from exc
    if changed:
        console.print(f"[bold yellow]{changed}[/]")
    runs = len(cases) * repeats
    scope = (
        f"[bold]{configuration.name}[/] ({configuration.digest()}) on {len(cases)} dev "
        f"case(s) ({', '.join(c.id for c in cases)}) × {repeats} runs = {runs} runs"
    )
    if configuration.uses_llm:
        estimate, how = LedgerPreflight(Ledger()).estimate_with_advisor(
            PlannedExperiment(
                configuration=configuration.name,
                uses_llm=True,
                runs=runs,
                max_cost_usd=max_cost,
                attempt_models=configuration.repair.attempt_models,
                advisor_model=(
                    configuration.repair.advisor.model if configuration.repair.advisor else None
                ),
            )
        )
        scope += f" · estimated {usd(estimate)} ({how})"
    console.print(scope + " · results are directional (dev only, no test split)")
    if state.get("approve_each_round") and not approved and not dry_run:
        raise _fail(
            "approve_each_round is on: show the user this round's change and cost, and "
            "re-run with --approved once they say yes"
        )
    if dry_run:
        write_state(flow_dir, state)
        console.print("Dry run: gates passed, nothing was run.")
        return
    _check_max_cost(max_cost)
    baseline = (
        find_configuration("baseline", configs) if (configs / "baseline.toml").is_file() else None
    )
    plan = ExperimentPlan(
        root=base,
        results_dir=flow_dir.parent,
        split="dev",
        configuration=configuration,
        cases=cases,
        repeats=repeats,
        resume=resume,
        baseline_configuration=baseline,
        max_cost_usd=max_cost,
        ceiling_s=timeout_s,
        sandbox=_resolve_sandbox(sandbox, allow_auto=False),
    )
    _print_tracing()
    try:
        outcome = run_experiment(plan)
    except (ConfigurationError, EvalError) as exc:
        raise _fail(str(exc)) from exc
    finally:
        flush()
    variant = outcome.path.name
    verdict = None
    try:
        against = matching_baseline(flow_dir, [c.id for c in cases])
        if against is None:
            console.print(
                "[yellow]No Baseline experiment on this dev set yet[/]: run "
                "`migrator eval climb --config baseline` (free) to compare against it."
            )
        summary = build_summary(outcome.path, against, now())
        write_summary(summary, outcome.path)
        best = (state.get("best") or {}).get("variant")
        if best and best != variant and (flow_dir / best / "experiment.json").is_file():
            verdict = keep_verdict(summary, build_summary(flow_dir / best))
    except EvalError as exc:
        console.print(f"[yellow]No summary yet:[/] {exc}")
    state = read_state(flow_dir)  # the runner rewrote metrics; keep its keys
    state["train_ids"], state["test_ids"] = [c.id for c in cases], []
    record_round(
        state,
        variant=variant,
        configuration=configuration.name,
        digest=configuration.digest(),
        cases=[c.id for c in cases],
        verdict=verdict,
    )
    write_state(flow_dir, state)
    console.print(
        f"Round [bold]dev/{variant}[/]: {outcome.scored} runs scored, {outcome.errors} not "
        f"scored. Summary: {outcome.path / 'experiment-summary.md'}"
    )
    if verdict is not None:
        word = {True: "keep", False: "revert", None: "not comparable"}[verdict.keep]
        console.print(
            f"Keep rule vs {state['best']['variant']} (directional): {word}: {verdict.reason}"
        )
    if outcome.errors:
        raise typer.Exit(code=1)


@eval_app.command("retrieval")
def eval_retrieval(
    run: Annotated[
        Path,
        typer.Argument(help="A finished run folder (a Baseline run: the files after Rules)."),
    ],
    case: Annotated[str, typer.Option(help="The fixture case whose traps score it.")] = (
        "fixture-mui4"
    ),
    mode: Annotated[
        list[str] | None,
        typer.Option(help="Retrieval modes to compare (default: every built one)."),
    ] = None,
    root: RootOpt = None,
) -> None:
    """Offline, free: is each repair trap's guide section in its file's top 3?"""
    base = _repo_root(root)
    try:
        case_config = load_case(base / "evals" / "cases" / case / "case.toml")
        if case_config.split != "dev":
            raise RetrievalError(f"{case} is a {case_config.split} case; measure dev cases only")
        traps_path = case_config.traps_path()
        if traps_path is None:
            raise RetrievalError(f"{case} has no traps to score retrieval with")
        from migrator.config import load_traps

        traps = load_traps(traps_path)
        spec = next(s for s in available_specs() if s.id == case_config.migration)
        modes = mode or ["keyword", "keyword-imports", "keyword-context"]
        reports = [measure_retrieval(run, traps, spec, m) for m in modes]
    except (ConfigError, RetrievalError, StopIteration) as exc:
        raise _fail(str(exc)) from exc
    console.print(render_retrieval(reports), markup=False)
