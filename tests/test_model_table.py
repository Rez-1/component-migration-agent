"""The model table and the three model levels (M7 setup)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from migrator.configuration import Configuration, ConfigurationError, ensure_runnable
from migrator.cost import PRICES, Budget, CostGuard, Ledger, RunCaps, price_for
from migrator.evals.reference import LLMJudge, independent_judge, judge_key
from migrator.migrations import MigrationSpec
from migrator.model_table import (
    ModelLevels,
    UnknownModelError,
    card_for,
    chat_model,
    feature_notes,
    model_table,
    shipped_table,
)
from migrator.repair.model import GuardedModel
from migrator.repair.prompt import load_templates, tool_text
from migrator.repair.tools import RepairTools
from migrator.structured import ask_structured, first_json_object
from tests.fakes import ScriptedChatModel, ai, call

CONFIGS = Path(__file__).resolve().parent.parent / "evals" / "configs"

# A provider outside Claude, declared in the user's own table, with no features.
FAKE_TABLE = """
[[model]]
id = "fakeco:fake-large"
price = { input = 1.0, output = 4.0, cache_read = 0.1 }

[[model]]
id = "fakeco:fake-small"
price = { input = 0.2, output = 0.8, cache_read = 0.02 }
efforts = ["low"]
"""


@pytest.fixture
def fake_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    table = tmp_path / "models.toml"
    table.write_text(FAKE_TABLE, "utf-8")
    monkeypatch.setenv("MIGRATOR_MODELS", str(table))
    return table


def repair(**over: Any) -> dict[str, Any]:
    return {
        "enabled": True,
        "attempt_models": ["strong"],
        "max_attempts": 1,
        "effort": "low",
        "prompt_version": "v3",
        "retrieval": "keyword",
        **over,
    }


# --------------------------------------------------------------------------- prices


def test_every_shipped_model_has_a_price_and_claude_keeps_its_bare_ids() -> None:
    table = shipped_table()
    assert set(table.cards) == {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"}
    for ref, card in table.cards.items():
        assert card.ref == ref and card.provider == "anthropic"
        assert PRICES[ref] is PRICES[card.id]  # by ref and by full id
    # Checked on 2026-11-11: Sonnet 5.5 cache reads are 0.05x input, not the M6 $0.20.
    assert PRICES["claude-sonnet-5-5"].cache_read == 0.10
    assert PRICES["claude-opus-5-5"].cache_write_5m == 5.0
    assert price_for("claude-haiku-5-5", 150_000).input == 0.50  # the long-prompt card


def test_a_model_without_a_price_is_refused_before_anything_runs() -> None:
    with pytest.raises(UnknownModelError, match="no price"):
        card_for("openai:gpt-unknown")
    with pytest.raises(ValueError, match="won't run it"):
        Configuration.model_validate({"name": "x", "models": {"strong": "openai:gpt-unknown"}})
    with pytest.raises(ValueError, match="no price"):
        Configuration.model_validate(
            {"name": "x", "repair": repair(attempt_models=["claude-unknown"])}
        )


# --------------------------------------------------------------------------- levels


def test_levels_resolve_to_models_and_balanced_must_differ_from_strong() -> None:
    levels = ModelLevels()
    assert (levels.strong, levels.balanced, levels.fast) == (
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
    )
    assert levels.resolve("balanced") == "claude-sonnet-5-5"
    assert levels.resolve("anthropic:claude-opus-5-5") == "claude-opus-5-5"
    with pytest.raises(ValueError, match="must be a different model"):
        ModelLevels(balanced="anthropic:claude-opus-5-5")


def test_a_configuration_names_levels_and_digests_like_the_models_it_names() -> None:
    by_level = Configuration.model_validate(
        {
            "name": "x",
            "repair": repair(
                attempt_models=["strong"] * 3, max_attempts=3, reviewer_model="balanced"
            ),
        }
    )
    by_model = Configuration.model_validate(
        {
            "name": "x",
            "repair": repair(
                attempt_models=["claude-opus-5-5"] * 3,
                max_attempts=3,
                reviewer_model="claude-sonnet-5-5",
            ),
        }
    )
    assert by_level.repair.attempt_models == ["claude-opus-5-5"] * 3
    assert by_level.repair.reviewer_model == "claude-sonnet-5-5"
    assert by_level.digest() == by_model.digest()
    assert by_level.feature_notes() == []  # Claude declares everything the run asks for


def test_configurations_written_before_m7_keep_their_digests() -> None:
    from migrator.configuration import load_configuration

    # Computed with the code before the model table (commit b07f4b2).
    assert load_configuration(CONFIGS / "m6-opus-low-v4.toml").digest() == "ac11022ccfaa"


def test_the_reviewer_must_not_be_a_repair_model() -> None:
    with pytest.raises(ValueError, match="reviews its own work"):
        Configuration.model_validate(
            {"name": "x", "repair": repair(attempt_models=["balanced"], reviewer_model="balanced")}
        )


# --------------------------------------------------------------------------- features


def test_another_provider_plugs_in_from_the_users_table(fake_provider: Path) -> None:
    assert "fakeco:fake-large" in model_table().cards
    config = Configuration.model_validate(
        {
            "name": "x",
            "models": {"strong": "fakeco:fake-large", "balanced": "fakeco:fake-small"},
            "repair": repair(effort="medium", reviewer_model="balanced"),
        }
    )
    assert config.repair.attempt_models == ["fakeco:fake-large"]
    notes = config.feature_notes()
    assert notes == [
        "repair on fakeco:fake-large: turned off effort 'medium' (no effort control), which "
        "it doesn't declare",
        "repair on fakeco:fake-large: turned off prompt caching, which it doesn't declare",
        "repair on fakeco:fake-large: turned off strict tool schemas, which it doesn't declare",
        "reviewer on fakeco:fake-small: turned off effort 'medium' (it accepts low), which it "
        "doesn't declare",
        "reviewer on fakeco:fake-small: turned off structured output (its JSON answer is "
        "parsed from text instead), which it doesn't declare",
    ]
    # Its LangChain package isn't installed, so the run is refused before it starts.
    with pytest.raises(ConfigurationError, match="needs langchain-fakeco"):
        ensure_runnable(config)


def test_chat_model_passes_only_declared_features(
    fake_provider: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []

    def fake_init(model: str, **kwargs: Any) -> Any:
        seen.append({"model": model, **kwargs})
        return FakeListChatModel(responses=["x"])

    import langchain.chat_models

    monkeypatch.setattr(langchain.chat_models, "init_chat_model", fake_init)
    chat_model("fakeco:fake-large", "low", 1000)
    chat_model("fakeco:fake-small", "low", 1000)
    chat_model("claude-opus-5-5", "low", 1000)
    assert seen[0] == {
        "model": "fake-large",
        "model_provider": "fakeco",
        "max_tokens": 1000,
        "max_retries": 2,
    }
    assert seen[1]["reasoning_effort"] == "low" and seen[1]["model_provider"] == "fakeco"
    assert seen[2]["model_provider"] == "anthropic" and seen[2]["reasoning_effort"] == "low"


def test_the_repair_agent_binds_no_strict_tools_or_cache_breakpoints_without_them(
    tmp_path: Path, spec: MigrationSpec, fake_provider: Path
) -> None:
    model = ScriptedChatModel(script={"x": [ai(call("run_verify", note="n"))]})
    efforts: list[str | None] = []

    def factory(name: str, effort: str | None, max_tokens: int) -> Any:
        efforts.append(effort)
        return model

    guarded = GuardedModel(
        factory,
        RepairTools(tool_text(load_templates("v1"), spec)).tools,
        effort="low",
        run_id="r",
        case=None,
    )
    _message, record = guarded.call(
        "fakeco:fake-large",
        "system",
        [HumanMessage(content="## Failing file: `x`")],
        budget=Budget("r", RunCaps(run_usd=5, month_usd=20), Ledger(tmp_path / "l.jsonl")),
        file="x",
        attempt=1,
    )
    assert efforts == [None]  # it declares no effort levels
    assert model.bind_kwargs == {}  # no strict=True
    request = model.requests[0]
    assert "cache_control" not in request["kwargs"]
    assert "cache_control" not in request["messages"][0].content[0]
    assert record.requested_model == "fakeco:fake-large"


def test_feature_notes_are_empty_for_what_a_model_declares() -> None:
    assert feature_notes("judge", "claude-sonnet-5-5", effort="low", structured_output=True) == []


# --------------------------------------------------------------------------- structured


def test_without_structured_output_the_json_is_parsed_from_the_text(fake_provider: Path) -> None:
    assert first_json_object('Sure. {"a": {"b": 1}} and {"c": 2}') == {"a": {"b": 1}}
    chat = FakeListChatModel(responses=['Here: {"verdict": "matches", "x": 1}'])
    out = ask_structured(chat, "fakeco:fake-large", {"title": "t", "type": "object"}, "s", "p")
    assert out.parsed == {"verdict": "matches", "x": 1} and out.error is None
    chat = FakeListChatModel(responses=["no json here"])
    out = ask_structured(chat, "fakeco:fake-large", {"title": "t", "type": "object"}, "s", "p")
    assert out.parsed is None and out.error == "no JSON object in the answer"


# --------------------------------------------------------------------------- the judge


def test_the_m6_judge_keeps_its_cache_keys_and_another_judge_gets_its_own() -> None:
    # Computed with the code before the model table (commit b07f4b2): the cached M6
    # judgements (Opus 5.5) stay valid.
    assert judge_key("a.tsx", "old", "ref", "new") == "eaf5000a38d89c01d0b4"
    assert judge_key("a.tsx", "old", "ref", "new", model="claude-sonnet-5-5") != (
        "eaf5000a38d89c01d0b4"
    )


def test_the_judge_is_the_balanced_level_and_never_a_model_that_wrote_the_code() -> None:
    opus = Configuration.model_validate(
        {
            "name": "opus",
            "repair": repair(
                attempt_models=["claude-opus-5-5"], reviewer_model="claude-sonnet-5-5"
            ),
        }
    )
    assert independent_judge("balanced", opus) == "claude-sonnet-5-5"  # the reviewer may judge
    with pytest.raises(ValueError, match="no model judges its own work"):
        independent_judge("claude-opus-5-5", opus)
    assert independent_judge("strong", Configuration(name="baseline")) == "claude-opus-5-5"


def test_the_judge_works_on_any_priced_model_and_is_ledgered(
    tmp_path: Path, fake_provider: Path
) -> None:
    ledger = Ledger(tmp_path / "l.jsonl")
    answer = (
        'Done: {"reference_hunks": [{"id": "R1", "kind": "v5-styling", "what": "font"}], '
        '"verdict": "wrong", "reason": "misses the font size"}'
    )
    judge = LLMJudge(
        "case",
        CostGuard(1, 20, ledger),
        ledger,
        model="fakeco:fake-large",
        factory=lambda *_: FakeListChatModel(responses=[answer]),
    )
    found = judge("prompt", "a.tsx")
    assert found.verdict == "wrong" and found.reference_hunks[0].kind == "v5-styling"
    assert found.model == "fakeco:fake-large"
    [row] = ledger.rows()
    assert row.requested_model == "fakeco:fake-large" and row.run_id == "judge:case"
