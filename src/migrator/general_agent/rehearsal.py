"""The rehearsal: a general-agent run with no model, to try every other step for free.

Claude Code is replaced by a fixed script, run under the same sandbox, environment and
proxy the agent's commands get: the first codemod on ``src``, adding the migration's
new packages with the repo's package manager (which changes package.json and the
lockfile, so the Migrator's reinstall runs too), then the repo's own typecheck, lint
and tests. The probe's shell checks run through ``srt`` instead of through a model.
After it, the run goes on as a real one would: copy-back, the reinstall, final Verify,
Scoring.

A step's exit code is recorded, not judged: after a codemod the checks are expected to
fail. What a rehearsal looks for is a step that could not run here at all (a missing
binary, a refused host, a sandbox denial), which the step's log and the proxy's record
show.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from pydantic import BaseModel

from migrator.config import ResolvedRepoConfig
from migrator.general_agent.agent import AgentResult
from migrator.general_agent.sandbox import AgentPaths, SrtRunner
from migrator.migrations import MigrationSpec

TAIL = 1500


class RehearsalStep(BaseModel):
    name: str
    command: str
    exit_code: int
    duration_s: float
    timed_out: bool = False
    tail: str = ""  # the end of its output


def add_packages_command(spec: MigrationSpec, config: ResolvedRepoConfig) -> str | None:
    """Add the first dependency-map entry's new packages, as the agent would."""
    if not spec.dependency_map:
        return None
    pins = [f"{name}@{version}" for name, version in spec.dependency_map[0].new.items()]
    flags = list(config.install_flags)
    if config.package_manager == "yarn":
        return shlex.join(["yarn", "add", *pins, *flags])
    if config.package_manager == "pnpm":
        return shlex.join(["pnpm", "add", *pins, *flags])
    return shlex.join(["npm", "install", "--save", *pins, *flags])


def rehearsal_steps(
    spec: MigrationSpec, config: ResolvedRepoConfig, tools: list[str]
) -> list[tuple[str, str]]:
    steps: list[tuple[str, str]] = []
    first = next((s for s in spec.rule_steps if s.kind == "codemod"), None)
    if first is not None and tools and first.args:
        steps.append(("codemod", shlex.join([tools[0], first.args[0], "src"])))
    add = add_packages_command(spec, config)
    if add:
        steps.append(("add packages", add))
    verify = config.verify
    for name, command in (("typecheck", verify.typecheck), ("lint", verify.lint)):
        if command:
            steps.append((name, command))
    if verify.test:
        steps.append(("test", verify.test))
    return steps


def run_rehearsal(
    runner: SrtRunner,
    paths: AgentPaths,
    steps: list[tuple[str, str]],
    log_dir: Path,
    timeout_s: float,
) -> tuple[AgentResult, list[RehearsalStep]]:
    log_dir.mkdir(parents=True, exist_ok=True)
    done: list[RehearsalStep] = []
    left = timeout_s
    for i, (name, command) in enumerate(steps):
        log = log_dir / f"{i + 1:02d}-{name.replace(' ', '-')}.log"
        result = runner.run(command, paths.repo, timeout_s=max(left, 1.0), log_file=log)
        left -= result.duration_s
        done.append(
            RehearsalStep(
                name=name,
                command=command,
                exit_code=result.exit_code,
                duration_s=round(result.duration_s, 1),
                timed_out=result.timed_out,
                tail=result.output[-TAIL:],
            )
        )
        if left <= 0:
            break
    total = sum(s.duration_s for s in done)
    status = "timed_out" if left <= 0 else "completed"
    agent = AgentResult(
        status=status,
        detail="rehearsal: a fixed script, no model",
        num_turns=len(done),
        duration_s=round(total, 1),
        transcript=str(log_dir),
    )
    return agent, done
