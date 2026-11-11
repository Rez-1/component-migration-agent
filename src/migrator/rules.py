"""The Rules stage: the migration spec's ordered rule steps, each run exactly once.

The codemods exit 0 whatever happens, so what a step changed is found by hashing the
workspace before and after it. A step that fails stops the run with a Rules failure.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from migrator.config import ResolvedRepoConfig, all_dependencies, read_package_json
from migrator.execs import CommandResult, CommandRunner
from migrator.false_positives import (
    CodemodFalsePositive,
    remove_stray_parens,
    revert_false_positives,
)
from migrator.migrations import (
    CodemodStep,
    DependenciesStep,
    DependencyMapEntry,
    FormatStep,
    InstallStep,
    MigrationSpec,
    RuleStep,
    ScriptStep,
)
from migrator.scan.parser import parse_file
from migrator.verify import install
from migrator.workspace import (
    Snapshot,
    changed_files,
    installed_manifest,
    list_files,
    manifest_hash,
    snapshot,
)

StepStatus = Literal["ok", "skipped", "failed"]


class RulesInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace: Path
    spec: MigrationSpec
    config: ResolvedRepoConfig
    affected_files: list[str]
    tools_dir: Path
    log_dir: Path
    # node_modules lives in the sandbox's volume (speed-up 4): look for a tool inside it.
    probe_bins: bool = False


class RuleStepResult(BaseModel):
    kind: str
    name: str
    status: StepStatus
    changed_files: list[str] = []
    detail: str = ""
    duration_s: float = 0.0
    log: str = ""


class CodemodTodo(BaseModel):
    model_config = ConfigDict(frozen=True)

    file: str
    line: int
    text: str


class RulesResult(BaseModel):
    status: Literal["ok", "rules_failure"]
    reason: str | None = None
    steps: list[RuleStepResult]
    changed_files: list[str]  # every file a rule step changed, package files included
    codemod_todos: list[CodemodTodo] = []
    # Codemod changes to the repo's own components, undone after the codemods (M6).
    false_positives: list[CodemodFalsePositive] = []


class ToolsError(RuntimeError):
    pass


# --------------------------------------------------------------------------- tools


def tools_cache_root() -> Path:
    env = os.environ.get("MIGRATOR_CACHE_DIR")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".cache") / "migrator"


def ensure_tools(
    spec: MigrationSpec, runner: CommandRunner, cache_root: Path | None = None
) -> Path:
    """Install the spec's pinned Node tools once, from their lockfile, into the cache."""
    return ensure_tools_dir(spec.tools_dir(), spec.folder.name, runner, cache_root)


def ensure_tools_dir(
    source: Path, label: str, runner: CommandRunner, cache_root: Path | None = None
) -> Path:
    """Install a pinned Node tools workspace (``package.json`` and ``package-lock.json``)
    once into the cache, keyed by its lockfile; returns the installed folder."""
    lock = source / "package-lock.json"
    if not lock.is_file():
        raise ToolsError(f"{source} has no package-lock.json; the tools must be pinned")
    key = manifest_hash(source, "package-lock.json")[:12]
    target = (cache_root or tools_cache_root()) / "tools" / f"{label}-{key}"
    if installed_manifest(target) == manifest_hash(source, "package-lock.json"):
        return target
    target.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(source / name, target / name)
    result = runner.run(
        ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        target,
        log_file=target / "install.log",
    )
    if not result.ok:
        raise ToolsError(f"installing the pinned tools failed; see {target / 'install.log'}")
    (target / "node_modules" / ".migrator-install.json").write_text(
        json.dumps({"manifest": manifest_hash(target, "package-lock.json")}), "utf-8"
    )
    return target


# --------------------------------------------------------------------------- steps

_JSCODESHIFT_LINE = re.compile(r"^\s*(OKK|NOC|ERR|SKIP)\s+(\S+)(.*)$")


def parse_jscodeshift(output: str) -> dict[str, list[tuple[str, str]]]:
    """jscodeshift's ``--verbose=2`` lines by status: OKK, NOC, ERR, SKIP."""
    found: dict[str, list[tuple[str, str]]] = {"OKK": [], "NOC": [], "ERR": [], "SKIP": []}
    for line in output.splitlines():
        if m := _JSCODESHIFT_LINE.match(line):
            found[m[1]].append((m[2], m[3].strip()))
    return found


def apply_dependency_map(
    package: dict[str, object], mapping: list[DependencyMapEntry]
) -> list[str]:
    """Replace each old package by its new ones in the same section; returns what changed."""
    notes: list[str] = []
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps = package.get(section)
        if not isinstance(deps, dict):
            continue
        for entry in mapping:
            if entry.old not in deps:
                continue
            del deps[entry.old]
            notes.append(f"-{entry.old}")
            for name, version in entry.new.items():
                if deps.get(name) != version:
                    deps[name] = version
                    notes.append(f"+{name}@{version}")
        package[section] = dict(sorted(deps.items()))
    return notes


def apply_extra_dependencies(package: dict[str, object], extra: dict[str, str]) -> list[str]:
    """A repo's human-written dependency changes: set each package's version where it is
    already listed (dependencies by default), or remove it when the version is ""."""
    notes: list[str] = []
    sections = [s for s in ("dependencies", "devDependencies", "peerDependencies")
                if isinstance(package.get(s), dict)]  # fmt: skip
    for name, version in sorted(extra.items()):
        held = [s for s in sections if name in package[s]]  # type: ignore[operator]
        if not version:
            for s in held:
                del package[s][name]  # type: ignore[attr-defined]
            if held:
                notes.append(f"-{name} (repo config)")
            continue
        for s in held or ["dependencies"]:
            deps = package.setdefault(s, {})
            assert isinstance(deps, dict)
            if deps.get(name) != version:
                deps[name] = version
                notes.append(f"+{name}@{version} (repo config)")
            package[s] = dict(sorted(deps.items()))
    return notes


def _indent_of(text: str) -> int:
    m = re.search(r'^(\s+)"', text, re.MULTILINE)
    return len(m.group(1)) if m else 2


def _expand(args: list[str], files: list[str]) -> list[str]:
    out: list[str] = []
    for arg in args:
        out.extend(files) if arg == "{files}" else out.append(arg)
    return out


class _Run:
    """State while the steps run: what has changed so far, and where logs go."""

    def __init__(self, inp: RulesInput, runner: CommandRunner):
        self.inp = inp
        self.runner = runner
        self.ws = inp.workspace
        self.sources = list_files(self.ws, inp.config.source_globs, inp.config.exclude)
        self.tracked = sorted({*self.sources, "package.json", inp.config.lockfile})
        self.changed: set[str] = set()
        self.index = 0

    def snap(self) -> Snapshot:
        return snapshot(self.ws, self.tracked)

    def log_file(self, name: str) -> Path:
        return self.inp.log_dir / f"rules-{self.index:02d}-{name}.log"

    def run(self, command: list[str] | str, name: str) -> CommandResult:
        return self.runner.run(command, self.ws, log_file=self.log_file(name))

    # Each returns (status, detail, duration, log name).
    def install(self, step: InstallStep) -> tuple[StepStatus, str, float, str]:
        config = self.inp.config
        if installed_manifest(self.ws) == manifest_hash(self.ws, config.lockfile):
            return "skipped", "packages already installed for this package.json", 0.0, ""
        frozen = "package.json" not in self.changed
        log = self.log_file(step.name)
        result = install(self.runner, self.ws, config, frozen=frozen, log_file=log)
        if not result.ok:
            return (
                "failed",
                f"`{result.command}` exited {result.exit_code}",
                result.duration_s,
                log.name,
            )
        return "ok", result.command, result.duration_s, log.name

    def codemod(self, step: CodemodStep) -> tuple[StepStatus, str, float, str]:
        spec = self.inp.spec
        if step.tool not in spec.tools.bins:
            return "failed", f"unknown tool {step.tool!r}", 0.0, ""
        script = self.inp.tools_dir / spec.tools.bins[step.tool]
        files = sorted(self.inp.affected_files)
        result = self.run(["node", str(script), *_expand(step.args, files)], step.name)
        lines = parse_jscodeshift(result.output)
        errors = [(p, why) for p, why in lines["ERR"] if not p.endswith(".json")]
        seen = len(lines["OKK"]) + len(lines["NOC"]) + len(errors)
        log = self.log_file(step.name).name
        if errors:
            listed = "; ".join(f"{Path(p).name}: {why}" for p, why in errors[:3])
            return (
                "failed",
                f"{len(errors)} files not transformed ({listed})",
                result.duration_s,
                log,
            )
        if not result.ok or seen == 0:
            return (
                "failed",
                f"the codemod processed no files (exit {result.exit_code})",
                result.duration_s,
                log,
            )
        return (
            "ok",
            f"{len(lines['OKK'])} ok, {len(lines['NOC'])} unchanged",
            result.duration_s,
            log,
        )

    def format(self, step: FormatStep) -> tuple[StepStatus, str, float, str]:
        files = sorted(f for f in self.changed if f in self.sources)
        if not files:
            return "skipped", "no changed source files", 0.0, ""
        deps = all_dependencies(read_package_json(self.ws))
        bin_dir = self.ws / "node_modules" / ".bin"

        def has(tool: str) -> bool:
            if not self.inp.probe_bins:
                return (bin_dir / tool).exists()
            return self.runner.run(f"test -e node_modules/.bin/{tool}", self.ws).ok

        if "prettier" in deps and has("prettier"):
            # Relative to the workspace: inside the sandbox the absolute host path may not
            # exist (macOS /var/folders is mounted at its resolved /private/var path).
            result = self.run(["node_modules/.bin/prettier", "--write", *files], step.name)
            failed = not result.ok
            tool = "prettier --write"
        elif "eslint" in deps and has("eslint"):
            result = self.run(["node_modules/.bin/eslint", "--fix", *files], step.name)
            failed = result.exit_code not in (0, 1)  # 1 = unfixable lint errors remain
            tool = "eslint --fix"
        else:
            return "skipped", "the repo has no Prettier or ESLint", 0.0, ""
        status: StepStatus = "failed" if failed else "ok"
        detail = f"{tool} on {len(files)} files" + (f" (exit {result.exit_code})" if failed else "")
        return status, detail, result.duration_s, self.log_file(step.name).name

    def dependencies(self, step: DependenciesStep) -> tuple[StepStatus, str, float, str]:
        path = self.ws / "package.json"
        text = path.read_text("utf-8")
        package = read_package_json(self.ws)
        notes = apply_dependency_map(package, self.inp.spec.dependency_map)
        notes += apply_extra_dependencies(package, self.inp.config.extra_dependencies)
        if not notes:
            return "skipped", "no mapped dependencies", 0.0, ""
        path.write_text(
            json.dumps(package, indent=_indent_of(text), ensure_ascii=False) + "\n", "utf-8"
        )
        return "ok", " ".join(notes), 0.0, ""

    def script(self, step: ScriptStep) -> tuple[StepStatus, str, float, str]:
        files = " ".join(sorted(self.inp.affected_files))
        result = self.run(step.command.replace("{files}", files), step.name)
        status: StepStatus = "ok" if result.ok else "failed"
        return status, f"exit {result.exit_code}", result.duration_s, self.log_file(step.name).name

    def step(self, step: RuleStep) -> tuple[StepStatus, str, float, str]:
        match step:
            case InstallStep():
                return self.install(step)
            case CodemodStep():
                return self.codemod(step)
            case FormatStep():
                return self.format(step)
            case DependenciesStep():
                return self.dependencies(step)
            case ScriptStep():
                return self.script(step)


def find_codemod_todos(
    before: dict[str, bytes], after_root: Path, files: list[str], markers: list[str]
) -> list[CodemodTodo]:
    """Marker comments in ``files`` that were not there before the Rules stage."""
    if not markers:
        return []
    marker = re.compile(r"\b(" + "|".join(re.escape(m) for m in markers) + r")\b")

    def marked(source: bytes, path: str) -> list[tuple[int, str]]:
        parsed = parse_file(source, path, lambda _m: False)
        return [(c.line, c.text.strip()) for c in parsed.comments if marker.search(c.text)]

    todos: list[CodemodTodo] = []
    for path in files:
        old_texts = [text for _, text in marked(before.get(path, b""), path)]
        for line, text in marked((after_root / path).read_bytes(), path):
            if text in old_texts:
                old_texts.remove(text)
            else:
                todos.append(CodemodTodo(file=path, line=line, text=text))
    return todos


def undo_false_positives(
    inp: RulesInput, originals: dict[str, bytes], sources: list[str]
) -> list[CodemodFalsePositive]:
    """Undo the codemods' changes to the repo's own components, and remove the stray
    parentheses they leave inside a new wrapper (``false_positives``)."""
    usage = inp.spec.usage
    packages = all_dependencies(read_package_json(inp.workspace))
    found: list[CodemodFalsePositive] = []
    for rel in sources:
        path = inp.workspace / rel
        before = originals.get(rel)
        if before is None or not path.is_file():
            continue
        after = path.read_text("utf-8")
        original = before.decode("utf-8", "replace")
        text, fps = revert_false_positives(
            rel, original, after, lambda m: usage.is_old(m) or usage.is_new(m), packages
        )
        text, parens = remove_stray_parens(rel, original, text)
        fps = sorted(fps + parens, key=lambda f: f.line)
        if fps:
            path.write_text(text, "utf-8")
            found += fps
    return found


def apply_rules(inp: RulesInput, runner: CommandRunner) -> RulesResult:
    """Run the rule steps in order; stop at the first failed step (a Rules failure)."""
    inp.log_dir.mkdir(parents=True, exist_ok=True)
    state = _Run(inp, runner)
    originals = {p: (inp.workspace / p).read_bytes() for p in state.sources}
    results: list[RuleStepResult] = []
    reason: str | None = None
    false_positives: list[CodemodFalsePositive] = []
    for index, step in enumerate(inp.spec.rule_steps, start=1):
        state.index = index
        before = state.snap()
        status, detail, duration, log = state.step(step)
        changed = changed_files(before, state.snap())
        state.changed.update(changed)
        results.append(
            RuleStepResult(
                kind=step.kind,
                name=step.name,
                status=status,
                changed_files=changed,
                detail=detail,
                duration_s=duration,
                log=log,
            )
        )
        if status == "failed":
            reason = f"rule step {index} ({step.kind} {step.name}) failed: {detail}"
            break
        steps = inp.spec.rule_steps
        if step.kind == "codemod" and not any(s.kind == "codemod" for s in steps[index:]):
            # After the last codemod: undo its changes to the repo's own components.
            found = undo_false_positives(inp, originals, state.sources)
            false_positives += found
            if found:
                # A file the undo restored completely no longer counts as changed.
                state.changed = {
                    p
                    for p in state.changed
                    if p not in originals or (inp.workspace / p).read_bytes() != originals[p]
                }
    sources_changed = sorted(f for f in state.changed if f in originals)
    todos = find_codemod_todos(
        originals, inp.workspace, sources_changed, inp.spec.codemod_todo_markers
    )
    return RulesResult(
        status="rules_failure" if reason else "ok",
        reason=reason,
        steps=results,
        changed_files=sorted(state.changed),
        codemod_todos=todos,
        false_positives=false_positives,
    )
