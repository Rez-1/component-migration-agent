"""The scorecard's markdown, rendered from Scorecards that ``score()`` built (the
scoring rules themselves are tested in test_scoring.py)."""

from __future__ import annotations

from migrator.report import render_scorecard
from migrator.scoring import Evidence, score
from tests.test_scoring import card_input  # noqa: F401


def test_markdown_render(card_input: Evidence) -> None:  # noqa: F811
    md = render_scorecard(score(card_input))
    assert "**Clean run: no. Final verify found 2 failures in 2 files.**" in md
    assert "**1 of 3 affected files migrated without a human (33%)**" in md
    assert "| Missed | agent | 2: grid-types, dialog-backdrop |" in md
    assert "Fixed (their checks now pass at the final verify): never-caught." in md
    assert "| 1 files | Migrated by rules | 0 | Clean |" in md


def test_cheating_checks_and_cost_in_the_scorecard(card_input: Evidence) -> None:  # noqa: F811
    from migrator.checks import CheatingReport, Finding

    note = Finding(
        check="escape-hatch:eslint-disable",
        file="src/Clean.tsx",
        layer="rules",
        severity="fail",
        detail="an `eslint-disable` comment: 0 -> 1",
    )
    report = CheatingReport(hits=[], warnings=[], notes=[note], test_files={"a.test.tsx": "x"})
    card = score(card_input.model_copy(update={"cheating": report}))
    assert card.schema_version == 3
    assert (card.headline.cheating_check_hits, card.headline.cheating_check_warnings) == (0, 0)
    assert card.cost.total_usd == 0.0 and card.cost.run_cap_usd == 5.0
    md = render_scorecard(card)
    assert "| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |" in md
    assert "| src/Clean.tsx | rules | escape-hatch:eslint-disable |" in md
    assert "$0: this run made no model calls. Run cap $5.00; month cap $20.00." in md
    unchecked = render_scorecard(score(card_input))
    assert "| Cheating-check hits | — (not checked" in unchecked
