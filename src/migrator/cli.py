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
from migrator.evals.summary import build_summary, write_summary
from migrator.migrations import UnknownMigrationError, find_spec
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
from migrator.report import Scorecard, usd
from migrator.review import AutoReviewer, Reviewer, RichReviewer

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
        t = h.traps
        table.add_row(
            "Traps",
            f"{t.expected} expected · {t.other_layer} other layer · {t.missed} missed · "
            f"{t.not_scored} not scored",
        )
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
            f"[bold]migrator resume {result.run_id}[/]"
        )
        return
    if result.workspace:
        console.print(f"Workspace kept at {result.workspace}")
    _print_scorecard(result.scorecard, result.run_dir)
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
        Path | None, typer.Option(help="Where run files go (default runs/<run-id>/).")
    ] = None,
    keep_workspace: Annotated[
        bool, typer.Option(help="Keep the throwaway workspace for inspection.")
    ] = False,
    root: Annotated[
        Path | None, typer.Option(help="The folder holding evals/configs (default: here).")
    ] = None,
) -> None:
    """Migrate a target repo: Scan, Pre-check, Rules, Verify, Repair, Review, Report."""
    if not dry_run_:
        raise _fail(
            "only --dry-run is implemented. Real runs (a git worktree on "
            "migrate/mui-v5 with one commit per stage) arrive with PR creation in M4."
        )
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
    target = (run_dir or _default_run_dir(run_id)).resolve()
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
    )
    console.print(
        f"Run [bold]{run_id}[/] · configuration [bold]{configuration.name}[/]"
        + (
            f" · cost cap {usd(max_cost or configuration.cost.max_run_usd)} per run, "
            f"{usd(configuration.cost.max_month_usd)} per month"
            if configuration.uses_llm
            else " · rules only, no model calls"
        )
    )
    reviewer: Reviewer = AutoReviewer() if no_review else RichReviewer(console)
    try:
        result = start_run(opts, on_stage=_on_stage, reviewer=reviewer)
    except (RunError, ConfigError) as exc:
        raise _fail(str(exc)) from exc
    finally:
        _flush_traces()
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
        _flush_traces()
    _finish_run(result)


def _flush_traces() -> None:
    """A short-lived CLI must flush LangSmith traces before it exits (when tracing is on)."""
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()
    except Exception:  # tracing is optional; never fail a run over it
        pass


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
    root: RootOpt = None,
    results_dir: ResultsOpt = None,
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
        cases = load_cases(base / "evals" / "cases", split_name, case)
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
        )
    except (ConfigurationError, ConfigError, EvalError) as exc:
        raise _fail(str(exc)) from exc
    _check_max_cost(max_cost)
    console.print(
        f"[bold]{configuration.name}[/] on {len(cases)} {split} case(s) × {repeats} runs "
        f"· run cap {usd(configuration.cost.max_run_usd)}, month cap "
        f"{usd(configuration.cost.max_month_usd)}"
        + (f", experiment cap {usd(max_cost)}" if max_cost is not None else "")
    )
    if configuration.uses_llm:
        ledger = Ledger()
        _estimate, how = LedgerPreflight(ledger).estimate(
            PlannedExperiment(
                configuration=configuration.name,
                uses_llm=True,
                runs=len(cases) * repeats,
                max_cost_usd=max_cost,
                attempt_models=configuration.repair.attempt_models,
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

    try:
        outcome = run_experiment(plan, on_event=on_event)
    except (ConfigurationError, EvalError) as exc:
        raise _fail(str(exc)) from exc
    finally:
        _flush_traces()
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
