"""Scoring on replayed runs (issue #17): every golden under tests/data/scoring/ is
scored again from its saved evidence and must give the same Scorecard.

The goldens are the stable views of real runs: the fake-toolchain graph tests, the
free Docker Baselines (the three MUI fixture cases and the Angular fixture), the
scripted oracle runs on the fixtures, and a few hand-built inputs for the paths no free
run reaches (a cheating-check hit, a Rules failure). See tests/scoring_goldens.py for
how they are captured.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrator.report import REPORT_INPUT, build_scorecard, read_report_input, stable_view
from tests.scoring_goldens import EXPECTED, GOLDENS

CASES = sorted(p for p in GOLDENS.iterdir() if p.is_dir())


def test_there_are_goldens_for_every_kind_of_run() -> None:
    names = {p.name for p in CASES}
    for kind in ("docker-baseline-", "graph-", "oracle-", "synthetic-"):
        assert any(n.startswith(kind) for n in names), kind


@pytest.mark.parametrize("golden", CASES, ids=[p.name for p in CASES])
def test_a_golden_scores_to_its_stored_stable_view(golden: Path) -> None:
    card = build_scorecard(read_report_input(golden / REPORT_INPUT))
    assert stable_view(card) == json.loads((golden / EXPECTED).read_text("utf-8"))
