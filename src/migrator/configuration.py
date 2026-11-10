"""Configurations: everything an experiment varies, one TOML file each.

A configuration names the model per attempt, effort, repair prompt version, retrieval
mode, max attempts, cost caps and which rules are on. The Baseline is the
configuration with repair turned off. Configurations live in ``evals/configs/`` and are
also what a normal run is configured by (its caps and models).

From M3 a configuration with repair on runs the repair agent with the models it
names, one per attempt. ``ensure_runnable`` still guards the M2 refusal path.
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
# keyword: BM25 over the guide (M3). keyword-imports: the same, plus a boost for the
# guide sections of the components the failing file uses, and less weight on sections
# about components it doesn't (M5). keyword-context: keyword-imports, plus the JSX props
# around the failing lines in the query (M5). embeddings: reserved for a later
# experiment; refused at run time (see experiments.md).
Retrieval = Literal["keyword", "keyword-imports", "keyword-context", "embeddings"]

# Fields added after configurations were first digested (M5). They are left out of the
# digest while they hold their "off" value, so every configuration written before them
# keeps its digest and its experiments stay resumable and comparable.
_DIGEST_OPTIONAL = {
    "attempt_efforts": None,
    "advisor": None,
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


class AdvisorSettings(_Model):
    """The advisor tool (``advisor_20260301``): the attempt's model may consult ``model``.

    ``max_uses`` and ``max_tokens`` bound each request's consultations, so the cost cap
    can price a call's worst case including its advice."""

    model: str
    max_uses: int = Field(default=2, ge=1, le=10)
    max_tokens: int = Field(default=4000, ge=256, le=32000)


class RepairSettings(_Model):
    enabled: bool = False
    # One model id per attempt, e.g. ["claude-opus-5-5"] * 3; its length is max_attempts.
    attempt_models: list[str] = []
    effort: Effort | None = None
    prompt_version: str | None = None
    retrieval: Retrieval | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)
    # One effort per attempt, e.g. ["high", "low", "low"] for a Haiku -> Opus cascade;
    # None means ``effort`` for every attempt.
    attempt_efforts: list[Effort] | None = None
    # The advisor tool (a stronger model the attempt's model may consult), or None.
    advisor: AdvisorSettings | None = None
    # M6: group one error on one imported name in 3+ files into one task for the file
    # that defines it, repaired first (migrator.repair.shared).
    shared_causes: bool = False
    # M6: a passed patch the free test-fitting flag fires on becomes a hand-off
    # ("possible test-fitting: ..."), its patch set aside like any other hand-off.
    test_fitting_hand_off: bool = False
    # M6 option D: a flagged patch goes to this model (not the repair model) first; it
    # says v5_required (stays migrated, a review note) or fits_old_test (a hand-off).
    reviewer_model: str | None = None

    def effort_for(self, attempt: int) -> Effort | None:
        """The effort of attempt ``attempt`` (1-based; past the list, the last one)."""
        if self.attempt_efforts:
            return self.attempt_efforts[min(attempt, len(self.attempt_efforts)) - 1]
        return self.effort

    @model_validator(mode="after")
    def _complete_when_on(self) -> RepairSettings:
        if not self.enabled:
            if self.attempt_models:
                raise ValueError("repair is off, so attempt_models must be empty")
            if self.attempt_efforts or self.advisor:
                raise ValueError("repair is off, so attempt_efforts and advisor must be unset")
            return self
        if self.attempt_efforts is not None and len(self.attempt_efforts) != self.max_attempts:
            raise ValueError(
                f"attempt_efforts has {len(self.attempt_efforts)} entries; it needs one "
                f"effort per attempt ({self.max_attempts})"
            )
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
    """Hard caps in USD (Anthropic's prices), enforced per call by ``cost.CostGuard``."""

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


class NeedsRepairLoopError(ConfigurationError):
    """The configuration turns repair on, which needs the repair loop (M3)."""


# The repair loop exists from M3.
REPAIR_LOOP_AVAILABLE = True


def ensure_runnable(config: Configuration) -> None:
    """Refuse a configuration this version of the Migrator cannot run faithfully, before
    anything runs (an experiment would otherwise fail run by run)."""
    repair = config.repair
    if repair.enabled:
        from migrator.repair.prompt import UnknownPromptVersionError, load_templates

        if repair.retrieval == "embeddings":
            raise ConfigurationError(
                f"configuration {config.name!r}: retrieval 'embeddings' is not built (it "
                "needs a local embedding model or a paid API; see experiments.md)"
            )
        try:
            templates = load_templates(repair.prompt_version or "v1")
        except UnknownPromptVersionError as exc:
            raise ConfigurationError(f"configuration {config.name!r}: {exc}") from exc
        if bool(repair.advisor) != templates.options.get("advisor_note", False):
            raise ConfigurationError(
                f"configuration {config.name!r}: an advisor needs prompt 'v1-advisor', and "
                "that prompt needs [repair.advisor]"
            )
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
