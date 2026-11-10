from __future__ import annotations

from pathlib import Path

import pytest

from migrator.configuration import (
    BASELINE,
    Configuration,
    ConfigurationError,
    ensure_runnable,
    find_configuration,
    load_configuration,
)
from migrator.cost import (
    PRICES,
    NoLedgerPreflight,
    PlannedExperiment,
    RunCost,
    UnknownModelPriceError,
    Usage,
    cost_usd,
)
from migrator.migrations import MigrationSpec
from tests.conftest import REPO_ROOT

CONFIGS = REPO_ROOT / "evals" / "configs"


def test_shipped_configurations_load() -> None:
    names = sorted(p.stem for p in CONFIGS.glob("*.toml"))
    assert names == [
        "baseline",
        "cascade-haiku-opus",
        "haiku-advisor-opus",
        "haiku-debug",
        "haiku-high",
        "m6-baseline",
        "m6-opus-low",
        "m6-opus-low-v2",
        "opus-low",
        "opus-low-context",
        "opus-low-imports",
        "opus-low-tools-v2",
        "sonnet-medium",
    ]
    baseline = find_configuration("baseline", CONFIGS)
    assert not baseline.uses_llm
    assert (baseline.cost.max_run_usd, baseline.cost.max_month_usd) == (5.0, 20.0)
    opus = find_configuration("opus-low", CONFIGS)
    assert opus.repair.attempt_models == ["claude-opus-5-5"] * 3
    assert opus.repair.effort == "low"
    for name in names:
        for model in find_configuration(name, CONFIGS).repair.attempt_models:
            assert model in PRICES  # every configured model has a pinned price


def test_the_baseline_file_matches_the_built_in_baseline() -> None:
    assert find_configuration("baseline", CONFIGS).digest() == BASELINE.digest()


def test_repair_configurations_are_runnable_from_m3() -> None:
    for name in ("baseline", "opus-low", "haiku-debug"):
        ensure_runnable(find_configuration(name, CONFIGS))


def test_repair_on_needs_one_model_per_attempt() -> None:
    with pytest.raises(ValueError, match="one model per attempt"):
        Configuration.model_validate(
            {
                "name": "x",
                "repair": {
                    "enabled": True,
                    "attempt_models": ["claude-opus-5-5"],
                    "effort": "low",
                    "prompt_version": "v1",
                    "retrieval": "keyword",
                    "max_attempts": 3,
                },
            }
        )
    with pytest.raises(ValueError, match="effort"):
        Configuration.model_validate({"name": "x", "repair": {"enabled": True}})


def test_caps_must_be_positive_numbers() -> None:
    with pytest.raises(ValueError):
        Configuration.model_validate({"name": "x", "cost": {"max_run_usd": 0}})


def test_name_must_match_the_file(tmp_path: Path) -> None:
    path = tmp_path / "other.toml"
    path.write_text('name = "baseline"\n')
    with pytest.raises(ConfigurationError, match="must match"):
        load_configuration(path)
    with pytest.raises(ConfigurationError, match="no configuration 'nope'"):
        find_configuration("nope", CONFIGS)


def test_skipping_rules(spec: MigrationSpec) -> None:
    config = Configuration.model_validate({"name": "x", "rules": {"skip": ["box-sx-prop"]}})
    names = [s.name for s in config.apply_to(spec).rule_steps]
    assert "box-sx-prop" not in names
    assert len(names) == len(spec.rule_steps) - 1
    assert config.digest() != BASELINE.digest()


def test_the_dependency_bump_cannot_be_switched_off(spec: MigrationSpec) -> None:
    # Without it a run is not a migration, and would verify clean migrating nothing.
    for step in ("dependencies", "install", "nope"):
        config = Configuration.model_validate({"name": "x", "rules": {"skip": [step]}})
        with pytest.raises(ConfigurationError, match="not a codemod or script"):
            config.apply_to(spec)


def test_digest_ignores_the_description() -> None:
    a = Configuration(name="baseline", description="one")
    assert a.digest() == a.model_copy(update={"description": "two"}).digest()


# --------------------------------------------------------------------------- cost


def test_cost_from_tokens_and_the_pinned_table() -> None:
    usage = Usage(
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_read_input_tokens=2_000_000,
        cache_creation_input_tokens=100_000,
    )
    # 4.00 + 2.00 + 0.40 + 0.50 (5-minute writes at 1.25x input)
    assert cost_usd("claude-opus-5-5", usage) == pytest.approx(6.90)
    # Haiku 5.5 has a second rate card for prompts over 100K tokens ($0.50 / $2.50).
    assert cost_usd("claude-haiku-5-5", usage) == pytest.approx(0.5 + 0.25 + 0.1 + 0.0625)
    small = Usage(input_tokens=10_000, output_tokens=1_000, cache_read_input_tokens=50_000)
    assert cost_usd("claude-haiku-5-5", small) == pytest.approx(0.001 + 0.0005 + 0.0005)
    with pytest.raises(UnknownModelPriceError):
        cost_usd("gpt-5", usage)


def test_no_llm_run_cost_is_zero_with_caps() -> None:
    cost = RunCost.no_llm(5.0, 20.0)
    assert (cost.total_usd, cost.model_calls, cost.cache_read_share) == (0.0, 0, None)
    assert (cost.run_cap_usd, cost.month_cap_usd) == (5.0, 20.0)


def test_preflight_passes_rules_only_and_refuses_llm_runs() -> None:
    check = NoLedgerPreflight().check
    ok = check(PlannedExperiment(configuration="b", uses_llm=False, runs=2, max_cost_usd=None))
    assert ok.ok and ok.estimated_usd == 0.0
    no_cap = check(PlannedExperiment(configuration="o", uses_llm=True, runs=2, max_cost_usd=None))
    assert not no_cap.ok and "--max-cost" in no_cap.reason
    capped = check(PlannedExperiment(configuration="o", uses_llm=True, runs=2, max_cost_usd=9))
    assert not capped.ok and "ledger" in capped.reason
