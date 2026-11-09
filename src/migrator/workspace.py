"""Workspaces (the copy of the target repo a run changes), file hashing and git.

The codemods exit 0 whatever happens, so the Rules stage finds out what a rule step
changed by hashing the workspace before and after it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel

# Never copied into a dry-run workspace: the repo's git data, installed packages and
# the Migrator's own run files.
COPY_IGNORE = (".git", "node_modules", ".migrator")


def create_dry_run_workspace(repo: Path, dest: Path) -> Path:
    """Copy ``repo`` to ``dest`` (which must not exist) for a dry run.

    The copy has no ``.git`` and no ``node_modules``, so the real repo is never touched.
    """
    if dest.exists():
        raise FileExistsError(dest)
    shutil.copytree(repo, dest, ignore=shutil.ignore_patterns(*COPY_IGNORE), symlinks=True)
    return dest


def matches(path: str, globs: Iterable[str]) -> bool:
    """Whether a repo-relative POSIX path matches any glob (``**`` spans folders)."""
    pure = PurePosixPath(path)
    return any(pure.full_match(g) for g in globs)


def list_files(root: Path, globs: Iterable[str], exclude: Iterable[str] = ()) -> list[str]:
    """Repo-relative POSIX paths of the files under ``root`` matching ``globs``, sorted."""
    globs, exclude = list(globs), list(exclude)
    found: set[str] = set()
    for pattern in globs:
        for path in root.glob(pattern):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                if not matches(rel, exclude) and not rel.startswith("node_modules/"):
                    found.add(rel)
    return sorted(found)


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


Snapshot = dict[str, str]  # repo-relative path -> sha256 ("" when missing)


def snapshot(root: Path, paths: Iterable[str]) -> Snapshot:
    return {p: hash_file(root / p) if (root / p).is_file() else "" for p in paths}


def changed_files(before: Snapshot, after: Snapshot) -> list[str]:
    """Paths whose content differs between two snapshots (added and removed included)."""
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


# --------------------------------------------------------------------------- installs

INSTALL_MARKER = "node_modules/.migrator-install.json"


def install_command(manager: str, frozen: bool, flags: Iterable[str] = ()) -> list[str]:
    """The install command for a package manager: frozen to the lockfile, or updating it."""
    base = {
        ("npm", True): ["npm", "ci", "--no-audit", "--no-fund"],
        ("npm", False): ["npm", "install", "--no-audit", "--no-fund"],
        ("yarn", True): ["yarn", "install", "--frozen-lockfile"],
        ("yarn", False): ["yarn", "install"],
        ("pnpm", True): ["pnpm", "install", "--frozen-lockfile"],
        ("pnpm", False): ["pnpm", "install", "--no-frozen-lockfile"],
    }[(manager, frozen)]
    return [*base, *flags]


def manifest_hash(root: Path, lockfile: str) -> str:
    """What an install depends on: package.json and the lockfile."""
    digest = hashlib.sha256()
    for name in ("package.json", lockfile):
        path = root / name
        digest.update(name.encode() + b"\0" + (path.read_bytes() if path.is_file() else b""))
    return digest.hexdigest()


def installed_manifest(root: Path) -> str | None:
    """The manifest hash of the last install the Migrator ran in this workspace."""
    marker = root / INSTALL_MARKER
    try:
        return str(json.loads(marker.read_text("utf-8"))["manifest"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def record_install(root: Path, lockfile: str) -> None:
    marker = root / INSTALL_MARKER
    if marker.parent.is_dir():
        marker.write_text(json.dumps({"manifest": manifest_hash(root, lockfile)}), "utf-8")


# --------------------------------------------------------------------------- git (real runs)
#
# A normal run (ticket #9) works in a ``git worktree`` of the target repo on its own
# branch, so stage commits land on that branch and the user's working tree is never
# touched. Git always runs on the host, never in the sandbox: the container never sees
# ``.git``. Commits skip the repo's hooks (a pre-commit hook would run repo code on the
# host, outside the sandbox) and carry trailers that make each stage's commit
# idempotent across a crash and resume.

RUN_FILES_DIR = ".migrator"  # <repo>/.migrator/runs/<run-id>/: never committed
# Never part of a stage commit, whatever the repo's .gitignore says.
_NEVER_COMMIT_DIRS = ("node_modules", RUN_FILES_DIR)
TRAILER_RUN = "Migrator-Run"
TRAILER_STAGE = "Migrator-Stage"


class GitError(RuntimeError):
    """A git command failed, or the repo is not in a state a real run accepts."""


def git(args: Iterable[str], cwd: Path, *, stdin: str | None = None) -> str:
    """Run git on the host; its stdout, or ``GitError`` with its stderr."""
    argv = ["git", *args]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            input=stdin,
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"`{shlex.join(argv)}` could not run: {exc}") from exc
    if proc.returncode != 0:
        said = (proc.stderr or proc.stdout).strip()
        raise GitError(f"`{shlex.join(argv)}` failed: {said}")
    return proc.stdout


StageName = Literal["rules", "agent", "review"]


class StageCommit(BaseModel):
    """One stage's commit on the migration branch."""

    stage: StageName
    sha: str
    title: str
    files: list[str]


class Worktree(BaseModel):
    """The real run's workspace: a worktree of ``repo`` on ``branch``."""

    repo: Path
    path: Path
    branch: str
    base_branch: str | None  # the branch checked out when the run started (None: detached)
    base_sha: str


def repo_toplevel(repo: Path) -> Path:
    try:
        top = git(["rev-parse", "--show-toplevel"], repo).strip()
    except GitError as exc:
        raise GitError(
            f"{repo} is not a git repository; a normal run commits to a branch, so it needs "
            "one (or use --dry-run)"
        ) from exc
    return Path(top).resolve()


def dirty_paths(repo: Path) -> list[str]:
    """Uncommitted changes and untracked files, leaving out the Migrator's run files."""
    out = git(
        [
            "status",
            "--porcelain",
            "--untracked-files=normal",
            "--",
            ".",
            f":(exclude){RUN_FILES_DIR}",
        ],
        repo,
    )
    return [line[3:] for line in out.splitlines() if line.strip()]


def branch_exists(repo: Path, branch: str) -> bool:
    try:
        git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], repo)
    except GitError:
        return False
    return True


def run_files_ignored(repo: Path) -> bool:
    """Whether git ignores ``.migrator/`` (its .gitignore or .git/info/exclude)."""
    try:
        git(["check-ignore", "-q", f"{RUN_FILES_DIR}/runs"], repo)
    except GitError:
        return False
    return True


def check_real_run(repo: Path, branch: str) -> None:
    """Refuse a real run that would surprise: not the repo root, a dirty tree, or a
    branch that already exists."""
    top = repo_toplevel(repo)
    if top != repo.resolve():
        raise GitError(f"{repo} is inside the git repo {top}; run the Migrator on the repo root")
    try:
        git(["rev-parse", "--verify", "HEAD"], repo)
    except GitError as exc:
        raise GitError(f"{repo} has no commits yet; commit the code to migrate first") from exc
    dirty = dirty_paths(repo)
    if dirty:
        shown = ", ".join(dirty[:5]) + (f" and {len(dirty) - 5} more" if len(dirty) > 5 else "")
        raise GitError(
            f"the working tree has uncommitted changes ({shown}). The migration starts from "
            "the last commit, so commit or stash them first."
        )
    if branch_exists(repo, branch):
        held = worktree_of(repo, branch)
        remove = f"`git worktree remove --force {held}`, then " if held else ""
        raise GitError(
            f"the branch {branch} already exists. Delete it ({remove}`git branch -D "
            f"{branch}`) or choose another with --branch."
        )


def add_worktree(repo: Path, path: Path, branch: str) -> Worktree:
    """A new worktree of ``repo``'s HEAD at ``path`` on a new ``branch``."""
    repo = repo.resolve()
    base_sha = git(["rev-parse", "HEAD"], repo).strip()
    try:
        base_branch: str | None = git(["symbolic-ref", "--short", "-q", "HEAD"], repo).strip()
    except GitError:
        base_branch = None
    path.parent.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", "-b", branch, str(path), base_sha], repo)
    return Worktree(
        repo=repo, path=path.resolve(), branch=branch, base_branch=base_branch, base_sha=base_sha
    )


def remove_worktree(worktree: Worktree) -> bool:
    """Remove the worktree folder (installed packages included). The branch stays when
    it has commits; a branch the run never committed to is deleted too, so a rejected
    run does not block the next one. True when the branch was deleted."""
    try:
        git(["worktree", "remove", "--force", str(worktree.path)], worktree.repo)
    except GitError:
        shutil.rmtree(worktree.path, ignore_errors=True)
        git(["worktree", "prune"], worktree.repo)
    tip = git(["rev-parse", f"refs/heads/{worktree.branch}"], worktree.repo).strip()
    if tip != worktree.base_sha:
        return False
    git(["branch", "-D", worktree.branch], worktree.repo)
    return True


def worktree_of(repo: Path, branch: str) -> Path | None:
    """The worktree that has ``branch`` checked out, if any."""
    path: str | None = None
    for line in git(["worktree", "list", "--porcelain"], repo).splitlines():
        if line.startswith("worktree "):
            path = line.removeprefix("worktree ")
        elif line == f"branch refs/heads/{branch}" and path:
            return Path(path)
    return None


def _trailers(message: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in message.splitlines():
        key, sep, value = line.partition(": ")
        if sep and key in (TRAILER_RUN, TRAILER_STAGE):
            found[key] = value.strip()
    return found


def find_stage_commit(worktree: Worktree, run_id: str, stage: StageName) -> StageCommit | None:
    """This run's commit for ``stage`` on the branch, if it was already made."""
    log = git(["log", "--format=%H%x1f%s%x1f%B%x1e", f"{worktree.base_sha}..HEAD"], worktree.path)
    for entry in log.split("\x1e"):
        parts = entry.strip("\n").split("\x1f")
        if len(parts) != 3:
            continue
        sha, title, body = parts
        trailers = _trailers(body)
        if trailers.get(TRAILER_RUN) == run_id and trailers.get(TRAILER_STAGE) == stage:
            files = git(["diff-tree", "--no-commit-id", "--name-only", "-r", sha], worktree.path)
            return StageCommit(stage=stage, sha=sha, title=title, files=files.split())
    return None


def _never_committed(path: str) -> bool:
    return any(part in _NEVER_COMMIT_DIRS for part in PurePosixPath(path).parts)


def commit_stage(
    worktree: Worktree,
    *,
    run_id: str,
    stage: StageName,
    title: str,
    body: str,
) -> StageCommit | None:
    """Commit everything the stage changed in the worktree (never node_modules or the
    run files), once: a commit this run already made for the stage is returned instead
    of a second one. None when the stage changed nothing."""
    done = find_stage_commit(worktree, run_id, stage)
    if done is not None:
        return done
    git(["add", "-A"], worktree.path)
    # Naming an ignored folder in `git add` is an error, so unstage instead.
    staged = git(["diff", "--cached", "--name-only", "-z"], worktree.path).split("\0")
    never = [p for p in staged if p and _never_committed(p)]
    if never:
        git(["rm", "--cached", "-r", "-q", "--", *never], worktree.path)
    staged = [p for p in staged if p and not _never_committed(p)]
    if not staged:
        return None
    message = f"{title}\n\n{body.strip()}\n\n{TRAILER_RUN}: {run_id}\n{TRAILER_STAGE}: {stage}\n"
    git(
        ["-c", "core.hooksPath=/dev/null", "commit", "--no-verify", "--quiet", "-F", "-"],
        worktree.path,
        stdin=message,
    )
    sha = git(["rev-parse", "HEAD"], worktree.path).strip()
    return StageCommit(stage=stage, sha=sha, title=title, files=sorted(staged))
