"""Tooling for contributors who add a migration (M7): ``migrator spec new`` and
``migrator spec check``.

An app developer never writes a migration spec: specs ship with the Migrator, one per
supported migration. A contributor adding one runs ``spec new`` for a commented
template, fills it in (the ``add-migration`` Claude Code skill guides the research),
and runs ``spec check`` until it passes. The rules live here, in code, so the skill
only guides and a spec is checked the same way whoever wrote it.

``check_spec`` returns one ``Check`` per rule: *fail* blocks the spec, *warn* is worth a
look, *ok* says what was verified. Network checks (the guide's tag on GitHub, the
pinned packages on npm) run only when asked.
"""

from __future__ import annotations

import json
import re
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from migrator.migrations import (
    MIGRATIONS_DIR,
    CodemodStep,
    DependenciesStep,
    InstallStep,
    MigrationSpec,
    load_spec,
)
from migrator.migrations.guide import load_guide

TEMPLATE = Path(__file__).with_name("spec_template.toml")
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
VERSION_ID = re.compile(r"^[a-z0-9@/._-]+@[0-9a-z.-]+$")
EXACT = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")

Status = Literal["ok", "warn", "fail"]


class Check(BaseModel):
    name: str
    status: Status
    detail: str


class SpecToolError(ValueError):
    pass


# --------------------------------------------------------------------------- spec new


SOURCE_TEMPLATE = """\
# Vendored guide: {library_name} {from_} -> {to}

TODO: copy the guide's files here unchanged, with the licence notice its licence
requires (`LICENSE`), and fill in where they came from.

| | |
|---|---|
| Repository | TODO |
| Tag | TODO |
| Commit | TODO |
| Path | TODO |
| Files | TODO |
| Copied | TODO (date, and the raw URL each file came from) |
| Check | TODO (`git hash-object <file>` of the largest file) |
"""

TOOLS_TEMPLATE = {
    "name": "migrator-tools-{name}",
    "private": True,
    "description": "Pinned Node tools for the {id} Rules stage. Installed once with npm ci "
    "into the Migrator's cache, never into the target repo.",
    "license": "MIT",
    "dependencies": {},
}


def new_spec(
    name: str, from_: str, to: str, library_name: str, root: Path = MIGRATIONS_DIR
) -> Path:
    """Write a migration folder with a commented ``migration.toml`` template, a guide
    folder with its ``SOURCE.md`` to fill in, and an empty tools workspace."""
    if not NAME.match(name):
        raise SpecToolError(f"{name!r}: use lower-case words joined by '-', e.g. mui-4-to-5")
    for label, value in (("from", from_), ("to", to)):
        if not VERSION_ID.match(value):
            raise SpecToolError(f"--{label} {value!r}: use library@major, e.g. mui@4")
    folder = root / name
    if folder.exists():
        raise SpecToolError(f"{folder} already exists")
    fill = {"{name}": name, "{from_}": from_, "{to}": to, "{library_name}": library_name}
    text = TEMPLATE.read_text("utf-8")
    for key, value in fill.items():
        text = text.replace(key, value)
    (folder / "guide").mkdir(parents=True)
    (folder / "tools").mkdir()
    (folder / "migration.toml").write_text(text, "utf-8")
    source = SOURCE_TEMPLATE.format(library_name=library_name, from_=from_, to=to)
    (folder / "guide" / "SOURCE.md").write_text(source, "utf-8")
    tools = {
        k: (v.format(name=name, id=f"{from_}->{to}") if isinstance(v, str) else v)
        for k, v in TOOLS_TEMPLATE.items()
    }
    (folder / "tools" / "package.json").write_text(json.dumps(tools, indent=2) + "\n", "utf-8")
    return folder


# --------------------------------------------------------------------------- spec check

Fetch = Callable[[str], int]  # URL -> HTTP status (0 when unreachable)


def http_status(url: str) -> int:
    request = urllib.request.Request(
        url, method="GET", headers={"User-Agent": "migrator-spec-check", "Accept": "*/*"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, TimeoutError):
        return 0


def resolve_folder(name_or_path: str, root: Path = MIGRATIONS_DIR) -> Path:
    path = Path(name_or_path)
    if (path / "migration.toml").is_file():
        return path
    if path.name == "migration.toml" and path.is_file():
        return path.parent
    if (root / name_or_path / "migration.toml").is_file():
        return root / name_or_path
    known = ", ".join(sorted(p.parent.name for p in root.glob("*/migration.toml"))) or "none"
    raise SpecToolError(f"no migration spec {name_or_path!r} (known: {known})")


def _todos(data: Any, where: str = "") -> Iterator[str]:
    """Every value still holding the template's TODO placeholder."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key != "codemod_todo_markers":  # legitimately lists "TODO"
                yield from _todos(value, f"{where}.{key}" if where else key)
    elif isinstance(data, list):
        for i, value in enumerate(data):
            yield from _todos(value, f"{where}[{i}]")
    elif isinstance(data, str) and "TODO" in data:
        yield where


def check_spec(folder: Path, *, network: bool = False, fetch: Fetch = http_status) -> list[Check]:
    """Every rule a migration spec must pass, in order. Stops after the TOML if the spec
    doesn't load, since the other checks need it."""
    checks: list[Check] = []

    def add(name: str, status: Status, detail: str) -> None:
        checks.append(Check(name=name, status=status, detail=detail))

    toml = folder / "migration.toml"
    try:
        data = tomllib.loads(toml.read_text("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        add("toml", "fail", f"{toml} is not valid TOML: {exc}")
        return checks
    todos = list(_todos(data))
    if todos:
        add("placeholders", "fail", f"still TODO: {', '.join(todos)}")
    try:
        spec = load_spec(folder)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'spec'}: {e['msg']}" for e in exc.errors()
        )
        add("schema", "fail", problems)
        return checks
    add("schema", "ok", f"{spec.id} loads")
    if spec.id != f"{spec.from_}->{spec.to}":
        add("id", "fail", f"id {spec.id!r} should be {spec.from_}->{spec.to}")

    _check_guide(spec, add)
    _check_pins(spec, add)
    _check_tools(spec, add)
    _check_steps(spec, add)
    if network:
        _check_network(spec, add, fetch)
    return checks


def _check_guide(spec: MigrationSpec, add: Callable[[str, Status, str], None]) -> None:
    g = spec.guide
    guide_dir = spec.guide_dir()
    missing = [f for f in g.files if not (guide_dir / f).is_file()]
    if missing:
        add("guide files", "fail", f"missing in {guide_dir}: {', '.join(missing)}")
        return
    if not (guide_dir / "SOURCE.md").is_file():
        add("guide files", "fail", f"{guide_dir} has no SOURCE.md (where the files came from)")
    if not (guide_dir / "LICENSE").is_file():
        add("guide files", "warn", f"{guide_dir} has no LICENSE (the guide's licence notice)")
    if not COMMIT.match(g.commit):
        add("guide pin", "fail", f"commit {g.commit!r} is not a full 40-character commit")
    else:
        add("guide pin", "ok", f"{g.repo} at {g.tag} ({g.commit[:12]})")
    if g.change_level <= g.section_level:
        add("guide split", "fail", "change_level must be deeper than section_level")
        return
    changes = load_guide(guide_dir, g)
    per_file = {f: sum(c.file == f for c in changes) for f in g.files}
    empty = [f for f, n in per_file.items() if n == 0]
    kinds = sum(c.kind == "change" for c in changes)
    if not changes:
        add(
            "guide split",
            "fail",
            f"no sections at heading level {g.section_level}; check section_level",
        )
        return
    detail = (
        f"{len(changes)} sections ({kinds} change headings at level {g.change_level}, "
        f"{len(changes) - kinds} sections without one) in {len(g.files)} files"
    )
    add(
        "guide split",
        "warn" if empty else "ok",
        detail + (f"; no sections in {', '.join(empty)}" if empty else ""),
    )
    if g.codemod_marker and not any(c.codemod_handled for c in changes):
        add("guide split", "warn", f"no change heading starts with {g.codemod_marker!r}")


def _check_pins(spec: MigrationSpec, add: Callable[[str, Status, str], None]) -> None:
    loose = [
        f"{pkg}@{ver}"
        for entry in spec.dependency_map
        for pkg, ver in entry.new.items()
        if not EXACT.match(ver)
    ]
    if loose:
        add("pins", "fail", f"not exact versions: {', '.join(loose)}")
    elif spec.dependency_map:
        n = sum(len(e.new) for e in spec.dependency_map)
        add("pins", "ok", f"{n} exact pins in {len(spec.dependency_map)} dependency-map entries")
    olds = {e.old for e in spec.dependency_map}
    unmapped = [p for p in spec.detection.packages if spec.dependency_map and p not in olds]
    if unmapped:
        add("pins", "warn", f"detected but not in the dependency map: {', '.join(unmapped)}")


def _check_tools(spec: MigrationSpec, add: Callable[[str, Status, str], None]) -> None:
    codemods = [s for s in spec.rule_steps if isinstance(s, CodemodStep)]
    if not codemods:
        return
    if spec.tools is None:
        add("tools", "fail", "codemod steps need [tools]")
        return
    tools = spec.tools_dir()
    package, lock = tools / "package.json", tools / "package-lock.json"
    if not package.is_file() or not lock.is_file():
        add("tools", "fail", f"{tools} needs package.json and package-lock.json")
        return
    deps: dict[str, str] = json.loads(package.read_text("utf-8")).get("dependencies", {})
    loose = [f"{p}@{v}" for p, v in deps.items() if not EXACT.match(v)]
    if loose:
        add("tools", "fail", f"tools not pinned exactly: {', '.join(loose)}")
    locked = json.loads(lock.read_text("utf-8")).get("packages", {})
    for step in codemods:
        bin_path = spec.tools.bins.get(step.tool)
        if bin_path is None:
            add(
                "tools",
                "fail",
                f"codemod {step.name!r} names tool {step.tool!r}, not in [tools.bins]",
            )
            continue
        owner = _package_of(bin_path)
        if owner is None or f"node_modules/{owner}" not in locked:
            add("tools", "fail", f"{step.tool} = {bin_path}: its package is not in the lockfile")
        elif owner not in deps:
            add("tools", "warn", f"{owner} is only a transitive dependency of the tools")
        else:
            add("tools", "ok", f"{step.name}: {owner}@{deps[owner]} ({bin_path})")
        if not any("{files}" in a for a in step.args):
            add("tools", "warn", f"codemod {step.name!r} has no {{files}} argument")


def _package_of(bin_path: str) -> str | None:
    parts = Path(bin_path).parts
    if len(parts) < 2 or parts[0] != "node_modules":
        return None
    return "/".join(parts[1:3]) if parts[1].startswith("@") else parts[1]


def _check_steps(spec: MigrationSpec, add: Callable[[str, Status, str], None]) -> None:
    steps = spec.rule_steps
    first_codemod = next((i for i, s in enumerate(steps) if isinstance(s, CodemodStep)), None)
    if first_codemod is not None and not any(
        isinstance(s, InstallStep) for s in steps[:first_codemod]
    ):
        add("rule steps", "warn", "no install before the first codemod")
    if spec.dependency_map and not any(isinstance(s, DependenciesStep) for s in steps):
        add("rule steps", "fail", "a dependency map but no dependencies step")
    if any(isinstance(s, DependenciesStep) for s in steps) and not spec.dependency_map:
        add("rule steps", "warn", "a dependencies step but an empty dependency map")
    deps_at = [i for i, s in enumerate(steps) if isinstance(s, DependenciesStep)]
    if deps_at and not any(isinstance(s, InstallStep) for s in steps[deps_at[-1] :]):
        add("rule steps", "fail", "nothing installs the new dependencies after the bump")
    order = " -> ".join(s.name if s.kind in ("codemod", "script") else s.kind for s in steps)
    add("rule steps", "ok", order or "none")


def _check_network(
    spec: MigrationSpec, add: Callable[[str, Status, str], None], fetch: Fetch
) -> None:
    g = spec.guide
    url = f"https://api.github.com/repos/{g.repo}/commits/{g.commit}"
    status = fetch(url)
    if status == 200:
        add("guide pin", "ok", f"commit {g.commit[:12]} exists in {g.repo}")
    else:
        add(
            "guide pin",
            "fail" if status == 404 else "warn",
            f"GitHub answered {status or 'nothing'} for {url}",
        )
    pins = [(p, v) for e in spec.dependency_map for p, v in e.new.items()]
    bad = 0
    for pkg, ver in pins:
        status = fetch(f"https://registry.npmjs.org/{pkg}/{ver}")
        if status != 200:
            bad += 1
            add(
                "pins",
                "fail" if status == 404 else "warn",
                f"npm answered {status or 'nothing'} for {pkg}@{ver}",
            )
    if pins and not bad:
        add("pins", "ok", f"all {len(pins)} pinned versions exist on npm")
