"""The Checker: every Verify of one run after its Pre-check.

A run verifies its workspace many times (after Rules, the recheck, each Narrow verify
of the repair agent, a human's edit at Review, the final verify), always with the same
inputs: the repo config, the Pre-existing failures, the stale rules from the after-Rules
snapshot and the leftovers check. The Checker holds them, so each caller says only
what differs: a label, and for a Narrow verify the files to test around.

It keeps no state between steps: the graph is checkpointed and rebuilds it from the
run's state at every step. The Pre-check is not one of its operations, since it is
what produces the Pre-existing failures.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import cached_property
from pathlib import Path

from migrator.config import ResolvedRepoConfig
from migrator.execs import CommandRunner
from migrator.verify import SnapshotRun, VerifyInput, VerifyResult, update_snapshots, verify
from migrator.verify.leftovers import rules_under_todos
from migrator.verify.parsers import Failure


class Checker:
    """One run's verification: a full check, a Narrow verify and a snapshot update."""

    def __init__(
        self,
        *,
        workspace: Path,
        config: ResolvedRepoConfig,
        pre_existing: list[Failure],
        after_rules: Callable[[], Mapping[str, str]],
        runner: CommandRunner,
        log_dir: Path,
    ):
        self.workspace = workspace
        self.config = config
        self.pre_existing = pre_existing
        # Read only when the leftovers check has TODO markers to look for.
        self._after_rules = after_rules
        self.runner = runner
        self.log_dir = log_dir

    @cached_property
    def stale_rules(self) -> list[tuple[str, str]]:
        """Stylesheet rules under the Rules stage's TODO comments, as it left them (M7)."""
        check = self.config.leftovers
        if check is None or not check.todo_markers:
            return []
        return rules_under_todos(self._after_rules(), check.todo_markers)

    def _input(self, label: str, related_to: list[str] | None = None) -> VerifyInput:
        return VerifyInput(
            workspace=self.workspace,
            commands=self.config.verify,
            runner=self.config.runner,
            log_dir=self.log_dir,
            label=label,
            pre_existing=self.pre_existing,
            related_to=related_to,
            leftovers=self.config.leftovers,
            stale_rules=self.stale_rules,
        )

    def check(self, label: str) -> VerifyResult:
        """Verify the whole workspace; ``label`` names its logs."""
        return verify(self._input(label), self.runner)

    def narrow(self, label: str, related_to: list[str]) -> VerifyResult:
        """A Narrow verify: only the tests related to ``related_to`` run; the type-check,
        lint and leftovers still cover the whole workspace."""
        return verify(self._input(label, related_to), self.runner)

    def update_snapshots(
        self,
        label: str,
        result: VerifyResult,
        snapshot_hashes: Callable[[], dict[str, str]],
    ) -> tuple[VerifyResult, SnapshotRun | None]:
        """The snapshot policy (M6) on ``result``: see ``verify.update_snapshots``."""
        return update_snapshots(self._input(label), result, self.runner, snapshot_hashes)
