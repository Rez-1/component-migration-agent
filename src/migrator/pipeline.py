"""Starting, driving and resuming a run's graph (``migrator.graph``).

Every run is one LangGraph graph with a checkpointer and one ``thread_id`` (the run
id). CLI runs use ``SqliteSaver`` with the database in the run folder, so a run paused
for review can be resumed by another process (``migrator resume <run-id>``); evals use
``InMemorySaver``, because they answer every hand-off in the same process.

Two kinds of run (ticket #9):

- A **dry run** happens in a throwaway copy; the target repo is never touched. Evals
  and CI only make dry runs.
- A **real run** refuses a dirty working tree, then works in a ``git worktree`` of the
  repo's HEAD on a new branch (``migrate/mui-v5``), outside the repo folder, and commits
  each stage there. The user's own working tree is never touched; the run files go in
  ``<repo>/.migrator/runs/<run-id>/``, which no commit includes.
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

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

from migrator import __version__
from migrator.config import (
    CaseConfig,
    ConfigError,
    LeftoverCheck,
    RepoConfig,
    ResolvedRepoConfig,
    TrapList,
    load_case,
    load_traps,
    read_package_json,
)
from migrator.configuration import BASELINE, Configuration, ensure_runnable
from migrator.cost import CostGuard, Ledger, UnknownModelPriceError, price_for
from migrator.detection import resolve_repo_config
from migrator.execs import (
    CommandRunner,
    DeadlineRunner,
    LocalRunner,
    Sandbox,
    SandboxError,
    make_runner,
    node_image,
    node_major,
)
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
from migrator.precheck_cache import PrecheckCache
from migrator.repair.model import GuardedModel, ModelFactory, provider_model
from migrator.repair.prompt import load_templates, tool_text
from migrator.repair.retriever import GuideRetriever
from migrator.repair.tools import RepairTools
from migrator.report import write_json
from migrator.review import AutoReviewer, Reviewer, ReviewPayload
from migrator.rules import tools_cache_root
from migrator.scan import ScanInput, UsageReport, scan
from migrator.scan.render import render_usage_report
from migrator.scoring import Scorecard
from migrator.verify.runners import adapter_for
from migrator.workspace import (
    RUN_FILES_DIR,
    GitError,
    Worktree,
    add_worktree,
    check_real_run,
)

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
    # Where commands run (ticket #15): "docker" (the pinned node image, network off
    # during Verify) or "local" (this machine). Callers choose; the CLI defaults evals to
    # Docker. A runner passed to start_run explicitly (tests) wins over this.
    sandbox: Sandbox = "local"
    # A real run: a git worktree on ``branch`` (default from the spec, migrate/mui-v5)
    # with one commit per stage. Never in evals.
    real: bool = False
    branch: str | None = None
    # Reuse each case's install and Pre-check across runs (M6 speed-up 2; evals).
    precheck_cache: bool = False
    # One long-lived container per run, commands by docker exec (M6 speed-up 3; evals).
    run_container: bool = False
    # node_modules in a Docker volume of the run container (M6 speed-up 4; needs 3).
    node_modules_volume: bool = False
    # tsc --incremental in the type-check (M6 speed-up 5).
    incremental_typecheck: bool = False


class RunResult(BaseModel):
    run_id: str
    run_dir: Path
    usage: UsageReport
    scorecard: Scorecard
    workspace: Path | None  # kept only with keep_workspace
    branch: str | None = None  # a real run's migration branch


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


_DETECT_SKIP = ["**/node_modules/**", "**/dist/**", "**/build/**", "**/.angular/**"]


def has_old_usage(repo: Path, spec: MigrationSpec) -> bool:
    """Whether any source file imports an old module (a quick text search, before Scan)."""
    from migrator.workspace import list_files

    quoted = re.compile(r"""['"]([^'"\n]+)['"]""")
    # Every source file, not the spec's globs: a repo's code may live outside src/
    # (codecharta: app/), and a repo's own globs are resolved only later.
    for rel in list_files(repo, ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"], _DETECT_SKIP):
        try:
            text = (repo / rel).read_text("utf-8", errors="replace")
        except OSError:
            continue
        if any(spec.usage.is_old(m) for m in quoted.findall(text)):
            return True
    return False


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
    majors = spec.detection.majors
    for name in found:
        if _major(deps[name]) not in majors:
            wanted = " or ".join(str(m) for m in majors)
            raise RunError(f"{name} is {deps[name]}, not major version {wanted}")
    if spec.detection.requires_old_usage and not has_old_usage(repo, spec):
        raise RunError(
            f"{repo} has no {spec.from_} usages left (nothing imports "
            f"{' or '.join(spec.usage.old_modules)}), so there is nothing to migrate"
        )
    for pre in spec.preconditions:
        version = deps.get(pre.package)
        major = _major(version) if version else None
        if major is None or major < pre.min_major:
            raise RunError(f"{spec.id} needs {pre.package} >= {pre.min_major} (found {version})")


def resolve_config(
    repo: Path, spec: MigrationSpec, case: CaseConfig | None, incremental: bool = False
) -> ResolvedRepoConfig:
    override: RepoConfig | None = case.repo if case else None
    try:
        config = resolve_repo_config(repo, override, spec.source_globs, spec.exclude)
    except ConfigError as exc:
        raise RunError(str(exc)) from exc
    if case is not None:
        config = config.model_copy(update={"runner": case.runner})
    if incremental:
        verify = config.verify.model_copy(update={"typecheck_incremental": True})
        config = config.model_copy(update={"verify": verify})
    if spec.leftovers_fail:
        leftovers = LeftoverCheck(
            old_modules=spec.usage.old_modules,
            old_styles=spec.usage.old_styles,
            todo_markers=spec.failing_todo_markers,
            source_globs=config.source_globs,
            exclude=config.exclude,
        )
        config = config.model_copy(update={"leftovers": leftovers})
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
    sandbox: Sandbox = "local"
    status: Literal["running", "paused", "done"] = "running"
    paused_hashes: dict[str, str] | None = None
    workspace: str | None = None
    worktree: Worktree | None = None  # a real run's worktree and branch
    pr_url: str | None = None  # set by `migrator pr --open`
    # The run's RunOptions as start_run used them, minus the fields recorded above
    # (spec, case, configuration) and the folder itself. Resume rebuilds the options
    # from this, so an option added to RunOptions reaches resume without more code.
    # None in run.json files written before it existed.
    options: dict[str, Any] | None = None


# RunOptions fields that run.json records in its own fields, or that resume knows
# from where it is (run_dir).
_REBUILT_OPTIONS = {"spec", "case", "configuration", "run_dir"}


def record_options(opts: RunOptions) -> dict[str, Any]:
    return opts.model_dump(mode="json", exclude=_REBUILT_OPTIONS)


def options_from_record(record: RunRecord, run_dir: Path) -> RunOptions:
    """The RunOptions a run started with, rebuilt from its run.json."""
    saved = record.options
    if saved is None:  # a run.json from before ``options``: what it did record
        saved = {
            "repo": record.repo,
            "traps": record.traps,
            "keep_workspace": record.keep_workspace,
            "tools_cache": record.tools_cache,
            "run_id": record.run_id,
            "max_run_usd": record.max_run_usd,
            "mode": record.mode,
            "sandbox": record.sandbox,
            "real": record.worktree is not None,
            "branch": record.worktree.branch if record.worktree else None,
        }
    return RunOptions.model_validate(
        {
            **saved,
            "spec": find_spec(record.migration_from, record.migration_to),
            "case": load_case(Path(record.case)) if record.case else None,
            "configuration": Configuration.model_validate(record.configuration),
            "run_dir": run_dir,
        }
    )


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


def sandbox_runner(
    sandbox: Sandbox,
    config: ResolvedRepoConfig,
    tools_cache: Path | None,
    per_run: bool = False,
    node_modules_volume: bool = False,
) -> tuple[CommandRunner, Path | None]:
    """The run's runner and its codemod tools cache. Docker installs the tools inside
    the container (for Linux), so they get a cache of their own per image, mounted
    read-only while the codemods run."""
    if sandbox == "local":
        return LocalRunner(), tools_cache
    image = node_image(config.node)
    tag = re.sub(r"[^A-Za-z0-9.]+", "-", image.split("@")[0])
    cache = (tools_cache or tools_cache_root() / "docker" / tag).resolve()
    browser = None
    if adapter_for(config.runner).needs_browser:
        # The tests run in Chrome (Karma): the same Node, with Debian's Chromium (M7).
        from migrator.visual import ensure_browser_image

        try:
            browser = ensure_browser_image(node=node_major(config.node))
        except (SandboxError, KeyError) as exc:
            raise RunError(f"no image with Chromium for Node {config.node}: {exc}") from exc
    runner = make_runner(
        "docker",
        config.node,
        read_only=[cache],
        per_run=per_run,
        node_modules_volume=per_run and node_modules_volume,
        image=browser,
    )
    return runner, cache


def open_runner(
    opts: RunOptions, config: ResolvedRepoConfig, runner: CommandRunner | None
) -> tuple[CommandRunner, CommandRunner | None, RunOptions]:
    """The runner a run's commands go through, for start and resume alike: the
    sandbox's (unless a runner is passed, as tests do), under the run's ceiling.
    Returns the runner, the one made here (the caller closes it when the run ends)
    and the options with the tools cache the sandbox chose."""
    owned: CommandRunner | None = None
    if runner is None:
        try:
            runner, tools_cache = sandbox_runner(
                opts.sandbox,
                config,
                opts.tools_cache,
                per_run=opts.run_container and opts.mode == "eval",
                node_modules_volume=opts.node_modules_volume,
            )
        except SandboxError as exc:
            raise RunError(str(exc)) from exc
        owned = runner
        opts = opts.model_copy(update={"tools_cache": tools_cache})
    if opts.ceiling_s is not None:
        runner = DeadlineRunner(runner, opts.ceiling_s)
    return runner, owned, opts


def close_runner(owned: CommandRunner | None) -> None:
    close = getattr(owned, "close", None)
    if callable(close):
        close()  # the run's container (speed-up 3)


def default_branch(spec: MigrationSpec) -> str:
    """``migrate/mui-v5`` for a migration to ``mui@5``."""
    return "migrate/" + re.sub(r"[^A-Za-z0-9.-]+", "-", spec.to.replace("@", "-v"))


def worktree_path(repo: Path, run_id: str) -> Path:
    """Outside the repo folder, so the user's own tsc, ESLint and Jest never see it."""
    return tools_cache_root() / "worktrees" / f"{repo.name}-{run_id}"


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
    worktree: Worktree | None = None,
) -> RunDeps:
    configuration = opts.configuration
    spec = configuration.apply_to(opts.spec)
    run_cap = opts.max_run_usd if opts.max_run_usd is not None else configuration.cost.max_run_usd
    month_cap = configuration.cost.max_month_usd
    # The per-call guard stops at the lower of the run cap and the hard stop (M6, $2);
    # the worst-case reservation is still checked against the run cap.
    stop = configuration.cost.stop_run_usd
    guard_cap = min(run_cap, stop) if stop is not None else run_cap
    model: GuardedModel | None = None
    tools: RepairTools | None = None
    retriever: GuideRetriever | None = None
    templates = None
    if configuration.repair.enabled:
        repair = configuration.repair
        templates = load_templates(repair.prompt_version or "v1")
        # ensure_runnable has refused an advisor without its prompt, and embeddings.
        if repair.advisor is not None:
            try:
                price_for(repair.advisor.model)  # an unpriced advisor can't be capped
            except UnknownModelPriceError as exc:
                raise RunError(str(exc)) from exc
        tools = RepairTools(tool_text(templates, spec))
        retriever = GuideRetriever.from_spec(spec, mode=repair.retrieval or "keyword")
        model = GuardedModel(
            model_factory or provider_model,
            CostGuard(guard_cap, month_cap, ledger),
            tools.tools,
            effort=repair.effort,
            run_id=run_id,
            case=opts.case.id if opts.case else None,
            tags=[f"config:{configuration.name}", *([f"case:{opts.case.id}"] if opts.case else [])],
            configuration=configuration.name,
            advisor=repair.advisor,
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
        worktree=worktree,
        sandbox=opts.sandbox,
        guard_cap_usd=guard_cap,
        precheck_cache=PrecheckCache(tools_cache_root() / "precheck")
        if opts.precheck_cache and not opts.real
        else None,
    )


@contextmanager
def sqlite_checkpointer(run_dir: Path) -> Iterator[SqliteSaver]:
    run_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(run_dir / "checkpoints.sqlite"), check_same_thread=False)
    try:
        yield SqliteSaver(conn)
    finally:
        conn.close()


def _graph_config(
    run_id: str, opts: RunOptions, callbacks: list[BaseCallbackHandler] | None = None
) -> RunnableConfig:
    """The graph's config: a checkpoint thread per run, and the LangSmith names and
    metadata (used only when tracing is on, see ``migrator.tracing``)."""
    case = opts.case.id if opts.case else None
    config: RunnableConfig = {
        "configurable": {"thread_id": run_id},
        "recursion_limit": RECURSION_LIMIT,
        "run_name": "migrator-run",
        "tags": [
            f"config:{opts.configuration.name}",
            f"mode:{opts.mode}",
            *([f"case:{case}"] if case else []),
        ],
        "metadata": {
            "thread_id": run_id,  # groups the first invoke and every resume in LangSmith
            "run_id": run_id,
            "configuration": opts.configuration.name,
            "case": case,
            "repo": opts.repo.name,
            "mode": opts.mode,
            "real_run": opts.real,
            "sandbox": opts.sandbox,
            "migrator_version": __version__,
        },
    }
    if callbacks:
        config["callbacks"] = list(callbacks)
    return config


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
        branch=card.meta.branch,
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
    callbacks: list[BaseCallbackHandler] | None = None,
) -> RunResult | PausedRun:
    """Run the whole graph. With a Reviewer that pauses (the CLI's), the run can stop at
    a hand-off and return ``PausedRun``; ``resume_run`` continues it."""
    configuration = opts.configuration
    ensure_runnable(configuration)
    repo = opts.repo.resolve()
    spec = configuration.apply_to(opts.spec)
    run_dir = opts.run_dir.resolve()
    run_id = opts.run_id or run_dir.name
    check_detection(repo, spec)
    config = resolve_config(repo, spec, opts.case, opts.incremental_typecheck)
    branch = opts.branch or default_branch(spec)
    if opts.real:
        if opts.mode == "eval":
            raise RunError("evals only make dry runs; a real run commits to the target repo")
        try:
            check_real_run(repo, branch)
        except GitError as exc:
            raise RunError(str(exc)) from exc
    base_runner, owned, opts = open_runner(opts, config, runner)
    usage = run_scan(repo, spec, config)
    if not usage.affected_files():
        raise RunError(f"{repo} has no usages of {spec.from_} in {', '.join(config.source_globs)}")
    traps_path = opts.traps or (opts.case.traps_path() if opts.case else None)
    traps = load_traps(traps_path) if traps_path is not None else None
    ledger = ledger or Ledger()
    worktree: Worktree | None = None
    if opts.real:
        try:
            worktree = add_worktree(repo, worktree_path(repo, run_id), branch)
        except GitError as exc:
            raise RunError(str(exc)) from exc
    deps = build_deps(
        opts,
        runner=base_runner,
        config=config,
        traps=traps,
        run_id=run_id,
        ledger=ledger,
        model_factory=model_factory,
        on_stage=on_stage,
        worktree=worktree,
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
        sandbox=opts.sandbox,
        worktree=worktree,
        workspace=str(worktree.workspace) if worktree else None,
        options=record_options(opts),
    )
    write_run_record(run_dir, record)
    reviewer = reviewer or AutoReviewer()
    builder = RunGraph(deps).build()
    config_ = _graph_config(run_id, opts, callbacks)
    use_sqlite = durable if durable is not None else checkpointer is None and opts.mode == "cli"
    durability: Literal["sync", "async"] = "sync" if use_sqlite else "async"

    first = initial_state(run_id, run_dir)
    if worktree is not None:
        first["workspace"] = str(worktree.workspace)

    def go(saver: BaseCheckpointSaver[Any]) -> RunResult | PausedRun:
        graph = builder.compile(checkpointer=saver)
        state, paused = _drive(graph, first, config_, reviewer, durability)
        return _finish(state, paused, run_dir, record, opts.keep_workspace)

    try:
        if checkpointer is not None:
            return go(checkpointer)
        if use_sqlite:
            with sqlite_checkpointer(run_dir) as saver:
                return go(saver)
        return go(InMemorySaver())
    finally:
        close_runner(owned)


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
    callbacks: list[BaseCallbackHandler] | None = None,
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
    opts = options_from_record(record, run_dir)
    traps = load_traps(Path(record.traps)) if record.traps else None
    spec = opts.configuration.apply_to(opts.spec)
    config = resolve_config(opts.repo, spec, opts.case, opts.incremental_typecheck)
    run_runner, owned, opts = open_runner(opts, config, runner)
    try:
        return _resume(
            record,
            run_dir,
            opts,
            build_deps(
                opts,
                runner=run_runner,
                config=config,
                traps=traps,
                run_id=record.run_id,
                ledger=ledger or Ledger(),
                model_factory=model_factory,
                on_stage=on_stage,
                worktree=record.worktree,
            ),
            reviewer,
            now,
            callbacks,
        )
    finally:
        close_runner(owned)


def _resume(
    record: RunRecord,
    run_dir: Path,
    opts: RunOptions,
    deps: RunDeps,
    reviewer: Reviewer,
    now: dict[str, str],
    callbacks: list[BaseCallbackHandler] | None,
) -> RunResult | PausedRun:
    builder = RunGraph(deps).build()
    config_ = _graph_config(record.run_id, opts, callbacks)
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
    """A run folder: the path itself, ``runs/<run-id>/`` under the current folder (dry
    runs), or ``.migrator/runs/<run-id>/`` (real runs, from inside the target repo)."""
    candidate = Path(run_id)
    if candidate.is_dir() and run_record_path(candidate).is_file():
        return candidate
    here = base or Path.cwd()
    places = [here / "runs" / run_id, here / RUN_FILES_DIR / "runs" / run_id]
    for path in places:
        if run_record_path(path).is_file():
            return path
    raise RunError(
        f"no run {run_id!r} in {places[0].parent} or {places[1].parent} (looked for run.json)"
    )
