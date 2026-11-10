"""The hill-climbing setup: the harness gate, dev-only cases, the keep rule, the
``eval climb`` command's gates, and the offline retrieval metric (free, no model)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from migrator.cli import app
from migrator.config import CaseConfig, load_traps
from migrator.evals.hillclimb import (
    ClimbError,
    check_harness,
    harness_digest,
    keep_verdict,
    matching_baseline,
    record_round,
    sync_cases,
)
from migrator.evals.retrieval import measure, render
from migrator.evals.summary import CostSummary, ExperimentSummary, MetricSummary
from migrator.migrations import MigrationSpec
from migrator.repair.prompt import enclosing_props, library_imports
from tests.conftest import REPO_ROOT

FLOW = REPO_ROOT / ".claude" / "hillclimb" / "dev"
BASELINE_RUN = FLOW / "baseline" / "runs" / "fixture-mui4_rep0"
TRAPS = REPO_ROOT / "evals" / "cases" / "fixture-mui4" / "traps.yaml"

# --------------------------------------------------------------------------- harness


def test_the_harness_digest_changes_with_any_listed_file(tmp_path: Path) -> None:
    (tmp_path / "grader").mkdir()
    (tmp_path / "grader" / "a.py").write_text("x = 1\n")
    (tmp_path / "grader" / "node_modules").mkdir()
    (tmp_path / "grader" / "node_modules" / "big.js").write_text("ignored\n")
    (tmp_path / "uv.lock").write_text("lock\n")
    sha, covered = harness_digest(tmp_path, ["grader", "uv.lock", "missing"])
    assert covered == ["grader/a.py", "uv.lock"]
    (tmp_path / "grader" / "node_modules" / "big.js").write_text("still ignored\n")
    assert harness_digest(tmp_path, ["grader", "uv.lock"])[0] == sha
    (tmp_path / "grader" / "a.py").write_text("x = 2\n")
    assert harness_digest(tmp_path, ["grader", "uv.lock"])[0] != sha


def test_the_gate_refuses_until_approved_and_after_any_change(tmp_path: Path) -> None:
    (tmp_path / "grade.py").write_text("ok\n")
    state: dict[str, Any] = {"harness_paths": ["grade.py"], "harness_sha": None}
    with pytest.raises(ClimbError, match="--approve-harness"):
        check_harness(tmp_path, state, approve=False)
    assert "approved" in (check_harness(tmp_path, state, approve=True) or "")
    assert check_harness(tmp_path, state, approve=False) is None
    (tmp_path / "grade.py").write_text("gamed\n")
    with pytest.raises(ClimbError, match="changed since it was approved"):
        check_harness(tmp_path, state, approve=False)
    with pytest.raises(ClimbError, match="no harness_paths"):
        check_harness(tmp_path, {}, approve=False)


def test_the_committed_state_covers_the_grader_checks_and_traps() -> None:
    state = json.loads((FLOW / "_state.json").read_text())
    paths = set(state["harness_paths"])
    for needed in (
        "src/migrator/report.py",
        "src/migrator/checks",
        "src/migrator/evals",
        "evals/cases",
        "fixtures",
        "uv.lock",
    ):
        assert needed in paths
    assert state["approve_each_round"] is True
    assert state["test_ids"] == []
    # M5's result: opus-low re-run on the full dev set (round 0b) stayed best.
    assert state["best"]["variant"] == "v3"
    cases = [
        json.loads((FLOW / v / "experiment.json").read_text())["cases"]
        for v in ("baseline", "v1", "v3")
    ]
    assert cases == [["fixture-mui4"], ["fixture-mui4"], ["fixture-mui4", "fixture-mui4-hard"]]


# --------------------------------------------------------------------------- cases


def case(case_id: str, split: str) -> CaseConfig:
    return CaseConfig.model_validate(
        {
            "id": case_id,
            "split": split,
            "source": "fixtures/x",
            "migration": "mui@4->mui@5",
            "runner": "jest",
            "reference": "none",
        }
    )


def test_cases_are_dev_only_and_a_new_dev_case_is_announced() -> None:
    state: dict[str, Any] = {"train_ids": ["a"], "test_ids": []}
    assert sync_cases(state, [case("a", "dev")]) is None
    note = sync_cases(state, [case("a", "dev"), case("b", "dev")])
    assert note is not None and "b joined" in note
    assert state["train_ids"] == ["a", "b"] and state["test_ids"] == []
    with pytest.raises(ClimbError, match="held-out"):
        sync_cases(state, [case("a", "dev"), case("h", "held-out")])
    with pytest.raises(ClimbError, match="test_ids"):
        sync_cases({"train_ids": ["a"], "test_ids": ["h"]}, [case("a", "dev")])


# --------------------------------------------------------------------------- keep rule


def summary(
    *,
    clean: int = 2,
    traps: float = 9,
    regressions: float = 0,
    cheating: float = 0,
    per_clean: float | None = 0.20,
    cases: tuple[str, ...] = ("fixture-mui4",),
) -> ExperimentSummary:
    def metric(metric_id: str, mean: float) -> MetricSummary:
        return MetricSummary(
            id=metric_id,
            label=metric_id,
            unit="count",
            values=[mean],
            mean=mean,
            min=mean,
            max=mean,
        )

    return ExperimentSummary(
        experiment="dev/vX",
        split="dev",
        configuration="c",
        configuration_digest="d",
        cases=list(cases),
        repeats=2,
        runs_planned=2,
        runs_scored=2,
        runs_not_scored={},
        runs=[],
        clean_runs=clean,
        metrics=[
            metric("repair_traps_expected", traps),
            metric("regressions", regressions),
            metric("cheating_hits", cheating),
        ],
        cost=CostSummary(
            total_usd=0.4, per_run_usd=0.2, per_clean_run_usd=per_clean, clean_runs=clean
        ),
        traps=[],
        against=None,
    )


def test_the_keep_rule() -> None:
    best = summary()
    cheaper = keep_verdict(summary(per_clean=0.10), best)
    assert cheaper.keep is True and cheaper.cheaper and cheaper.label == "directional"
    assert keep_verdict(summary(per_clean=0.30, traps=9.5), best).keep is True  # better quality
    worse = keep_verdict(summary(per_clean=0.05, clean=1), best)
    assert worse.keep is False and worse.worse == ["clean_rate"]  # cheap but worse: revert
    assert keep_verdict(summary(per_clean=0.05, cheating=1), best).keep is False
    assert keep_verdict(summary(per_clean=0.05, regressions=1), best).keep is False
    same = keep_verdict(summary(), best)
    assert same.keep is False and "not lower" in same.reason
    other = keep_verdict(summary(cases=("fixture-mui4", "fixture-mui4-hard")), best)
    assert other.keep is None and "not comparable" in other.reason


def test_rounds_are_recorded() -> None:
    state: dict[str, Any] = {"rounds": [{"variant": "v1"}]}
    record_round(
        state,
        variant="v2",
        configuration="c",
        digest="d",
        cases=["a"],
        verdict=keep_verdict(summary(), summary()),
    )
    assert state["current_round"] == 2
    assert state["rounds"][-1]["verdict"]["keep"] is False


def test_the_baseline_to_compare_with_ran_the_same_cases() -> None:
    assert matching_baseline(FLOW, ["fixture-mui4"]) == FLOW / "baseline"
    # Round 0a re-ran the Baseline on the full dev set.
    assert matching_baseline(FLOW, ["fixture-mui4", "fixture-mui4-hard"]) == FLOW / "v2"
    assert matching_baseline(FLOW, ["fixture-mui4-holdout"]) is None


# --------------------------------------------------------------------------- the command


@pytest.fixture
def flow(tmp_path: Path) -> Path:
    copy = tmp_path / "hillclimb" / "dev"
    copy.mkdir(parents=True)
    state = json.loads((FLOW / "_state.json").read_text())
    # A stable subset, so files another change touches mid-test can't trip the gate.
    state["harness_paths"] = ["src/migrator/evals", "uv.lock"]
    (copy / "_state.json").write_text(json.dumps(state))
    return copy


def climb(flow: Path, *args: str) -> Any:
    return CliRunner().invoke(
        app,
        ["eval", "climb", "--root", str(REPO_ROOT), "--flow", str(flow), *args],
        env={"COLUMNS": "300"},
    )


def test_climb_refuses_an_unapproved_harness_and_an_unapproved_round(flow: Path) -> None:
    first = climb(flow, "--config", "opus-low", "--dry-run")
    assert first.exit_code == 2 and "approve-harness" in first.output
    approved = climb(flow, "--config", "cascade-haiku-opus", "--dry-run", "--approve-harness")
    assert approved.exit_code == 0, approved.output
    assert "harness approved" in approved.output and "directional" in approved.output
    assert "attempt 2 claude-opus-5-5" in approved.output  # the cascade's pre-flight
    state = json.loads((flow / "_state.json").read_text())
    assert state["harness_sha"] and "fixture-mui4" in state["train_ids"]
    assert all("holdout" not in i for i in state["train_ids"]) and state["test_ids"] == []
    unapproved = climb(flow, "--config", "opus-low", "--max-cost", "1")
    assert unapproved.exit_code == 2 and "approve_each_round" in unapproved.output


# --------------------------------------------------------------------------- retrieval


def test_library_imports_and_enclosing_props() -> None:
    text = (
        "import Autocomplete from '@mui/material/Autocomplete';\n"
        "import { TextField, Typography as T } from '@mui/material';\n"
        "import { useState } from 'react';\n"
        "export const S = () => (\n"
        "  <Autocomplete\n"
        "    renderOption={(o) => (\n"
        "      <span>{o.label}</span>\n"
        "    )}\n"
        "  />\n"
        ");\n"
    )
    assert library_imports(text, ["@mui/material"]) == ["Autocomplete", "TextField", "Typography"]
    assert enclosing_props(text, "src/S.tsx", [7]) == ["renderOption"]
    assert enclosing_props(text, "src/S.tsx", [1]) == []


def test_offline_retrieval_hit_rate_on_the_dev_fixture(spec: MigrationSpec) -> None:
    """The measured miss: Search's renderOption section is not in keyword's top 3; the
    context variant (the JSX prop around the failing line) puts it first."""
    traps = load_traps(TRAPS)
    reports = [
        measure(BASELINE_RUN, traps, spec, m)
        for m in ("keyword", "keyword-imports", "keyword-context")
    ]
    hits = [r.hits for r in reports]
    assert [len(r.traps) for r in reports] == [9, 9, 9]
    assert hits == [5, 5, 6]
    search = [next(t for t in r.traps if t.trap == "autocomplete-render-option") for r in reports]
    assert [t.hit for t in search] == [False, False, True]
    assert search[2].rank == 1
    table = render(reports)
    assert "**5 of 9**" in table and "**6 of 9**" in table
