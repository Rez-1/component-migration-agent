"""RunContext: what every node gets besides the state.

A node is ``def node(ctx: RunContext, state: RunState) -> RunState``. The context holds
the run's dependencies (``RunDeps``) and its folder (``RunFiles``); it keeps nothing
between steps, so its helpers rebuild what they return from the checkpointed state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

from migrator.checks import FileSet
from migrator.config import CaseConfig, ResolvedRepoConfig, TrapList
from migrator.configuration import Configuration
from migrator.cost import Budget, CallRecord, Ledger, RunCaps
from migrator.execs import CommandRunner
from migrator.migrations import MigrationSpec
from migrator.precheck_cache import PrecheckCache
from migrator.repair.model import GuardedModel
from migrator.repair.prompt import PromptTemplates
from migrator.repair.records import RepairReport
from migrator.repair.retriever import GuideRetriever
from migrator.repair.tools import RepairSession, RepairTools, SessionState
from migrator.run.files import RunFiles
from migrator.run.state import RunState, failures_of
from migrator.verify import PrecheckResult
from migrator.verify.checker import Checker
from migrator.workspace import Worktree

Mode = Literal["eval", "cli"]
StageCallback = Callable[[str, str], None]


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
        caps: RunCaps,
        ledger: Ledger,
        model: GuardedModel | None,
        tools: RepairTools | None,
        templates: PromptTemplates | None,
        retriever: GuideRetriever | None,
        on_stage: StageCallback | None = None,
        worktree: Worktree | None = None,
        sandbox: str = "local",
        precheck_cache: PrecheckCache | None = None,
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
        self.caps = caps  # the run's Cost caps; each step's Budget is built from them
        self.ledger = ledger
        self.model = model
        self.tools = tools
        self.templates = templates
        self.retriever = retriever
        self.say = on_stage or (lambda _stage, _msg: None)
        self.worktree = worktree  # a real run's git worktree; None for a dry run
        self.sandbox = sandbox
        self.precheck_cache = precheck_cache  # speed-up 2 (M6); None: no cache
        self.reviewer_factory = reviewer_factory  # tests pass a fake; None: Claude

    @property
    def repair_on(self) -> bool:
        return self.configuration.repair.enabled and self.model is not None


class RunContext:
    """The run's dependencies and folder, and what nodes build again from the state."""

    def __init__(self, deps: RunDeps, files: RunFiles):
        self.deps = deps
        self.files = files

    def workspace(self, state: RunState) -> Path:
        ws = state.get("workspace")
        if not ws:
            raise RuntimeError("the run has no workspace")
        return Path(ws)

    def checker(self, state: RunState, start_of_repair: FileSet | None = None) -> Checker:
        """The run's Checker, rebuilt from its state (it keeps none between steps);
        ``start_of_repair``: that snapshot, when the caller has read it already."""
        return Checker(
            workspace=self.workspace(state),
            config=self.deps.config,
            pre_existing=PrecheckResult.model_validate(state["precheck"]).pre_existing_failures,
            after_rules=lambda: (
                self.files.start_of_repair() if start_of_repair is None else start_of_repair
            ),
            runner=self.deps.runner,
            log_dir=self.files.logs,
        )

    def budget(self, state: Mapping[str, Any]) -> Budget:
        """The run's Budget, built again from the checkpointed state: its recorded calls
        and Reservation (it keeps nothing between steps). Pipeline uses it on resume."""
        spent = sum(CallRecord.model_validate(c).cost_usd for c in state.get("calls") or [])
        repair = state.get("repair") or {}
        return Budget(
            state["run_id"],
            self.deps.caps,
            self.deps.ledger,
            spent_usd=spent,
            reserved_usd=repair.get("reserved_usd"),
        )

    def repair_session(self, state: RunState, file: SessionState) -> RepairSession:
        """One file's RepairSession over the workspace as the state has it, for the
        agent's tools or for the narrow verify of a human's edit at Review."""
        d = self.deps
        assert d.templates is not None and d.retriever is not None
        start = self.files.start_of_repair()
        return RepairSession(
            file,
            workspace=self.workspace(state),
            after_rules=start,
            test_files=state.get("test_files") or {},
            known_failures=failures_of(state.get("known_failures")),
            checker=self.checker(state, start),
            templates=d.templates,
            retriever=d.retriever,
            link_base=d.spec.guide.link_base,
        )

    def report(self, state: RunState) -> RepairReport:
        """The repair report: a dict in the state, read once by each node that changes
        it and written back once in that node's return."""
        return RepairReport.model_validate(
            state.get("repair") or {"enabled": self.deps.configuration.repair.enabled}
        )
