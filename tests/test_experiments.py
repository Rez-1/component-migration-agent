"""M5's candidate configurations, on the fake model: per-attempt effort (a cascade), cost
per model, the cascade's cost cap and pre-flight and the advisor tool's accounting. No test calls
a real model."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from migrator.configuration import (
    AdvisorSettings,
    Configuration,
    ConfigurationError,
    ensure_runnable,
    find_configuration,
)
from migrator.cost import (
    PRICES,
    Budget,
    CallRecord,
    Ledger,
    LedgerPreflight,
    LedgerRow,
    PlannedExperiment,
    RunCaps,
    RunCost,
    Usage,
    cost_usd,
    now_utc,
    run_cost,
    split_iterations,
    worst_case_usd,
)
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunOptions, start_run
from migrator.repair.model import GuardedModel, advisor_tool, price_message
from migrator.repair.prompt import PROMPTS_DIR, load_templates
from migrator.report import render_scorecard
from tests.conftest import REPO_ROOT, FakeRunner
from tests.fakes import FakeToolchain, ScriptedChatModel, ai, call, make_mini_repo
from tests.test_graph import CARD, DASH, GOOD, THEME, card_of, configuration

CONFIGS = REPO_ROOT / "evals" / "configs"

# --------------------------------------------------------------------------- configurations


def test_configurations_written_before_m5_keep_their_digests() -> None:
    """New fields are left out of the digest while unset, so M2-M4 results stay
    resumable and comparable."""
    assert find_configuration("baseline", CONFIGS).digest() == "73a3262d088d"
    assert find_configuration("opus-low", CONFIGS).digest() == "d81d48a907d0"


CANDIDATES = (
    "haiku-high",
    "sonnet-medium",
    "cascade-haiku-opus",
    "haiku-advisor-opus",
)


def test_every_candidate_is_one_configuration_with_its_own_digest() -> None:
    digests = {find_configuration(n, CONFIGS).digest() for n in ("opus-low", *CANDIDATES)}
    assert len(digests) == len(CANDIDATES) + 1
    for name in CANDIDATES:
        config = find_configuration(name, CONFIGS)
        assert config.uses_llm
        for model in config.repair.attempt_models:
            assert model in PRICES
        if config.repair.advisor:
            assert config.repair.advisor.model in PRICES
        load_templates(config.repair.prompt_version or "v1")


def test_a_cascade_names_a_model_and_an_effort_per_attempt() -> None:
    cascade = find_configuration("cascade-haiku-opus", CONFIGS)
    repair = cascade.repair
    assert repair.attempt_models == ["claude-haiku-5-5", "claude-opus-5-5", "claude-opus-5-5"]
    assert [repair.effort_for(i) for i in (1, 2, 3)] == ["high", "low", "low"]
    assert find_configuration("opus-low", CONFIGS).repair.effort_for(2) == "low"
    data: dict[str, Any] = {
        "name": "x",
        "repair": {
            "enabled": True,
            "attempt_models": ["claude-opus-5-5"] * 3,
            "attempt_efforts": ["low", "low"],
            "effort": "low",
            "prompt_version": "v1",
            "retrieval": "keyword",
        },
    }
    with pytest.raises(ValueError, match="one effort per attempt"):
        Configuration.model_validate(data)
    with pytest.raises(ValueError, match="repair is off"):
        Configuration.model_validate(
            {"name": "x", "repair": {"enabled": False, "advisor": {"model": "claude-opus-5-5"}}}
        )


def test_prompt_versions_are_frozen() -> None:
    """A wording change must be a new prompt version: v1's files (the prompt of every
    M3/M4 result) are pinned by digest, and v1-advisor differs only as stated."""
    folder = PROMPTS_DIR / "v1"
    blob = b"".join(p.name.encode() + p.read_bytes() for p in sorted(folder.iterdir()))
    assert hashlib.sha256(blob).hexdigest()[:12] == "e1749bdb2941"
    advisor = load_templates("v1-advisor")
    assert "advisor" in advisor.system and advisor.tools == load_templates("v1").tools


# --------------------------------------------------------------------------- cascade


class RecordingFactory:
    """A model factory that records the (model, effort) of every model it builds."""

    def __init__(self, model: ScriptedChatModel):
        self.model = model
        self.built: list[tuple[str, str | None]] = []

    def __call__(self, model_id: str, effort: str | None, max_tokens: int) -> BaseChatModel:
        self.built.append((model_id, effort))
        self.model.model_id = model_id
        return self.model


def cascade_config(**cost: float) -> Configuration:
    return Configuration.model_validate(
        {
            "name": "cascade",
            "repair": {
                "enabled": True,
                "attempt_models": ["claude-haiku-5-5", "claude-opus-5-5", "claude-opus-5-5"],
                "attempt_efforts": ["high", "low", "low"],
                "effort": "low",
                "prompt_version": "v1",
                "retrieval": "keyword",
                "max_attempts": 3,
            },
            "cost": cost,
        }
    )


def run_with(
    tmp_path: Path,
    spec: MigrationSpec,
    script: dict[str, list[AIMessage]],
    config: Configuration,
    *,
    max_run_usd: float | None = None,
) -> tuple[Any, ScriptedChatModel, RecordingFactory]:
    repo = tmp_path / "repo"
    make_mini_repo(repo)
    model = ScriptedChatModel(script=script)
    factory = RecordingFactory(model)
    result = start_run(
        RunOptions.model_validate(
            {
                "repo": repo,
                "spec": spec,
                "run_dir": tmp_path / "run",
                "configuration": config,
                "tools_cache": tmp_path / "cache",
                "run_id": "r1",
                "max_run_usd": max_run_usd,
                "mode": "eval",
            }
        ),
        FakeRunner(FakeToolchain()),
        model_factory=factory,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    return result, model, factory


def test_a_cascade_escalates_model_and_effort_and_costs_each_model(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    miss = ai(call("run_verify", note="first try"), model="claude-haiku-5-5")
    script = {**GOOD, DASH: [miss, *GOOD[DASH]]}
    # GOOD's other replies say they came from Opus; attempt 1 of THEME and CARD is Haiku.
    script[THEME] = [m.model_copy(update={"response_metadata": {**m.response_metadata,
                     "model_name": "claude-haiku-5-5"}}) for m in GOOD[THEME]]  # fmt: skip
    script[CARD] = [m.model_copy(update={"response_metadata": {**m.response_metadata,
                    "model_name": "claude-haiku-5-5"}}) for m in GOOD[CARD]]  # fmt: skip
    result, _, factory = run_with(tmp_path, spec, script, cascade_config())
    card = card_of(result)
    assert ("claude-haiku-5-5", "high") in factory.built
    assert ("claude-opus-5-5", "low") in factory.built
    record = next(f for f in card.repair.files if f.path == DASH)
    assert [a.model for a in record.attempts] == ["claude-haiku-5-5", "claude-opus-5-5"]
    by_model = {m.model: m for m in card.cost.by_model}
    assert set(by_model) == {"claude-haiku-5-5", "claude-opus-5-5"}
    assert by_model["claude-opus-5-5"].calls == len(GOOD[DASH])
    assert round(sum(m.cost_usd for m in card.cost.by_model), 6) == card.cost.total_usd
    assert "claude-haiku-5-5 $" in render_scorecard(card)  # the scorecard shows each model


def test_the_cascade_cap_prices_each_attempt_at_its_own_model(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    """A cap that covers Haiku's worst case but not Opus's: attempt 1 is sent, the
    escalation to Opus is refused before it is sent."""
    miss = ai(call("run_verify", note="first try"), model="claude-haiku-5-5")
    script = {DASH: [miss, *GOOD[DASH]], THEME: [], CARD: []}
    haiku_worst = worst_case_usd("claude-haiku-5-5", 20_000, 16_000)
    opus_worst = worst_case_usd("claude-opus-5-5", 1_000, 16_000)
    cap = 0.1
    assert haiku_worst * 3 < cap < opus_worst
    result, _, _ = run_with(tmp_path, spec, script, cascade_config(), max_run_usd=cap)
    card = card_of(result)
    record = next(f for f in card.repair.files if f.path == DASH)
    assert [a.model for a in record.attempts] == ["claude-haiku-5-5", "claude-opus-5-5"]
    assert record.attempts[-1].result == "cost_cap"
    assert "claude-opus-5-5" in (record.reason or "")
    assert card.cost.stopped_by_cap and card.cost.total_usd <= cap


def test_a_run_without_model_calls_serialises_as_before() -> None:
    data = RunCost.no_llm(5, 20).model_dump(mode="json")
    assert "by_model" not in data
    calls = [
        CallRecord(
            model="claude-opus-5-5",
            requested_model="claude-opus-5-5",
            usage=Usage(output_tokens=100),
            cost_usd=cost_usd("claude-opus-5-5", Usage(output_tokens=100)),
        )
    ]
    assert run_cost(calls, 5, 20).model_dump(mode="json")["by_model"] == [
        {"model": "claude-opus-5-5", "calls": 1, "cost_usd": 0.002}
    ]


def test_preflight_prices_a_cascade_per_attempt(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")

    def row(run: str, file: str, attempt: int, model: str, usd: float) -> None:
        ledger.append(
            LedgerRow(
                at=now_utc(),
                run_id=run,
                file=file,
                attempt=attempt,
                model=model,
                requested_model=model,
                usage=Usage(),
                cost_usd=usd,
            )
        )

    for i in range(8):  # one run: 8 first attempts on Haiku, 2 second attempts on Opus
        row("h", f"f{i}", 1, "claude-haiku-5-5", 0.002)
    for i in range(6):
        row("o", f"g{i}", 1, "claude-opus-5-5", 0.02)
    row("h", "f0", 2, "claude-opus-5-5", 0.02)
    row("h", "f1", 2, "claude-opus-5-5", 0.02)
    plan = PlannedExperiment(
        configuration="cascade",
        uses_llm=True,
        runs=2,
        max_cost_usd=5,
        attempt_models=["claude-haiku-5-5", "claude-opus-5-5", "claude-opus-5-5"],
    )
    estimate, how = LedgerPreflight(ledger).estimate(plan)
    # 2 runs in the ledger: 14 first attempts and 2 second ones -> 7 and 1 per run.
    assert estimate == pytest.approx(2 * (7 * 0.002 + 1 * 0.02))
    assert "attempt 1 claude-haiku-5-5" in how and "attempt 2 claude-opus-5-5" in how


def test_preflight_scales_a_model_it_has_not_seen(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    for i in range(10):
        ledger.append(
            LedgerRow(
                at=now_utc(),
                run_id="o",
                file=f"f{i}",
                attempt=1,
                model="claude-opus-5-5",
                requested_model="claude-opus-5-5",
                usage=Usage(),
                cost_usd=0.02,
            )
        )
    plan = PlannedExperiment(
        configuration="sonnet",
        uses_llm=True,
        runs=2,
        max_cost_usd=5,
        attempt_models=["claude-sonnet-5-5"] * 3,
    )
    estimate, how = LedgerPreflight(ledger).estimate(plan)
    assert estimate == pytest.approx(2 * 10 * 0.01)  # Sonnet's output is half Opus's price
    assert "scaled from 10 attempts on claude-opus-5-5" in how
    advised = plan.model_copy(update={"advisor_model": "claude-opus-5-5"})
    with_advice, why = LedgerPreflight(ledger).estimate_with_advisor(advised)
    assert with_advice > estimate and "advisor claude-opus-5-5" in why


# --------------------------------------------------------------------------- advisor

ADVISOR = AdvisorSettings(model="claude-opus-5-5", max_uses=2, max_tokens=4000)


def advised_reply() -> AIMessage:
    reply = ai(call("run_verify", note="done"), model="claude-haiku-5-5", output_tokens=300)
    reply.response_metadata["usage"] = {
        "input_tokens": 1000,
        "output_tokens": 300,
        "iterations": [
            {"type": "message", "input_tokens": 600, "output_tokens": 100,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            {"type": "advisor_message", "model": "claude-opus-5-5", "input_tokens": 2000,
             "output_tokens": 500, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": 0},
            {"type": "message", "input_tokens": 400, "output_tokens": 200,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        ],
    }  # fmt: skip
    return reply


def test_advisor_tokens_are_priced_at_the_advisor_model() -> None:
    reply = advised_reply()
    split = split_iterations(reply.response_metadata)
    assert split is not None and split.executor == Usage(input_tokens=1000, output_tokens=300)
    priced = price_message(reply, "claude-haiku-5-5")
    advice = Usage(input_tokens=2000, output_tokens=500)
    assert priced.advisor_model == "claude-opus-5-5" and priced.advisor_calls == 1
    assert priced.advisor_cost_usd == cost_usd("claude-opus-5-5", advice)
    assert priced.cost_usd == pytest.approx(
        cost_usd("claude-haiku-5-5", priced.usage) + priced.advisor_cost_usd
    )
    assert split_iterations(ai(call("run_verify", note="x")).response_metadata) is None


def test_the_advisor_is_bound_and_its_worst_case_is_capped(tmp_path: Path) -> None:
    model = ScriptedChatModel(script={"?": [advised_reply()]})
    budget = Budget("r", RunCaps(run_usd=5, month_usd=20), Ledger(tmp_path / "ledger.jsonl"))
    guarded = GuardedModel(
        lambda m, e, t: model, [], effort="high", run_id="r", case=None, advisor=ADVISOR
    )
    worst = guarded.advisor_worst_usd(10_000)
    assert worst == pytest.approx(2 * worst_case_usd("claude-opus-5-5", 26_000, 4000))
    _message, record = guarded.call(
        "claude-haiku-5-5", "system", [], budget=budget, file="a.ts", attempt=1
    )
    assert advisor_tool(ADVISOR) in model._bound_tools
    assert record.advisor_calls == 1 and record.advisor_model == "claude-opus-5-5"
    rows = budget.ledger.rows()
    assert [r.model for r in rows] == ["claude-haiku-5-5", "claude-opus-5-5"]
    assert round(sum(r.cost_usd for r in rows), 6) == record.cost_usd
    cost = run_cost([record], 5, 20)
    assert {m.model for m in cost.by_model} == {"claude-haiku-5-5", "claude-opus-5-5"}
    assert cost.total_usd == pytest.approx(record.cost_usd)
    tight = Budget("r", RunCaps(run_usd=0.2, month_usd=20), Ledger(tmp_path / "other.jsonl"))
    from migrator.cost import CostCapError

    with pytest.raises(CostCapError):  # Haiku alone would fit; with two consultations not
        guarded.call("claude-haiku-5-5", "s", [], budget=tight, file=None, attempt=1)


def test_the_advisor_needs_its_prompt_and_its_prompt_needs_the_advisor(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    """Refused before anything runs: a run, and an experiment (``ensure_runnable``)."""
    advised = find_configuration("haiku-advisor-opus", CONFIGS)
    ensure_runnable(advised)
    wrong = advised.model_copy(
        update={"repair": advised.repair.model_copy(update={"prompt_version": "v1"})}
    )
    with pytest.raises(ConfigurationError, match="v1-advisor"):
        run_with(tmp_path / "a", spec, {}, wrong)
    with pytest.raises(ConfigurationError, match="needs \\[repair"):
        ensure_runnable(plain_config(prompt_version="v1-advisor"))
    unpriced = advised.model_copy(
        update={
            "repair": advised.repair.model_copy(
                update={"advisor": AdvisorSettings(model="claude-unknown")}
            )
        }
    )
    # M7: refused when the run's options are validated, before anything runs.
    with pytest.raises(ValueError, match="no price"):
        run_with(tmp_path / "b", spec, {}, unpriced)


def plain_config(**repair: Any) -> Configuration:
    base = configuration()
    return base.model_copy(update={"repair": base.repair.model_copy(update=repair)})
