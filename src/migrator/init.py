"""``migrator init``: detect a target repo's setup and write a commented ``migrate.toml``.

Every value comes from a file in the repo, and the comment next to it says which one;
what can't be detected is written as a TODO and printed. No LLM, no network. The
developer checks the file before the first run: detection is a starting point, and the
verify commands in particular decide what "migrated" means.
"""

from __future__ import annotations

import json
from pathlib import Path

from migrator.detection import Detected, RepoDetection, detect

__all__ = ["InitError", "detect", "render_migrate_toml", "write_migrate_toml"]


# --------------------------------------------------------------------------- the file


def _toml(value: object) -> str:
    return json.dumps(value)  # strings and string lists are valid TOML in JSON form


def render_migrate_toml(r: RepoDetection) -> str:
    out = [
        "# migrate.toml, written by `migrator init`: check every value before the first run.",
        "# Each comment says where the value came from; TODO lines need you. The verify",
        "# commands decide what counts as migrated: they must not change files (no --fix)",
        "# and must exit non-zero on a failure.",
        "",
    ]

    def line(key: str, d: Detected, todo: str) -> None:
        if d.value is None:
            out.append(f"# TODO {todo}: {d.source}")
            out.append(f"# {key} = ")
        else:
            out.append(f"# from {d.source}")
            out.append(f"{key} = {_toml(d.value)}")

    pm = r.package_manager
    out.append(f"# Package manager: {pm.value or 'TODO'} (from {pm.source}; detected at run time).")
    line("node", r.node, 'set the Node major version, such as "20"')
    line("runner", r.runner, 'set "jest" or "vitest"')
    line("source_globs", r.source_globs, "list the source files to scan")
    out.append('exclude = ["**/node_modules/**"]')
    out.append("install_flags = []")
    out += ["", "[verify]"]
    line("typecheck", r.typecheck, "a command that type-checks without emitting")
    line("lint", r.lint, "a lint command without --fix")
    line("test", r.test, "a command that runs the tests once")
    if isinstance(r.install_env.value, dict):
        out += ["", "[install_env]", f"# from {r.install_env.source}; no unit test needs them"]
        out += [f"{k} = {_toml(v)}" for k, v in r.install_env.value.items()]
    return "\n".join(out) + "\n"


class InitError(RuntimeError):
    pass


def write_migrate_toml(repo: Path, *, force: bool = False) -> tuple[Path, RepoDetection]:
    path = repo / "migrate.toml"
    if path.exists() and not force:
        raise InitError(f"{path} exists; pass --force to overwrite it")
    result = detect(repo)
    path.write_text(render_migrate_toml(result), "utf-8")
    return path, result
