"""``migrator init``: detect a target repo's setup and write a commented ``migrate.toml``.

Every value comes from a file in the repo, and the comment next to it says which one;
what can't be detected is written as a TODO and printed. No LLM, no network. The
developer checks the file before the first run: detection is a starting point, and the
verify commands in particular decide what "migrated" means.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel

from migrator.config import (
    LOCKFILES,
    PackageManager,
    all_dependencies,
    read_package_json,
    run_script_command,
)


class Detected(BaseModel):
    """One value and where it came from (None: not detected, with why)."""

    value: str | list[str] | dict[str, str] | None
    source: str


class InitResult(BaseModel):
    package_manager: Detected
    node: Detected
    runner: Detected
    typecheck: Detected
    lint: Detected
    test: Detected
    source_globs: Detected
    install_env: Detected
    todos: list[str]


# --------------------------------------------------------------------------- detectors


def detect_manager(repo: Path) -> Detected:
    for name, manager in LOCKFILES.items():
        if (repo / name).is_file():
            return Detected(value=manager, source=name)
    return Detected(value=None, source="no lockfile (package-lock.json, yarn.lock, pnpm-lock.yaml)")


def _major(text: str) -> str | None:
    m = re.search(r"(\d+)", text.strip().removeprefix("v"))
    return m.group(1) if m else None


def detect_node(repo: Path, package: dict[str, object]) -> Detected:
    for name in (".nvmrc", ".node-version"):
        path = repo / name
        if path.is_file():
            text = path.read_text("utf-8").strip()
            major = _major(text)
            if major:
                return Detected(value=major, source=f"{name} ({text})")
    engines = package.get("engines")
    if isinstance(engines, dict) and isinstance(engines.get("node"), str):
        spec = str(engines["node"])
        major = _major(spec)
        if major:
            return Detected(value=major, source=f'package.json engines.node ("{spec}")')
    return Detected(value=None, source="no .nvmrc, .node-version or engines.node")


def detect_runner(deps: dict[str, str]) -> Detected:
    if "vitest" in deps:
        return Detected(value="vitest", source=f"vitest {deps['vitest']} in package.json")
    if "jest" in deps:
        return Detected(value="jest", source=f"jest {deps['jest']} in package.json")
    if "react-scripts" in deps:
        return Detected(
            value="jest", source=f"react-scripts {deps['react-scripts']} (CRA runs Jest)"
        )
    return Detected(value=None, source="no vitest, jest or react-scripts in package.json")


_FIX = re.compile(r"(^|\s)--fix(\s|$)")


def detect_verify(
    scripts: dict[str, str], manager: PackageManager, repo: Path, runner: str | None
) -> tuple[Detected, Detected, Detected]:
    def cmd(name: str) -> str:
        return run_script_command(manager, name)

    # Type-check: a script by a known name, else any script that only runs tsc.
    typecheck = Detected(value=None, source="no type-check script")
    for name in ("typecheck", "type-check", "tsc", "check-types", "compile-all"):
        if name in scripts:
            typecheck = Detected(value=cmd(name), source=f'scripts.{name}: "{scripts[name]}"')
            break
    else:
        tsc = [n for n, body in scripts.items() if re.match(r"^\s*tsc\b", body)]
        if tsc:
            n = tsc[0]
            typecheck = Detected(value=cmd(n), source=f'scripts.{n}: "{scripts[n]}"')
        elif (repo / "tsconfig.json").is_file():
            typecheck = Detected(value="npx tsc --noEmit", source="tsconfig.json, no script")

    # Lint: never a script that runs --fix (verify must not change files).
    lint = Detected(value=None, source="no lint script")
    candidates = [n for n in ("lint", "lint-check", "lint:check", "eslint") if n in scripts]
    for name in candidates:
        body = scripts[name]
        if _FIX.search(body):
            lint = Detected(
                value=None, source=f'scripts.{name} runs --fix ("{body}"), so it is not used'
            )
            continue
        lint = Detected(value=cmd(name), source=f'scripts.{name}: "{body}"')
        break

    # Tests: the `test` script; CRA's watches unless told otherwise.
    test = Detected(value=None, source="no test script")
    script = next((n for n in ("test", "test:unit", "test:ci") if n in scripts), None)
    if script is not None:
        body = scripts[script]
        value = cmd(script)
        source = f'scripts.{script}: "{body}"'
        if script != "test":
            source += "; check it runs every unit test you want verified"
        if "react-scripts test" in body and "--watchAll=false" not in body:
            sep = " -- " if manager == "npm" else " "
            value = f"{value}{sep}--watchAll=false"
            source += ", plus --watchAll=false (react-scripts would watch)"
        if runner == "vitest" and "vitest" in body and " run" not in body:
            source += "; check it runs once (`vitest run`), not in watch mode"
        test = Detected(value=value, source=source)
    return typecheck, lint, test


def detect_globs(repo: Path) -> Detected:
    folder = "src" if (repo / "src").is_dir() else None
    if folder is None:
        return Detected(value=None, source="no src/ folder")
    exts = sorted(
        {
            p.suffix
            for p in (repo / folder).rglob("*")
            if p.suffix in (".ts", ".tsx", ".js", ".jsx") and "node_modules" not in p.parts
        }
    )
    if not exts:
        return Detected(value=None, source="no .ts/.tsx/.js/.jsx files under src/")
    return Detected(
        value=[f"{folder}/**/*{e}" for e in exts], source=f"the file types found under {folder}/"
    )


# Install-time downloads that unit tests don't need, by the dependency that does them.
_INSTALL_ENV = {
    "electron": ("ELECTRON_SKIP_BINARY_DOWNLOAD", "1"),
    "playwright": ("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", "1"),
    "@playwright/test": ("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", "1"),
    "cypress": ("CYPRESS_INSTALL_BINARY", "0"),
    "puppeteer": ("PUPPETEER_SKIP_DOWNLOAD", "1"),
}


def detect_install_env(deps: dict[str, str]) -> Detected:
    env: dict[str, str] = {}
    why: list[str] = []
    for dep, (key, value) in _INSTALL_ENV.items():
        if dep in deps:
            env[key] = value
            why.append(dep)
    return Detected(
        value=env or None,
        source=f"{', '.join(why)} download binaries at install" if why else "none needed",
    )


def detect(repo: Path) -> InitResult:
    package = read_package_json(repo)
    deps = all_dependencies(package)
    raw = package.get("scripts")
    scripts = {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
    manager = detect_manager(repo)
    runner = detect_runner(deps)
    pm: PackageManager = manager.value if isinstance(manager.value, str) else "npm"  # type: ignore[assignment]
    typecheck, lint, test = detect_verify(
        scripts, pm, repo, runner.value if isinstance(runner.value, str) else None
    )
    result = InitResult(
        package_manager=manager,
        node=detect_node(repo, package),
        runner=runner,
        typecheck=typecheck,
        lint=lint,
        test=test,
        source_globs=detect_globs(repo),
        install_env=detect_install_env(deps),
        todos=[],
    )
    labels = {
        "package_manager": "package manager (add a lockfile; the Migrator installs from it)",
        "node": "Node version",
        "runner": "test runner",
        "typecheck": "type-check command",
        "lint": "lint command",
        "test": "test command",
        "source_globs": "source globs",
    }
    from migrator.execs import NODE_IMAGES

    node = result.node
    if isinstance(node.value, str) and node.value not in NODE_IMAGES:
        pinned = ", ".join(sorted(NODE_IMAGES, key=int))
        result.node = Detected(
            value=None,
            source=f"{node.source} asks for Node {node.value}, which the sandbox has no "
            f"pinned image for (pinned: {pinned}); pick the nearest one that runs the repo",
        )
    result.todos = [
        f"{label}: {getattr(result, key).source}"
        for key, label in labels.items()
        if getattr(result, key).value is None
    ]
    return result


# --------------------------------------------------------------------------- the file


def _toml(value: object) -> str:
    return json.dumps(value)  # strings and string lists are valid TOML in JSON form


def render_migrate_toml(r: InitResult) -> str:
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


def write_migrate_toml(repo: Path, *, force: bool = False) -> tuple[Path, InitResult]:
    path = repo / "migrate.toml"
    if path.exists() and not force:
        raise InitError(f"{path} exists; pass --force to overwrite it")
    result = detect(repo)
    path.write_text(render_migrate_toml(result), "utf-8")
    return path, result
