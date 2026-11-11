"""The Pre-check cache (M6 speed-up 2): install and verify an untouched repo once.

Every run of a case starts from the same untouched code, so its Pre-check (install,
type-check, lint, tests with coverage) gives the same result each time; on kubeflow it
takes about 4 of a run's minutes. The first run stores the installed workspace and the
Pre-check result; later runs, Baseline and agent runs alike, clone the workspace
(copy-on-write where the file system allows: APFS on macOS, reflinks on Linux) and reuse
the result.

The key is everything the Pre-check depends on: the repo's files (lockfile and
package.json included), the resolved repo config (verify commands, coverage, install
flags and environment), where commands run (the sandbox and its pinned Node image) and
the Migrator's version. Change any of them and it is a different entry.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import platform
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel

from migrator import __version__
from migrator.config import ResolvedRepoConfig
from migrator.verify import PrecheckResult

_SKIP = {".git", "node_modules", ".migrator"}
# Bumped whenever what a Pre-check records changes shape (2: failure text with the run's
# temporary folder written as ".."; 3: test names cleaned the same way; 4: test
# failures charged to files matched with exact case).
CACHE_FORMAT = 4
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_LOCK = threading.Lock()


class CachedPrecheck(BaseModel):
    precheck: PrecheckResult
    node_version: str | None
    npm_version: str | None
    # With node_modules in a Docker volume (speed-up 4): the cache's copy of it.
    node_modules_volume: str | None = None


def tree_hash(root: Path) -> str:
    """sha256 over every file's path and content (not .git, node_modules, run files)."""
    digest = hashlib.sha256()
    for folder, dirs, files in sorted(root.walk(), key=lambda t: str(t[0])):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP)
        for name in sorted(files):
            path = folder / name
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            try:
                digest.update(path.read_bytes())
            except OSError:
                digest.update(b"<unreadable>")
            digest.update(b"\0")
    return digest.hexdigest()


def cache_key(repo: Path, config: ResolvedRepoConfig, where: str) -> str:
    """``where``: the sandbox and its image, such as ``docker:node:16…@sha256:…``."""
    digest = hashlib.sha256()
    parts = (str(CACHE_FORMAT), __version__, where, config.model_dump_json(), tree_hash(repo))
    for part in parts:
        digest.update(part.encode() + b"\0")
    return digest.hexdigest()[:24]


def clone_tree(src: Path, dest: Path) -> None:
    """Copy a folder, sharing blocks with the source where the file system can."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    if system == "Darwin":
        argv = ["cp", "-cR", str(src), str(dest)]
    elif system == "Linux":
        argv = ["cp", "-a", "--reflink=auto", str(src), str(dest)]
    else:
        shutil.copytree(src, dest, symlinks=True)
        return
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, symlinks=True)


class PrecheckCache:
    def __init__(self, root: Path):
        self.root = root

    def entry(self, key: str) -> Path:
        return self.root / key

    def get(self, key: str) -> CachedPrecheck | None:
        done = self.entry(key) / "result.json"
        if not done.is_file():
            return None
        return CachedPrecheck.model_validate_json(done.read_text("utf-8"))

    def workspace(self, key: str) -> Path:
        return self.entry(key) / "workspace"

    def logs(self, key: str) -> Path:
        return self.entry(key) / "logs"

    def put(
        self, key: str, workspace: Path, logs: Path, result: CachedPrecheck, untouched: Path
    ) -> None:
        """Store a completed Pre-check; result.json is written last, as the done marker.
        ``untouched`` is the run's snapshot of the code before the install."""
        entry = self.entry(key)
        shutil.rmtree(entry, ignore_errors=True)
        entry.mkdir(parents=True)
        clone_tree(workspace, self.workspace(key))
        if logs.is_dir():
            shutil.copytree(logs, self.logs(key))
        shutil.copy2(untouched, entry / "untouched.json")
        (entry / "result.json").write_text(result.model_dump_json(indent=2) + "\n", "utf-8")

    @contextmanager
    def locked(self, key: str) -> Iterator[None]:
        """One Pre-check per key at a time: threads in this process and other processes."""
        with _LOCKS_LOCK:
            lock = _LOCKS.setdefault(key, threading.Lock())
        self.root.mkdir(parents=True, exist_ok=True)
        with lock, (self.root / f"{key}.lock").open("w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)


def restore_logs(cache: PrecheckCache, key: str, log_dir: Path) -> None:
    """The cached Pre-check's logs, copied into this run's log folder."""
    src = cache.logs(key)
    if not src.is_dir():
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    for path in src.rglob("*"):
        if path.is_file():
            target = log_dir / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    (log_dir / "precheck-from-cache.json").write_text(json.dumps({"key": key}) + "\n", "utf-8")
