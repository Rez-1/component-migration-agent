"""The held-out fixture's Baseline and oracle, for real (``pytest -m slow``).

Node, npm and network, no LLM. The Baseline must match the committed scorecard in
docs/results/baseline-holdout/; the oracle replays ``evals/cases/fixture-mui4-holdout/
reference/`` with a scripted model through the whole graph, as tests/test_oracle_slow.py
does for fixture-mui4: all 6 agent traps Expected, the human trap handed off, a clean
run, and with the human fix at Review no failure at all.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from langchain_core.messages import AIMessage

from migrator.config import load_case
from migrator.cost import Ledger
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunOptions, RunResult, dry_run, start_run
from migrator.repair.records import ReviewAnswer
from migrator.review import ReviewPayload
from migrator.scoring import stable_view
from tests.conftest import REPO_ROOT
from tests.fakes import ScriptedChatModel, ai, call, factory_for
from tests.test_graph import configuration
from tests.test_holdout import HOLDOUT, HOLDOUT_CASE

REFERENCE = HOLDOUT_CASE / "reference"
HANDED_OFF = "src/screens/ShipmentTracker.tsx"
EXPECTED = REPO_ROOT / "docs" / "results" / "baseline-holdout" / "scorecard.json"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("npm") is None, reason="needs Node and npm"),
]


def options(tmp_path: Path, spec: MigrationSpec, **kw: Any) -> RunOptions:
    return RunOptions.model_validate(
        {
            "repo": HOLDOUT,
            "spec": spec,
            "run_dir": tmp_path / "run",
            "case": load_case(HOLDOUT_CASE / "case.toml"),
            **kw,
        }
    )


def test_baseline_dry_run_on_the_holdout_fixture(tmp_path: Path, spec: MigrationSpec) -> None:
    card = dry_run(options(tmp_path, spec)).scorecard
    assert card.status == "completed"
    assert card.precheck.status == "ok"
    assert card.precheck.pre_existing_failures == []
    assert card.rules is not None
    assert len([f for f in card.rules.changed_files if f.startswith("src/")]) == 9

    assert card.verify is not None
    failures = card.verify.failures
    type_errors = [f for f in failures if f.source == "typecheck"]
    assert (len(type_errors), len({f.file for f in type_errors})) == (9, 6)
    assert [f for f in failures if f.source == "lint"] == []
    totals = card.verify.test_totals
    assert totals is not None
    assert (totals.tests_total, totals.tests_failed, totals.suites_failed) == (15, 7, 5)

    h = card.headline
    assert (h.failures, h.failing_files, h.codemod_todos) == (16, 7, 1)
    migrated = sorted(f.path for f in card.files if f.outcome == "Migrated by rules")
    assert migrated == ["src/App.tsx", "src/theme.ts"]

    assert card.traps is not None
    by_layer: dict[str, set[str]] = {}
    for trap in card.traps:
        by_layer.setdefault(trap.expected_layer, set()).add(trap.result)
    assert by_layer == {
        "rules": {"Expected"},
        "agent": {"Missed"},
        "human": {"Missed"},
        "visual-only": {"Not scored"},
    }
    for trap in card.traps:
        if trap.expected_layer in ("agent", "human"):
            assert all(c.fired for c in trap.checks), f"{trap.id}: a listed check stayed quiet"
    assert card.cheating is not None and card.cheating.hits == []
    assert card.cost.total_usd == 0.0

    expected = json.loads(EXPECTED.read_text("utf-8"))
    assert stable_view(card) == stable_view(expected)


def oracle_script() -> dict[str, list[AIMessage]]:
    fixes = yaml.safe_load((REFERENCE / "agent-fixes.yaml").read_text())
    script: dict[str, list[AIMessage]] = {}
    for entry in fixes["files"]:
        edits = [
            call("apply_edit", path=e["path"], old_text=e["old"], new_text=e["new"])
            for e in entry["edits"]
        ]
        script[entry["path"]] = [ai(*edits, call("run_verify", note=entry["note"]))]
    script[HANDED_OFF] = [
        ai(
            call(
                "hand_off",
                reason="the test selects step icons by v4 class names; only the test can change",
            )
        )
    ]
    return script


def test_the_holdout_reference_fixes_score_every_agent_trap_expected(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    script = oracle_script()
    model = ScriptedChatModel(script=script)
    card = dry_run(
        options(tmp_path, spec, configuration=configuration()),
        model_factory=factory_for(model),
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    ).scorecard
    assert card.status == "completed"
    assert card.repair is not None
    assert sorted(r.path for r in card.repair.files) == sorted(script)
    for record in card.repair.files:
        assert record.edits_rejected == {}, record.path
        if record.path != HANDED_OFF:
            assert record.outcome == "Migrated by agent", (record.path, record.reason)
            assert [a.result for a in record.attempts] == ["passed"], record.path

    assert card.traps is not None
    assert {(t.expected_layer, t.result) for t in card.traps} == {
        ("rules", "Expected"),
        ("agent", "Expected"),
        ("human", "Expected"),
        ("visual-only", "Not scored"),
    }
    h = card.headline
    assert h.traps is not None and (h.traps.expected, h.traps.missed) == (15, 0)
    assert h.clean_run
    assert {f.file for f in card.verify.failures} == {HANDED_OFF}  # type: ignore[union-attr]
    assert (h.hand_offs, h.regressions, h.cheating_check_hits) == (1, 0, 0)
    assert (h.outcomes["Migrated by rules"], h.outcomes["Migrated by agent"]) == (2, 6)
    assert (h.migrated_without_human.count, h.migrated_without_human.total) == (8, 9)
    assert card.cost.model_calls == len(script)


def test_the_holdout_human_fix_at_review_leaves_no_failure(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    human = yaml.safe_load((REFERENCE / "human-fix.yaml").read_text())

    class HumanEditor:
        def review(self, payload: ReviewPayload) -> ReviewAnswer:
            assert payload.path == human["handed_off"]
            for e in human["edits"]:
                path = Path(payload.workspace) / e["path"]
                text = path.read_text()
                assert text.count(e["old"]) == 1
                path.write_text(text.replace(e["old"], e["new"]))
            return ReviewAnswer(choice="edit")

    result = start_run(
        options(tmp_path, spec, mode="cli", configuration=configuration()),
        model_factory=factory_for(ScriptedChatModel(script=oracle_script())),
        reviewer=HumanEditor(),
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    assert isinstance(result, RunResult)
    card = result.scorecard
    assert card.verify is not None and card.verify.failures == []
    assert card.headline.clean_run
    assert card.headline.outcomes["Migrated by human"] == 1
    assert card.cheating is not None and card.cheating.hits == []
    test_file = "src/screens/__tests__/ShipmentTracker.test.tsx"
    assert any(n.file == test_file and n.layer == "human" for n in card.cheating.notes)
    assert card.headline.traps is not None and card.headline.traps.expected == 15
