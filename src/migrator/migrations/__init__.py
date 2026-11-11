"""Migration specs: the pure-data description of one version jump, and its loader.

Each migration is a folder next to this module (for example ``mui-4-to-5/``) holding
``migration.toml``, the vendored guide and a pinned Node tools workspace.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MIGRATIONS_DIR = Path(__file__).parent


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Detection(_Model):
    packages: list[str]
    major: int


class Precondition(_Model):
    package: str
    min_major: int


class UsagePatterns(_Model):
    old_modules: list[str]
    new_modules: list[str]

    @field_validator("old_modules", "new_modules")
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


RuleStep = Annotated[
    InstallStep | DependenciesStep | CodemodStep | FormatStep | ScriptStep,
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
    tools: ToolsConfig
    dependency_map: list[DependencyMapEntry] = []
    rule_steps: list[RuleStep]
    # Selectors the visual check hides in every screenshot (M7): animated decorations
    # of the library, such as a click ripple, that would differ between two captures.
    visual_hide: list[str] = []

    # Set by the loader: the folder the spec came from. Not part of the TOML.
    folder: Path = Field(default=Path(), exclude=True)

    @field_validator("rule_steps")
    @classmethod
    def _codemods_run_once(cls, steps: list[RuleStep]) -> list[RuleStep]:
        names = [s.name for s in steps if isinstance(s, CodemodStep)]
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
        return self.folder / self.tools.workspace


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
