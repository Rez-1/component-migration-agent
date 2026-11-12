"""Scoring on replayed runs (issue #17): every golden under tests/data/scoring/ is
scored again from its saved evidence and must give the same Scorecard.

The goldens are the stable views of real runs, captured before Scoring moved to
``migrator.scoring``: the fake-toolchain graph tests, the free Docker Baselines (the
three MUI fixture cases and the Angular fixture), the scripted oracle runs on the
fixtures, and a few hand-built inputs for the paths no free run reaches (a
cheating-check hit, a Rules failure). Their evidence was written as ``ReportInput``
and converted to ``Evidence`` with ``MigratorChanges`` (the Migrator's fields moved
under ``changes``); the stable views are unchanged. See tests/scoring_goldens.py.

The scoring rules themselves are tested through ``score()`` on small hand-built
evidence (``card_input``); the markdown is tested in test_report.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from migrator.checks import Layer
from migrator.config import Trap, TrapList, TrapLocation
from migrator.migrations import MigrationSpec
from migrator.repair.records import FileRepair, RepairReport
from migrator.rules import RulesResult, RuleStepResult
from migrator.run.stages.report import EVIDENCE_FILE
from migrator.scan import ScanInput, UsageReport, scan
from migrator.scoring import (
    AgentChanges,
    Evidence,
    MigratorChanges,
    RunMeta,
    Scorecard,
    TrapResult,
    Unfinished,
    score,
    stable_view,
)
from migrator.verify import Failure, PrecheckResult, VerifyResult
from tests.scoring_goldens import EXPECTED, GOLDENS

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
def card_input(tmp_path: Path, spec: MigrationSpec) -> Evidence:
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
    return Evidence(
        usage=usage,
        precheck=PrecheckResult(status="ok", verify=VerifyResult(commands=[], failures=[])),
        changes=MigratorChanges(rules=rules),
        verify=VerifyResult(commands=[], failures=[TYPE_ERROR, TEST_FAIL]),
        final_usage=final,
        traps=traps,
        case="t",
        meta=_meta(),
    )


def changed(evidence: Evidence, **changes: Any) -> Evidence:
    """``evidence`` with some of the Migrator's changes replaced."""
    return evidence.model_copy(update={"changes": evidence.changes.model_copy(update=changes)})


def _rules_changed(evidence: Evidence, files: list[str]) -> Evidence:
    assert isinstance(evidence.changes, MigratorChanges)
    rules = evidence.changes.rules
    assert rules is not None
    return changed(evidence, rules=rules.model_copy(update={"changed_files": files}))


def test_baseline_outcomes_and_headline(card_input: Evidence) -> None:
    card = score(card_input)
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


def test_trap_results(card_input: Evidence) -> None:
    card = score(card_input)
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
    card_input: Evidence, tmp_path: Path, spec: MigrationSpec
) -> None:
    final = _usage(tmp_path / "unchanged", spec, FILES)
    card = score(
        card_input.model_copy(
            update={"final_usage": final, "verify": VerifyResult(commands=[], failures=[])}
        )
    )
    clean = next(f for f in card.files if f.path == "src/Clean.tsx")
    assert clean.outcome == "Unmigrated"
    assert clean.note == "1 old usages left" or clean.note.endswith("old usages left")


def test_a_rules_failure_leaves_every_file_unmigrated(card_input: Evidence) -> None:
    failed = RulesResult(
        status="rules_failure", reason="rule step 1 (install) failed", steps=[], changed_files=[]
    )
    card = score(changed(card_input, rules=failed).model_copy(update={"verify": None}))
    assert card.status == "rules_failure"
    assert {f.outcome for f in card.files} == {"Unmigrated"}
    assert not card.headline.clean_run
    assert card.traps is not None
    assert next(t for t in card.traps if t.id == "grid-rename").result == "Missed"


def test_clean_run_when_verify_finds_nothing(card_input: Evidence) -> None:
    card = score(card_input.model_copy(update={"verify": VerifyResult(commands=[], failures=[])}))
    assert card.headline.clean_run
    assert card.headline.migrated_without_human.share == 1.0


def test_stable_view_drops_meta_only(card_input: Evidence) -> None:
    card = score(card_input)
    other = score(
        card_input.model_copy(
            update={"meta": _meta().model_copy(update={"run_id": "r2", "duration_s": 99.0})}
        )
    )
    assert stable_view(card) == stable_view(other)
    assert "meta" not in stable_view(card)
    assert stable_view(card.model_dump(mode="json")) == stable_view(card)


def test_schema_2_scorecards_still_load() -> None:
    """M2 experiments' scorecards (no repair block, no regressions list) must load, or
    ``eval summary`` can't compare a new experiment with the M2 Baseline."""
    import json

    from tests.conftest import REPO_ROOT

    data = json.loads((REPO_ROOT / "docs/results/baseline/scorecard.json").read_text())
    for key in ("repair", "regressions"):
        data.pop(key)
    data["schema_version"] = 2
    for key in ("stopped_by_cap", "warnings"):
        data["cost"].pop(key)
    card = Scorecard.model_validate(data)
    assert card.regressions == [] and card.repair is None


# --------------------------------------------------------------------------- traps


def _one_trap(
    evidence: Evidence,
    trap: Trap,
    failures: list[Failure],
    later_layers: dict[str, Layer] | None = None,
) -> TrapResult:
    """The result of ``trap`` alone, scored with ``failures`` at the final verify."""
    inp = changed(evidence, later_layers=later_layers).model_copy(
        update={
            "traps": TrapList(schema_version=1, case="t", traps=[trap]),
            "verify": VerifyResult(commands=[], failures=failures),
        }
    )
    card = score(inp)
    assert card.traps is not None
    return card.traps[0]


def test_a_crashed_suite_fires_the_trap_check_and_untouched_files_miss(
    card_input: Evidence,
) -> None:
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
    result = _one_trap(card_input, trap, [crashed])
    assert result.result == "Missed" and result.checks[0].fired
    quiet = _trap("quiet", "agent", "src/Other.tsx", ["typecheck"])
    assert _one_trap(card_input, quiet, []).result == "Missed"
    by_rules = _rules_changed(card_input, [*sorted(FILES), "src/Other.tsx"])
    assert _one_trap(by_rules, quiet, []).result == "Other layer"


def test_a_missed_trap_is_silent_only_when_no_check_fires(card_input: Evidence) -> None:
    # The cascade case: the agent fixed the screen, not the helper the trap lives in,
    # so the helper's test passes and nothing in verify points at the trap.
    trap = _trap("spread", "agent", "src/helper.ts", ["src/__tests__/Tested.test.tsx › focus"])
    silent = _one_trap(card_input, trap, [])
    assert silent.result == "Missed" and silent.silent_miss
    failing = Failure(
        source="test",
        file="src/Tested.tsx",
        message="expected focus",
        test_file="src/__tests__/Tested.test.tsx",
        test_name="focus",
    )
    caught = _one_trap(card_input, trap, [failing])
    assert caught.result == "Missed" and not caught.silent_miss
    fixed = _one_trap(card_input, trap, [], {"src/helper.ts": "agent"})
    assert fixed.result == "Expected" and not fixed.silent_miss
    rules_trap = _trap("rule", "rules", "src/helper.ts", ["typecheck"])
    failed = RulesResult(status="rules_failure", reason="x", steps=[], changed_files=[])
    missed = _one_trap(changed(card_input, rules=failed), rules_trap, [])
    assert missed.result == "Missed" and not missed.silent_miss


def test_the_silent_misses_are_counted_in_the_headline(card_input: Evidence) -> None:
    card = score(card_input)
    assert card.headline.traps is not None
    assert card.headline.traps.silent == sum(t.silent_miss for t in card.traps or [])


# ------------------------------------------- files changed while repairing another file


def _companion_card(
    card_input: Evidence,
    owner: FileRepair,
    later: dict[str, Layer],
    failures: list[Failure] | None = None,
) -> dict[str, tuple[str, str]]:
    """Outcomes when src/Tested.tsx's repair also edits src/Clean.tsx (a local import
    with no failure and so no repair record of its own)."""
    inp = changed(
        card_input,
        repair=RepairReport(
            enabled=True,
            files=[owner],
            review_list=[owner.path] if owner.outcome == "Handed off" else [],
        ),
        later_layers=later,
    ).model_copy(update={"verify": VerifyResult(commands=[], failures=failures or [])})
    card = score(inp)
    return {f.path: (f.outcome, f.note) for f in card.files}


def _owner(**kw: Any) -> FileRepair:
    return FileRepair.model_validate(
        {"path": "src/Tested.tsx", "touched": ["src/Tested.tsx", "src/Clean.tsx"], **kw}
    )


def test_an_import_fixed_during_another_repair_is_migrated_by_agent(
    card_input: Evidence,
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
    card_input: Evidence,
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
    card_input: Evidence,
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


def test_an_import_kept_as_part_of_a_hand_off_is_handed_off(card_input: Evidence) -> None:
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
    card_input: Evidence,
) -> None:
    out = _companion_card(
        card_input,
        _owner(outcome="Handed off", review="edit", migrated_by_human=True),
        {"src/Tested.tsx": "human", "src/Clean.tsx": "agent"},
    )
    assert out["src/Tested.tsx"][0] == "Migrated by human"
    assert out["src/Clean.tsx"][0] == "Migrated by human"


def test_an_affected_file_nobody_changed_is_still_unmigrated(card_input: Evidence) -> None:
    inp = _rules_changed(card_input, ["package.json"]).model_copy(
        update={"verify": VerifyResult(commands=[], failures=[])}
    )
    out = {f.path: (f.outcome, f.note) for f in score(inp).files}
    assert out["src/Clean.tsx"] == ("Unmigrated", "not changed by any layer")


# --------------------------------------------------------------------------- replayed runs

CASES = sorted(p for p in GOLDENS.iterdir() if p.is_dir())


# --------------------------------------------------------------------------- a general agent


OTHER = Failure(source="lint", file="src/util.ts", line=3, code="no-unused-vars", message="x")


def by_agent(evidence: Evidence, failures: list[Failure], **changes: Any) -> Evidence:
    """``evidence`` as a general agent's workspace: no Rules stage, every affected file
    changed by the agent unless ``changed_files`` says otherwise."""
    agent = AgentChanges(changed_files=changes.pop("changed_files", sorted(FILES)), **changes)
    return evidence.model_copy(
        update={"changes": agent, "verify": VerifyResult(commands=[], failures=failures)}
    )


def test_a_general_agents_files_are_its_own_and_its_unfinished_ones_are_hand_offs(
    card_input: Evidence,
) -> None:
    left = Unfinished(path="src/Tested.tsx", reason="needs a test change a human must make")
    card = score(by_agent(card_input, [TYPE_ERROR, TEST_FAIL], unfinished=[left]))
    outcomes = {f.path: (f.outcome, f.layer, f.note) for f in card.files}
    assert card.status == "completed"  # no Rules stage is not a Rules failure
    assert outcomes["src/Clean.tsx"][:2] == ("Migrated by agent", "agent")
    assert outcomes["src/Broken.tsx"][0] == "Unmigrated"
    assert outcomes["src/Tested.tsx"] == ("Handed off", "agent", left.reason)
    assert card.handed_off == ["src/Tested.tsx"] and card.headline.hand_offs == 1
    assert card.rules is None and card.repair is None
    assert not card.headline.clean_run  # Broken.tsx fails outside the hand-offs


def test_a_general_agents_clean_run(card_input: Evidence) -> None:
    left = Unfinished(path="src/Broken.tsx", reason="Grid's v5 props")
    card = score(by_agent(card_input, [TYPE_ERROR], unfinished=[left]))
    assert card.headline.clean_run  # its only failure is in a handed-off file


def test_without_a_rules_stage_regressions_count_against_the_pre_check(
    card_input: Evidence,
) -> None:
    card = score(by_agent(card_input, [TYPE_ERROR, OTHER]))
    # Broken.tsx fails, but the agent changed it itself: Unmigrated, not a Regression.
    assert card.regressions == ["src/util.ts"] and card.headline.regressions == 1
    assert card.regressions_against == "Pre-check"
    known = card_input.precheck.model_copy(
        update={"verify": VerifyResult(commands=[], failures=[OTHER])}
    )
    again = score(by_agent(card_input, [OTHER]).model_copy(update={"precheck": known}))
    assert again.regressions == []  # it failed at the Pre-check already


def test_a_file_the_agent_left_alone_that_now_fails_is_a_regression(
    card_input: Evidence,
) -> None:
    card = score(by_agent(card_input, [TYPE_ERROR], changed_files=["src/Clean.tsx"]))
    assert card.regressions == ["src/Broken.tsx"]


def test_without_a_rules_stage_a_rules_trap_the_agent_handled_is_other_layer(
    card_input: Evidence,
) -> None:
    card = score(by_agent(card_input, [TEST_FAIL]))
    assert card.traps is not None
    results = {t.id: t.result for t in card.traps}
    assert results["grid-rename"] == "Other layer"  # the agent did what Rules would have
    assert results["grid-types"] == "Expected"  # its check is quiet, the agent's file
    assert results["dialog-backdrop"] == "Missed"  # its test still fails
    untouched = score(by_agent(card_input, [], changed_files=["src/Clean.tsx"]))
    assert untouched.traps is not None
    assert {t.id: t.result for t in untouched.traps}["grid-rename"] == "Missed"


def test_a_general_agents_evidence_replays_and_says_what_it_is(card_input: Evidence) -> None:
    left = Unfinished(path="src/Tested.tsx", reason="test change")
    evidence = by_agent(card_input, [OTHER], unfinished=[left])
    again = Evidence.model_validate_json(evidence.model_dump_json())
    assert isinstance(again.changes, AgentChanges)
    assert stable_view(score(again)) == stable_view(score(evidence))
    view = stable_view(score(evidence))
    assert view["regressions_against"] == "Pre-check"
    assert view["handed_off"] == ["src/Tested.tsx"]
    migrator_view = stable_view(score(card_input))
    assert "regressions_against" not in migrator_view and "handed_off" not in migrator_view


def test_old_scorecards_get_their_hand_offs_from_the_review_list(card_input: Evidence) -> None:
    review = RepairReport(enabled=True, review_list=["src/Broken.tsx"])
    data = score(changed(card_input, repair=review)).model_dump(mode="json")
    data.pop("handed_off")
    assert Scorecard.model_validate(data).handed_off == ["src/Broken.tsx"]


def test_the_real_repo_silent_miss_rule() -> None:
    from migrator.evals.reference import real_repo_silent_miss

    assert real_repo_silent_miss("wrong", 0, handed_off=False)
    assert real_repo_silent_miss("untouched", 0, handed_off=False)
    assert not real_repo_silent_miss("wrong", 2, handed_off=False)  # verify shows it
    assert not real_repo_silent_miss("wrong", 0, handed_off=True)  # a human will look
    assert not real_repo_silent_miss("matches", 0, handed_off=False)


def test_there_are_goldens_for_every_kind_of_run() -> None:
    names = {p.name for p in CASES}
    for kind in ("docker-baseline-", "graph-", "oracle-", "synthetic-"):
        assert any(n.startswith(kind) for n in names), kind


@pytest.mark.parametrize("golden", CASES, ids=[p.name for p in CASES])
def test_a_golden_scores_to_its_stored_stable_view(golden: Path) -> None:
    evidence = Evidence.model_validate_json((golden / EVIDENCE_FILE).read_text("utf-8"))
    assert stable_view(score(evidence)) == json.loads((golden / EXPECTED).read_text("utf-8"))
