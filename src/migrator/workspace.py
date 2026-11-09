"""Workspaces (the copy of the target repo a run changes) and file hashing.

The codemods exit 0 whatever happens, so the Rules stage finds out what a rule step
changed by hashing the workspace before and after it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

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
