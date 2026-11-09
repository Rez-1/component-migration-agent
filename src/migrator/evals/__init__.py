"""Evals: cases, the experiment runner and its results layout.

An experiment is every run of one configuration over a split's cases, each case
repeated (2 by default, per the brief). Each run is a full dry run with its own fresh
workspace. Results are written in the ``claude-api`` skill's ``build-eval`` layout so
its report viewer works on them:

    <results>/<split>/                 a "flow": one per split
        _state.json                    metric and perf-field declarations for the viewer
        baseline/ | v<N>/              one "variant" per experiment
            experiment.json            the manifest: configuration, cases, repeats
            results.jsonl              one row per scored run (case x rep)
            errors.jsonl               runs that produced no score, with a failure class
            traces/<case>_rep<k>.json  the run as viewer turns (stages, rule steps)
            runs/<case>_rep<k>/        the run's own files: scorecard.json/.md, logs
            summary.json               the viewer's variant header
            change.md, change.patch    for a non-Baseline experiment: its configuration

The Baseline experiment lives in ``baseline/``; every other experiment gets the next
``v<N>`` (the viewer ignores any other name). Experiment ids are ``<split>/<variant>``.
"""

from __future__ import annotations

import difflib
import json
import re
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from migrator import __version__
from migrator.config import CaseConfig, load_case
from migrator.configuration import Configuration, ensure_runnable
from migrator.cost import CostPreflight, NoLedgerPreflight, PlannedExperiment, Usage
from migrator.execs import CommandRunner, RunTimeoutError
from migrator.migrations import MigrationSpec, available_specs
from migrator.pipeline import RunError, RunOptions, RunResult, dry_run, new_run_id
from migrator.report import Scorecard

MANIFEST_VERSION = 1
DEFAULT_REPEATS = 2
DEFAULT_CEILING_S = 1800.0
Split = Literal["dev", "held-out"]

# Viewer declarations (build-eval _state.json). The first binary metric is the
# viewer's headline, so clean_run comes first (ticket #10).
METRICS: list[dict[str, Any]] = [
    {"id": "clean_run", "label": "Clean run", "kind": "binary"},
    {"id": "migrated_share", "label": "Migrated share", "kind": "float", "scale": 1},
    {"id": "repair_traps_expected", "label": "Repair traps", "kind": "float", "scale": 1},
    {
        "id": "cheating_hits",
        "label": "Cheating hits",
        "kind": "float",
        "scale": 10,
        "better": "lower",
    },
    {"id": "regressions", "label": "Regressions", "kind": "float", "scale": 10, "better": "lower"},
]
PERF_FIELDS: list[dict[str, str]] = [
    {"id": "cost_usd", "label": "Cost", "unit": "$"},
    {"id": "latency_s", "label": "Time", "unit": "s"},
    {"id": "tool_calls", "label": "Tool calls"},
]


class EvalError(RuntimeError):
    """An experiment cannot start: no cases, an unknown experiment, a changed config."""


# --------------------------------------------------------------------------- cases


def load_cases(cases_dir: Path, split: Split, case_id: str | None = None) -> list[CaseConfig]:
    """The cases of one split (or the one named case, which must be in that split)."""
    cases = [load_case(p) for p in sorted(cases_dir.glob("*/case.toml"))]
    if case_id is not None:
        chosen = [c for c in cases if c.id == case_id]
        if not chosen:
            known = ", ".join(c.id for c in cases) or "none"
            raise EvalError(f"no case {case_id!r} in {cases_dir} (known: {known})")
        if chosen[0].split != split:
            raise EvalError(f"case {case_id!r} is in the {chosen[0].split} split, not {split}")
        return chosen
    picked = [c for c in cases if c.split == split]
    if not picked:
        raise EvalError(f"no {split} cases in {cases_dir}")
    return picked


def spec_for(case: CaseConfig) -> MigrationSpec:
    for spec in available_specs():
        if spec.id == case.migration:
            return spec
    raise EvalError(f"case {case.id!r} names an unknown migration {case.migration!r}")


def case_prompt(case: CaseConfig, spec: MigrationSpec) -> str:
    return f"Migrate {case.source} from {spec.from_} to {spec.to}"


# --------------------------------------------------------------------------- records


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Manifest(_Model):
    schema_version: int = MANIFEST_VERSION
    experiment: str  # <split>/<variant>
    split: Split
    configuration: str
    configuration_digest: str
    configuration_data: dict[str, Any]
    cases: list[str]
    repeats: int
    created_at: str
    migrator_version: str


class ResultRow(_Model):
    """One scored run, in the build-eval ``results.jsonl`` shape."""

    prompt_id: str  # the case id
    prompt: str
    tags: list[str]
    rep: int  # 0-based, as in traces/<id>_rep<k>.json
    status: Literal["ok"]
    stop_reason: str | None  # the repair agent's last stop reason; None without one
    grade: dict[str, float]
    model: str | None  # from the responses; None when no model was called
    usage: Usage
    cost_usd: float
    latency_s: float
    tool_calls: int
    meta: dict[str, Any]


FailureClass = Literal["case_rejected", "rules_failure", "timeout", "harness"]


class ErrorRow(_Model):
    """A run that produced no score: never averaged in as a failure of the system."""

    prompt_id: str
    rep: int
    failure_class: FailureClass
    message: str
    model: str | None = None
    usage: Usage = Usage()
    at: str
    meta: dict[str, Any] = {}


def grade(card: Scorecard) -> dict[str, float]:
    """The run's grade dict: clean_run first (the viewer's headline), then the rest."""
    h = card.headline
    out: dict[str, float] = {
        "clean_run": 1.0 if h.clean_run else 0.0,
        "migrated_share": h.migrated_without_human.share,
    }
    if card.traps is not None:
        agent = [t for t in card.traps if t.expected_layer == "agent"]
        if agent:
            expected = sum(t.result == "Expected" for t in agent)
            out["repair_traps_expected"] = round(expected / len(agent), 4)
    out["cheating_hits"] = float(h.cheating_check_hits)
    out["regressions"] = float(h.regressions)
    return out


def result_row(
    case: CaseConfig, spec: MigrationSpec, rep: int, card: Scorecard, scorecard_path: str
) -> ResultRow:
    cost = card.cost
    return ResultRow(
        prompt_id=case.id,
        prompt=case_prompt(case, spec),
        tags=["fixture" if case.traps else "repo", case.split],
        rep=rep,
        status="ok",
        stop_reason=None,
        grade=grade(card),
        model=(cost.models[0] if len(cost.models) == 1 else None) if cost.models else None,
        usage=cost.usage,
        cost_usd=cost.total_usd,
        latency_s=card.meta.duration_s,
        tool_calls=0,  # repair-agent tool calls (M3); the Baseline makes none
        meta={
            "run_id": card.meta.run_id,
            "configuration": card.configuration,
            "configuration_digest": card.configuration_digest,
            "scorecard": scorecard_path,
            "models": cost.models,
        },
    )


def trace_turns(card: Scorecard, config: Configuration, prompt: str) -> list[dict[str, Any]]:
    """The run as build-eval viewer turns: one tool call and result per stage step."""
    repair = (
        f"repair on ({', '.join(config.repair.attempt_models)}, effort {config.repair.effort})"
        if config.repair.enabled
        else "repair off"
    )
    turns: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": f"Configuration `{config.name}` ({config.digest()}): "
            f"{config.description} Rules on, {repair}.",
        },
        {"role": "user", "content": prompt},
    ]

    def step(name: str, args: Any, result: Any) -> None:
        turns.append({"role": "tool_call", "name": name, "content": json.dumps(args, indent=2)})
        turns.append({"role": "tool_result", "name": name, "content": json.dumps(result, indent=2)})

    pre = card.precheck
    step(
        "pre-check",
        [c.command for c in pre.commands],
        {
            "status": pre.status,
            "reason": pre.reason,
            "pre_existing_failures": len(pre.pre_existing_failures),
            "test_totals": pre.test_totals.model_dump() if pre.test_totals else None,
        },
    )
    if card.rules:
        for s in card.rules.steps:
            step(
                f"rule step: {s.kind}" + ("" if s.name == s.kind else f" {s.name}"),
                {"kind": s.kind, "name": s.name},
                {"status": s.status, "detail": s.detail, "changed_files": s.changed_files},
            )
    if card.verify:
        step(
            "verify",
            [c.command for c in card.verify.commands],
            {
                "failures": [f.model_dump(exclude_none=True) for f in card.verify.failures],
                "test_totals": card.verify.test_totals.model_dump()
                if card.verify.test_totals
                else None,
            },
        )
    if card.cheating:
        step(
            "cheating checks",
            {"test_files": len(card.cheating.test_files)},
            {
                "hits": [f.model_dump() for f in card.cheating.hits],
                "warnings": [f.model_dump() for f in card.cheating.warnings],
                "notes": [f.model_dump() for f in card.cheating.notes],
            },
        )
    from migrator.report import render_scorecard

    turns.append({"role": "assistant", "content": render_scorecard(card)})
    return turns


# --------------------------------------------------------------------------- layout


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append(path: Path, model: BaseModel) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(model.model_dump(mode="json"), ensure_ascii=False) + "\n")


def read_rows(variant: Path) -> list[ResultRow]:
    path = variant / "results.jsonl"
    if not path.is_file():
        return []
    return [
        ResultRow.model_validate_json(line) for line in path.read_text("utf-8").splitlines() if line
    ]


def read_errors(variant: Path) -> list[ErrorRow]:
    path = variant / "errors.jsonl"
    if not path.is_file():
        return []
    return [
        ErrorRow.model_validate_json(line) for line in path.read_text("utf-8").splitlines() if line
    ]


def read_manifest(variant: Path) -> Manifest:
    path = variant / "experiment.json"
    if not path.is_file():
        raise EvalError(f"{variant} is not an experiment (no experiment.json)")
    return Manifest.model_validate_json(path.read_text("utf-8"))


def experiment_dir(results_dir: Path, experiment: str) -> Path:
    """``dev/baseline`` -> ``<results>/dev/baseline``; a path works too."""
    as_path = Path(experiment)
    if as_path.is_dir() and (as_path / "experiment.json").is_file():
        return as_path.resolve()
    if not re.fullmatch(r"(dev|held-out)/(baseline|v\d+)", experiment):
        raise EvalError(
            f"{experiment!r} is not an experiment id (<split>/baseline or <split>/v<N>) "
            "or an experiment folder"
        )
    path = results_dir / experiment
    if not (path / "experiment.json").is_file():
        raise EvalError(f"no experiment {experiment} in {results_dir}")
    return path.resolve()


def _next_variant(flow: Path, config: Configuration) -> str:
    if config.name == "baseline" and not (flow / "baseline").exists():
        return "baseline"
    numbers = [int(p.name[1:]) for p in flow.glob("v*") if p.is_dir() and p.name[1:].isdigit()]
    return f"v{max(numbers, default=0) + 1}"


def _write_state(flow: Path) -> None:
    state = flow / "_state.json"
    data: dict[str, Any] = {}
    if state.is_file():
        data = json.loads(state.read_text("utf-8"))
    data.update({"metrics": METRICS, "perf_fields": PERF_FIELDS})
    state.write_text(json.dumps(data, indent=2) + "\n", "utf-8")


def _write_variant_header(
    variant: Path, config: Configuration, baseline_config: Configuration | None
) -> None:
    (variant / "summary.json").write_text(
        json.dumps(
            {"label": config.name, "description": config.description, "target": "code"}, indent=2
        )
        + "\n",
        "utf-8",
    )
    if variant.name == "baseline" or config.path is None:
        return
    lines = [f"configuration `{config.name}`: {config.description}", ""]
    patch = ""
    if baseline_config is not None and baseline_config.path is not None:
        old = baseline_config.path.read_text("utf-8").splitlines(keepends=True)
        new = config.path.read_text("utf-8").splitlines(keepends=True)
        rel_old = f"evals/configs/{baseline_config.path.name}"
        rel_new = f"evals/configs/{config.path.name}"
        patch = "".join(difflib.unified_diff(old, new, rel_old, rel_new))
        lines.append(f"Compared with `{baseline_config.name}`: see change.patch.")
    (variant / "change.md").write_text("\n".join(lines) + "\n", "utf-8")
    (variant / "change.patch").write_text(patch, "utf-8")


# --------------------------------------------------------------------------- runner


class RunEvent(BaseModel):
    case: str
    rep: int
    kind: Literal["start", "scored", "error", "skipped", "stage"]
    message: str = ""


RunFn = Callable[[RunOptions, CommandRunner | None], RunResult]


def _default_run(opts: RunOptions, runner: CommandRunner | None) -> RunResult:
    return dry_run(opts, runner)


class ExperimentPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    root: Path  # the repository root that case sources are relative to
    results_dir: Path
    split: Split
    configuration: Configuration
    cases: list[CaseConfig]
    repeats: int = DEFAULT_REPEATS
    resume: str | None = None  # an experiment id to continue
    baseline_configuration: Configuration | None = None  # for change.patch
    max_cost_usd: float | None = None
    ceiling_s: float = DEFAULT_CEILING_S
    tools_cache: Path | None = None


class ExperimentOutcome(BaseModel):
    experiment: str
    path: Path
    scored: int
    errors: int
    skipped: int


def run_experiment(
    plan: ExperimentPlan,
    *,
    preflight: CostPreflight | None = None,
    run: RunFn = _default_run,
    runner: CommandRunner | None = None,
    on_event: Callable[[RunEvent], None] | None = None,
) -> ExperimentOutcome:
    """Run (or resume) one experiment; each (case, rep) is written as it completes."""
    config = plan.configuration
    ensure_runnable(config)  # a repair configuration fails here, before anything runs
    if plan.repeats < 1:
        raise EvalError("repeats must be at least 1")
    emit = on_event or (lambda _e: None)
    flow = plan.results_dir / plan.split

    if plan.resume is not None:
        variant = experiment_dir(plan.results_dir, plan.resume)
        manifest = read_manifest(variant)
        if manifest.configuration_digest != config.digest():
            raise EvalError(
                f"{manifest.experiment} ran configuration {manifest.configuration!r} "
                f"({manifest.configuration_digest}); {config.name!r} is now "
                f"{config.digest()}, so its results would not be comparable"
            )
        case_ids = manifest.cases
        repeats = manifest.repeats
        cases = [c for c in plan.cases if c.id in case_ids]
        if len(cases) != len(case_ids):
            raise EvalError(f"{manifest.experiment} has cases that no longer exist")
    else:
        flow.mkdir(parents=True, exist_ok=True)
        variant = flow / _next_variant(flow, config)
        variant.mkdir()
        cases, repeats = plan.cases, plan.repeats
        manifest = Manifest(
            experiment=f"{plan.split}/{variant.name}",
            split=plan.split,
            configuration=config.name,
            configuration_digest=config.digest(),
            configuration_data=config.model_dump(mode="json"),
            cases=[c.id for c in cases],
            repeats=repeats,
            created_at=now(),
            migrator_version=__version__,
        )
        (variant / "experiment.json").write_text(manifest.model_dump_json(indent=2) + "\n", "utf-8")
        _write_state(flow)
        _write_variant_header(variant, config, plan.baseline_configuration)

    done = {(r.prompt_id, r.rep) for r in read_rows(variant)}
    todo = [(c, rep) for c in cases for rep in range(repeats) if (c.id, rep) not in done]
    pre = (preflight or NoLedgerPreflight()).check(
        PlannedExperiment(
            configuration=config.name,
            uses_llm=config.uses_llm,
            runs=len(todo),
            max_cost_usd=plan.max_cost_usd,
        )
    )
    if not pre.ok:
        raise EvalError(f"cost pre-flight refused the experiment: {pre.reason}")

    (variant / "traces").mkdir(exist_ok=True)
    scored = errors = 0
    for case, rep in [(c, r) for c in cases for r in range(repeats)]:
        if (case.id, rep) in done:
            emit(RunEvent(case=case.id, rep=rep, kind="skipped", message="already scored"))
            continue
        key = f"{case.id}_rep{rep}"
        run_dir = variant / "runs" / key
        emit(RunEvent(case=case.id, rep=rep, kind="start"))
        spec = spec_for(case)
        opts = RunOptions(
            repo=(plan.root / case.source).resolve(),
            spec=spec,
            run_dir=run_dir,
            case=case,
            configuration=config,
            ceiling_s=plan.ceiling_s,
            tools_cache=plan.tools_cache,
            run_id=new_run_id(),
        )
        started = time.monotonic()
        failure: tuple[FailureClass, str] | None = None
        card: Scorecard | None = None
        try:
            card = run(opts, runner).scorecard
        except RunTimeoutError as exc:
            failure = ("timeout", str(exc))
        except RunError as exc:
            failure = ("case_rejected", str(exc))
        except Exception as exc:  # a harness bug must not cost the rest of the experiment
            failure = ("harness", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        if card is not None and card.status != "completed":
            failure = (
                "case_rejected" if card.status == "rejected" else "rules_failure",
                card.reason or card.status,
            )
        scorecard_path = f"{variant.name}/runs/{key}/scorecard.json"
        if failure is not None:
            errors += 1
            _append(
                variant / "errors.jsonl",
                ErrorRow(
                    prompt_id=case.id,
                    rep=rep,
                    failure_class=failure[0],
                    message=failure[1],
                    at=now(),
                    meta={
                        "elapsed_s": round(time.monotonic() - started, 1),
                        "scorecard": scorecard_path if card is not None else None,
                    },
                ),
            )
            emit(
                RunEvent(
                    case=case.id,
                    rep=rep,
                    kind="error",
                    message=f"{failure[0]}: {failure[1].splitlines()[0]}",
                )
            )
            continue
        assert card is not None
        prompt = case_prompt(case, spec)
        (variant / "traces" / f"{key}.json").write_text(
            json.dumps(trace_turns(card, config, prompt), indent=2, ensure_ascii=False) + "\n",
            "utf-8",
        )
        _append(variant / "results.jsonl", result_row(case, spec, rep, card, scorecard_path))
        scored += 1
        h = card.headline
        emit(
            RunEvent(
                case=case.id,
                rep=rep,
                kind="scored",
                message=f"clean run {'yes' if h.clean_run else 'no'}, "
                f"{h.migrated_without_human.count}/{h.migrated_without_human.total} migrated "
                f"without a human, {h.cheating_check_hits} cheating-check hits",
            )
        )
    return ExperimentOutcome(
        experiment=manifest.experiment,
        path=variant,
        scored=scored,
        errors=errors,
        skipped=len(done),
    )
