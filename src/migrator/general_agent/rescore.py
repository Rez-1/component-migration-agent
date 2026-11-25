"""Re-score finished general-agent runs with the codemod baseline (M8).

The runs before ``general_agent.baseline`` were checked against the untouched workspace,
so a line the codemod writes failed them. This recomputes their cheating checks the way
the final Verify now does, from what each run saved (its untouched and final files, its
Evidence), and writes the Scorecard and the experiment's result rows again. Nothing is
run again but the codemods, on a clone of the case's Pre-check workspace.

Before it changes anything it checks itself: the checks with the old baseline must give
each run's recorded findings exactly, or the run is left as it was.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from migrator.checks import (
    CheatingReport,
    CheckInput,
    FileSet,
    Layer,
    read_test_rules,
    run_checks,
)
from migrator.config import CaseConfig
from migrator.evals import (
    EvalError,
    read_manifest,
    read_rows,
    result_row,
    spec_for,
)
from migrator.execs import LocalRunner
from migrator.general_agent.baseline import BASELINE_FILE, cheating_start, codemod_baseline
from migrator.report import render_scorecard, write_json
from migrator.rules import ensure_tools, tools_cache_root
from migrator.run.evidence import EVIDENCE_FILE, write_evidence
from migrator.run.files import load_files, save_files
from migrator.scan import UsageReport
from migrator.scoring import Scorecard, score
from migrator.scoring.evidence import Evidence


class Rescored(BaseModel):
    run: str
    status: str  # "rescored", or why it was left as it was
    hits_before: int = 0
    hits_after: int = 0
    clean_before: bool = False
    clean_after: bool = False


def _precheck_workspace(untouched: FileSet, cache_root: Path) -> Path | None:
    """The cached Pre-check workspace of the same untouched code (it has the installed
    packages the codemods need)."""
    for entry in sorted((cache_root / "precheck").glob("*/untouched.json")):
        if load_files(entry) == untouched and (entry.parent / "workspace").is_dir():
            return entry.parent / "workspace"
    return None


def _checks(
    evidence: Evidence, start: FileSet, untouched: FileSet, final: FileSet, workspace: Path
) -> CheatingReport:
    layers: dict[str, Layer] = {
        p: "agent" for p in start.keys() | final.keys() if start.get(p) != final.get(p)
    }
    return run_checks(
        CheckInput(
            before=untouched,
            after_rules=start,
            final=final,
            later_layers=layers,
            test_rules=read_test_rules(workspace),
            precheck_totals=evidence.precheck.test_totals,
            final_totals=evidence.verify.test_totals if evidence.verify else None,
        )
    )


def rescore_run(run_dir: Path, case: CaseConfig) -> tuple[Rescored, Evidence | None]:
    name = run_dir.name
    if not (run_dir / "general-agent" / "run.json").is_file():
        return Rescored(run=name, status="not a general-agent run"), None
    evidence = Evidence.model_validate_json((run_dir / EVIDENCE_FILE).read_text("utf-8"))
    if evidence.cheating is None:
        return Rescored(run=name, status="no cheating checks recorded"), None
    untouched = load_files(run_dir / "state" / "untouched.json")
    final = load_files(run_dir / "state" / "final.json")
    cache_root = tools_cache_root()
    workspace = _precheck_workspace(untouched, cache_root)
    if workspace is None:
        return Rescored(run=name, status="no Pre-check workspace of this code in the cache"), None
    old = _checks(evidence, untouched, untouched, final, workspace)
    if old.model_dump() != evidence.cheating.model_dump():
        return Rescored(run=name, status="the old checks don't reproduce its findings"), None
    spec = spec_for(case)
    baseline_path = run_dir / "general-agent" / BASELINE_FILE
    baseline = load_files(baseline_path) or None
    if baseline is None:
        usage = UsageReport.model_validate_json((run_dir / "usage-report.json").read_text())
        from migrator.pipeline import resolve_config  # the pipeline imports this module's package

        config = resolve_config(workspace, spec, case)
        baseline, note = codemod_baseline(
            workspace=workspace,
            spec=spec,
            config=config,
            affected_files=usage.affected_files(),
            tools_dir=ensure_tools(spec, LocalRunner(), cache_root) if spec.tools else None,
            runner=LocalRunner(),
            scratch=run_dir / "general-agent" / "codemod-baseline",
        )
        if baseline is None:
            return Rescored(run=name, status=f"no codemod baseline: {note}"), None
        save_files(baseline_path, baseline)
    new = _checks(evidence, cheating_start(untouched, baseline, final), untouched, final, workspace)
    before = score(evidence)
    rescored = evidence.model_copy(update={"cheating": new})
    after = score(rescored)
    write_evidence(rescored, run_dir / EVIDENCE_FILE)
    write_json(after, run_dir / "scorecard.json")
    (run_dir / "scorecard.md").write_text(render_scorecard(after), "utf-8")
    return (
        Rescored(
            run=name,
            status="rescored",
            hits_before=len(evidence.cheating.hits),
            hits_after=len(new.hits),
            clean_before=before.headline.clean_run,
            clean_after=after.headline.clean_run,
        ),
        rescored,
    )


def rescore_experiment(variant: Path, cases: list[CaseConfig]) -> list[Rescored]:
    """Re-score every general-agent run of an experiment and rewrite its result rows."""
    manifest = read_manifest(variant)
    by_id = {c.id: c for c in cases}
    rows = read_rows(variant)
    done: list[Rescored] = []
    out: list[str] = []
    for row in rows:
        case = by_id.get(row.prompt_id)
        if case is None:
            raise EvalError(f"{manifest.experiment}: case {row.prompt_id!r} no longer exists")
        card_path = variant.parent / str(row.meta["scorecard"])  # relative to the split
        run_dir = card_path.parent
        found, _ = rescore_run(run_dir, case)
        done.append(found)
        if found.status == "rescored":
            card = Scorecard.model_validate_json(card_path.read_text("utf-8"))
            path = str(row.meta["scorecard"])
            row = result_row(case, spec_for(case), row.rep, card, path, run_dir)
        out.append(row.model_dump_json())
    (variant / "results.jsonl").write_text("".join(line + "\n" for line in out), "utf-8")
    (variant / "rescored.json").write_text(
        json.dumps([d.model_dump() for d in done], indent=2) + "\n", "utf-8"
    )
    return done
