"""The known-good run on the harder dev fixture (``-m slow``).

The sibling of ``tests/test_oracle_slow.py`` for ``evals/cases/fixture-mui4-hard``: a
scripted model makes exactly the edits in its ``reference/agent-fixes.yaml`` via
``apply_edit``, on the real fixture with the real codemods, tsc, ESLint and Jest (Node
and npm needed; no LLM). Six of its fixes land in a shared module the failing screen
imports, so this also checks that the guardrails' scope rule leaves every legitimate
fix in reach. The harness must score a clean run with every agent trap Expected.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from langchain_core.messages import AIMessage

from migrator.config import load_case
from migrator.cost import Ledger
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunOptions, dry_run
from tests.conftest import REPO_ROOT
from tests.fakes import ScriptedChatModel, ai, call, factory_for
from tests.test_graph import configuration

FIXTURE_HARD = REPO_ROOT / "fixtures" / "mui4-app-hard"
CASE_HARD = REPO_ROOT / "evals" / "cases" / "fixture-mui4-hard"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("npm") is None, reason="needs Node and npm"),
]


def oracle_script() -> dict[str, list[AIMessage]]:
    fixes = yaml.safe_load((CASE_HARD / "reference" / "agent-fixes.yaml").read_text())
    script: dict[str, list[AIMessage]] = {}
    for entry in fixes["files"]:
        edits = [
            call("apply_edit", path=e["path"], old_text=e["old"], new_text=e["new"])
            for e in entry["edits"]
        ]
        script[entry["path"]] = [ai(*edits, call("run_verify", note=entry["note"]))]
    return script


def test_the_hard_reference_fixes_score_every_agent_trap_expected(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    script = oracle_script()
    model = ScriptedChatModel(script=script)
    result = dry_run(
        RunOptions.model_validate(
            {
                "repo": FIXTURE_HARD,
                "spec": spec,
                "run_dir": tmp_path / "run",
                "case": load_case(CASE_HARD / "case.toml"),
                "configuration": configuration(),
            }
        ),
        model_factory=factory_for(model),
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    card = result.scorecard
    assert card.status == "completed"
    assert card.repair is not None

    # Every failing file got its scripted fix, one conversation each; the shared
    # wrappers that fail on their own come before the screens.
    repaired = [r.path for r in card.repair.files]
    assert sorted(repaired) == sorted(script)
    assert repaired[:2] == ["src/components/RangeSlider.tsx", "src/components/StatusChip.tsx"]
    assert {r["file"] for r in model.requests} == set(script)

    # No guardrail tripped on a legitimate fix (several reach into an imported module),
    # and every fix passed on its first attempt.
    for record in card.repair.files:
        assert record.edits_rejected == {}, record.path
        assert record.outcome == "Migrated by agent", (record.path, record.reason)
        assert [a.result for a in record.attempts] == ["passed"], record.path

    assert card.traps is not None
    assert {(t.expected_layer, t.result) for t in card.traps} == {
        ("rules", "Expected"),
        ("agent", "Expected"),
    }
    assert card.headline.traps is not None
    assert (card.headline.traps.expected, card.headline.traps.missed) == (15, 0)

    h = card.headline
    assert h.clean_run
    assert card.verify is not None and card.verify.failures == []
    assert (h.hand_offs, h.regressions, h.cheating_check_hits) == (0, 0, 0)
    # theme.ts, LabelPicker and DurationInput have no repair record of their own (each is
    # fixed during a screen's repair); they still count as Migrated by agent.
    assert {f.outcome for f in card.files} == {"Migrated by rules", "Migrated by agent"}
    assert h.migrated_without_human.count == h.migrated_without_human.total == 12
    assert card.cost.model_calls == len(script)
