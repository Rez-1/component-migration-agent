"""The general agent's Rules baseline for the cheating checks: what the codemods alone do.

A Migrator run's codemods are its Rules layer: a pattern they add (preset-safe inserts an
``eslint-disable-next-line`` above a theme augmentation, for example) is a note, never a
failure. A general agent runs the same codemods itself, so without a baseline the same
line would fail its run. Here the spec's codemod steps run, as the Migrator's Rules stage
runs them, on a copy-on-write clone of the untouched, installed workspace (the codemods
look up the repo's installed v4 packages), and the cheating checks compare the agent's
work against that.

Only the codemod steps run (no install, format or dependency step): the baseline is for
the patterns a codemod writes. The codemods are the pinned tools, run with Node on this
machine; they parse the repo's files and never run its code.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from migrator.checks import FileSet, read_files
from migrator.config import ResolvedRepoConfig
from migrator.execs import CommandRunner
from migrator.migrations import MigrationSpec
from migrator.precheck_cache import clone_tree
from migrator.rules import RulesInput, apply_rules

BASELINE_FILE = "codemod-baseline.json"


def codemod_baseline(
    *,
    workspace: Path,
    spec: MigrationSpec,
    config: ResolvedRepoConfig,
    affected_files: list[str],
    tools_dir: Path | None,
    runner: CommandRunner,
    scratch: Path,
) -> tuple[FileSet | None, str]:
    """The untouched ``workspace``'s files after the spec's codemod steps, and what
    happened. ``None`` when there is no codemod step or one failed (the checks then use
    the untouched workspace, as before). ``workspace`` itself is never changed."""
    codemods = [s for s in spec.rule_steps if s.kind == "codemod"]
    if not codemods:
        return None, "no codemod step in the migration"
    shutil.rmtree(scratch, ignore_errors=True)
    repo = scratch / "repo"
    clone_tree(workspace, repo)
    try:
        result = apply_rules(
            RulesInput(
                workspace=repo,
                spec=spec.model_copy(update={"rule_steps": codemods}),
                config=config,
                affected_files=affected_files,
                tools_dir=tools_dir,
                log_dir=scratch / "logs",
            ),
            runner,
        )
        if result.status != "ok":
            return None, f"the codemods failed: {result.reason}"
        return read_files(repo), f"{len(result.changed_files)} files changed by the codemods"
    finally:
        shutil.rmtree(repo, ignore_errors=True)  # the logs stay; the repo's source doesn't


def cheating_start(untouched: FileSet, baseline: FileSet | None, final: FileSet) -> FileSet:
    """The Start of Repair the cheating checks use for a general-agent run: the codemods'
    version of each file, except one the agent left as it was untouched (it undid the
    codemod there, which is not a change of its own)."""
    if baseline is None:
        return untouched
    start: FileSet = {}
    for path in untouched.keys() | baseline.keys():
        if path in untouched and final.get(path) == untouched[path]:
            start[path] = untouched[path]
        elif path in baseline:
            start[path] = baseline[path]
        else:
            start[path] = untouched[path]
    return dict(sorted(start.items()))
