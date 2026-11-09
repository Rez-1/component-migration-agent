"""Starting, driving and resuming a run's graph (``migrator.graph``).

Every run is one LangGraph graph with a checkpointer and one ``thread_id`` (the run
id). CLI runs use ``SqliteSaver`` with the database in the run folder, so a run paused
for review can be resumed by another process (``migrator resume <run-id>``); evals use
``InMemorySaver``, because they answer every hand-off in the same process. M3 supports
dry runs: the whole run happens in a throwaway copy and the target repo is never
touched.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

from migrator.config import (
    CaseConfig,
    ConfigError,
    RepoConfig,
    ResolvedRepoConfig,
    TrapList,
    load_case,
    load_traps,
    read_package_json,
    resolve_repo_config,
)
from migrator.configuration import BASELINE, Configuration, ensure_runnable
from migrator.cost import CostGuard, Ledger
from migrator.execs import CommandRunner, DeadlineRunner, LocalRunner
from migrator.graph import (
    RECURSION_LIMIT,
    Mode,
    RunDeps,
    RunGraph,
    StageCallback,
    code_hashes,
    initial_state,
)
from migrator.migrations import MigrationSpec, find_spec
from migrator.repair.model import GuardedModel, ModelFactory, anthropic_model
from migrator.repair.prompt import load_templates, tool_text
from migrator.repair.retriever import GuideRetriever
from migrator.repair.tools import RepairTools
from migrator.report import Scorecard, write_json
from migrator.review import AutoReviewer, Reviewer, ReviewPayload
from migrator.scan import ScanInput, UsageReport, scan
from migrator.scan.render import render_usage_report

__all__ = ["RunError", "RunOptions", "RunResult", "check_detection", "dry_run"]


class RunError(RuntimeError):
    """The run cannot start (wrong repo, missing lockfile, no usages) or resume."""


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
    # The run's USD cap; None uses the configuration's. Never unlimited.
    max_run_usd: float | None = None
    mode: Mode = "eval"  # "cli": real use (cheating-check hits become hand-offs)


class RunResult(BaseModel):
    run_id: str
    run_dir: Path
    usage: UsageReport
    scorecard: Scorecard
    workspace: Path | None  # kept only with keep_workspace


class PausedRun(BaseModel):
    """A run paused at a hand-off; ``migrator resume <run_id>`` continues it."""

    run_id: str
    run_dir: Path
    payload: ReviewPayload


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


# --------------------------------------------------------------------------- run record


class RunRecord(BaseModel):
    """``run.json`` in the run folder: what ``migrator resume`` needs to rebuild the run."""

    run_id: str
    thread_id: str
    repo: str
    migration_from: str
    migration_to: str
    case: str | None  # path of case.toml
    traps: str | None
    configuration: dict[str, Any]
    keep_workspace: bool
    tools_cache: str | None
    max_run_usd: float | None
    mode: Mode
    status: Literal["running", "paused", "done"] = "running"
    paused_hashes: dict[str, str] | None = None
    workspace: str | None = None


def run_record_path(run_dir: Path) -> Path:
    return run_dir / "run.json"


def read_run_record(run_dir: Path) -> RunRecord:
    path = run_record_path(run_dir)
    if not path.is_file():
        raise RunError(f"{run_dir} is not a run folder (no run.json)")
    return RunRecord.model_validate_json(path.read_text("utf-8"))


def write_run_record(run_dir: Path, record: RunRecord) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    run_record_path(run_dir).write_text(record.model_dump_json(indent=2) + "\n", "utf-8")


# --------------------------------------------------------------------------- deps


def build_deps(
    opts: RunOptions,
    *,
    runner: CommandRunner,
    config: ResolvedRepoConfig,
    traps: TrapList | None,
    run_id: str,
    ledger: Ledger,
    model_factory: ModelFactory | None,
    on_stage: StageCallback | None,
) -> RunDeps:
    configuration = opts.configuration
    spec = configuration.apply_to(opts.spec)
    run_cap = opts.max_run_usd if opts.max_run_usd is not None else configuration.cost.max_run_usd
    month_cap = configuration.cost.max_month_usd
    model: GuardedModel | None = None
    tools: RepairTools | None = None
    retriever: GuideRetriever | None = None
    templates = None
    if configuration.repair.enabled:
        repair = configuration.repair
        templates = load_templates(repair.prompt_version or "v1")
        tools = RepairTools(tool_text(templates, spec))
        if repair.retrieval != "keyword":
            raise RunError(
                f"retrieval {repair.retrieval!r} is an M5 experiment; only keyword exists"
            )
        retriever = GuideRetriever.from_spec(spec)
        model = GuardedModel(
            model_factory or anthropic_model,
            CostGuard(run_cap, month_cap, ledger),
            tools.tools,
            effort=repair.effort,
            run_id=run_id,
            case=opts.case.id if opts.case else None,
            tags=[f"config:{configuration.name}", *([f"case:{opts.case.id}"] if opts.case else [])],
        )
    return RunDeps(
        repo=opts.repo.resolve(),
        spec=spec,
        configuration=configuration,
        case=opts.case,
        traps=traps,
        config=config,
        runner=runner,
        mode=opts.mode,
        keep_workspace=opts.keep_workspace,
        tools_cache=opts.tools_cache,
        run_cap_usd=run_cap,
        month_cap_usd=month_cap,
        ledger=ledger,
        model=model,
        tools=tools,
        templates=templates,
        retriever=retriever,
        on_stage=on_stage,
    )


@contextmanager
def sqlite_checkpointer(run_dir: Path) -> Iterator[SqliteSaver]:
    run_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(run_dir / "checkpoints.sqlite"), check_same_thread=False)
    try:
        yield SqliteSaver(conn)
    finally:
        conn.close()


def _graph_config(run_id: str, opts: RunOptions) -> RunnableConfig:
    return {
        "configurable": {"thread_id": run_id},
        "recursion_limit": RECURSION_LIMIT,
        "run_name": "migrator-run",
        "tags": [f"config:{opts.configuration.name}"],
        "metadata": {
            "thread_id": run_id,
            "configuration": opts.configuration.name,
            "case": opts.case.id if opts.case else None,
        },
    }


def _drive(
    graph: Any,
    first_input: Any,
    config: RunnableConfig,
    reviewer: Reviewer,
    durability: Literal["sync", "async"],
) -> tuple[dict[str, Any], ReviewPayload | None]:
    """Invoke the graph, answering each Review interrupt; (final state, pause payload)."""
    result: dict[str, Any] = graph.invoke(first_input, config, durability=durability)
    while "__interrupt__" in result:
        payload = ReviewPayload.model_validate(result["__interrupt__"][0].value)
        answer = reviewer.review(payload)
        if answer is None:
            return result, payload
        result = graph.invoke(
            Command(resume=answer.model_dump(mode="json")), config, durability=durability
        )
    return result, None


def _result(state: dict[str, Any], run_id: str, run_dir: Path, keep: bool) -> RunResult:
    card = Scorecard.model_validate_json((run_dir / "scorecard.json").read_text("utf-8"))
    usage = UsageReport.model_validate_json((run_dir / "usage-report.json").read_text("utf-8"))
    ws = state.get("workspace")
    return RunResult(
        run_id=run_id,
        run_dir=run_dir,
        usage=usage,
        scorecard=card,
        workspace=Path(ws) if keep and ws else None,
    )


def start_run(
    opts: RunOptions,
    runner: CommandRunner | None = None,
    on_stage: StageCallback | None = None,
    *,
    model_factory: ModelFactory | None = None,
    reviewer: Reviewer | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    ledger: Ledger | None = None,
    durable: bool | None = None,
) -> RunResult | PausedRun:
    """Run the whole graph. With a Reviewer that pauses (the CLI's), the run can stop at
    a hand-off and return ``PausedRun``; ``resume_run`` continues it."""
    configuration = opts.configuration
    ensure_runnable(configuration)
    base_runner: CommandRunner = runner or LocalRunner()
    if opts.ceiling_s is not None:
        base_runner = DeadlineRunner(base_runner, opts.ceiling_s)
    repo = opts.repo.resolve()
    spec = configuration.apply_to(opts.spec)
    run_dir = opts.run_dir.resolve()
    run_id = opts.run_id or run_dir.name
    check_detection(repo, spec)
    config = resolve_config(repo, spec, opts.case)
    usage = run_scan(repo, spec, config)
    if not usage.affected_files():
        raise RunError(f"{repo} has no usages of {spec.from_} in {', '.join(config.source_globs)}")
    traps_path = opts.traps or (opts.case.traps_path() if opts.case else None)
    traps = load_traps(traps_path) if traps_path is not None else None
    ledger = ledger or Ledger()
    deps = build_deps(
        opts,
        runner=base_runner,
        config=config,
        traps=traps,
        run_id=run_id,
        ledger=ledger,
        model_factory=model_factory,
        on_stage=on_stage,
    )
    record = RunRecord(
        run_id=run_id,
        thread_id=run_id,
        repo=str(repo),
        migration_from=opts.spec.from_,
        migration_to=opts.spec.to,
        case=str(opts.case.folder / "case.toml") if opts.case else None,
        traps=str(traps_path) if traps_path else None,
        configuration=configuration.model_dump(mode="json"),
        keep_workspace=opts.keep_workspace,
        tools_cache=str(opts.tools_cache) if opts.tools_cache else None,
        max_run_usd=opts.max_run_usd,
        mode=opts.mode,
    )
    write_run_record(run_dir, record)
    reviewer = reviewer or AutoReviewer()
    builder = RunGraph(deps).build()
    config_ = _graph_config(run_id, opts)
    use_sqlite = durable if durable is not None else checkpointer is None and opts.mode == "cli"
    durability: Literal["sync", "async"] = "sync" if use_sqlite else "async"

    def go(saver: BaseCheckpointSaver[Any]) -> RunResult | PausedRun:
        graph = builder.compile(checkpointer=saver)
        state, paused = _drive(graph, initial_state(run_id, run_dir), config_, reviewer, durability)
        return _finish(state, paused, run_dir, record, opts.keep_workspace)

    if checkpointer is not None:
        return go(checkpointer)
    if use_sqlite:
        with sqlite_checkpointer(run_dir) as saver:
            return go(saver)
    return go(InMemorySaver())


def _finish(
    state: dict[str, Any],
    paused: ReviewPayload | None,
    run_dir: Path,
    record: RunRecord,
    keep: bool,
) -> RunResult | PausedRun:
    if paused is not None:
        record = record.model_copy(
            update={
                "status": "paused",
                "paused_hashes": code_hashes(Path(paused.workspace)),
                "workspace": paused.workspace,
            }
        )
        write_run_record(run_dir, record)
        return PausedRun(run_id=record.run_id, run_dir=run_dir, payload=paused)
    write_run_record(run_dir, record.model_copy(update={"status": "done"}))
    return _result(state, record.run_id, run_dir, keep)


def dry_run(
    opts: RunOptions,
    runner: CommandRunner | None = None,
    on_stage: StageCallback | None = None,
    *,
    model_factory: ModelFactory | None = None,
    ledger: Ledger | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> RunResult:
    """A full run in a throwaway copy, every hand-off reverted (evals, CI, --no-review)."""
    result = start_run(
        opts,
        runner,
        on_stage,
        model_factory=model_factory,
        reviewer=AutoReviewer(),
        checkpointer=checkpointer,
        ledger=ledger,
    )
    assert isinstance(result, RunResult)  # the AutoReviewer never pauses
    return result


class ChangedWorkspaceError(RunError):
    def __init__(self, changed: list[str]):
        super().__init__(
            "the workspace changed while the run was paused: "
            + ", ".join(changed)
            + ". Pass --accept-changes to continue (changed files count as the human's)."
        )
        self.changed = changed


def resume_run(
    run_dir: Path,
    *,
    reviewer: Reviewer,
    accept_changes: bool = False,
    runner: CommandRunner | None = None,
    on_stage: StageCallback | None = None,
    model_factory: ModelFactory | None = None,
    ledger: Ledger | None = None,
) -> RunResult | PausedRun:
    """Continue a run paused at a hand-off, from its SQLite checkpoint."""
    run_dir = run_dir.resolve()
    record = read_run_record(run_dir)
    if record.status != "paused":
        raise RunError(f"run {record.run_id} is {record.status}, not paused for review")
    if not record.workspace or not Path(record.workspace).is_dir():
        raise RunError(f"the run's workspace is gone ({record.workspace}); start a new run")
    now = code_hashes(Path(record.workspace))
    before = record.paused_hashes or {}
    changed = sorted(p for p in now.keys() | before.keys() if now.get(p) != before.get(p))
    if changed and not accept_changes:
        raise ChangedWorkspaceError(changed)
    spec = find_spec(record.migration_from, record.migration_to)
    case = load_case(Path(record.case)) if record.case else None
    configuration = Configuration.model_validate(record.configuration)
    opts = RunOptions(
        repo=Path(record.repo),
        spec=spec,
        run_dir=run_dir,
        case=case,
        traps=Path(record.traps) if record.traps else None,
        keep_workspace=record.keep_workspace,
        tools_cache=Path(record.tools_cache) if record.tools_cache else None,
        configuration=configuration,
        run_id=record.run_id,
        max_run_usd=record.max_run_usd,
        mode=record.mode,
    )
    traps = load_traps(Path(record.traps)) if record.traps else None
    config = resolve_config(opts.repo, configuration.apply_to(spec), case)
    deps = build_deps(
        opts,
        runner=runner or LocalRunner(),
        config=config,
        traps=traps,
        run_id=record.run_id,
        ledger=ledger or Ledger(),
        model_factory=model_factory,
        on_stage=on_stage,
    )
    builder = RunGraph(deps).build()
    config_ = _graph_config(record.run_id, opts)
    with sqlite_checkpointer(run_dir) as saver:
        graph = builder.compile(checkpointer=saver)
        snapshot = graph.get_state(config_)
        pending = [i for t in snapshot.tasks for i in t.interrupts]
        if not pending:
            raise RunError(f"run {record.run_id} has no pending review in its checkpoint")
        payload = ReviewPayload.model_validate(pending[0].value)
        answer = reviewer.review(payload)
        if answer is None:
            write_run_record(run_dir, record.model_copy(update={"paused_hashes": now}))
            return PausedRun(run_id=record.run_id, run_dir=run_dir, payload=payload)
        state, paused = _drive(
            graph,
            Command(resume=answer.model_dump(mode="json")),
            config_,
            reviewer,
            "sync",
        )
        return _finish(state, paused, run_dir, record, record.keep_workspace)


def find_run_dir(run_id: str, base: Path | None = None) -> Path:
    """``runs/<run-id>/`` under the current folder (where ``migrate`` writes runs)."""
    candidate = Path(run_id)
    if candidate.is_dir() and run_record_path(candidate).is_file():
        return candidate
    path = (base or Path.cwd()) / "runs" / run_id
    if not run_record_path(path).is_file():
        raise RunError(f"no run {run_id!r} in {path.parent} (looked for run.json)")
    return path
