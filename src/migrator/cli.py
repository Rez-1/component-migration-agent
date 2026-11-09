"""The ``migrator`` command line (Typer commands only; the work lives in the stages)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from migrator.config import ConfigError, load_case
from migrator.migrations import UnknownMigrationError, find_spec
from migrator.pipeline import (
    RunError,
    RunOptions,
    check_detection,
    dry_run,
    new_run_id,
    resolve_config,
    run_scan,
    write_usage_report,
)
from migrator.report import Scorecard

app = typer.Typer(
    help="The Migrator: moves a target repo from one component-library version to the next.",
    no_args_is_help=True,
    add_completion=False,
)
eval_app = typer.Typer(help="Eval runs and experiment summaries (M2).", no_args_is_help=True)
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
) -> None:
    """Migrate a target repo: Scan, Pre-check, Rules, Verify, Report (Repair from M3)."""
    if not dry_run_:
        raise _fail(
            "only --dry-run is implemented in M1. Real runs (a git worktree on "
            "migrate/mui-v5 with one commit per stage) arrive with PR creation in M4."
        )
    try:
        spec = find_spec(from_, to)
        case_config = load_case(case) if case else None
    except (UnknownMigrationError, ConfigError) as exc:
        raise _fail(str(exc)) from exc
    run_id = new_run_id()
    target = (run_dir or _default_run_dir(run_id)).resolve()
    opts = RunOptions(
        repo=repo,
        spec=spec,
        run_dir=target,
        case=case_config,
        traps=traps,
        keep_workspace=keep_workspace,
    )
    with console.status("Starting", spinner="dots") as status:

        def on_stage(stage: str, message: str) -> None:
            status.update(f"[bold]{stage}[/] {message}")
            console.log(f"[bold]{stage}[/] {message}")

        try:
            result = dry_run(opts, on_stage=on_stage)
        except (RunError, ConfigError) as exc:
            raise _fail(str(exc)) from exc
    if result.workspace:
        console.print(f"Workspace kept at {result.workspace}")
    _print_scorecard(result.scorecard, result.run_dir)
    if result.scorecard.status != "completed":
        raise typer.Exit(code=1)


@app.command("resume")
def resume_command(run_id: Annotated[str, typer.Argument(help="The run to continue.")]) -> None:
    """Continue a run paused for review (M3)."""
    raise _fail("resume is not implemented yet: runs pause for review from M3")


@eval_app.command("run")
def eval_run(
    split: Annotated[str, typer.Option(help="dev or held-out")] = "dev",
    config: Annotated[str, typer.Option(help="A configuration in evals/configs/.")] = "baseline",
) -> None:
    """Run an experiment: every case in a split under one configuration (M2)."""
    raise _fail("eval run is not implemented yet (M2)")


@eval_app.command("summary")
def eval_summary(experiment: Annotated[str, typer.Argument()]) -> None:
    """Summarise an experiment's scorecards (M2)."""
    raise _fail("eval summary is not implemented yet (M2)")
