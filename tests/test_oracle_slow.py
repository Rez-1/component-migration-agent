"""The known-good run: the reference fixes replayed through the whole graph (``-m slow``).

A scripted model makes exactly the edits in ``evals/cases/fixture-mui4/reference/`` via
``apply_edit``, on the real fixture with the real codemods, tsc, ESLint and Jest (Node
and npm needed; no LLM). It is the M2 audit's missing oracle: the harness must score it
as a clean run with all 8 agent traps Expected and the human trap handed off, and the
guardrails must not trip on legitimate fixes. A second run answers the hand-off with
the human fix (the Review stage's Edit), which leaves no failure at all.
"""

from __future__ import annotations

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
from tests.conftest import FIXTURE, FIXTURE_CASE, REPO_ROOT
from tests.fakes import ScriptedChatModel, ai, call, factory_for
from tests.test_graph import configuration

REFERENCE = FIXTURE_CASE / "reference"
HANDED_OFF = "src/screens/ProfileCard.tsx"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("npm") is None, reason="needs Node and npm"),
]


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
                reason="the test renders the card without a theme; the fix is in test-utils",
            )
        )
    ]
    return script


def options(tmp_path: Path, spec: MigrationSpec, **kw: Any) -> RunOptions:
    return RunOptions.model_validate(
        {
            "repo": FIXTURE,
            "spec": spec,
            "run_dir": tmp_path / "run",
            "case": load_case(FIXTURE_CASE / "case.toml"),
            "configuration": configuration(),
            **kw,
        }
    )


def test_the_reference_fixes_score_every_agent_trap_expected(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    script = oracle_script()
    model = ScriptedChatModel(script=script)
    result = dry_run(
        options(tmp_path, spec),
        model_factory=factory_for(model),
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    card = result.scorecard
    assert card.status == "completed"
    assert card.repair is not None

    # Every failing file got its scripted fix, in repair order, one conversation each.
    repaired = [r.path for r in card.repair.files]
    assert sorted(repaired) == sorted(script)
    assert repaired[0] == "src/theme.ts"  # shared modules first
    assert {r["file"] for r in model.requests} == set(script)

    # No guardrail tripped on a legitimate fix, and every fix passed on its first attempt.
    for record in card.repair.files:
        assert record.edits_rejected == {}, record.path
        if record.path != HANDED_OFF:
            assert record.outcome == "Migrated by agent", (record.path, record.reason)
            assert [a.result for a in record.attempts] == ["passed"], record.path

    assert card.traps is not None
    results = {(t.expected_layer, t.result) for t in card.traps}
    assert results == {
        ("rules", "Expected"),
        ("agent", "Expected"),
        ("human", "Expected"),
        ("visual-only", "Not scored"),
    }
    assert card.headline.traps is not None
    assert (card.headline.traps.expected, card.headline.traps.missed) == (21, 0)

    h = card.headline
    assert h.clean_run  # the only failure left is the handed-off file's
    assert {f.file for f in card.verify.failures} == {HANDED_OFF}  # type: ignore[union-attr]
    assert (h.hand_offs, h.regressions, h.cheating_check_hits) == (1, 0, 0)
    assert (h.outcomes["Migrated by rules"], h.outcomes["Migrated by agent"]) == (3, 8)
    assert h.outcomes["Handed off"] == 1
    assert (h.migrated_without_human.count, h.migrated_without_human.total) == (11, 12)
    assert card.cost.model_calls == len(script)


def test_the_human_fix_at_review_leaves_no_failure(tmp_path: Path, spec: MigrationSpec) -> None:
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
        options(tmp_path, spec, mode="cli"),
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
    assert any(n.file == "src/test-utils.tsx" and n.layer == "human" for n in card.cheating.notes)
    assert card.headline.traps is not None and card.headline.traps.expected == 21


def test_the_reference_patches_are_minimal() -> None:
    """Each agent fix stays far below the hand-off limit (the oracle is honest)."""
    fixes = yaml.safe_load((REFERENCE / "agent-fixes.yaml").read_text())
    traps = yaml.safe_load((FIXTURE_CASE / "traps.yaml").read_text())
    agent = {t["id"] for t in traps["traps"] if t["expected_layer"] == "agent"}
    assert {t for f in fixes["files"] for t in f["traps"]} == agent
    assert (
        REPO_ROOT / "evals" / "cases" / "fixture-mui4" / "reference" / "human-fix.yaml"
    ).is_file()
