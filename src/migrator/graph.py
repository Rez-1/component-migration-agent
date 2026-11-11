"""The whole run as one checkpointed LangGraph graph (ticket #11).

    Scan -> Pre-check -> Rules -> Verify -> Repair (one failing file at a time)
         -> Review (one interrupt per hand-off) -> Verify (final) -> Report

Each stage is a thin node over its plain stage function. Because every node's result
is checkpointed before the next starts, the Rules stage runs exactly once even across
a pause and resume (the codemods are not idempotent); a marker file also refuses to
re-run Rules if a crash interrupted them half-way.

Repair is built from a model node and a tools node with no agent wrapper, so its
limits are edges, not prompt text: an attempt ends when the agent calls ``run_verify``
(or at 15 tool calls, which hands the file off), a file gets at most 3 attempts, and
the cost cap ends Repair for every remaining file (they end Unmigrated, and the run
still goes through Review and Report, so there is always a scorecard).

A real run (not ``--dry-run``) works in a git worktree on the migration branch and
commits each stage from its own node, after Rules, after Repair and after Review
(``commit_rules``, ``commit_agent``, ``commit_review``). Commit nodes never pause, and
each looks for its own commit (by its trailers) before making one, so a crash or a
resume never commits a stage twice. Dry runs pass through them unchanged.

Review handles one hand-off per node execution and loops through an edge. The node
does nothing before ``interrupt()``: the payload (diff, failures, file hashes) is
computed by ``prepare_review`` and stored in state, so a resumed Review never repeats
a change. Large artifacts (file snapshots, verify logs, conversations) are files in the
run folder; the state holds their paths.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    messages_to_dict,
)
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from migrator import __version__
from migrator.checks import (
    CheatingReport,
    CheckInput,
    FileSet,
    Layer,
    find_test_files,
    import_graph,
    read_files,
    read_test_rules,
    run_checks,
)
from migrator.config import CaseConfig, ResolvedRepoConfig, TrapList
from migrator.configuration import Configuration
from migrator.cost import (
    CallRecord,
    CostCapError,
    CostGuard,
    Ledger,
    release_run,
    reserve_run,
    run_cost,
)
from migrator.execs import (
    CommandRunner,
    DockerRunner,
    RunContainerRunner,
    SandboxError,
    node_image,
)
from migrator.migrations import MigrationSpec
from migrator.precheck_cache import (
    CachedPrecheck,
    PrecheckCache,
    cache_key,
    clone_tree,
    restore_logs,
)
from migrator.repair.context import local_imports, unified_diff
from migrator.repair.guardrails import added_escape_hatches
from migrator.repair.model import GuardedModel
from migrator.repair.prompt import (
    PromptTemplates,
    describe_failure,
    first_message,
    system_prompt,
)
from migrator.repair.records import AttemptRecord, FileRepair, RepairReport, ReviewAnswer
from migrator.repair.retriever import GuideRetriever, render_section
from migrator.repair.reviewer import (
    Review,
    failing_tests_of,
    patch_diff,
    read_tests,
    review_patch,
    review_prompt,
)
from migrator.repair.reviewer import default_model as default_review_model
from migrator.repair.shared import SharedCause, find_shared_causes, shared_cause_section
from migrator.repair.tools import (
    RepairSession,
    RepairTools,
    SessionState,
    failure_key,
)
from migrator.report import (
    ReportInput,
    RunMeta,
    SnapshotUpdate,
    build_scorecard,
    render_pr_body,
    render_scorecard,
    repeated_edits,
    test_fitting_flags,
    usd,
    write_json,
)
from migrator.review import ReviewPayload
from migrator.rules import (
    RulesInput,
    RulesResult,
    ToolsError,
    apply_rules,
    ensure_tools,
    tools_cache_root,
)
from migrator.scan import ScanInput, UsageReport, scan
from migrator.scan.render import render_usage_report
from migrator.verify import (
    Failure,
    PrecheckInput,
    PrecheckResult,
    VerifyInput,
    VerifyResult,
    precheck,
    update_snapshots,
    verify,
)
from migrator.verify.leftovers import rules_under_todos
from migrator.visual import VisualError, capture, ensure_browser_image, ensure_visual_tools
from migrator.visual.compare import VisualReport, new_page_errors
from migrator.visual.compare import compare as compare_captures
from migrator.workspace import (
    GitError,
    StageCommit,
    StageName,
    Worktree,
    commit_stage,
    create_dry_run_workspace,
    hash_file,
    remove_worktree,
)

Mode = Literal["eval", "cli"]
StageCallback = Callable[[str, str], None]
MAX_TOOL_CALLS = 15
RECURSION_LIMIT = 10_000
NUDGE = (
    "Your reply had no tool call. End this attempt with `run_verify` (with a one-line "
    "note), or call `hand_off` if a human must make this fix."
)


class RunState(TypedDict, total=False):
    """The run's graph state: small and structured, JSON-friendly values only."""

    run_id: str
    run_dir: str
    workspace: str | None
    started_at: str
    visual_before: dict[str, Any] | None  # M7: the before capture, or why there is none
    timings: dict[str, float]
    config: dict[str, Any]  # ResolvedRepoConfig
    usage_path: str
    node_version: str | None
    npm_version: str | None
    precheck: dict[str, Any]  # PrecheckResult
    rules: dict[str, Any] | None  # RulesResult
    rules_done: bool
    verify: dict[str, Any] | None  # the Verify after Rules
    known_failures: list[dict[str, Any]]  # latest known failures (Failure)
    file_start_failures: list[dict[str, Any]]  # known failures when this file's repair began
    test_files: dict[str, str]
    queue: list[str]  # failing files still to repair, in order
    current: dict[str, Any] | None  # SessionState of the file being repaired
    messages: list[BaseMessage]  # that file's conversation (append-only)
    repair: dict[str, Any]  # RepairReport
    calls: list[dict[str, Any]]  # CallRecord, one per model call
    review_queue: list[str]
    review: dict[str, Any] | None  # ReviewPayload of the hand-off being reviewed
    final: dict[str, Any] | None  # the final Verify
    final_usage_path: str | None
    cheating: dict[str, Any] | None
    scorecard_path: str | None
    commits: list[dict[str, Any]]  # StageCommit, one per stage that changed files (real runs)
    snapshot_updates: list[dict[str, Any]]  # SnapshotUpdate: snapshots the Migrator rewrote
    shared_causes: list[dict[str, Any]]  # SharedCause (M6): one task per shared definition


class RunDeps:
    """What the nodes need that is not state: tools, runners, the model, callbacks."""

    def __init__(
        self,
        *,
        repo: Path,
        spec: MigrationSpec,
        configuration: Configuration,
        case: CaseConfig | None,
        traps: TrapList | None,
        config: ResolvedRepoConfig,
        runner: CommandRunner,
        mode: Mode,
        keep_workspace: bool,
        tools_cache: Path | None,
        run_cap_usd: float,
        month_cap_usd: float,
        ledger: Ledger,
        model: GuardedModel | None,
        tools: RepairTools | None,
        templates: PromptTemplates | None,
        retriever: GuideRetriever | None,
        on_stage: StageCallback | None = None,
        worktree: Worktree | None = None,
        sandbox: str = "local",
        precheck_cache: PrecheckCache | None = None,
        guard_cap_usd: float | None = None,
        reviewer_factory: Any = None,
    ):
        self.repo = repo
        self.spec = spec
        self.configuration = configuration
        self.case = case
        self.traps = traps
        self.config = config
        self.runner = runner
        self.mode = mode
        self.keep_workspace = keep_workspace
        self.tools_cache = tools_cache
        self.run_cap_usd = run_cap_usd
        self.month_cap_usd = month_cap_usd
        self.ledger = ledger
        self.model = model
        self.tools = tools
        self.templates = templates
        self.retriever = retriever
        self.say = on_stage or (lambda _stage, _msg: None)
        self.worktree = worktree  # a real run's git worktree; None for a dry run
        self.sandbox = sandbox
        self.precheck_cache = precheck_cache  # speed-up 2 (M6); None: no cache
        # What the cost guard enforces per call: the run cap, or the lower hard stop.
        self.guard_cap_usd = guard_cap_usd if guard_cap_usd is not None else run_cap_usd
        self.reviewer_factory = reviewer_factory  # tests pass a fake; None: Claude

    @property
    def repair_on(self) -> bool:
        return self.configuration.repair.enabled and self.model is not None


# --------------------------------------------------------------------------- helpers


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-")


def _failures(rows: list[dict[str, Any]] | None) -> list[Failure]:
    return [Failure.model_validate(r) for r in rows or []]


def _dump_failures(failures: list[Failure]) -> list[dict[str, Any]]:
    return [f.model_dump(mode="json") for f in failures]


def _save_files(path: Path, files: FileSet) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(files, ensure_ascii=False), "utf-8")
    return str(path)


def _load_files(path: Path) -> FileSet:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text("utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def _tool_version(runner: CommandRunner, tool: str, cwd: Path) -> str | None:
    result = runner.run([tool, "--version"], cwd, timeout_s=30)
    return result.output.strip().removeprefix("v") if result.ok else None


def code_hashes(workspace: Path) -> dict[str, str]:
    """Hashes of the workspace's code files (the same set the cheating checks read)."""
    return {p: hash_file(workspace / p) for p in sorted(read_files(workspace))}


def repair_order(failing: list[str], files: FileSet) -> list[str]:
    """Failing files in repair order: a file before the files that (transitively)
    import it; otherwise non-component modules (``.ts``: themes, utilities) before
    components (``.tsx``), then by path. A shared module such as ``theme.ts`` reaches
    many screens through the app shell, so fixing it first stops its failures being
    charged to (and handed off from) the screens' repairs."""
    importers = import_graph(files)
    reach: dict[str, set[str]] = {}

    def importers_of(path: str) -> set[str]:
        if path not in reach:
            seen: set[str] = set()
            stack = list(importers.get(path, ()))
            while stack:
                p = stack.pop()
                if p not in seen:
                    seen.add(p)
                    stack.extend(importers.get(p, ()))
            reach[path] = seen
        return reach[path]

    remaining = sorted(failing, key=lambda p: (p.endswith((".tsx", ".jsx")), p))
    ordered: list[str] = []
    while remaining:
        for p in remaining:
            # p can go now unless another remaining file is imported by p (directly or not)
            if not any(p in importers_of(q) for q in remaining if q != p):
                ordered.append(p)
                remaining.remove(p)
                break
        else:  # an import cycle: take the first in the tie order
            ordered.append(remaining.pop(0))
    return ordered


# --------------------------------------------------------------------------- the graph


class RunGraph:
    """Builds the run's StateGraph over the stage functions."""

    def __init__(self, deps: RunDeps):
        self.d = deps

    # ------------------------------------------------------------------ plumbing

    def run_dir(self, state: RunState) -> Path:
        return Path(state["run_dir"])

    def workspace(self, state: RunState) -> Path:
        ws = state.get("workspace")
        if not ws:
            raise RuntimeError("the run has no workspace")
        return Path(ws)

    def logs(self, state: RunState) -> Path:
        return self.run_dir(state) / "logs"

    def snapshots(self, state: RunState) -> Path:
        return self.run_dir(state) / "state"

    def untouched(self, state: RunState) -> FileSet:
        return _load_files(self.snapshots(state) / "untouched.json")

    def after_rules(self, state: RunState) -> FileSet:
        return _load_files(self.snapshots(state) / "after-rules.json")

    def stale_rules(self, state: RunState) -> list[tuple[str, str]]:
        """Stylesheet rules under the Rules stage's failing TODOs (M7)."""
        check = self.d.config.leftovers
        if check is None or not check.todo_markers:
            return []
        return rules_under_todos(self.after_rules(state), check.todo_markers)

    def timed(self, state: RunState, stage: str, t0: float) -> dict[str, float]:
        timings = dict(state.get("timings") or {})
        timings[stage] = round(timings.get(stage, 0.0) + time.monotonic() - t0, 2)
        return timings

    def attempt_model(self, attempt: int) -> str:
        models = self.d.configuration.repair.attempt_models
        return models[min(attempt, len(models)) - 1]

    def report_of(self, state: RunState) -> RepairReport:
        return RepairReport.model_validate(
            state.get("repair") or {"enabled": self.d.configuration.repair.enabled}
        )

    # ------------------------------------------------------------------ stages

    def scan_node(self, state: RunState) -> RunState:
        t0 = time.monotonic()
        d = self.d
        d.say("Scan", f"scanning {d.repo.name}")
        usage = scan(
            ScanInput(
                repo=d.repo,
                spec=d.spec,
                source_globs=d.config.source_globs,
                exclude=d.config.exclude,
            )
        )
        run_dir = self.run_dir(state)
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(usage, run_dir / "usage-report.json")
        (run_dir / "usage-report.md").write_text(render_usage_report(usage), "utf-8")
        d.say(
            "Scan",
            f"{usage.totals.affected_files} affected files, {usage.totals.old_usages} usages",
        )
        return {
            "usage_path": str(run_dir / "usage-report.json"),
            "config": d.config.model_dump(mode="json"),
            "repair": RepairReport(enabled=d.configuration.repair.enabled).model_dump(mode="json"),
            "calls": [],
            "timings": self.timed(state, "scan", t0),
        }

    def precheck_node(self, state: RunState) -> RunState:
        t0 = time.monotonic()
        d = self.d
        if d.worktree is not None:
            workspace = d.worktree.workspace  # a real run: the worktree on the migration branch
        else:
            parent = Path(tempfile.mkdtemp(prefix=f"migrator-{state['run_id']}-"))
            workspace = parent / "workspace"
        untouched = self.snapshots(state) / "untouched.json"
        if d.precheck_cache is not None and d.worktree is None:
            # Speed-up 2 (M6): one install and Pre-check per case, cloned into each run.
            cache = d.precheck_cache
            key = cache_key(d.repo, d.config, self.where())
            with cache.locked(key):
                hit = cache.get(key)
                if hit is None:
                    create_dry_run_workspace(d.repo, workspace)
                    node_version, npm_version, pre = self.run_precheck(state, workspace)
                    if pre.status == "ok":
                        volume = self.snapshot_node_modules(key)
                        cache.put(
                            key,
                            workspace,
                            self.logs(state),
                            CachedPrecheck(
                                precheck=pre,
                                node_version=node_version,
                                npm_version=npm_version,
                                node_modules_volume=volume,
                            ),
                            untouched,
                        )
                else:
                    d.say("Pre-check", "reusing this case's cached install and Pre-check")
                    run_box = _base_runner(d.runner)
                    if hit.node_modules_volume and isinstance(run_box, RunContainerRunner):
                        run_box.seed_node_modules(hit.node_modules_volume)
                    clone_tree(cache.workspace(key), workspace)
                    restore_logs(cache, key, self.logs(state))
                    untouched.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(cache.entry(key) / "untouched.json", untouched)
                    node_version, npm_version, pre = hit.node_version, hit.npm_version, hit.precheck
        else:
            if d.worktree is None:
                create_dry_run_workspace(d.repo, workspace)
            node_version, npm_version, pre = self.run_precheck(state, workspace)
        d.say("Pre-check", pre.status if pre.status == "ok" else f"rejected: {pre.reason}")
        before = self.visual_capture(state, workspace, "before") if pre.status == "ok" else None
        return {
            "visual_before": before,
            "workspace": str(workspace),
            "node_version": node_version,
            "npm_version": npm_version,
            "precheck": pre.model_dump(mode="json"),
            "timings": self.timed(state, "precheck", t0),
        }

    def review_flagged(
        self, state: RunState, record: FileRepair, flagged: str, model: str
    ) -> Review | None:
        """The test-fitting reviewer on one flagged patch (M6 option D); None when its
        call doesn't fit the caps or fails (the flag then decides, as without it)."""
        d = self.d
        workspace = self.workspace(state)
        after = self.after_rules(state)
        current = {rel: (workspace / rel).read_text("utf-8") for rel in record.touched}
        failures = failing_tests_of(record.path, _failures(state.get("file_start_failures")))
        tests = read_tests(workspace, failures)
        lines = flagged.removeprefix("possible test-fitting: ").split("; ")
        query = " ".join([*re.findall(r"[A-Z][A-Za-z]+|aria-\w+|describeChild", " ".join(lines))])
        guide = (
            [render_section(doc, d.spec.guide.link_base) for doc in d.retriever.rank(query, k=2)]
            if d.retriever is not None and query
            else []
        )
        prompt = review_prompt(
            record.path, patch_diff(record.touched, after, current), lines, failures, tests, guide
        )
        spent = sum(CallRecord.model_validate(c).cost_usd for c in state.get("calls") or [])
        try:
            return review_patch(
                prompt,
                model=model,
                guard=CostGuard(d.guard_cap_usd, d.month_cap_usd, d.ledger),
                ledger=d.ledger,
                run_id=state["run_id"],
                case=d.case.id if d.case else None,
                path=record.path,
                run_spent_usd=spent,
                factory=d.reviewer_factory or default_review_model,
            )
        except Exception as exc:  # the flag still decides: a hand-off
            d.say("Repair", f"{record.path}: the reviewer could not answer ({exc})")
            return None

    def visual_capture(self, state: RunState, workspace: Path, label: str) -> dict[str, Any] | None:
        """Screenshots of the app as ``workspace`` is now (M7), or why there are none; None
        when the repo has no [visual] section. A failure never fails the run."""
        d = self.d
        cfg = d.config.visual
        if cfg is None:
            return None
        if d.sandbox != "docker":
            return {"skipped": "the visual check runs only in the Docker sandbox"}
        cfg = cfg.model_copy(update={"hide": [*d.spec.visual_hide, *cfg.hide]})
        made_out = cfg.build is not None and not (workspace / cfg.out).exists()
        t0 = time.monotonic()
        try:
            browser = DockerRunner(ensure_browser_image())
            tools = ensure_visual_tools(browser, d.tools_cache)
            cap = capture(
                workspace,
                cfg,
                self.run_dir(state) / "visual" / label,
                build_runner=d.runner,
                browser_runner=browser,
                tools=tools,
            )
        except (VisualError, SandboxError, ToolsError) as exc:
            d.say("Visual", f"{label}: {exc}")
            return {"skipped": f"the {label} capture failed: {exc}"}
        finally:
            if made_out:  # the repo's build output must not end up in a commit
                shutil.rmtree(workspace / cfg.out, ignore_errors=True)
        ok = sum(p.ok for p in cap.pages)
        d.say(
            "Visual",
            f"{label}: {ok} of {len(cap.pages)} pages ({round(time.monotonic() - t0)} s)",
        )
        return cap.model_dump(mode="json")

    def visual_report(self, state: RunState, finished: bool) -> VisualReport | None:
        """Before against after, page by page, and pages that broke (M7)."""
        cfg = self.d.config.visual
        if cfg is None:
            return None
        before = state.get("visual_before")
        if not before or before.get("skipped"):
            why = (before or {}).get("skipped") or "there is no before capture"
            return VisualReport(skipped=str(why))
        if not finished:
            return VisualReport(skipped="the run stopped before its final verify")
        after = self.visual_capture(state, self.workspace(state), "after")
        if not after or after.get("skipped"):
            return VisualReport(skipped=str((after or {}).get("skipped")))
        names = [p.name for p in cfg.pages]
        files = {p.name: p.files for p in cfg.pages}
        comparisons = []
        reference = self.visual_reference()
        if reference is not None:
            comparisons.append(
                compare_captures(
                    reference,
                    Path(after["folder"]),
                    names,
                    self.run_dir(state) / "visual" / "reference-vs-after",
                    a_label="the reference PR",
                    b_label="this run",
                    threshold=cfg.threshold,
                    files=files,
                )
            )
        comparisons.append(
            compare_captures(
                Path(before["folder"]),
                Path(after["folder"]),
                names,
                self.run_dir(state) / "visual" / "before-vs-after",
                a_label="before",
                b_label="after",
                threshold=cfg.threshold,
                files=files,
            )
        )
        return VisualReport(
            built_by=str(after.get("built_by")),
            comparisons=comparisons,
            new_page_errors=new_page_errors(before["pages"], after["pages"], "after"),
        )

    def visual_reference(self) -> Path | None:
        """For a real-repo eval case: screenshots of the reference PR's own build, made
        once per case and visual config and kept in the cache (M7). None without one."""
        d = self.d
        cfg = d.config.visual
        if cfg is None or d.case is None or d.case.upstream is None or d.mode != "eval":
            return None
        from migrator.evals.upstream import materialize_reference
        from migrator.verify import install

        cfg = cfg.model_copy(update={"hide": [*d.spec.visual_hide, *cfg.hide]})
        try:
            image = ensure_browser_image()
            browser = DockerRunner(image)
            tools = ensure_visual_tools(browser, d.tools_cache)
            key = hashlib.sha256(
                "\0".join(
                    [d.case.upstream.reference_head, cfg.model_dump_json(), image, tools.name]
                ).encode()
            ).hexdigest()[:16]
            out = (d.tools_cache or tools_cache_root()) / "visual-reference" / f"{d.case.id}-{key}"
            if (out / "shots" / "capture.json").is_file():
                return out / "shots"
            ref = materialize_reference(d.case, d.tools_cache)
            if not (ref / "node_modules").is_dir():
                d.say("Visual", "installing the reference PR's dependencies (once per case)")
                done = install(d.runner, ref, d.config, frozen=True, log_file=out / "install.log")
                if not done.ok:
                    raise VisualError(f"installing the reference failed; see {out / 'install.log'}")
            cap = capture(ref, cfg, out, build_runner=d.runner, browser_runner=browser, tools=tools)
        except (VisualError, SandboxError, ToolsError, GitError, ValueError) as exc:
            d.say("Visual", f"no reference capture: {exc}")
            return None
        d.say("Visual", f"reference PR: {sum(p.ok for p in cap.pages)} of {len(cap.pages)} pages")
        return cap.folder

    def where(self) -> str:
        """Where commands run, as part of the Pre-check cache key."""
        d = self.d
        if d.sandbox != "docker":
            return "local"
        box = _base_runner(d.runner)
        volume = isinstance(box, RunContainerRunner) and box.node_modules_volume
        return f"docker:{node_image(d.config.node)}" + (":node_modules-volume" if volume else "")

    def snapshot_node_modules(self, key: str) -> str | None:
        """With node_modules in the run's volume (speed-up 4): copy it to a cache volume."""
        box = _base_runner(self.d.runner)
        if not isinstance(box, RunContainerRunner) or box.volume is None:
            return None
        name = f"migrator-nm-cache-{key}"
        box._docker("volume", "rm", "-f", name, timeout_s=60)
        box.new_volume(name)
        box.copy_volume(box.volume, name)
        return name

    def run_precheck(
        self, state: RunState, workspace: Path
    ) -> tuple[str | None, str | None, PrecheckResult]:
        """Install and verify the untouched workspace (the Pre-check itself)."""
        d = self.d
        node_version = _tool_version(d.runner, "node", workspace)
        npm_version = _tool_version(d.runner, d.config.package_manager, workspace)
        # What the Pre-check verifies: the untouched workspace, for the cheating checks.
        _save_files(self.snapshots(state) / "untouched.json", read_files(workspace))
        d.say("Pre-check", "installing and verifying the untouched workspace")
        pre = precheck(
            PrecheckInput(workspace=workspace, config=d.config, log_dir=self.logs(state)), d.runner
        )
        return node_version, npm_version, pre

    def rules_node(self, state: RunState) -> RunState:
        t0 = time.monotonic()
        d = self.d
        if state.get("rules_done"):
            return {}
        marker = self.snapshots(state) / "rules-started"
        if marker.exists():
            raise RuntimeError(
                "the Rules stage was interrupted part-way in this run; the codemods are not "
                "idempotent, so it cannot run again on this workspace. Start a new run."
            )
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(_now(), "utf-8")
        workspace = self.workspace(state)
        usage = UsageReport.model_validate_json(Path(state["usage_path"]).read_text("utf-8"))
        d.say("Rules", "running the rule steps")
        try:
            tools = ensure_tools(d.spec, d.runner, d.tools_cache) if d.spec.tools else None
        except ToolsError as exc:
            rules = RulesResult(status="rules_failure", reason=str(exc), steps=[], changed_files=[])
        else:
            rules = apply_rules(
                RulesInput(
                    probe_bins=isinstance(_base_runner(d.runner), RunContainerRunner)
                    and _base_runner(d.runner).node_modules_volume,
                    workspace=workspace,
                    spec=d.spec,
                    config=d.config,
                    affected_files=usage.affected_files(),
                    tools_dir=tools,
                    log_dir=self.logs(state),
                ),
                d.runner,
            )
        d.say(
            "Rules",
            f"{len(rules.changed_files)} files changed"
            if rules.status == "ok"
            else f"Rules failure: {rules.reason}",
        )
        _save_files(self.snapshots(state) / "after-rules.json", read_files(workspace))
        return {
            "rules": rules.model_dump(mode="json"),
            "rules_done": True,
            "timings": self.timed(state, "rules", t0),
        }

    def verify_node(self, state: RunState) -> RunState:
        t0 = time.monotonic()
        d = self.d
        pre = PrecheckResult.model_validate(state["precheck"])
        d.say("Verify", "type-check, lint, tests")
        result = verify(
            VerifyInput(
                workspace=self.workspace(state),
                commands=d.config.verify,
                runner=d.config.runner,
                log_dir=self.logs(state),
                label="verify",
                pre_existing=pre.pre_existing_failures,
                leftovers=d.config.leftovers,
                stale_rules=self.stale_rules(state),
            ),
            d.runner,
        )
        d.say("Verify", f"{len(result.failures)} failures in {len(result.failing_files())} files")
        updates: list[dict[str, Any]] = []
        if d.config.update_snapshots:
            result, updates = self.update_snapshots(state, result, "verify")
            if updates:
                # The Migrator's own change, before repair: part of the Rules layer.
                _save_files(
                    self.snapshots(state) / "after-rules.json",
                    read_files(self.workspace(state)),
                )
        return {
            "verify": result.model_dump(mode="json"),
            "known_failures": _dump_failures(result.failures),
            "snapshot_updates": updates,
            "timings": self.timed(state, "verify", t0),
        }

    def update_snapshots(
        self, state: RunState, result: VerifyResult, stage: str
    ) -> tuple[VerifyResult, list[dict[str, Any]]]:
        """The snapshot policy (M6): rewrite snapshot-only failures, list each one."""
        d = self.d
        workspace = self.workspace(state)
        result, run = update_snapshots(
            VerifyInput(
                workspace=workspace,
                commands=d.config.verify,
                runner=d.config.runner,
                log_dir=self.logs(state),
                label=stage,
            ),
            result,
            d.runner,
            lambda: snapshot_hashes(workspace),
        )
        if run is None:
            return result, []
        snaps = run.changed_files
        updates = [
            SnapshotUpdate(
                test_file=t,
                snapshot_file=next((s for s in snaps if snapshot_belongs(s, t)), None),
                tests=names,
                stage=stage,
            ).model_dump(mode="json")
            for t, names in run.updated.items()
        ]
        d.say(
            "Verify",
            f"snapshots: updated {len(updates)} test files whose only failures were "
            f"snapshot mismatches ({len(snaps)} snapshot files changed), for a human to review",
        )
        return result, updates

    # ------------------------------------------------------------------ repair

    def plan_repair_node(self, state: RunState) -> RunState:
        d = self.d
        result = VerifyResult.model_validate(state["verify"])
        untouched = self.untouched(state)
        after = self.after_rules(state)
        tests = find_test_files(untouched, after.keys(), read_test_rules(self.workspace(state)))
        failing = [p for p in result.failing_files() if p in after]
        if not d.repair_on:
            return {"test_files": tests, "queue": [], "review_queue": []}
        order = repair_order(failing, after)
        causes: list[SharedCause] = []
        if d.configuration.repair.shared_causes:
            causes = find_shared_causes(result.failures, after, tests)
            sources = [c.source for c in causes if c.source in after]
            order = [*dict.fromkeys(sources), *[p for p in order if p not in sources]]
            for c in causes:
                d.say(
                    "Repair",
                    f"shared cause: {c.code} on {c.symbol} from {c.source} in "
                    f"{len(c.callers)} files; repairing {c.source} first",
                )
        d.say("Repair", f"{len(order)} failing files to repair: {', '.join(order) or 'none'}")
        reserve = d.configuration.cost.reserve_attempt_usd
        if reserve is not None and order:
            # Runs must finish (M6): reserve the whole worst case before the first call.
            # Failing test files are handed off without a model call, so they cost nothing.
            paid = [p for p in order if p not in tests]
            attempts = d.configuration.repair.max_attempts
            worst = round(len(paid) * attempts * reserve, 2)
            ok, available = reserve_run(
                state["run_id"], worst, d.run_cap_usd, d.month_cap_usd, d.ledger
            )
            report = self.report_of(state)
            report.reserved_usd = worst
            if not ok:
                why = (
                    f"the worst case ({len(paid)} files x {attempts} attempts x ${reserve:.2f} "
                    f"= ${worst:.2f}) is more than the ${available:.2f} available (run cap "
                    f"${d.run_cap_usd:.2f}, less what this month and other running runs have "
                    "spent or reserved), so repair did not start"
                )
                report.stopped_by_cost_cap = True
                report.cost_cap_reason = why
                d.say("Repair", why)
            else:
                d.say("Repair", f"reserved ${worst:.2f} of ${available:.2f} available")
            return {
                "test_files": tests,
                "queue": order,
                "review_queue": [],
                "messages": [],
                "repair": report.model_dump(mode="json"),
                "shared_causes": [c.model_dump(mode="json") for c in causes],
            }
        return {
            "test_files": tests,
            "queue": order,
            "review_queue": [],
            "messages": [],
            "shared_causes": [c.model_dump(mode="json") for c in causes],
        }

    def next_file_node(self, state: RunState) -> RunState:
        report = self.report_of(state)
        queue = list(state.get("queue") or [])
        if report.stopped_by_cost_cap and queue:
            for path in queue:
                report.files.append(
                    FileRepair(path=path, outcome="Unmigrated", reason="cost cap: not attempted")
                )
            self.d.say("Repair", f"cost cap: {len(queue)} files not attempted")
            return {"queue": [], "repair": report.model_dump(mode="json")}
        if self.d.configuration.repair.shared_causes and queue:
            # After a shared definition was repaired, only callers that still fail stay.
            known = {f.file for f in _failures(state.get("known_failures"))}
            sources = {c["source"] for c in state.get("shared_causes") or []}
            kept = [p for p in queue if p in known or p in sources]
            if kept != queue:
                gone = [p for p in queue if p not in kept]
                self.d.say("Repair", f"no longer failing, skipped: {', '.join(gone)}")
                return {"queue": kept}
        return {}

    def route_next_file(self, state: RunState) -> str:
        return "start_file" if state.get("queue") else "commit_agent"

    def start_file_node(self, state: RunState) -> RunState:
        d = self.d
        assert d.templates is not None and d.retriever is not None
        queue = list(state.get("queue") or [])
        path = queue.pop(0)
        workspace = self.workspace(state)
        after = self.after_rules(state)
        tests = state.get("test_files") or {}
        known = _failures(state.get("known_failures"))
        mine = [f for f in known if f.file == path]
        causes = [SharedCause.model_validate(c) for c in state.get("shared_causes") or []]
        owned = [c for c in causes if c.source == path]
        calling = [c for c in causes if path in c.callers and c.source != path]
        target_keys: list[tuple[str, str]] = []
        for c in owned:
            still = [f for f in known if (f.file, f.code) in c.failure_keys()]
            mine += [f for f in still if f not in mine]
            target_keys += [(str(f.file), str(f.code)) for f in still]
        first_model = d.configuration.repair.attempt_models[0]
        record = FileRepair(path=path, attempts=[AttemptRecord(number=1, model=first_model)])
        session = SessionState(
            path=path,
            max_attempts=d.configuration.repair.max_attempts,
            allowed_imports=[p for p in local_imports(path, after) if p not in tests],
            baseline_keys=[failure_key(f) for f in known],
            record=record,
            target_keys=sorted(set(target_keys)),
        )
        d.say("Repair", f"{path}: {len(mine)} failures")
        if path in tests:
            session.ended = "handed_off"
            record.outcome = "Handed off"
            record.reason = (
                f"the failure is in a Test file ({tests[path]}), which only a human may change"
            )
            record.attempts = []
            return {
                "queue": queue,
                "current": session.model_dump(mode="json"),
                "messages": [],
                "file_start_failures": state.get("known_failures") or [],
            }
        usage = UsageReport.model_validate_json(Path(state["usage_path"]).read_text("utf-8"))
        file_usages = usage.file(path)
        symbols = [u.symbol.split(".")[0] for u in file_usages.old_usages] if file_usages else []
        text = first_message(
            d.templates,
            d.spec,
            d.retriever,
            path=path,
            max_attempts=session.max_attempts,
            failures=mine,
            untouched=self.untouched(state).get(path),
            after_rules=(workspace / path).read_text("utf-8"),
            files={
                **after,
                **{
                    p: (workspace / p).read_text("utf-8")
                    for p in after
                    if (workspace / p).is_file()
                },
            },
            test_files=tests,
            symbols=list(dict.fromkeys(s for s in symbols if s != "*")),
        )
        if owned or calling:
            sections = [shared_cause_section(c, path) for c in [*owned, *calling]]
            text += "\n\n### Shared cause\n\n" + "\n\n".join(sections)
        return {
            "queue": queue,
            "current": session.model_dump(mode="json"),
            "messages": [HumanMessage(content=text)],
            "file_start_failures": state.get("known_failures") or [],
        }

    def route_start_file(self, state: RunState) -> str:
        current = state.get("current") or {}
        return "file_end" if current.get("ended") else "agent"

    def agent_node(self, state: RunState) -> RunState:
        t0 = time.monotonic()
        d = self.d
        assert d.model is not None and d.templates is not None
        session = SessionState.model_validate(state["current"])
        report = self.report_of(state)
        calls = [CallRecord.model_validate(c) for c in state.get("calls") or []]
        spent = sum(c.cost_usd for c in calls)
        model = self.attempt_model(session.attempt)
        record = session.record
        if not record.attempts or record.attempts[-1].number != session.attempt:
            record.attempts.append(AttemptRecord(number=session.attempt, model=model))
        system = system_prompt(d.templates, d.spec, max_attempts=session.max_attempts)
        messages = list(state.get("messages") or [])
        try:
            message, call = d.model.call(
                model,
                system,
                messages,
                run_spent_usd=spent,
                file=session.path,
                attempt=session.attempt,
                effort=d.configuration.repair.effort_for(session.attempt),
            )
        except CostCapError as exc:
            session.ended = "cost_cap"
            record.outcome = "Unmigrated"
            record.reason = f"cost cap: {exc}"
            record.attempts[-1].result = "cost_cap"
            report.stopped_by_cost_cap = True
            report.cost_cap_reason = str(exc)
            d.say("Repair", f"cost cap reached: {exc}")
            return {
                "current": session.model_dump(mode="json"),
                "repair": report.model_dump(mode="json"),
                "timings": self.timed(state, "repair", t0),
            }
        record.attempts[-1].stop_reason = call.stop_reason
        if call.stop_reason == "refusal":
            session.ended = "handed_off"
            record.outcome = "Handed off"
            record.reason = "the model declined the request (refusal)"
            record.attempts[-1].result = "handed_off"
        return {
            "current": session.model_dump(mode="json"),
            "messages": [*messages, message],
            "calls": [*[c.model_dump(mode="json") for c in calls], call.model_dump(mode="json")],
            "timings": self.timed(state, "repair", t0),
        }

    def route_agent(self, state: RunState) -> str:
        current = state.get("current") or {}
        return "file_end" if current.get("ended") else "tools"

    def tools_node(self, state: RunState) -> RunState:
        t0 = time.monotonic()
        d = self.d
        assert d.tools is not None and d.templates is not None and d.retriever is not None
        session_state = SessionState.model_validate(state["current"])
        messages = list(state.get("messages") or [])
        last = messages[-1] if messages else None
        known = _failures(state.get("known_failures"))
        pre = PrecheckResult.model_validate(state["precheck"])
        session = RepairSession(
            session_state,
            workspace=self.workspace(state),
            after_rules=self.after_rules(state),
            test_files=state.get("test_files") or {},
            known_failures=known,
            pre_existing=pre.pre_existing_failures,
            config=d.config,
            runner=d.runner,
            log_dir=self.logs(state),
            templates=d.templates,
            retriever=d.retriever,
            link_base=d.spec.guide.link_base,
        )
        d.tools.session = session
        new: list[BaseMessage] = []
        try:
            calls = last.tool_calls if isinstance(last, AIMessage) else []
            if not calls:
                # No tool call (text only, or cut off): nudge, and count it against the budget.
                session_state.tool_calls += 1
                session.current_attempt.tool_calls += 1
                new.append(HumanMessage(content=NUDGE))
            for call in calls:
                if session_state.ended is not None:
                    new.append(
                        ToolMessage(
                            content="Not run: this file's repair has ended.",
                            tool_call_id=call["id"] or "",
                            name=call["name"],
                            status="error",
                        )
                    )
                    continue
                attempt_before = session_state.attempt
                session_state.tool_calls += 1
                session.current_attempt.tool_calls += 1
                new.append(d.tools.invoke(call))
                if session_state.ended is None and session_state.attempt != attempt_before:
                    # run_verify failed and a new attempt starts: later calls are its own
                    session.record.attempts.append(
                        AttemptRecord(
                            number=session_state.attempt,
                            model=self.attempt_model(session_state.attempt),
                        )
                    )
            if session_state.ended is None and session_state.tool_calls >= MAX_TOOL_CALLS:
                session.hand_off(
                    f"tool-call budget used: {MAX_TOOL_CALLS} calls in attempt "
                    f"{session_state.attempt} without passing run_verify"
                )
        finally:
            d.tools.session = None
        return {
            "current": session_state.model_dump(mode="json"),
            "messages": [*messages, *new],
            "known_failures": _dump_failures(session.known_failures),
            "timings": self.timed(state, "repair", t0),
        }

    def route_tools(self, state: RunState) -> str:
        current = state.get("current") or {}
        return "file_end" if current.get("ended") else "agent"

    def file_end_node(self, state: RunState) -> RunState:
        d = self.d
        session = SessionState.model_validate(state["current"])
        record = session.record
        report = self.report_of(state)
        workspace = self.workspace(state)
        review_queue = list(state.get("review_queue") or [])
        updates: RunState = {}
        if session.ended == "cost_cap":
            # No half-done patch lands: put the file back as this repair found it.
            for rel, text in session.originals.items():
                (workspace / rel).write_text(text, "utf-8")
            record.touched = []
            record.patch_lines = {}
            updates["known_failures"] = state.get("file_start_failures") or []
        elif session.ended == "passed" and d.mode == "cli":
            after = self.after_rules(state)
            hits = [
                f"{rel}: {', '.join(found)}"
                for rel in record.touched
                if (
                    found := added_escape_hatches(
                        rel, after.get(rel, ""), (workspace / rel).read_text("utf-8")
                    )
                )
            ]
            if hits:  # in real use a cheating-check hit is a hand-off, not a migrated file
                record.outcome = "Handed off"
                record.reason = "cheating check: " + "; ".join(hits)
        if (
            session.ended == "passed"
            and record.outcome == "Migrated by agent"
            and d.configuration.repair.test_fitting_hand_off
        ):
            # M6: a passing patch that changes what a failing test looks at (accessibility
            # props, the rendered element) goes to a human instead of counting as migrated.
            why = test_fitting_reason(
                record.path,
                record.touched,
                self.after_rules(state),
                {rel: (workspace / rel).read_text("utf-8") for rel in record.touched},
                _failures(state.get("file_start_failures")),
            )
            reviewer = d.configuration.repair.reviewer_model
            if why is not None and reviewer is not None:
                review = self.review_flagged(state, record, why, reviewer)
                if review is not None:
                    updates["calls"] = [
                        *(state.get("calls") or []),
                        review.call.model_dump(mode="json"),
                    ]
                    record.reviewed_by = review.model
                    record.review_verdict = review.verdict
                    record.review_reason = review.reason
                    if review.verdict == "v5_required":
                        d.say("Repair", f"{record.path}: flagged, reviewed as v5_required")
                        why = None  # stays migrated; the review is a note for a human
            if why is not None:
                record.outcome = "Handed off"
                record.test_fitting_hand_off = True
                record.reason = why + (
                    f" (reviewed by {record.reviewed_by}: {record.review_reason})"
                    if record.reviewed_by
                    else ""
                )
        if record.outcome == "Handed off":
            review_queue.append(record.path)
            report.review_list.append(record.path)
            if session.originals:
                # Set the patch aside until Review: the next files are repaired in a
                # workspace without it (a broken patch must not fail their tests).
                known = _failures(state.get("known_failures"))
                record.failures_at_hand_off = [
                    describe_failure(f, record.path) for f in known if f.file == record.path
                ]
                record.originals = dict(session.originals)
                record.set_aside = {
                    rel: (workspace / rel).read_text("utf-8") for rel in session.originals
                }
                for rel, text in session.originals.items():
                    (workspace / rel).write_text(text, "utf-8")
                updates["known_failures"] = state.get("file_start_failures") or []
        messages = list(state.get("messages") or [])
        if messages:
            conv = self.run_dir(state) / "repair" / f"{_slug(record.path)}.json"
            conv.parent.mkdir(parents=True, exist_ok=True)
            conv.write_text(
                json.dumps(messages_to_dict(messages), indent=2, ensure_ascii=False), "utf-8"
            )
            record.conversation = str(conv.relative_to(self.run_dir(state)))
        report.files.append(record)
        d.say(
            "Repair",
            f"{record.path}: {record.outcome}" + (f" ({record.reason})" if record.reason else ""),
        )
        return {
            **updates,
            "current": None,
            "messages": [],
            "repair": report.model_dump(mode="json"),
            "review_queue": review_queue,
        }

    # ------------------------------------------------------------------ review

    def prepare_review_node(self, state: RunState) -> RunState:
        queue = list(state.get("review_queue") or [])
        if not queue:
            return {"review": None}
        path = queue[0]
        report = self.report_of(state)
        record = report.record(path) or FileRepair(path=path)
        workspace = self.workspace(state)
        after = self.after_rules(state)
        known = _failures(state.get("known_failures"))
        failures = [describe_failure(f, path) for f in known if f.file == path]
        updates: RunState = {}
        if record.set_aside and not record.restored_for_review:
            # Put the patch back for the human to see (and edit); Revert removes it.
            for rel, text in record.set_aside.items():
                (workspace / rel).write_text(text, "utf-8")
            record.restored_for_review = True
            failures = record.failures_at_hand_off
            updates["repair"] = report.model_dump(mode="json")
        diff = "".join(
            unified_diff(rel, after.get(rel), (workspace / rel).read_text("utf-8"))
            for rel in record.touched
            if (workspace / rel).is_file()
        )
        attempts = [
            f"attempt {a.number} ({a.model}, {a.tool_calls} tool calls): {a.result or '—'}"
            + (f", {a.failures_left} failures left" if a.failures_left is not None else "")
            + (f' — "{a.note}"' if a.note else "")
            for a in record.attempts
        ]
        payload = ReviewPayload(
            path=path,
            reason=record.reason or "handed off",
            attempts=attempts,
            failures=failures,
            diff=diff,
            workspace=str(workspace),
            hashes=code_hashes(workspace),
            remaining=len(queue) - 1,
        )
        return {**updates, "review": payload.model_dump(mode="json")}

    def route_prepare_review(self, state: RunState) -> str:
        return "review" if state.get("review") else "commit_review"

    def review_node(self, state: RunState) -> RunState:
        # Nothing before interrupt(): on resume this node starts again from here.
        payload = ReviewPayload.model_validate(state["review"])
        answer = interrupt(payload.model_dump(mode="json"), response_schema=ReviewAnswer)
        if isinstance(answer, dict):
            answer = ReviewAnswer.model_validate(answer)
        d = self.d
        workspace = self.workspace(state)
        report = self.report_of(state)
        record = report.record(payload.path)
        if record is None:
            raise RuntimeError(f"no repair record for {payload.path}")
        now = code_hashes(workspace)
        changed = sorted(
            p for p in now.keys() | payload.hashes.keys() if now.get(p) != payload.hashes.get(p)
        )
        for rel in changed:
            if rel not in report.human_changed:
                report.human_changed.append(rel)
        known = _failures(state.get("known_failures"))
        queue = list(state.get("review_queue") or [])
        record.review = answer.choice
        updates: RunState = {}
        if answer.choice == "revert":
            after = self.after_rules(state)
            for rel in record.touched:
                if rel in changed:
                    continue  # a human changed it while paused: theirs wins
                before = record.originals.get(rel, after.get(rel))
                if before is not None:
                    (workspace / rel).write_text(before, "utf-8")
            record.touched = [rel for rel in record.touched if rel in changed]
            queue.pop(0)
        elif answer.choice == "keep":
            queue.pop(0)
        else:  # edit: the human changed files; check the file again with the narrow verify
            assert d.templates is not None and d.retriever is not None
            pre = PrecheckResult.model_validate(state["precheck"])
            session = RepairSession(
                SessionState(
                    path=payload.path,
                    baseline_keys=[failure_key(f) for f in known if f.file != payload.path],
                    record=record.model_copy(
                        update={"touched": sorted({*record.touched, *changed})}
                    ),
                ),
                workspace=workspace,
                after_rules=self.after_rules(state),
                test_files=state.get("test_files") or {},
                known_failures=known,
                pre_existing=pre.pre_existing_failures,
                config=d.config,
                runner=d.runner,
                log_dir=self.logs(state),
                templates=d.templates,
                retriever=d.retriever,
                link_base=d.spec.guide.link_base,
            )
            left, elsewhere, _ran = session.narrow_verify(f"review-{_slug(payload.path)}")
            known = session.known_failures
            if not left and not elsewhere:
                record.migrated_by_human = True
                queue.pop(0)
                d.say("Review", f"{payload.path}: fixed by a human")
            else:
                d.say(
                    "Review",
                    f"{payload.path}: still {len(left) + len(elsewhere)} failures after the edit",
                )
        updates.update(
            {
                "repair": report.model_dump(mode="json"),
                "review_queue": queue,
                "known_failures": _dump_failures(known),
                "review": None,
            }
        )
        return updates

    # ------------------------------------------------------------------ stage commits

    def commit_rules_node(self, state: RunState) -> RunState:
        return self.commit(state, "rules")

    def commit_agent_node(self, state: RunState) -> RunState:
        return self.commit(state, "agent")

    def commit_review_node(self, state: RunState) -> RunState:
        return self.commit(state, "review")

    def commit(self, state: RunState, stage: StageName) -> RunState:
        """Commit one stage's changes on a real run's branch, once (a no-op for dry runs)."""
        d = self.d
        if d.worktree is None:
            return {}
        commits = [StageCommit.model_validate(c) for c in state.get("commits") or []]
        if any(c.stage == stage for c in commits):
            return {}
        title, body = self.commit_message(stage, state)
        made = commit_stage(d.worktree, run_id=state["run_id"], stage=stage, title=title, body=body)
        if made is None:
            d.say("Commit", f"{stage}: nothing changed, no commit")
            return {}
        d.say("Commit", f"{made.sha[:8]} {made.title} ({len(made.files)} files)")
        return {
            "commits": [*[c.model_dump(mode="json") for c in commits], made.model_dump(mode="json")]
        }

    def commit_message(self, stage: StageName, state: RunState) -> tuple[str, str]:
        migration = f"{self.d.spec.from_} to {self.d.spec.to}"
        if stage == "rules":
            return f"Migrate {migration}: Rules (codemods and dependency map)", rules_commit_body(
                RulesResult.model_validate(state["rules"])
            )
        report = self.report_of(state)
        if stage == "agent":
            fixed = [f for f in report.files if f.outcome == "Migrated by agent"]
            calls = [CallRecord.model_validate(c) for c in state.get("calls") or []]
            return (
                f"Migrate {migration}: repair agent fixes in {len(fixed)} files",
                agent_commit_body(report, calls),
            )
        return f"Migrate {migration}: changes made at Review", review_commit_body(report)

    # ------------------------------------------------------------------ final verify, report

    def final_verify_node(self, state: RunState) -> RunState:
        t0 = time.monotonic()
        d = self.d
        pre = PrecheckResult.model_validate(state["precheck"])
        workspace = self.workspace(state)
        report = self.report_of(state)
        repaired = any(f.touched for f in report.files) or bool(report.human_changed)
        if state.get("verify") and not repaired:
            # Nothing changed since the Verify after Rules: it is the final verify.
            final = VerifyResult.model_validate(state["verify"])
        else:
            d.say("Verify", "final: type-check, lint, tests")
            final = verify(
                VerifyInput(
                    workspace=workspace,
                    commands=d.config.verify,
                    runner=d.config.runner,
                    log_dir=self.logs(state),
                    label="final",
                    pre_existing=pre.pre_existing_failures,
                    leftovers=d.config.leftovers,
                    stale_rules=self.stale_rules(state),
                ),
                d.runner,
            )
        final_snapshots: list[dict[str, Any]] = []
        if d.config.update_snapshots:
            final, final_snapshots = self.update_snapshots(state, final, "final")
        final_usage = scan(
            ScanInput(
                repo=workspace,
                spec=d.spec,
                source_globs=d.config.source_globs,
                exclude=d.config.exclude,
            )
        )
        final_usage_path = self.run_dir(state) / "state" / "final-usage.json"
        write_json(final_usage, final_usage_path)
        final_files = read_files(workspace)
        # The final code, for scoring against a reference PR afterwards (M6).
        _save_files(self.snapshots(state) / "final.json", final_files)
        after = self.after_rules(state)
        cheating = run_checks(
            CheckInput(
                before=self.untouched(state),
                after_rules=after,
                final=final_files,
                later_layers=final_layers(
                    after, final_files, report, self.migrator_snapshots(state, final_snapshots)
                ),
                test_rules=read_test_rules(workspace),
                precheck_totals=pre.test_totals,
                final_totals=final.test_totals,
                rules_totals=VerifyResult.model_validate(state["verify"]).test_totals
                if state.get("verify")
                else None,
            )
        )
        d.say("Checks", f"{len(cheating.hits)} cheating-check hits, {len(cheating.notes)} notes")
        d.say("Verify", f"{len(final.failures)} failures in {len(final.failing_files())} files")
        return {
            "final": final.model_dump(mode="json"),
            "final_usage_path": str(final_usage_path),
            "cheating": cheating.model_dump(mode="json"),
            "snapshot_updates": [*(state.get("snapshot_updates") or []), *final_snapshots],
            "timings": self.timed(state, "final_verify", t0),
        }

    def migrator_snapshots(
        self, state: RunState, extra: list[dict[str, Any]] | None = None
    ) -> set[str]:
        """Snapshot files the Migrator itself rewrote (never the agent's layer)."""
        rows = [*(state.get("snapshot_updates") or []), *(extra or [])]
        return {str(r["snapshot_file"]) for r in rows if r.get("snapshot_file")}

    def report_node(self, state: RunState) -> RunState:
        d = self.d
        run_dir = self.run_dir(state)
        usage = UsageReport.model_validate_json(Path(state["usage_path"]).read_text("utf-8"))
        pre = PrecheckResult.model_validate(state["precheck"])
        rules = RulesResult.model_validate(state["rules"]) if state.get("rules") else None
        post_rules = VerifyResult.model_validate(state["verify"]) if state.get("verify") else None
        final = VerifyResult.model_validate(state["final"]) if state.get("final") else None
        final_usage = (
            UsageReport.model_validate_json(Path(fp).read_text("utf-8"))
            if (fp := state.get("final_usage_path"))
            else None
        )
        report = self.report_of(state)
        calls = [CallRecord.model_validate(c) for c in state.get("calls") or []]
        timings = dict(state.get("timings") or {})
        if calls:
            timings["model"] = round(sum(c.duration_s for c in calls), 2)
        started = datetime.strptime(state["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        finished = datetime.now(UTC)
        meta = RunMeta(
            run_id=state["run_id"],
            started_at=state["started_at"],
            finished_at=finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
            duration_s=round((finished - started).total_seconds(), 1),
            migrator_version=__version__,
            node_version=state.get("node_version"),
            npm_version=state.get("npm_version"),
            timings_s=timings,
            sandbox=d.sandbox,
            branch=d.worktree.branch if d.worktree else None,
            base_branch=d.worktree.base_branch if d.worktree else None,
            commits=[StageCommit.model_validate(c) for c in state.get("commits") or []],
            features_off=d.configuration.feature_notes(),
        )
        layers: dict[str, Layer] | None = None
        if (
            state.get("workspace")
            and rules is not None
            and rules.status == "ok"
            and final is not None
        ):
            layers = final_layers(
                self.after_rules(state),
                read_files(self.workspace(state)),
                report,
                self.migrator_snapshots(state),
            )
        visual = self.visual_report(
            state,
            finished=bool(state.get("workspace"))
            and rules is not None
            and rules.status == "ok"
            and final is not None,
        )
        cost = run_cost(
            calls,
            d.run_cap_usd,
            d.month_cap_usd,
            month_spent_usd=d.ledger.month_spent() if calls else None,
            stopped_by_cap=report.stopped_by_cost_cap,
        )
        card = build_scorecard(
            ReportInput(
                usage=usage,
                precheck=pre,
                rules=rules,
                rules_verify=post_rules,
                verify=final,
                final_usage=final_usage,
                traps=d.traps,
                configuration=d.configuration.name,
                configuration_digest=d.configuration.digest(),
                cheating=CheatingReport.model_validate(state["cheating"])
                if state.get("cheating")
                else None,
                cost=cost,
                repair=report if d.configuration.repair.enabled else None,
                later_layers=layers,
                repeated_edits=repeated_edits(
                    self.after_rules(state), read_files(self.workspace(state)), layers
                )
                if layers is not None and d.configuration.repair.shared_causes
                else None,
                test_fitting=test_fitting_flags(
                    self.after_rules(state),
                    read_files(self.workspace(state)),
                    [(f.path, f.touched) for f in report.files if f.touched],
                    {f.file for f in post_rules.failures if f.source == "test" and f.file},
                )
                if layers is not None and post_rules is not None and d.configuration.repair.enabled
                else None,
                snapshots_to_review=[
                    SnapshotUpdate.model_validate(r) for r in state.get("snapshot_updates") or []
                ]
                if d.config.update_snapshots
                else None,
                case=d.case.id if d.case else (d.traps.case if d.traps else None),
                visual=visual,
                meta=meta,
            )
        )
        release_run(state["run_id"])  # this run's worst-case reservation ends here
        write_json(card, run_dir / "scorecard.json")
        (run_dir / "scorecard.md").write_text(render_scorecard(card), "utf-8")
        # The PR body, rendered from the same JSON; written for every run, opened as a PR
        # only by the separate `migrator pr --open` step.
        (run_dir / "pr-body.md").write_text(render_pr_body(card), "utf-8")
        d.say("Report", f"written to {run_dir}")
        ws = state.get("workspace")
        if ws and not d.keep_workspace:
            if d.worktree is None:
                shutil.rmtree(Path(ws).parent, ignore_errors=True)
            elif remove_worktree(d.worktree):  # the branch stays when it has commits
                d.say("Report", f"nothing was committed, so {d.worktree.branch} was removed")
        return {"scorecard_path": str(run_dir / "scorecard.json")}

    # ------------------------------------------------------------------ wiring

    def route_precheck(self, state: RunState) -> str:
        pre = state.get("precheck") or {}
        return "rules" if pre.get("status") == "ok" else "report"

    def route_rules(self, state: RunState) -> str:
        rules = state.get("rules") or {}
        return "commit_rules" if rules.get("status") == "ok" else "report"

    def build(self) -> StateGraph[RunState]:
        g: StateGraph[RunState] = StateGraph(RunState)
        g.add_node("scan", self.scan_node)
        g.add_node("precheck", self.precheck_node)
        g.add_node("rules", self.rules_node)
        g.add_node("commit_rules", self.commit_rules_node)
        g.add_node("verify", self.verify_node)
        g.add_node("plan_repair", self.plan_repair_node)
        g.add_node("next_file", self.next_file_node)
        g.add_node("start_file", self.start_file_node)
        g.add_node("agent", self.agent_node)
        g.add_node("tools", self.tools_node)
        g.add_node("file_end", self.file_end_node)
        g.add_node("commit_agent", self.commit_agent_node)
        g.add_node("prepare_review", self.prepare_review_node)
        g.add_node("review", self.review_node)
        g.add_node("commit_review", self.commit_review_node)
        g.add_node("final_verify", self.final_verify_node)
        g.add_node("report", self.report_node)

        g.add_edge(START, "scan")
        g.add_edge("scan", "precheck")
        g.add_conditional_edges("precheck", self.route_precheck, ["rules", "report"])
        g.add_conditional_edges("rules", self.route_rules, ["commit_rules", "report"])
        g.add_edge("commit_rules", "verify")
        g.add_edge("verify", "plan_repair")
        g.add_edge("plan_repair", "next_file")
        g.add_conditional_edges("next_file", self.route_next_file, ["start_file", "commit_agent"])
        g.add_edge("commit_agent", "prepare_review")
        g.add_conditional_edges("start_file", self.route_start_file, ["agent", "file_end"])
        g.add_conditional_edges("agent", self.route_agent, ["tools", "file_end"])
        g.add_conditional_edges("tools", self.route_tools, ["agent", "file_end"])
        g.add_edge("file_end", "next_file")
        g.add_conditional_edges(
            "prepare_review", self.route_prepare_review, ["review", "commit_review"]
        )
        g.add_edge("review", "prepare_review")
        g.add_edge("commit_review", "final_verify")
        g.add_edge("final_verify", "report")
        g.add_edge("report", END)
        return g


# --------------------------------------------------------------------------- commit messages


def rules_commit_body(rules: RulesResult) -> str:
    lines = ["The deterministic layer, no model: the migration spec's rule steps, in order.", ""]
    for step in rules.steps:
        if step.status == "skipped":
            continue
        label = step.kind if step.name == step.kind else f"{step.kind} {step.name}"
        lines.append(f"- {label}: {step.detail}")
    todos = len(rules.codemod_todos)
    lines += [
        "",
        f"Codemod TODOs left: {todos}" + (" (listed in the PR body)." if todos else "."),
    ]
    return "\n".join(lines)


def agent_commit_body(report: RepairReport, calls: list[CallRecord]) -> str:
    fixed = [f for f in report.files if f.outcome == "Migrated by agent"]
    lines = [
        "Fixed by the repair agent; each passed the narrow verify (type-check, lint on the",
        "file, related tests):",
        "",
    ]
    for f in fixed:
        models = ", ".join(dict.fromkeys(a.model for a in f.attempts))
        others = [p for p in f.touched if p != f.path]
        lines.append(
            f"- {f.path}: {len(f.attempts)} attempt{'s' if len(f.attempts) != 1 else ''} ({models})"
            + (f", also {', '.join(others)}" if others else "")
        )
    handed = [f for f in report.files if f.outcome == "Handed off"]
    if handed:
        lines += ["", "Handed off to Review (not in this commit):"]
        lines += [f"- {f.path}: {f.reason or 'handed off'}" for f in handed]
    unmigrated = [f for f in report.files if f.outcome == "Unmigrated"]
    if unmigrated:
        lines += ["", "Unmigrated:"] + [f"- {f.path}: {f.reason or ''}" for f in unmigrated]
    cost = sum(c.cost_usd for c in calls)
    lines += ["", f"{len(calls)} model calls, {usd(cost)}."]
    return "\n".join(lines)


def review_commit_body(report: RepairReport) -> str:
    lines = ["Decided by a human at Review:", ""]
    for f in report.files:
        if f.migrated_by_human:
            lines.append(f"- {f.path}: edited by a human; passes the narrow verify")
        elif f.review == "keep":
            lines.append(f"- {f.path}: the repair agent's patch kept; still handed off")
    reviewed = {f.path for f in report.files if f.migrated_by_human or f.review == "keep"}
    others = [p for p in report.human_changed if p not in reviewed]
    if others:
        lines += ["", "Also changed by the human: " + ", ".join(others)]
    return "\n".join(lines)


def final_layers(
    after_rules: FileSet,
    final: FileSet,
    report: RepairReport,
    migrator_snapshots: set[str] | None = None,
) -> dict[str, Layer]:
    """Who changed each file after the Rules stage: the human (at Review) or the agent.
    Snapshot files the Migrator itself rewrote at the final verify (the snapshot policy,
    M6) count as the Rules layer: deterministic, and listed for a human to review."""
    human = set(report.human_changed)
    ours = migrator_snapshots or set()
    layers: dict[str, Layer] = {}
    for path in after_rules.keys() | final.keys():
        if after_rules.get(path) != final.get(path):
            layers[path] = "rules" if path in ours else "human" if path in human else "agent"
    return layers


def _base_runner(runner: Any) -> Any:
    """The runner under any wrappers (the run's DeadlineRunner)."""
    while hasattr(runner, "inner"):
        runner = runner.inner
    return runner


def test_fitting_reason(
    path: str,
    touched: list[str],
    after_rules: Mapping[str, str],
    current: Mapping[str, str],
    start_failures: list[Failure],
) -> str | None:
    """The hand-off reason when a passing patch for a file that failed a test changed
    accessibility props or the rendered element (M6), else None."""
    flags = test_fitting_flags(
        dict(after_rules),
        dict(current),
        [(path, touched)],
        {f.file for f in start_failures if f.source == "test" and f.file},
    )
    if not flags:
        return None
    return "possible test-fitting: " + "; ".join(
        f"{fl.file}: {', '.join(fl.lines[:3])}" for fl in flags
    )


def snapshot_hashes(workspace: Path) -> dict[str, str]:
    """sha256 of every snapshot file in the workspace (not in node_modules)."""
    out: dict[str, str] = {}
    for folder, dirs, files in workspace.walk():
        dirs[:] = [x for x in dirs if x not in ("node_modules", ".git")]
        for name in files:
            if name.endswith(".snap"):
                path = folder / name
                out[path.relative_to(workspace).as_posix()] = hash_file(path)
    return out


def snapshot_belongs(snapshot: str, test_file: str) -> bool:
    """``a/__snapshots__/B.test.tsx.snap`` belongs to ``a/B.test.tsx``."""
    snap, test = PurePosixPath(snapshot), PurePosixPath(test_file)
    return snap.name == f"{test.name}.snap" and snap.parent.parent == test.parent


def initial_state(run_id: str, run_dir: Path) -> RunState:
    return {"run_id": run_id, "run_dir": str(run_dir), "started_at": _now(), "timings": {}}
