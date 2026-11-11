"""Per-repo and per-case configuration.

``RepoConfig`` is one schema shared by a target repo's ``migrate.toml`` (top level) and
a case's ``case.toml`` (its ``[repo]`` table). Fields left unset fall through: the case
overrides the repo's ``migrate.toml``, which overrides detection and the migration
spec's defaults.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from migrator.visual import VisualConfig

Runner = Literal["jest", "vitest", "karma"]
VerifyName = Literal["typecheck", "lint", "test"]
VERIFY_ORDER: tuple[VerifyName, ...] = ("typecheck", "lint", "test")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VerifyCommands(_Model):
    typecheck: str | None = None
    lint: str | None = None
    test: str | None = None
    # M6 speed-up 5: run each tsc in the type-check with --incremental, its build info
    # kept in the workspace's .migrator/ folder (never committed, never scanned).
    typecheck_incremental: bool | None = None


class RepoConfig(_Model):
    """Everything about a target repo that detection may get wrong."""

    node: str | None = None
    install_flags: list[str] | None = None
    source_globs: list[str] | None = None
    exclude: list[str] | None = None
    runner: Runner | None = None
    verify: VerifyCommands | None = None
    # Environment for package installs only, e.g. ELECTRON_SKIP_BINARY_DOWNLOAD=1.
    install_env: dict[str, str] | None = None
    # Extra dependency changes a human wrote for this repo (never the LLM), applied by
    # the dependencies rule step after the migration's own dependency map: a package
    # name and its new version, or "" to remove it (M6, e.g. a third-party MUI wrapper
    # whose next major needs the new library).
    extra_dependencies: dict[str, str] | None = None
    # Run the Pre-check's tests once with coverage, to label each migrated file covered
    # or not covered by a test (M6).
    coverage: bool | None = None
    # The snapshot policy (M6): when a test file's only failures are snapshot
    # mismatches, the Migrator updates its snapshots and lists them for a human.
    update_snapshots: bool | None = None
    # The visual check (M7): how to build the app and which pages to screenshot.
    visual: VisualConfig | None = None

    def merged_over(self, base: RepoConfig) -> RepoConfig:
        """This config's set fields on top of ``base``; verify commands merge per command."""
        data = base.model_dump(exclude_none=True)
        mine = self.model_dump(exclude_none=True)
        verify = {**data.get("verify", {}), **mine.pop("verify", {})}
        data.update(mine)
        if verify:
            data["verify"] = verify
        return RepoConfig.model_validate(data)


class Upstream(_Model):
    """A real repo case (M6): a public repo cloned at the reference PR's base commit
    into the Migrator's cache (never into this repository)."""

    repo: str  # a git URL
    commit: str  # the reference PR's base commit: what the run migrates
    subdir: str = ""  # the target repo's folder inside the upstream repo
    reference_pr: str  # the merged migration PR's URL
    reference_head: str  # the PR's last commit: the reference is commit..reference_head


class CaseConfig(_Model):
    id: str
    migration: str
    # A fixture's folder, relative to this repository; empty for an upstream case,
    # whose source is its cached checkout.
    source: str = ""
    split: Literal["dev", "held-out"]
    runner: Runner
    reference: str
    traps: str | None = None
    upstream: Upstream | None = None
    # The run's wall-clock ceiling in seconds, when the case needs more than the default
    # (real repos with slow test suites).
    ceiling_s: float | None = None
    repo: RepoConfig = RepoConfig()

    # Set by the loader: the case's folder. Not part of the TOML.
    folder: Path = Field(default=Path(), exclude=True)

    @model_validator(mode="after")
    def _one_source(self) -> CaseConfig:
        if bool(self.source) == (self.upstream is not None):
            raise ValueError("a case names either a fixture `source` or an [upstream] repo")
        return self

    def traps_path(self) -> Path | None:
        return self.folder / self.traps if self.traps else None


def load_repo_config(repo: Path) -> RepoConfig:
    """The target repo's own ``migrate.toml``, or an empty config."""
    path = repo / "migrate.toml"
    if not path.exists():
        return RepoConfig()
    with path.open("rb") as fh:
        return RepoConfig.model_validate(tomllib.load(fh))


def load_case(path: Path) -> CaseConfig:
    with path.open("rb") as fh:
        case = CaseConfig.model_validate(tomllib.load(fh))
    return case.model_copy(update={"folder": path.parent.resolve()})


# --------------------------------------------------------------------------- detection

PackageManager = Literal["npm", "yarn", "pnpm"]
LOCKFILES: dict[str, PackageManager] = {
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
}


class ConfigError(ValueError):
    pass


def detect_package_manager(repo: Path) -> tuple[PackageManager, str]:
    """The package manager and lockfile name; a repo without a lockfile is refused."""
    for name, manager in LOCKFILES.items():
        if (repo / name).exists():
            return manager, name
    raise ConfigError(
        f"{repo} has no lockfile ({', '.join(LOCKFILES)}); the Migrator needs one to "
        "install the same packages the repo uses"
    )


def read_package_json(repo: Path) -> dict[str, object]:
    path = repo / "package.json"
    if not path.exists():
        raise ConfigError(f"{repo} has no package.json")
    data = json.loads(path.read_text("utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"{path} is not a JSON object")
    return data


def _scripts(package: dict[str, object]) -> dict[str, str]:
    scripts = package.get("scripts")
    return {str(k): str(v) for k, v in scripts.items()} if isinstance(scripts, dict) else {}


def all_dependencies(package: dict[str, object]) -> dict[str, str]:
    deps: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        value = package.get(section)
        if isinstance(value, dict):
            deps.update({str(k): str(v) for k, v in value.items()})
    return deps


def run_script_command(manager: PackageManager, script: str) -> str:
    if manager == "npm":
        return "npm test" if script == "test" else f"npm run {script}"
    return f"{manager} {script}" if manager == "yarn" else f"pnpm run {script}"


def detect_verify_commands(repo: Path, manager: PackageManager) -> VerifyCommands:
    """Verify commands from package.json scripts, when the config does not name them."""
    scripts = _scripts(read_package_json(repo))
    typecheck = next((s for s in ("typecheck", "type-check", "tsc") if s in scripts), None)
    return VerifyCommands(
        typecheck=run_script_command(manager, typecheck)
        if typecheck
        else ("npx tsc --noEmit" if (repo / "tsconfig.json").exists() else None),
        lint=run_script_command(manager, "lint") if "lint" in scripts else None,
        test=run_script_command(manager, "test") if "test" in scripts else None,
    )


def detect_runner(repo: Path) -> Runner | None:
    deps = all_dependencies(read_package_json(repo))
    if "vitest" in deps:
        return "vitest"
    if "jest" in deps:
        return "jest"
    return None


class LeftoverCheck(_Model):
    """What still counts as the old version after the Rules stage (M7), checked by every
    Verify after it (never the Pre-check). For a migration whose old code still compiles
    (Angular's legacy components do), it is the only failure an unmigrated file gets."""

    old_modules: list[str]  # regexes for module specifiers, as in the spec's [usage]
    old_styles: list[str] = []  # regexes for stylesheet lines (mat.legacy-*)
    todo_markers: list[str] = []  # Codemod TODOs that count as failures (if the spec says)
    source_globs: list[str]
    exclude: list[str] = []


class ResolvedRepoConfig(_Model):
    """A RepoConfig with every value decided."""

    package_manager: PackageManager
    lockfile: str
    node: str | None
    install_flags: list[str]
    source_globs: list[str]
    exclude: list[str]
    runner: Runner | None
    verify: VerifyCommands
    install_env: dict[str, str] = {}
    extra_dependencies: dict[str, str] = {}
    coverage: bool = False
    update_snapshots: bool = False
    visual: VisualConfig | None = None
    leftovers: LeftoverCheck | None = None


def resolve_repo_config(
    repo: Path,
    override: RepoConfig | None,
    default_globs: list[str],
    default_exclude: list[str],
) -> ResolvedRepoConfig:
    config = load_repo_config(repo)
    if override is not None:
        config = override.merged_over(config)
    manager, lockfile = detect_package_manager(repo)
    detected = detect_verify_commands(repo, manager)
    given = config.verify or VerifyCommands()
    verify = VerifyCommands(
        typecheck=given.typecheck or detected.typecheck,
        lint=given.lint or detected.lint,
        test=given.test or detected.test,
        typecheck_incremental=given.typecheck_incremental,
    )
    return ResolvedRepoConfig(
        package_manager=manager,
        lockfile=lockfile,
        node=config.node,
        install_flags=config.install_flags or [],
        source_globs=config.source_globs or default_globs,
        exclude=config.exclude or default_exclude,
        runner=config.runner or detect_runner(repo),
        verify=verify,
        install_env=config.install_env or {},
        extra_dependencies=config.extra_dependencies or {},
        coverage=bool(config.coverage),
        update_snapshots=bool(config.update_snapshots),
        visual=config.visual,
    )


# --------------------------------------------------------------------------- traps


class TrapLocation(_Model):
    model_config = ConfigDict(extra="allow", frozen=True)
    file: str
    line: int | None = None
    symbol: str | None = None


class Trap(_Model):
    model_config = ConfigDict(extra="allow", frozen=True)
    id: str
    title: str
    expected_layer: Literal["rules", "agent", "human", "visual-only"]
    location: TrapLocation
    caught_by: list[str] | Literal["none"] = "none"

    def checks(self) -> list[str]:
        return [] if self.caught_by == "none" else list(self.caught_by)


class TrapList(_Model):
    model_config = ConfigDict(extra="allow", frozen=True)
    schema_version: int
    case: str
    traps: list[Trap]


def load_traps(path: Path) -> TrapList:
    return TrapList.model_validate(yaml.safe_load(path.read_text("utf-8")))
