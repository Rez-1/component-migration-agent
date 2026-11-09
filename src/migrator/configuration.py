"""Configurations: everything an experiment varies, one TOML file each.

A configuration names the model per attempt, effort, repair prompt version, retrieval
mode, max attempts, cost caps and which rules are on. The Baseline is the
configuration with repair turned off. Configurations live in ``evals/configs/`` and are
also what a normal run is configured by (its caps and models).

M2 runs rules-only configurations. A configuration with repair on is valid and can be
loaded, but running it needs the repair loop (M3) and fails with
``NeedsRepairLoopError`` instead of silently running the Baseline.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from migrator.migrations import CodemodStep, MigrationSpec, ScriptStep

SCHEMA_VERSION = 1

Effort = Literal["low", "medium", "high", "xhigh", "max"]
Retrieval = Literal["keyword", "embeddings"]

# Rule steps a configuration may switch off. Install, dependencies and format are not
# optional: without the dependency bump a run is not a migration at all (and would
# verify clean while migrating nothing).
OPTIONAL_STEP_KINDS = ("codemod", "script")

# Default caps (ticket #12): on by default, no unlimited mode.
DEFAULT_MAX_RUN_USD = 5.0
DEFAULT_MAX_MONTH_USD = 20.0


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RepairSettings(_Model):
    enabled: bool = False
    # One model id per attempt, e.g. ["claude-opus-5-5"] * 3; its length is max_attempts.
    attempt_models: list[str] = []
    effort: Effort | None = None
    prompt_version: str | None = None
    retrieval: Retrieval | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def _complete_when_on(self) -> RepairSettings:
        if not self.enabled:
            if self.attempt_models:
                raise ValueError("repair is off, so attempt_models must be empty")
            return self
        missing = [
            name
            for name in ("effort", "prompt_version", "retrieval")
            if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(f"repair is on but {', '.join(missing)} not set")
        if len(self.attempt_models) != self.max_attempts:
            raise ValueError(
                f"attempt_models has {len(self.attempt_models)} entries; it needs one "
                f"model per attempt ({self.max_attempts})"
            )
        return self


class CostCaps(_Model):
    """Hard caps in USD (Anthropic's prices); the ledger that enforces them is M3."""

    max_run_usd: float = Field(default=DEFAULT_MAX_RUN_USD, gt=0)
    max_month_usd: float = Field(default=DEFAULT_MAX_MONTH_USD, gt=0)


class RulesSettings(_Model):
    # Names of codemod or script rule steps to switch off; everything else runs.
    skip: list[str] = []


class Configuration(_Model):
    schema_version: int = SCHEMA_VERSION
    name: str
    description: str = ""
    repair: RepairSettings = RepairSettings()
    cost: CostCaps = CostCaps()
    rules: RulesSettings = RulesSettings()

    # Set by the loader. Not part of the TOML.
    path: Path | None = Field(default=None, exclude=True)

    @property
    def uses_llm(self) -> bool:
        return self.repair.enabled

    def digest(self) -> str:
        """A short hash of everything the configuration varies (not its description)."""
        data = self.model_dump(mode="json", exclude={"description"})
        blob = json.dumps(data, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]

    def apply_to(self, spec: MigrationSpec) -> MigrationSpec:
        """The spec with this configuration's switched-off rule steps removed."""
        if not self.rules.skip:
            return spec
        optional = {s.name for s in spec.rule_steps if isinstance(s, CodemodStep | ScriptStep)}
        unknown = sorted(set(self.rules.skip) - optional)
        if unknown:
            raise ConfigurationError(
                f"configuration {self.name!r} skips {', '.join(unknown)}, which "
                f"{'is not a' if len(unknown) == 1 else 'are not'} codemod or script "
                f"step of {spec.id} (optional steps: {', '.join(sorted(optional))})"
            )
        steps = [s for s in spec.rule_steps if s.name not in self.rules.skip]
        return spec.model_copy(update={"rule_steps": steps})


BASELINE = Configuration(name="baseline", description="Rules only: no repair agent.")


class ConfigurationError(ValueError):
    pass


class NeedsRepairLoopError(ConfigurationError):
    """The configuration turns repair on, which needs the repair loop (M3)."""


# M3 flips this when the repair loop lands.
REPAIR_LOOP_AVAILABLE = False


def ensure_runnable(config: Configuration) -> None:
    """Refuse a configuration this version of the Migrator cannot run faithfully."""
    if config.repair.enabled and not REPAIR_LOOP_AVAILABLE:
        models = ", ".join(dict.fromkeys(config.repair.attempt_models))
        raise NeedsRepairLoopError(
            f"configuration {config.name!r} turns repair on ({models}, effort "
            f"{config.repair.effort}), which needs the repair loop (M3). Only rules-only "
            "configurations such as 'baseline' can run in this version; nothing was run."
        )


def load_configuration(path: Path) -> Configuration:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    try:
        config = Configuration.model_validate(data)
    except ValueError as exc:
        raise ConfigurationError(f"{path}: {exc}") from exc
    if config.name != path.stem:
        raise ConfigurationError(f"{path}: name {config.name!r} must match the file name")
    return config.model_copy(update={"path": path.resolve()})


def find_configuration(name_or_path: str, configs_dir: Path) -> Configuration:
    """A configuration by name (``evals/configs/<name>.toml``) or by path."""
    candidate = Path(name_or_path)
    if candidate.suffix == ".toml" and candidate.is_file():
        return load_configuration(candidate)
    path = configs_dir / f"{name_or_path}.toml"
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in configs_dir.glob("*.toml"))) or "none"
        raise ConfigurationError(f"no configuration {name_or_path!r} in {configs_dir} ({known})")
    return load_configuration(path)
