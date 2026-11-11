"""Migration specs: the pure-data description of one version jump, and its loader.

Each migration is a folder next to this module (for example ``mui-4-to-5/``) holding
``migration.toml``, the vendored guide and a pinned Node tools workspace.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MIGRATIONS_DIR = Path(__file__).parent


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Detection(_Model):
    packages: list[str]
    # The old version's major, or several (Angular Material's legacy components ship in
    # both 15 and 16).
    major: int | list[int]
    # Also require at least one usage of an old module in the source (M7): when the
    # major alone can't tell the old version from the new one (legacy and MDC
    # components live in the same Angular Material 15 package).
    requires_old_usage: bool = False

    @property
    def majors(self) -> list[int]:
        return self.major if isinstance(self.major, list) else [self.major]


class Precondition(_Model):
    package: str
    min_major: int


class UsagePatterns(_Model):
    old_modules: list[str]
    new_modules: list[str]
    # Stylesheet patterns of the old version (M7, Angular: `mat\.legacy-`).
    old_styles: list[str] = []

    @field_validator("old_modules", "new_modules", "old_styles")
    @classmethod
    def _valid_regexes(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            re.compile(pattern)
        return patterns

    def is_old(self, module: str) -> bool:
        return any(re.search(p, module) for p in self.old_modules)

    def is_new(self, module: str) -> bool:
        return any(re.search(p, module) for p in self.new_modules)


class GuideConfig(_Model):
    repo: str
    tag: str
    commit: str
    dir: str
    files: list[str]
    section_level: int = Field(ge=1, le=6)
    change_level: int = Field(ge=1, le=6)
    codemod_marker: str | None = None
    drop_sections: list[str] = []
    link_base: str | None = None
    # A guide that lists a section's changes as top-level bullet points, not headings
    # (Angular's MDC guide): each bullet becomes one change (M7).
    change_bullets: bool = False


class ToolsConfig(_Model):
    workspace: str
    bins: dict[str, str]


class DependencyMapEntry(_Model):
    old: str
    new: dict[str, str]


class InstallStep(_Model):
    kind: Literal["install"]
    name: str = "install"


class DependenciesStep(_Model):
    kind: Literal["dependencies"]
    name: str = "dependencies"


class CodemodStep(_Model):
    kind: Literal["codemod"]
    name: str
    tool: str
    args: list[str]


class FormatStep(_Model):
    kind: Literal["format"]
    name: str = "format"


class ScriptStep(_Model):
    kind: Literal["script"]
    name: str
    command: str


class SchematicStep(_Model):
    """A generator the target repo itself provides (M7: Angular's
    ``ng generate @angular/material:mdc-migration``), run once from the repo root with
    the repo's own installed tools, so it is not pinned in a tools workspace. Its exit
    code is not trusted: Angular's schematic logs failures and still exits 0, so the log
    is read for them."""

    kind: Literal["schematic"]
    name: str
    command: list[str]  # an argv, run without a shell
    env: dict[str, str] = {}
    # A log line matching one of these fails the whole step (a Rules failure).
    fail_on: list[str] = []
    # A log line matching this names one file the schematic could not process (named
    # group ``file``); those files are left for the repair agent.
    file_failed: str | None = None
    # A log line matching this names one file it changed (named group ``file``).
    file_changed: str | None = None

    @field_validator("fail_on")
    @classmethod
    def _regexes(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            re.compile(pattern)
        return patterns

    @field_validator("file_failed", "file_changed")
    @classmethod
    def _file_group(cls, pattern: str | None) -> str | None:
        if pattern is not None and "file" not in re.compile(pattern).groupindex:
            raise ValueError(f"{pattern!r} needs a named group (?P<file>...)")
        return pattern


RuleStep = Annotated[
    InstallStep | DependenciesStep | CodemodStep | FormatStep | ScriptStep | SchematicStep,
    Field(discriminator="kind"),
]


class MigrationSpec(_Model):
    id: str
    from_: str = Field(alias="from")
    to: str
    library_name: str
    from_version: str
    to_version: str
    codemod_name: str
    guide_title: str
    repair_notes: list[str]
    detection: Detection
    preconditions: list[Precondition] = []
    usage: UsagePatterns
    codemod_todo_markers: list[str]
    source_globs: list[str]
    exclude: list[str] = []
    guide: GuideConfig
    # Pinned Node tools (codemods); None when the deterministic layer runs from the
    # target repo's own tools (a schematic).
    tools: ToolsConfig | None = None
    dependency_map: list[DependencyMapEntry] = []
    rule_steps: list[RuleStep]
    # After Rules, every Verify also fails on what is left of the old version: imports of
    # old modules and old stylesheet patterns (M7; for a migration whose old code still
    # compiles). With todos_fail, the Codemod TODOs left in the source fail too.
    leftovers_fail: bool = False
    todos_fail: bool = False
    # Selectors the visual check hides in every screenshot (M7): animated decorations
    # of the library, such as a click ripple, that would differ between two captures.
    visual_hide: list[str] = []

    # Set by the loader: the folder the spec came from. Not part of the TOML.
    folder: Path = Field(default=Path(), exclude=True)

    @field_validator("rule_steps")
    @classmethod
    def _codemods_run_once(cls, steps: list[RuleStep]) -> list[RuleStep]:
        names = [s.name for s in steps if isinstance(s, CodemodStep | SchematicStep)]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"codemods must run exactly once; repeated: {sorted(duplicates)}")
        return steps

    def guide_dir(self) -> Path:
        return self.folder / self.guide.dir

    def import_prefixes(self) -> list[str]:
        """The new version's packages (from the dependency map), as import prefixes."""
        return sorted({name for entry in self.dependency_map for name in entry.new})

    def tools_dir(self) -> Path:
        if self.tools is None:
            raise ValueError(f"{self.id} has no [tools]: its rule steps use the repo's own")
        return self.folder / self.tools.workspace

    @model_validator(mode="after")
    def _codemods_need_tools(self) -> MigrationSpec:
        if self.tools is None and any(isinstance(s, CodemodStep) for s in self.rule_steps):
            raise ValueError("codemod steps need [tools]: the pinned tools workspace")
        return self


class UnknownMigrationError(LookupError):
    pass


def load_spec(folder: Path) -> MigrationSpec:
    """Load and validate ``migration.toml`` from a migration folder."""
    with (folder / "migration.toml").open("rb") as fh:
        data = tomllib.load(fh)
    spec = MigrationSpec.model_validate(data)
    return spec.model_copy(update={"folder": folder.resolve()})


def available_specs(root: Path = MIGRATIONS_DIR) -> list[MigrationSpec]:
    return [load_spec(p.parent) for p in sorted(root.glob("*/migration.toml"))]


def find_spec(from_: str, to: str, root: Path = MIGRATIONS_DIR) -> MigrationSpec:
    """Find the spec for one version jump, such as ``mui@4`` -> ``mui@5``."""
    specs = available_specs(root)
    for spec in specs:
        if spec.from_ == from_ and spec.to == to:
            return spec
    known = ", ".join(f"{s.from_} -> {s.to}" for s in specs) or "none"
    raise UnknownMigrationError(f"no migration from {from_} to {to} (known: {known})")
