"""Running shell commands for the stages.

Every command a run executes goes through a ``CommandRunner``. ``LocalRunner`` runs
them on this machine; a Docker runner (M4) will implement the same protocol, so the
stages never call ``subprocess`` themselves.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class CommandResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    command: str
    cwd: str
    exit_code: int
    output: str  # stdout and stderr, interleaved as the command wrote them
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class CommandRunner(Protocol):
    def run(
        self,
        command: str | Sequence[str],
        cwd: Path,
        *,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        log_file: Path | None = None,
    ) -> CommandResult:
        """Run ``command`` (a shell string, or an argv list run without a shell)."""
        ...


def display(command: str | Sequence[str]) -> str:
    return command if isinstance(command, str) else shlex.join(command)


class LocalRunner:
    """Runs commands on the local machine, with the caller's permissions."""

    def __init__(self, default_timeout_s: float = 1800, base_env: Mapping[str, str] | None = None):
        self.default_timeout_s = default_timeout_s
        self.base_env = dict(base_env) if base_env is not None else None

    def run(
        self,
        command: str | Sequence[str],
        cwd: Path,
        *,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        log_file: Path | None = None,
    ) -> CommandResult:
        full_env = dict(self.base_env if self.base_env is not None else os.environ)
        # Deterministic, uncoloured output for the parsers.
        full_env.update({"CI": "1", "FORCE_COLOR": "0", "NO_COLOR": "1"})
        full_env.update(env or {})
        started = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                command,
                cwd=cwd,
                env=full_env,
                shell=isinstance(command, str),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=timeout_s or self.default_timeout_s,
                check=False,
            )
            code, output = proc.returncode, proc.stdout
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            code = -1
            raw = exc.stdout
            output = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else (raw or "")
        result = CommandResult(
            command=display(command),
            cwd=str(cwd),
            exit_code=code,
            output=output,
            duration_s=round(time.monotonic() - started, 2),
            timed_out=timed_out,
        )
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text(
                f"$ {result.command}\n# cwd: {cwd}\n# exit: {code}"
                f"{' (timed out)' if timed_out else ''} in {result.duration_s}s\n\n{output}",
                "utf-8",
            )
        return result


class RunTimeoutError(TimeoutError):
    """A run passed its wall-clock ceiling."""


class DeadlineRunner:
    """Wraps a runner with a hard wall-clock ceiling for a whole run.

    Each command gets at most the time left; once the ceiling has passed, the next
    command raises ``RunTimeoutError`` instead of starting. Every slow part of a run is
    a command, so this bounds the run without threads.
    """

    def __init__(self, inner: CommandRunner, ceiling_s: float):
        self.inner = inner
        self.ceiling_s = ceiling_s
        self.deadline = time.monotonic() + ceiling_s

    def run(
        self,
        command: str | Sequence[str],
        cwd: Path,
        *,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        log_file: Path | None = None,
    ) -> CommandResult:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise RunTimeoutError(
                f"the run passed its {self.ceiling_s:.0f} s ceiling before `{display(command)}`"
            )
        result = self.inner.run(
            command,
            cwd,
            env=env,
            timeout_s=min(timeout_s, left) if timeout_s else left,
            log_file=log_file,
        )
        if result.timed_out and self.deadline - time.monotonic() <= 0:
            raise RunTimeoutError(
                f"the run passed its {self.ceiling_s:.0f} s ceiling during `{result.command}`"
            )
        return result
