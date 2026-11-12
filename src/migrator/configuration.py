"""Configurations: everything an experiment varies, one TOML file each.

A configuration names the model per attempt, effort, repair prompt version, retrieval
mode, max attempts, cost caps and which rules are on. The Baseline is the
configuration with repair turned off. Configurations live in ``evals/configs/`` and are
also what a normal run is configured by (its caps and models).

From M3 a configuration with repair on runs the repair agent with the models it
names, one per attempt. ``ensure_runnable`` refuses one this version can't run
faithfully (an unknown prompt, a missing provider package) before anything runs.

From M7 a configuration names model **levels** (``strong``, ``balanced``, ``fast``)
wherever it named a model, and its ``[models]`` table says which model fills each level
(Claude's by default; see ``migrator.model_table``). Levels are resolved when the
configuration loads, so everything downstream sees model ids, and the digest is taken
over the resolved models: a configuration that names levels digests the same as one
naming the same models directly. Every configuration written before M7 names models,
so its digest is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from migrator.migrations import CodemodStep, MigrationSpec, ScriptStep
from migrator.model_table import (
    ModelLevels,
    UnknownModelError,
    feature_notes,
    missing_packages,
)

SCHEMA_VERSION = 1

Effort = Literal["low", "medium", "high", "xhigh", "max"]
# keyword: BM25 over the guide (M3). M5's keyword-imports and keyword-context lost their
# rounds and were removed after 0eddf6e (see experiments.md).
Retrieval = Literal["keyword"]

# Fields added after configurations were first digested (M5, M6). They are left out of
# the digest while they hold their "off" value, so every configuration written before
# them keeps its digest and its experiments stay resumable and comparable. (M5's
# attempt_efforts and advisor were left out the same way; they were removed after
# 0eddf6e, so no surviving digest changed.)
_DIGEST_OPTIONAL = {
    "shared_causes": False,
    "test_fitting_hand_off": False,
    "reviewer_model": None,
}

# Rule steps a configuration may switch off. Install, dependencies and format are not
# optional: without the dependency bump a run is not a migration at all (and would
# verify clean while migrating nothing).
OPTIONAL_STEP_KINDS = ("codemod", "script")

# Default caps (ticket #12): on by default, no unlimited mode.
DEFAULT_MAX_RUN_USD = 5.0
DEFAULT_MAX_MONTH_USD = 20.0


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Fields removed after 0eddf6e (M5's per-attempt efforts and advisor tool). Configurations
# stored before then (run.json, experiment.json) carry them at their "off" value, which
# is accepted and dropped so those runs still resume and score; any other value is
# refused, since this version can't run it.
_REMOVED = {"attempt_efforts": None, "advisor": None}


def _drop_removed(data: Any, removed: dict[str, Any], where: str) -> Any:
    if not isinstance(data, dict):
        return data
    for key, off in removed.items():
        if key in data and data[key] != off:
            raise ValueError(
                f"{where}{key} was removed after commit 0eddf6e; check out that commit to "
                "run this configuration"
            )
    return {k: v for k, v in data.items() if k not in removed}


class RepairSettings(_Model):
    enabled: bool = False
    # One model id per attempt, e.g. ["claude-opus-5-5"] * 3; its length is max_attempts.
    attempt_models: list[str] = []
    effort: Effort | None = None
    prompt_version: str | None = None
    retrieval: Retrieval | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)
    # M6: group one error on one imported name in 3+ files into one task for the file
    # that defines it, repaired first (migrator.repair.shared).
    shared_causes: bool = False
    # M6: a passed patch the free test-fitting flag fires on becomes a hand-off
    # ("possible test-fitting: ..."), its patch set aside like any other hand-off.
    test_fitting_hand_off: bool = False
    # M6 option D: a flagged patch goes to this model (not the repair model) first; it
    # says v5_required (stays migrated, a review note) or fits_old_test (a hand-off).
    reviewer_model: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _removed_fields(cls, data: Any) -> Any:
        return _drop_removed(data, _REMOVED, "repair.")

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
    """Hard caps in USD (Anthropic's prices), enforced per call by the run's ``cost.Budget``."""

    max_run_usd: float = Field(default=DEFAULT_MAX_RUN_USD, gt=0)
    max_month_usd: float = Field(default=DEFAULT_MAX_MONTH_USD, gt=0)
    # Runs must finish (M6): when set, repair starts only if the run can cover its whole
    # worst case, every failing file x max_attempts x this, from what is left of the run
    # and month caps. None (every configuration before M6): no reservation.
    reserve_attempt_usd: float | None = Field(default=None, gt=0)
    # A hard stop per run (M6, the owner's $2): the cost guard refuses any call past it,
    # whatever the run cap and the reservation allow. None: the run cap is the stop.
    stop_run_usd: float | None = Field(default=None, gt=0)


class RulesSettings(_Model):
    # Names of codemod or script rule steps to switch off; everything else runs.
    skip: list[str] = []


class Configuration(_Model):
    schema_version: int = SCHEMA_VERSION
    name: str
    description: str = ""
    # Which model fills each level (M7). Not digested itself: the levels a configuration
    # uses are resolved into the repair settings, which are.
    models: ModelLevels = ModelLevels()
    repair: RepairSettings = RepairSettings()
    cost: CostCaps = CostCaps()
    rules: RulesSettings = RulesSettings()

    # Set by the loader. Not part of the TOML.
    path: Path | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _resolve_levels(self) -> Configuration:
        """Levels become model ids; every model must be in the model table (priced); the
        reviewer must not be a model that repairs."""
        r = self.repair
        try:
            attempts = [self.models.resolve(m) for m in r.attempt_models]
            reviewer = self.models.resolve(r.reviewer_model) if r.reviewer_model else None
        except UnknownModelError as exc:
            raise ValueError(str(exc)) from exc
        if reviewer is not None and reviewer in attempts:
            raise ValueError(
                f"the reviewer ({reviewer}) also repairs; a reviewer must be a different "
                "model from every repair attempt's, so no model reviews its own work"
            )
        update = {"attempt_models": attempts, "reviewer_model": reviewer}
        if any(getattr(r, k) != v for k, v in update.items()):
            # Frozen models: set in place (pydantic wants an after-validator to return self).
            object.__setattr__(self, "repair", r.model_copy(update=update))
        return self

    def models_used(self) -> list[str]:
        """Every model a run of this configuration may call."""
        r = self.repair
        names = [*r.attempt_models, *([r.reviewer_model] if r.reviewer_model else [])]
        return list(dict.fromkeys(names))

    def feature_notes(self) -> list[str]:
        """The features this configuration asks for that a model doesn't declare, which
        the run turns off (one line each, for the run's output and scorecard)."""
        from migrator.repair.reviewer import REVIEW_EFFORT

        r = self.repair
        if not r.enabled:
            return []
        notes: list[str] = []
        for model in r.attempt_models:
            notes += feature_notes(
                "repair", model, effort=r.effort, caching=True, strict_tools=True
            )
        if r.reviewer_model:
            notes += feature_notes(
                "reviewer", r.reviewer_model, effort=REVIEW_EFFORT, structured_output=True
            )
        return list(dict.fromkeys(notes))

    @property
    def uses_llm(self) -> bool:
        return self.repair.enabled

    def digest(self) -> str:
        """A short hash of everything the configuration varies (not its description)."""
        data = self.model_dump(mode="json", exclude={"description", "models"})
        repair = data["repair"]
        for key, off in _DIGEST_OPTIONAL.items():
            if repair.get(key) == off:
                repair.pop(key)
        for key in ("reserve_attempt_usd", "stop_run_usd"):
            if data["cost"].get(key) is None:
                data["cost"].pop(key, None)
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


def ensure_runnable(config: Configuration) -> None:
    """Refuse a configuration this version of the Migrator cannot run faithfully, before
    anything runs (an experiment would otherwise fail run by run)."""
    repair = config.repair
    if repair.enabled:
        from migrator.repair.prompt import UnknownPromptVersionError, load_templates

        try:
            load_templates(repair.prompt_version or "v1")
        except UnknownPromptVersionError as exc:
            raise ConfigurationError(f"configuration {config.name!r}: {exc}") from exc
        missing = missing_packages(config.models_used())
        if missing:
            raise ConfigurationError(
                f"configuration {config.name!r} needs {', '.join(missing)}; install it "
                "(uv add ...) before running"
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
