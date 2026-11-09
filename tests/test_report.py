from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from migrator.checks import Layer
from migrator.config import Trap, TrapList, TrapLocation
from migrator.migrations import MigrationSpec
from migrator.repair.records import FileRepair, RepairReport
from migrator.report import (
    ReportInput,
    RunMeta,
    build_scorecard,
    render_scorecard,
    score_trap,
    stable_view,
)
from migrator.rules import RulesResult, RuleStepResult
from migrator.scan import ScanInput, UsageReport, scan
from migrator.verify import Failure, PrecheckResult, VerifyResult

FILES = {
    "src/Clean.tsx": "import Button from '@material-ui/core/Button';\nconst C = <Button />;\n",
    "src/Broken.tsx": "import { Grid } from '@material-ui/core';\nconst B = () => <Grid />;\n",
    "src/Tested.tsx": "import { Dialog } from '@material-ui/core';\nconst T = <Dialog open />;\n",
}


def _usage(tmp_path: Path, spec: MigrationSpec, files: dict[str, str]) -> UsageReport:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return scan(ScanInput(repo=tmp_path, spec=spec, source_globs=["src/**/*.tsx"], exclude=[]))


def _meta() -> RunMeta:
    return RunMeta(
        run_id="r1",
        started_at="2026-11-09T00:00:00Z",
        finished_at="2026-11-09T00:01:00Z",
        duration_s=60.0,
        migrator_version="0.1.0",
        node_version="24.14.0",
        npm_version="11.9.0",
        timings_s={"rules": 10.0},
    )


def _trap(id_: str, layer: str, file: str, caught_by: list[str] | str = "none") -> Trap:
    return Trap.model_validate(
        {
            "id": id_,
            "title": id_,
            "expected_layer": layer,
            "location": TrapLocation(file=file),
            "caught_by": caught_by,
        }
    )


TYPE_ERROR = Failure(
    source="typecheck", file="src/Broken.tsx", line=2, code="TS2322", message="bad"
)
TEST_FAIL = Failure(
    source="test",
    file="src/Tested.tsx",
    message="Error: not found",
    test_file="src/__tests__/Tested.test.tsx",
    test_name="Tested › stays open",
)


@pytest.fixture
def card_input(tmp_path: Path, spec: MigrationSpec) -> ReportInput:
    usage = _usage(tmp_path / "before", spec, FILES)
    after = {k: v.replace("@material-ui/core", "@mui/material") for k, v in FILES.items()}
    final = _usage(tmp_path / "after", spec, after)
    rules = RulesResult(
        status="ok",
        steps=[
            RuleStepResult(
                kind="codemod", name="preset-safe", status="ok", changed_files=sorted(FILES)
            )
        ],
        changed_files=sorted([*FILES, "package.json"]),
    )
    traps = TrapList(
        schema_version=1,
        case="t",
        traps=[
            _trap("grid-rename", "rules", "src/Broken.tsx"),
            _trap("grid-types", "agent", "src/Broken.tsx", ["typecheck"]),
            _trap(
                "dialog-backdrop",
                "agent",
                "src/Tested.tsx",
                ["src/__tests__/Tested.test.tsx › stays open"],
            ),
            _trap("never-caught", "agent", "src/Clean.tsx", ["typecheck"]),
            _trap("colour", "visual-only", "src/Clean.tsx"),
        ],
    )
    return ReportInput(
        usage=usage,
        precheck=PrecheckResult(status="ok", verify=VerifyResult(commands=[], failures=[])),
        rules=rules,
        verify=VerifyResult(commands=[], failures=[TYPE_ERROR, TEST_FAIL]),
        final_usage=final,
        traps=traps,
        case="t",
        meta=_meta(),
    )


def test_baseline_outcomes_and_headline(card_input: ReportInput) -> None:
    card = build_scorecard(card_input)
    outcomes = {f.path: f.outcome for f in card.files}
    assert outcomes == {
        "src/Broken.tsx": "Unmigrated",
        "src/Clean.tsx": "Migrated by rules",
        "src/Tested.tsx": "Unmigrated",
    }
    h = card.headline
    assert not h.clean_run
    assert (h.failures, h.failing_files) == (2, 2)
    assert (h.migrated_without_human.count, h.migrated_without_human.total) == (1, 3)
    assert h.outcomes["Unmigrated"] == 2
    assert card.changed_not_affected == ["package.json"]


def test_trap_results(card_input: ReportInput) -> None:
    card = build_scorecard(card_input)
    assert card.traps is not None
    results = {t.id: t.result for t in card.traps}
    assert results == {
        "grid-rename": "Expected",
        "grid-types": "Missed",
        "dialog-backdrop": "Missed",
        "never-caught": "Other layer",  # its check did not fire, and no agent touched the file
        "colour": "Not scored",
    }
    dialog = next(t for t in card.traps if t.id == "dialog-backdrop")
    assert dialog.checks[0].fired
    assert dialog.evidence == ["test Tested › stays open: Error: not found"]
    assert card.headline.traps is not None
    assert card.headline.traps.expected == 1


def test_old_imports_left_keep_a_file_unmigrated(
    card_input: ReportInput, tmp_path: Path, spec: MigrationSpec
) -> None:
    final = _usage(tmp_path / "unchanged", spec, FILES)
    card = build_scorecard(
        card_input.model_copy(
            update={"final_usage": final, "verify": VerifyResult(commands=[], failures=[])}
        )
    )
    clean = next(f for f in card.files if f.path == "src/Clean.tsx")
    assert clean.outcome == "Unmigrated"
    assert clean.note == "1 old usages left" or clean.note.endswith("old usages left")


def test_a_rules_failure_leaves_every_file_unmigrated(card_input: ReportInput) -> None:
    failed = RulesResult(
        status="rules_failure", reason="rule step 1 (install) failed", steps=[], changed_files=[]
    )
    card = build_scorecard(card_input.model_copy(update={"rules": failed, "verify": None}))
    assert card.status == "rules_failure"
    assert {f.outcome for f in card.files} == {"Unmigrated"}
    assert not card.headline.clean_run
    assert card.traps is not None
    assert next(t for t in card.traps if t.id == "grid-rename").result == "Missed"


def test_clean_run_when_verify_finds_nothing(card_input: ReportInput) -> None:
    card = build_scorecard(
        card_input.model_copy(update={"verify": VerifyResult(commands=[], failures=[])})
    )
    assert card.headline.clean_run
    assert card.headline.migrated_without_human.share == 1.0


def test_stable_view_drops_meta_only(card_input: ReportInput) -> None:
    card = build_scorecard(card_input)
    other = build_scorecard(
        card_input.model_copy(
            update={"meta": _meta().model_copy(update={"run_id": "r2", "duration_s": 99.0})}
        )
    )
    assert stable_view(card) == stable_view(other)
    assert "meta" not in stable_view(card)
    assert stable_view(card.model_dump(mode="json")) == stable_view(card)


def test_markdown_render(card_input: ReportInput) -> None:
    md = render_scorecard(build_scorecard(card_input))
    assert "**Clean run: no. Final verify found 2 failures in 2 files.**" in md
    assert "**1 of 3 affected files migrated without a human (33%)**" in md
    assert "| Missed | agent | 2: grid-types, dialog-backdrop |" in md
    assert "Fixed (their checks now pass at the final verify): never-caught." in md
    assert "| 1 files | Migrated by rules | 0 | Clean |" in md


def test_cheating_checks_and_cost_in_the_scorecard(card_input: ReportInput) -> None:
    from migrator.checks import CheatingReport, Finding

    note = Finding(
        check="escape-hatch:eslint-disable",
        file="src/Clean.tsx",
        layer="rules",
        severity="fail",
        detail="an `eslint-disable` comment: 0 -> 1",
    )
    report = CheatingReport(hits=[], warnings=[], notes=[note], test_files={"a.test.tsx": "x"})
    card = build_scorecard(card_input.model_copy(update={"cheating": report}))
    assert card.schema_version == 3
    assert (card.headline.cheating_check_hits, card.headline.cheating_check_warnings) == (0, 0)
    assert card.cost.total_usd == 0.0 and card.cost.run_cap_usd == 5.0
    md = render_scorecard(card)
    assert "| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |" in md
    assert "| src/Clean.tsx | rules | escape-hatch:eslint-disable |" in md
    assert "$0: this run made no model calls. Run cap $5.00; month cap $20.00." in md
    unchecked = render_scorecard(build_scorecard(card_input))
    assert "| Cheating-check hits | — (not checked" in unchecked


def test_a_crashed_suite_fires_the_trap_check_and_untouched_files_miss() -> None:
    crashed = Failure(
        source="test",
        file="src/Tested.tsx",
        message="Cannot find module '@material-ui/core'",
        test_file="src/__tests__/Tested.test.tsx",
        test_name="(suite)",
    )
    trap = _trap(
        "dialog", "agent", "src/Tested.tsx", ["src/__tests__/Tested.test.tsx › stays open"]
    )
    result = score_trap(trap, [crashed], {}, set(), rules_ok=True)
    assert result.result == "Missed" and result.checks[0].fired
    quiet = _trap("quiet", "agent", "src/Other.tsx", ["typecheck"])
    assert score_trap(quiet, [], {}, set(), rules_ok=True).result == "Missed"
    assert score_trap(quiet, [], {"src/Other.tsx": "rules"}, set(), True).result == "Other layer"


def test_schema_2_scorecards_still_load() -> None:
    """M2 experiments' scorecards (no repair block, no regressions list) must load, or
    ``eval summary`` can't compare a new experiment with the M2 Baseline."""
    import json

    from migrator.report import Scorecard
    from tests.conftest import REPO_ROOT

    data = json.loads((REPO_ROOT / "docs/results/baseline/scorecard.json").read_text())
    for key in ("repair", "regressions"):
        data.pop(key)
    data["schema_version"] = 2
    for key in ("stopped_by_cap", "warnings"):
        data["cost"].pop(key)
    card = Scorecard.model_validate(data)
    assert card.regressions == [] and card.repair is None


# ------------------------------------------- files changed while repairing another file


def _companion_card(
    card_input: ReportInput,
    owner: FileRepair,
    later: dict[str, Layer],
    failures: list[Failure] | None = None,
) -> dict[str, tuple[str, str]]:
    """Outcomes when src/Tested.tsx's repair also edits src/Clean.tsx (a local import
    with no failure and so no repair record of its own)."""
    inp = card_input.model_copy(
        update={
            "verify": VerifyResult(commands=[], failures=failures or []),
            "repair": RepairReport(
                enabled=True,
                files=[owner],
                review_list=[owner.path] if owner.outcome == "Handed off" else [],
            ),
            "later_layers": later,
        }
    )
    card = build_scorecard(inp)
    return {f.path: (f.outcome, f.note) for f in card.files}


def _owner(**kw: Any) -> FileRepair:
    return FileRepair.model_validate(
        {"path": "src/Tested.tsx", "touched": ["src/Tested.tsx", "src/Clean.tsx"], **kw}
    )


def test_an_import_fixed_during_another_repair_is_migrated_by_agent(
    card_input: ReportInput,
) -> None:
    out = _companion_card(
        card_input,
        _owner(outcome="Migrated by agent"),
        {"src/Tested.tsx": "agent", "src/Clean.tsx": "agent"},
    )
    assert out["src/Tested.tsx"][0] == "Migrated by agent"
    assert out["src/Clean.tsx"] == (
        "Migrated by agent",
        "changed while repairing src/Tested.tsx",
    )


def test_an_import_changed_during_a_passing_repair_but_still_failing_is_unmigrated(
    card_input: ReportInput,
) -> None:
    clean_fails = Failure(source="typecheck", file="src/Clean.tsx", line=1, message="bad")
    out = _companion_card(
        card_input,
        _owner(outcome="Migrated by agent"),
        {"src/Tested.tsx": "agent", "src/Clean.tsx": "agent"},
        failures=[clean_fails],
    )
    outcome, note = out["src/Clean.tsx"]
    assert outcome == "Unmigrated"
    assert "changed while repairing src/Tested.tsx" in note


def test_an_import_reverted_with_a_hand_off_keeps_its_rules_outcome(
    card_input: ReportInput,
) -> None:
    # Reverted at Review: the file is back to its after-Rules text, so no later layer.
    out = _companion_card(
        card_input,
        _owner(outcome="Handed off", review="revert", touched=[]),
        {},
        failures=[TEST_FAIL],
    )
    assert out["src/Tested.tsx"][0] == "Handed off"
    assert out["src/Clean.tsx"] == ("Migrated by rules", "")


def test_an_import_kept_as_part_of_a_hand_off_is_handed_off(card_input: ReportInput) -> None:
    out = _companion_card(
        card_input,
        _owner(outcome="Handed off", review="keep"),
        {"src/Tested.tsx": "agent", "src/Clean.tsx": "agent"},
        failures=[TEST_FAIL],
    )
    assert out["src/Clean.tsx"] == (
        "Handed off",
        "part of the handed-off patch for src/Tested.tsx",
    )


def test_an_import_in_a_hand_off_a_human_fixed_is_migrated_by_human(
    card_input: ReportInput,
) -> None:
    out = _companion_card(
        card_input,
        _owner(outcome="Handed off", review="edit", migrated_by_human=True),
        {"src/Tested.tsx": "human", "src/Clean.tsx": "agent"},
    )
    assert out["src/Tested.tsx"][0] == "Migrated by human"
    assert out["src/Clean.tsx"][0] == "Migrated by human"


def test_an_affected_file_nobody_changed_is_still_unmigrated(card_input: ReportInput) -> None:
    inp = card_input.model_copy(
        update={
            "rules": card_input.rules.model_copy(update={"changed_files": ["package.json"]})
            if card_input.rules
            else None,
            "verify": VerifyResult(commands=[], failures=[]),
        }
    )
    out = {f.path: (f.outcome, f.note) for f in build_scorecard(inp).files}
    assert out["src/Clean.tsx"] == ("Unmigrated", "not changed by any layer")
