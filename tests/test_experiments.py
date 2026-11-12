"""M5's candidate configurations, on the fake model: a cascade (a model per attempt), cost
per model, and the cascade's cost cap and pre-flight. No test calls a real model. (M5's
per-attempt efforts and advisor tool were removed after 0eddf6e.)"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from migrator.configuration import (
    Configuration,
    find_configuration,
)
from migrator.cost import (
    PRICES,
    CallRecord,
    Ledger,
    LedgerPreflight,
    LedgerRow,
    PlannedExperiment,
    RunCost,
    Usage,
    cost_usd,
    now_utc,
    run_cost,
    worst_case_usd,
)
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunOptions, start_run
from migrator.repair.prompt import PROMPTS_DIR, load_templates
from migrator.report import render_scorecard
from tests.conftest import REPO_ROOT, FakeRunner
from tests.fakes import FakeToolchain, ScriptedChatModel, ai, call, make_mini_repo
from tests.test_graph import CARD, DASH, GOOD, THEME, card_of

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
)


def test_every_candidate_is_one_configuration_with_its_own_digest() -> None:
    digests = {find_configuration(n, CONFIGS).digest() for n in ("opus-low", *CANDIDATES)}
    assert len(digests) == len(CANDIDATES) + 1
    for name in CANDIDATES:
        config = find_configuration(name, CONFIGS)
        assert config.uses_llm
        for model in config.repair.attempt_models:
            assert model in PRICES
        load_templates(config.repair.prompt_version or "v1")


def test_prompt_versions_are_frozen() -> None:
    """A wording change must be a new prompt version: v1's files (the prompt of every
    M3/M4 result) are pinned by digest."""
    folder = PROMPTS_DIR / "v1"
    blob = b"".join(p.name.encode() + p.read_bytes() for p in sorted(folder.iterdir()))
    assert hashlib.sha256(blob).hexdigest()[:12] == "e1749bdb2941"


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
    """Attempt 1 on Haiku, the escalation on Opus, each costed at its own model. (The
    name predates the removal of per-attempt effort; kept so its recorded command lines
    stay checked.)"""
    miss = ai(call("run_verify", note="first try"), model="claude-haiku-5-5")
    script = {**GOOD, DASH: [miss, *GOOD[DASH]]}
    # GOOD's other replies say they came from Opus; attempt 1 of THEME and CARD is Haiku.
    script[THEME] = [m.model_copy(update={"response_metadata": {**m.response_metadata,
                     "model_name": "claude-haiku-5-5"}}) for m in GOOD[THEME]]  # fmt: skip
    script[CARD] = [m.model_copy(update={"response_metadata": {**m.response_metadata,
                    "model_name": "claude-haiku-5-5"}}) for m in GOOD[CARD]]  # fmt: skip
    result, _, factory = run_with(tmp_path, spec, script, cascade_config())
    card = card_of(result)
    assert ("claude-haiku-5-5", "low") in factory.built
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
