"""The real Baseline on the fixture: Node, npm and network, no LLM (``pytest -m slow``).

It asserts the numbers of the hand-run Baseline preview in traps.yaml and compares the
deterministic part of the scorecard with the committed one in docs/results/baseline/.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from migrator.config import load_case
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunOptions, dry_run
from migrator.report import stable_view
from tests.conftest import FIXTURE, FIXTURE_CASE, REPO_ROOT

EXPECTED = REPO_ROOT / "docs" / "results" / "baseline" / "scorecard.json"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("npm") is None, reason="needs Node and npm"),
]


def test_baseline_dry_run_on_the_fixture(tmp_path: Path, spec: MigrationSpec) -> None:
    before = {
        p: p.read_bytes()
        for p in FIXTURE.rglob("*")
        if p.is_file() and "node_modules" not in p.parts
    }
    result = dry_run(
        RunOptions(
            repo=FIXTURE,
            spec=spec,
            run_dir=tmp_path / "run",
            case=load_case(FIXTURE_CASE / "case.toml"),
        )
    )
    card = result.scorecard

    # The target repo is untouched by a dry run.
    after = {
        p: p.read_bytes()
        for p in FIXTURE.rglob("*")
        if p.is_file() and "node_modules" not in p.parts
    }
    assert after == before

    assert card.status == "completed"
    assert card.precheck.status == "ok"
    assert card.precheck.pre_existing_failures == []
    assert card.rules is not None
    sources = [f for f in card.rules.changed_files if f.startswith("src/")]
    assert len(sources) == 12  # the codemods changed 12 files

    assert card.verify is not None
    failures = card.verify.failures
    type_errors = [f for f in failures if f.source == "typecheck"]
    assert len(type_errors) == 8
    assert len({f.file for f in type_errors}) == 6
    assert [f for f in failures if f.source == "lint"] == []
    totals = card.verify.test_totals
    assert totals is not None
    assert (totals.tests_total, totals.tests_failed, totals.suites_failed) == (19, 7, 5)
    assert card.precheck.test_totals is not None
    assert card.precheck.test_totals.tests_total == 19

    h = card.headline
    assert (h.failures, h.failing_files) == (15, 9)
    assert not h.clean_run
    migrated = sorted(f.path for f in card.files if f.outcome == "Migrated by rules")
    assert migrated == ["src/App.tsx", "src/screens/Faq.tsx", "src/screens/UsersTable.tsx"]
    assert (h.migrated_without_human.count, h.migrated_without_human.total) == (3, 12)

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
            assert any(c.fired for c in trap.checks), f"{trap.id} not caught by verify"
            assert any(f.file == trap.file for f in failures), f"no failure in {trap.file}"

    # Same numbers as the committed expected scorecard (everything but meta).
    expected = json.loads(EXPECTED.read_text("utf-8"))
    assert stable_view(card) == stable_view(expected)
