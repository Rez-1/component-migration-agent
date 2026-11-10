"""Running shell commands for the stages.

Every command a run executes goes through a ``CommandRunner``, so the stages never call
``subprocess`` themselves. Two implementations (ticket #15):

- ``LocalRunner`` runs commands on this machine, with the caller's permissions.
- ``DockerRunner`` runs each command in a fresh ``node`` container: the image pinned by
  digest, only the command's folder (the workspace, or the tools cache while the tools
  install) and the run's log folder mounted, the network off except for package
  installs, a non-root user, a read-only root filesystem and resource limits. Verify
  and the repair agent's ``run_verify`` execute code the agent just edited; in Docker
  that code cannot reach the network, the user's home folder or their credentials.

Git never goes through a runner: commits and worktrees are the Migrator's own work on
the host (``migrator.workspace``), and the container never sees ``.git``.
"""

from __future__ import annotations

import os
import secrets
import shlex
import subprocess
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

Sandbox = Literal["docker", "local"]


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
            output = _decode(exc.stdout)
        result = CommandResult(
            command=display(command),
            cwd=str(cwd),
            exit_code=code,
            output=output,
            duration_s=round(time.monotonic() - started, 2),
            timed_out=timed_out,
        )
        _write_log(log_file, result)
        return result


def _write_log(log_file: Path | None, result: CommandResult, header: str = "") -> None:
    if log_file is None:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(
        f"$ {result.command}\n# cwd: {result.cwd}\n{header}# exit: {result.exit_code}"
        f"{' (timed out)' if result.timed_out else ''} in {result.duration_s}s\n\n"
        f"{result.output}",
        "utf-8",
    )


def _decode(raw: bytes | str | None) -> str:
    return raw.decode("utf-8", "replace") if isinstance(raw, bytes) else (raw or "")


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


# --------------------------------------------------------------------------- Docker

# Node images by major version, pinned by digest (the multi-arch index, so the same pin
# works on arm64 Macs and amd64 CI). Node 20 is the fixture's declared target
# (case.toml). Adding a version means adding its pin here, never a floating tag.
NODE_IMAGES: dict[str, str] = {
    # Node 16 (end of life since 2023) only for real repos that need it (M6: CRA 4/5).
    "16": "node:16.20.2-bookworm-slim"
    "@sha256:89061680359f5d9103d24f0066e2c96a8018c24d5c4fe8eb8d59d16dd4ab64ba",
    "20": "node:20.20.2-bookworm-slim"
    "@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0",
    "22": "node:22.21.1-bookworm-slim"
    "@sha256:25b3eb23a00590b7499f2a2ce939322727fcce1b15fdd69754fcd09536a3ae2c",
}
DEFAULT_NODE = "20"
NPM_CACHE_VOLUME = "migrator-npm-cache"
NPM_CACHE_DIR = "/npm-cache"
# Only these commands get a network: the package installs, which run before the repair
# agent edits anything. Everything else (codemods, Verify, run_verify) runs offline.
_INSTALLS = {("npm", "ci"), ("npm", "install"), ("yarn", "install"), ("pnpm", "install")}


# Docker Desktop's file sharing (virtiofs on macOS) caches file attributes for up to a
# second. A file the host rewrote just before a container starts can be read there
# with its old length: the first Docker Baseline failed when `npm install` read a
# truncated package.json the dependency step had written 0.3 s earlier. The runner
# waits until the newest file in the mounted folder is this old.
SETTLE_S = 1.1
_NOT_WATCHED = {"node_modules", ".git"}


def newest_mtime(root: Path) -> float:
    """The newest modification time of the files under ``root`` (not in node_modules)."""
    newest = 0.0
    for folder, dirs, files in root.walk():
        dirs[:] = [d for d in dirs if d not in _NOT_WATCHED]
        for name in files:
            try:
                newest = max(newest, (folder / name).stat().st_mtime)
            except OSError:
                continue
    return newest


def settle(root: Path, settle_s: float = SETTLE_S) -> float:
    """Sleep until every file under ``root`` is at least ``settle_s`` old; the wait."""
    wait = newest_mtime(root) + settle_s - time.time()
    if wait > 0:
        time.sleep(min(wait, settle_s))
        return min(wait, settle_s)
    return 0.0


class SandboxError(RuntimeError):
    """The sandbox cannot run: Docker is missing or stopped, or no image is pinned."""


def node_image(node: str | None) -> str:
    """The pinned image for a RepoConfig ``node`` value such as ``"20"`` or ``"20.11"``."""
    wanted = (node or DEFAULT_NODE).strip().removeprefix("v")
    major = wanted.split(".")[0]
    if major not in NODE_IMAGES:
        raise SandboxError(
            f"no pinned Docker image for Node {wanted} (pinned: "
            f"{', '.join(sorted(NODE_IMAGES))}); add one to NODE_IMAGES in migrator/execs.py "
            "or run with --sandbox local"
        )
    return NODE_IMAGES[major]


def needs_network(command: str | Sequence[str]) -> bool:
    """Whether a command is a package install (an argv list, never a shell string)."""
    return not isinstance(command, str) and tuple(command[:2]) in _INSTALLS


class DockerLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory: str = "4g"
    cpus: float = 4.0
    pids: int = 4096
    tmp_size: str = "2g"


class DockerRunner:
    """Runs each command in a fresh, pinned ``node`` container (see the module doc).

    Paths are mounted at their own (resolved) absolute path inside the container, so
    the paths tools print and the report files they write mean the same thing on both
    sides. ``read_only`` folders (the codemod tools cache) are mounted read-only.
    """

    def __init__(
        self,
        image: str,
        *,
        read_only: Iterable[Path] = (),
        docker: str = "docker",
        default_timeout_s: float = 1800,
        limits: DockerLimits | None = None,
        cache_volume: str = NPM_CACHE_VOLUME,
        user: str | None = None,
    ):
        self.image = image
        self.read_only = [p.resolve() for p in read_only]
        self.docker = docker
        self.default_timeout_s = default_timeout_s
        self.limits = limits or DockerLimits(cpus=float(min(4, os.cpu_count() or 1)))
        self.cache_volume = cache_volume
        self.user = user or f"{os.getuid()}:{os.getgid()}"
        self._ready = False
        self._cache_ready = False

    # ------------------------------------------------------------------ setup

    def _docker(self, *args: str, timeout_s: float = 60) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.docker, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SandboxError(
                f"Docker is not available ({exc}). Start Docker, or run with --sandbox local "
                "(commands then run on this machine with your permissions)."
            ) from exc

    def check(self) -> str:
        """Fail clearly unless the Docker daemon answers and the pinned image is here
        (pulled once if missing). Returns the server version."""
        if self._ready:
            return "ok"
        version = self._docker("version", "--format", "{{.Server.Version}}", timeout_s=30)
        if version.returncode != 0:
            said = version.stdout.strip().splitlines()
            why = said[-1] if said else "no output"
            raise SandboxError(
                f"Docker is not available: `docker version` failed ({why}). Start Docker, "
                "or run with --sandbox local (commands then run on this machine with your "
                "permissions)."
            )
        if self._docker("image", "inspect", self.image).returncode != 0:
            pulled = self._docker("pull", self.image, timeout_s=900)
            if pulled.returncode != 0:
                raise SandboxError(f"could not pull {self.image}: {pulled.stdout.strip()[-500:]}")
        self._ready = True
        return version.stdout.strip()

    def _ensure_cache(self) -> None:
        """The npm cache volume, owned by the container user (a new volume is root's)."""
        if self._cache_ready:
            return
        self._docker("volume", "create", self.cache_volume)
        chown = self._docker(
            "run", "--rm", "--network", "none", "--user", "0:0",
            "--mount", f"type=volume,src={self.cache_volume},dst={NPM_CACHE_DIR}",
            self.image, "chown", self.user, NPM_CACHE_DIR,
        )  # fmt: skip
        if chown.returncode != 0:
            raise SandboxError(f"could not prepare the npm cache volume: {chown.stdout.strip()}")
        self._cache_ready = True

    # ------------------------------------------------------------------ the command

    def mounts(self, cwd: Path, log_file: Path | None) -> list[tuple[Path, bool]]:
        """(path, read_only) for one command: its folder, the log folder, the tools."""
        cwd = cwd.resolve()
        found: list[tuple[Path, bool]] = [(cwd, False)]
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            logs = log_file.parent.resolve()
            if not logs.is_relative_to(cwd):
                found.append((logs, False))
        for path in self.read_only:
            # Not when the command runs inside it (installing the tools themselves).
            if not cwd.is_relative_to(path) and not path.is_relative_to(cwd):
                path.mkdir(parents=True, exist_ok=True)  # Docker refuses a missing source
                found.append((path, True))
        for path, _ro in found:
            if "," in str(path):
                raise SandboxError(f"cannot mount a path containing a comma: {path}")
        return found

    def argv(
        self,
        command: str | Sequence[str],
        cwd: Path,
        *,
        name: str,
        env: Mapping[str, str] | None = None,
        log_file: Path | None = None,
    ) -> list[str]:
        """The full ``docker run`` command line (pure, so it can be unit-tested)."""
        lim = self.limits
        args = [
            self.docker, "run", "--rm", "--init", "--name", name,
            "--user", self.user,
            "--network", "bridge" if needs_network(command) else "none",
            "--read-only", "--tmpfs", f"/tmp:rw,exec,nosuid,size={lim.tmp_size}",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", lim.memory, "--cpus", f"{lim.cpus:g}", "--pids-limit", str(lim.pids),
            "--mount", f"type=volume,src={self.cache_volume},dst={NPM_CACHE_DIR}",
        ]  # fmt: skip
        for path, read_only in self.mounts(cwd, log_file):
            spec = f"type=bind,src={path},dst={path}" + (",readonly" if read_only else "")
            args += ["--mount", spec]
        # A clean environment: nothing from the host's (no API keys, no tokens).
        container_env = {
            "HOME": "/tmp",
            "npm_config_cache": NPM_CACHE_DIR,
            "YARN_CACHE_FOLDER": f"{NPM_CACHE_DIR}/yarn",
            "npm_config_update_notifier": "false",
            "CI": "1",
            "FORCE_COLOR": "0",
            "NO_COLOR": "1",
            **(env or {}),
        }
        for key, value in container_env.items():
            args += ["--env", f"{key}={value}"]
        args += ["--workdir", str(cwd.resolve()), self.image]
        args += ["sh", "-c", command] if isinstance(command, str) else list(command)
        return args

    def run(
        self,
        command: str | Sequence[str],
        cwd: Path,
        *,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        log_file: Path | None = None,
    ) -> CommandResult:
        self.check()
        self._ensure_cache()
        settle(cwd)
        name = f"migrator-{secrets.token_hex(6)}"
        argv = self.argv(command, cwd, name=name, env=env, log_file=log_file)
        started = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                argv,
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
            output = _decode(exc.stdout)
            self._docker("kill", name, timeout_s=30)  # the CLI is gone; stop the container
        result = CommandResult(
            command=display(command),
            cwd=str(cwd),
            exit_code=code,
            output=output,
            duration_s=round(time.monotonic() - started, 2),
            timed_out=timed_out,
        )
        network = "bridge" if needs_network(command) else "none"
        _write_log(log_file, result, f"# sandbox: docker {self.image}, network {network}\n")
        return result


def make_runner(
    sandbox: Sandbox, node: str | None, *, read_only: Iterable[Path] = ()
) -> CommandRunner:
    """The runner for a run: Docker (checked now, so a missing daemon fails at the
    start, not at the first command) or local."""
    if sandbox == "local":
        return LocalRunner()
    runner = DockerRunner(node_image(node), read_only=read_only)
    runner.check()
    return runner


def docker_available(docker: str = "docker") -> bool:
    try:
        proc = subprocess.run(
            [docker, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0
