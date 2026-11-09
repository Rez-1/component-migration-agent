"""The experiment runner, its build-eval layout, and the experiment summary."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from migrator.checks import CheatingReport, Finding
from migrator.cli import app
from migrator.config import load_case
from migrator.configuration import BASELINE, Configuration, NeedsRepairLoopError
from migrator.cost import RunCost, Usage
from migrator.evals import (
    METRICS,
    EvalError,
    ExperimentPlan,
    load_cases,
    read_errors,
    read_rows,
    run_experiment,
)
from migrator.evals.summary import build_summary, render_summary, stable_view, write_summary
from migrator.execs import CommandRunner, RunTimeoutError
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunOptions, RunResult
from migrator.report import ReportInput, build_scorecard, render_scorecard, write_json
from migrator.verify import VerifyResult
from tests.conftest import FIXTURE_CASE, REPO_ROOT
from tests.test_report import TEST_FAIL, TYPE_ERROR, _meta, card_input  # noqa: F401

CASE = load_case(FIXTURE_CASE / "case.toml")
OPUS = Configuration.model_validate(
    {
        "name": "opus-low",
        "repair": {
            "enabled": True,
            "attempt_models": ["claude-opus-5-5"] * 3,
            "effort": "low",
            "prompt_version": "v1",
            "retrieval": "keyword",
        },
    }
)


class FakeRuns:
    """A run function that returns prepared scorecards instead of running Node."""

    def __init__(self, base: ReportInput, outcomes: list[str]):
        self.base = base
        self.outcomes: Iterator[str] = iter(outcomes)
        self.calls: list[RunOptions] = []

    def __call__(self, opts: RunOptions, runner: CommandRunner | None) -> RunResult:
        self.calls.append(opts)
        outcome = next(self.outcomes)
        if outcome == "timeout":
            raise RunTimeoutError("the run passed its 1 s ceiling")
        if outcome == "crash":
            raise ValueError("a harness bug")
        inp = self.base.model_copy(
            update={
                "configuration": opts.configuration.name,
                "configuration_digest": opts.configuration.digest(),
                "meta": _meta().model_copy(update={"run_id": opts.run_id or "r"}),
            }
        )
        if outcome == "clean":
            inp = inp.model_copy(update={"verify": VerifyResult(commands=[], failures=[])})
        if outcome == "cheat":
            hit = Finding(
                check="escape-hatch:any",
                file="src/Clean.tsx",
                layer="agent",
                severity="fail",
                detail="the `any` type: 0 -> 1",
            )
            inp = inp.model_copy(
                update={
                    "verify": VerifyResult(commands=[], failures=[]),
                    "cheating": CheatingReport(hits=[hit], warnings=[], notes=[], test_files={}),
                }
            )
        if outcome == "costly":
            cost = RunCost.no_llm(5, 20).model_copy(
                update={"total_usd": 3.0, "model_calls": 12, "models": ["claude-opus-5-5"]}
            )
            inp = inp.model_copy(
                update={"verify": VerifyResult(commands=[], failures=[]), "cost": cost}
            )
        card = build_scorecard(inp)
        write_json(card, opts.run_dir / "scorecard.json")
        (opts.run_dir / "scorecard.md").write_text(render_scorecard(card))
        return RunResult(
            run_id=card.meta.run_id,
            run_dir=opts.run_dir,
            usage=inp.usage,
            scorecard=card,
            workspace=None,
        )


def _plan(tmp_path: Path, config: Configuration = BASELINE, **kw: object) -> ExperimentPlan:
    return ExperimentPlan.model_validate(
        {
            "root": REPO_ROOT,
            "results_dir": tmp_path / "evals",
            "split": "dev",
            "configuration": config,
            "cases": [CASE],
            "repeats": 2,
            **kw,
        }
    )


def test_load_cases() -> None:
    cases_dir = REPO_ROOT / "evals" / "cases"
    assert [c.id for c in load_cases(cases_dir, "dev")] == ["fixture-mui4"]
    with pytest.raises(EvalError, match="no held-out cases"):
        load_cases(cases_dir, "held-out")
    with pytest.raises(EvalError, match="in the dev split"):
        load_cases(cases_dir, "held-out", "fixture-mui4")


def test_experiment_writes_the_build_eval_layout(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    runs = FakeRuns(card_input, ["dirty", "dirty"])
    outcome = run_experiment(_plan(tmp_path), run=runs)
    assert (outcome.experiment, outcome.scored, outcome.errors) == ("dev/baseline", 2, 0)
    variant = outcome.path
    state = json.loads((variant.parent / "_state.json").read_text())
    assert state["metrics"] == METRICS
    assert state["metrics"][0] == {"id": "clean_run", "label": "Clean run", "kind": "binary"}
    rows = read_rows(variant)
    assert [(r.prompt_id, r.rep) for r in rows] == [("fixture-mui4", 0), ("fixture-mui4", 1)]
    row = rows[0]
    assert list(row.grade) == [
        "clean_run",
        "migrated_share",
        "repair_traps_expected",
        "cheating_hits",
        "regressions",
    ]
    assert row.model is None and row.cost_usd == 0.0 and row.tags == ["fixture", "dev"]
    assert (variant.parent / row.meta["scorecard"]).is_file()
    trace = json.loads((variant / "traces" / "fixture-mui4_rep0.json").read_text())
    assert [t["role"] for t in trace[:2]] == ["system", "user"]
    assert trace[-1]["role"] == "assistant" and "# Scorecard" in trace[-1]["content"]
    assert {t["role"] for t in trace} <= {"system", "user", "assistant", "tool_call", "tool_result"}
    header = json.loads((variant / "summary.json").read_text())
    assert header["label"] == "baseline"
    # Each run gets its own run id and its own folder (a fresh workspace each).
    assert len({c.run_id for c in runs.calls}) == 2
    assert len({c.run_dir for c in runs.calls}) == 2


def test_a_second_experiment_is_the_next_variant(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    first = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty"] * 2))
    second = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty"] * 2))
    assert (first.experiment, second.experiment) == ("dev/baseline", "dev/v1")


def test_repair_configuration_fails_before_anything_runs(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    runs = FakeRuns(card_input, [])
    with pytest.raises(NeedsRepairLoopError):
        run_experiment(_plan(tmp_path, OPUS), run=runs)
    assert runs.calls == []
    assert not (tmp_path / "evals").exists()


def test_failed_runs_go_to_the_errors_sidecar_and_resume_reruns_them(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    out = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty", "timeout"]))
    assert (out.scored, out.errors) == (1, 1)
    errors = read_errors(out.path)
    assert [(e.rep, e.failure_class) for e in errors] == [(1, "timeout")]
    assert len(read_rows(out.path)) == 1  # the failed run holds no (case, rep) slot

    runs = FakeRuns(card_input, ["crash"])
    again = run_experiment(_plan(tmp_path, resume="dev/baseline"), run=runs)
    assert (again.scored, again.errors, again.skipped) == (0, 1, 1)
    assert read_errors(out.path)[-1].failure_class == "harness"

    final = run_experiment(
        _plan(tmp_path, resume="dev/baseline"), run=FakeRuns(card_input, ["dirty"])
    )
    assert (final.scored, final.skipped) == (1, 1)
    assert [r.rep for r in read_rows(out.path)] == [0, 1]


def test_resume_refuses_a_changed_configuration(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty"] * 2))
    changed = BASELINE.model_copy(
        update={"rules": BASELINE.rules.model_copy(update={"skip": ["x"]})}
    )
    with pytest.raises(EvalError, match="not be comparable"):
        run_experiment(
            _plan(tmp_path, changed, resume="dev/baseline"), run=FakeRuns(card_input, [])
        )


def test_a_cheating_hit_fails_the_run(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    out = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["clean", "cheat"]))
    rows = read_rows(out.path)
    assert [r.grade["clean_run"] for r in rows] == [1.0, 0.0]
    assert rows[1].grade["cheating_hits"] == 1.0
    card = json.loads((out.path.parent / rows[1].meta["scorecard"]).read_text())
    clean = next(f for f in card["files"] if f["path"] == "src/Clean.tsx")
    assert clean["outcome"] == "Unmigrated"
    assert clean["note"] == "cheating check: escape-hatch:any"


# --------------------------------------------------------------------------- summary


def test_summary_mean_and_both_values_for_two_runs(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    base = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty"] * 2))
    other = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["costly", "dirty"]))
    summary = build_summary(other.path, base.path, created_at="2026-11-09T00:00:00Z")
    share = next(m for m in summary.metrics if m.id == "migrated_share")
    assert share.values == [1.0, 0.3333]
    assert summary.clean_runs == 1
    assert summary.cost.total_usd == 3.0
    assert summary.cost.per_run_usd == 1.5
    assert summary.cost.per_clean_run_usd == 3.0
    assert summary.against is not None and summary.against.experiment == "dev/baseline"
    md = render_summary(summary)
    assert "Clean runs: 1 of 2 vs 0 of 2." in md
    assert "Cost per clean run: $3.00 (cost per run: $1.50)" in md
    assert "| Clean runs | yes / no | 1 of 2 | 0 of 2 | +1 |" in md
    assert "both values" in md


def test_cost_per_clean_run_is_undefined_without_clean_runs(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    out = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty"] * 2))
    summary = build_summary(out.path)
    assert summary.clean_runs == 0
    assert summary.cost.per_clean_run_usd is None
    assert "Cost per clean run: — (no clean runs)" in render_summary(summary)


def test_three_runs_show_the_range(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    out = run_experiment(
        _plan(tmp_path, repeats=3), run=FakeRuns(card_input, ["dirty", "clean", "dirty"])
    )
    md = render_summary(build_summary(out.path))
    assert "range over the runs" in md
    assert "| Migrated without a human | 33% to 100% |" in md


def test_trap_results_across_runs(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    out = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty", "clean"]))
    summary = build_summary(out.path)
    by_id = {t.id: t.results for t in summary.traps}
    assert by_id["grid-types"] == ["Missed", "Other layer"]
    assert by_id["colour"] == ["Not scored", "Not scored"]


def test_stable_summary_has_no_dates_and_rerenders(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    out = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty"] * 2))
    a = build_summary(out.path, created_at="2026-11-09T00:00:00Z")
    b = build_summary(out.path, created_at="2027-01-01T00:00:00Z")
    assert stable_view(a) == stable_view(b)
    md_path = write_summary(a, tmp_path / "pub", stable=True)
    md = md_path.read_text()
    assert "2026-11-09" not in md and "Time per run" not in md
    data = json.loads((tmp_path / "pub" / "experiment-summary.json").read_text())
    assert "meta" not in data
    from migrator.evals.summary import ExperimentSummary

    assert render_summary(ExperimentSummary.model_validate(data), stable=True) == md


def test_summary_recomputes_from_rows_and_catches_disagreement(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    out = run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty"] * 2))
    path = out.path / "results.jsonl"
    lines = path.read_text().splitlines()
    row = json.loads(lines[0])
    row["grade"]["clean_run"] = 1.0
    path.write_text("\n".join([json.dumps(row), *lines[1:]]) + "\n")
    with pytest.raises(EvalError, match="disagree"):
        build_summary(out.path)


COMMITTED = REPO_ROOT / "docs" / "results" / "baseline-experiment"


@pytest.mark.skipif(not COMMITTED.is_dir(), reason="no committed experiment summary yet")
def test_committed_experiment_summary_renders_from_its_json() -> None:
    from migrator.evals.summary import ExperimentSummary

    data = json.loads((COMMITTED / "experiment-summary.json").read_text())
    summary = ExperimentSummary.model_validate(data)
    assert (COMMITTED / "experiment-summary.md").read_text() == render_summary(summary, stable=True)


# --------------------------------------------------------------------------- CLI

cli = CliRunner()


def test_cli_eval_run_refuses_a_repair_configuration(tmp_path: Path) -> None:
    result = cli.invoke(
        app,
        [
            "eval",
            "run",
            "--config",
            "opus-low",
            "--root",
            str(REPO_ROOT),
            "--results-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert "needs the repair loop (M3)" in result.output
    assert list(tmp_path.iterdir()) == []


def test_cli_eval_summary_unknown_experiment(tmp_path: Path) -> None:
    result = cli.invoke(
        app,
        ["eval", "summary", "dev/v9", "--root", str(REPO_ROOT), "--results-dir", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "no experiment dev/v9" in result.output


def test_cli_eval_summary_writes_both_files(
    tmp_path: Path,
    card_input: ReportInput,  # noqa: F811
) -> None:
    run_experiment(_plan(tmp_path), run=FakeRuns(card_input, ["dirty"] * 2))
    result = cli.invoke(
        app,
        [
            "eval",
            "summary",
            "dev/baseline",
            "--root",
            str(REPO_ROOT),
            "--results-dir",
            str(tmp_path / "evals"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "clean runs 0 of 2" in result.output
    variant = tmp_path / "evals" / "dev" / "baseline"
    assert (variant / "experiment-summary.json").is_file()
    assert (variant / "experiment-summary.md").read_text().startswith("# Experiment summary")


def test_usage_adds_up() -> None:
    total = Usage(input_tokens=1, output_tokens=2) + Usage(input_tokens=3)
    assert (total.input_tokens, total.output_tokens) == (4, 2)


def test_spec_fixture_is_mui(spec: MigrationSpec) -> None:
    assert spec.id == CASE.migration


def test_deadline_runner_stops_a_run_past_its_ceiling(tmp_path: Path) -> None:
    from migrator.execs import DeadlineRunner
    from tests.conftest import FakeRunner

    inner = FakeRunner()
    runner = DeadlineRunner(inner, ceiling_s=60)
    assert runner.run("echo hi", tmp_path).ok
    runner.deadline = 0  # the ceiling has passed
    with pytest.raises(RunTimeoutError, match="ceiling"):
        runner.run("npm ci", tmp_path)
    assert inner.commands == ["echo hi"]
