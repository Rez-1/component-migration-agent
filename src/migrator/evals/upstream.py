"""Real-repo cases (M6): fetching an upstream repo at the reference PR's base commit.

A case with an ``[upstream]`` table names a public repo, the base commit of its merged
migration PR, the sub-folder that is the target repo, and the PR's last commit. The
first run clones the repo (blobless) into the Migrator's cache and extracts the base
commit's tree with ``git archive``, so the checkout has no ``.git`` and nothing lands in
this repository. Later runs reuse the extracted tree; a marker file says it is complete.

The **reference** is ``git diff <commit> <reference_head> -- <subdir>``: the PR's own
changes, in paths relative to the target repo.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import tarfile
from pathlib import Path

from migrator.config import CaseConfig, Upstream
from migrator.rules import tools_cache_root
from migrator.workspace import GitError, git

MARKER = ".migrator-upstream.json"


def _name(url: str) -> str:
    """``https://github.com/kubeflow/pipelines.git`` -> ``kubeflow-pipelines``."""
    tail = re.sub(r"\.git$", "", url.rstrip("/")).split("github.com/")[-1]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", tail)


def clone_dir(up: Upstream, cache: Path | None = None) -> Path:
    return (cache or tools_cache_root()) / "repos" / _name(up.repo)


def checkout_dir(case: CaseConfig, cache: Path | None = None) -> Path:
    assert case.upstream is not None
    return (cache or tools_cache_root()) / "cases" / f"{case.id}-{case.upstream.commit[:12]}"


def ensure_clone(up: Upstream, cache: Path | None = None) -> Path:
    """A blobless clone of the upstream repo that has both commits."""
    path = clone_dir(up, cache)
    if not (path / ".git").is_dir():
        path.parent.mkdir(parents=True, exist_ok=True)
        git(["clone", "--quiet", "--filter=blob:none", "--no-checkout", up.repo, str(path)],
            path.parent)  # fmt: skip
    for sha in (up.commit, up.reference_head):
        try:
            git(["cat-file", "-e", f"{sha}^{{commit}}"], path)
        except GitError:
            git(["fetch", "--quiet", "--filter=blob:none", "origin", sha], path)
    return path


def materialize(case: CaseConfig, cache: Path | None = None) -> Path:
    """The case's target repo at the base commit, extracted once into the cache."""
    up = case.upstream
    if up is None:
        raise ValueError(f"case {case.id!r} has no [upstream] table")
    root = checkout_dir(case, cache)
    target = root / up.subdir if up.subdir else root
    marker = root / MARKER
    if marker.is_file() and json.loads(marker.read_text("utf-8")).get("commit") == up.commit:
        return target
    shutil.rmtree(root, ignore_errors=True)
    clone = ensure_clone(up, cache)
    root.mkdir(parents=True)
    args = ["archive", "--format=tar", up.commit]
    if up.subdir:
        args.append(up.subdir)
    blob = _git_bytes(args, clone)
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        tar.extractall(root, filter="data")
    marker.write_text(
        json.dumps({"repo": up.repo, "commit": up.commit, "subdir": up.subdir}) + "\n", "utf-8"
    )
    return target


def materialize_reference(case: CaseConfig, cache: Path | None = None) -> Path:
    """The case's target repo as the merged migration PR left it (its last commit),
    extracted once into the cache: what the visual check compares a run against (M7)."""
    up = case.upstream
    if up is None:
        raise ValueError(f"case {case.id!r} has no [upstream] table")
    root = (cache or tools_cache_root()) / "cases" / f"{case.id}-ref-{up.reference_head[:12]}"
    target = root / up.subdir if up.subdir else root
    marker = root / MARKER
    if (
        marker.is_file()
        and json.loads(marker.read_text("utf-8")).get("commit") == up.reference_head
    ):
        return target
    shutil.rmtree(root, ignore_errors=True)
    clone = ensure_clone(up, cache)
    root.mkdir(parents=True)
    args = ["archive", "--format=tar", up.reference_head]
    if up.subdir:
        args.append(up.subdir)
    with tarfile.open(fileobj=io.BytesIO(_git_bytes(args, clone))) as tar:
        tar.extractall(root, filter="data")
    marker.write_text(
        json.dumps({"repo": up.repo, "commit": up.reference_head, "subdir": up.subdir}) + "\n",
        "utf-8",
    )
    return target


def _git_bytes(args: list[str], cwd: Path) -> bytes:
    import subprocess

    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False, timeout=600)
    if proc.returncode != 0:
        raise GitError(f"`git {' '.join(args)}` failed: {proc.stderr.decode(errors='replace')}")
    return proc.stdout


def reference_diff(case: CaseConfig, cache: Path | None = None) -> str:
    """The reference PR's diff, with paths relative to the target repo."""
    up = case.upstream
    if up is None:
        raise ValueError(f"case {case.id!r} has no [upstream] table")
    clone = ensure_clone(up, cache)
    args = ["diff", "--no-color", "--no-renames", up.commit, up.reference_head]
    if up.subdir:
        args += [f"--relative={up.subdir.rstrip('/')}/"]
    return git(args, clone)


def reference_file(case: CaseConfig, path: str, cache: Path | None = None) -> str | None:
    """A target-repo file as the reference PR left it (None when the PR deleted it)."""
    up = case.upstream
    assert up is not None
    full = f"{up.subdir.rstrip('/')}/{path}" if up.subdir else path
    try:
        return git(["show", f"{up.reference_head}:{full}"], ensure_clone(up, cache))
    except GitError:
        return None


def case_repo(case: CaseConfig, root: Path, cache: Path | None = None) -> Path:
    """The folder a case's runs copy: its fixture, or its cached upstream checkout."""
    if case.upstream is not None:
        return materialize(case, cache)
    return (root / case.source).resolve()


def reference_changes(case: CaseConfig, cache: Path | None = None) -> dict[str, str]:
    """Every file the reference PR changed: target-repo path -> A, M or D."""
    up = case.upstream
    if up is None:
        raise ValueError(f"case {case.id!r} has no [upstream] table")
    args = ["diff", "--name-status", "--no-renames", up.commit, up.reference_head]
    if up.subdir:
        args += [f"--relative={up.subdir.rstrip('/')}/"]
    out: dict[str, str] = {}
    for line in git(args, ensure_clone(up, cache)).splitlines():
        status, _, path = line.partition("\t")
        if path:
            out[path] = status[:1]
    return out
