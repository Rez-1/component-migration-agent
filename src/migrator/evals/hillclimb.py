"""Hill-climbing on the dev split: the ``claude-api`` skill's hillclimb loop, adapted.

The loop's state lives in a hillclimb *flow* folder, ``.claude/hillclimb/dev/`` by
default, which is also the eval runner's results folder for the dev split (the runner
writes ``<results>/<split>/``, so ``--results-dir .claude/hillclimb`` puts each round's
``v<N>/`` next to ``_state.json``). ``migrator eval climb`` is the one command a round
runs; it wraps ``eval run`` and ``eval summary`` with the loop's gates:

- **Dev only.** Cases come from the dev split, discovered each round (a new dev case
  joins without code changes); the held-out split can't be climbed, and ``_state.json``
  never names a held-out case. Held-out runs once, at the end, with ``eval run --split
  held-out``. With one or two dev cases there is no train/test split: every dev case is
  read and scored each round, and every result is labelled *directional*.
- **Harness integrity.** A SHA-256 over ``harness_paths`` (the grader, the cheating
  checks, the traps, the fixtures, this module, the lockfile) must match the one a
  person last approved with ``--approve-harness``; otherwise the round refuses to run.
  It is a change detector, not a security boundary (the skill's wording): what bounds an
  unattended run is the command the user allows.
- **Approval per round.** With ``approve_each_round`` set, a round runs only with
  ``--approved``, which the orchestrator passes after the user said yes to that round's
  change and cost.
- **The keep rule** (the user's, 9 Nov 2026): a change is kept when quality (clean runs,
  repair traps Expected, regressions, cheating-check hits) is no worse than the best
  round's and either quality improves or cost per clean run drops. ``keep_verdict``
  computes it; the decision and the experiment log stay with the orchestrator.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from migrator.config import CaseConfig
from migrator.evals.summary import ExperimentSummary

STATE_FILE = "_state.json"
SKIP_DIRS = frozenset({"node_modules", ".git", "__pycache__", ".pytest_cache", ".venv"})
QUALITY = ("clean_rate", "repair_traps_expected", "regressions", "cheating_hits")
LOWER_IS_BETTER = frozenset({"regressions", "cheating_hits"})


class ClimbError(RuntimeError):
    """A round cannot run: the harness changed, it needs approval, or the state is off."""

    def __init__(self, message: str, *, code: int = 2):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- state


def read_state(flow: Path) -> dict[str, Any]:
    path = flow / STATE_FILE
    if not path.is_file():
        raise ClimbError(f"no hillclimb state at {path}; see experiments.md for the setup")
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return data


def write_state(flow: Path, state: dict[str, Any]) -> None:
    (flow / STATE_FILE).write_text(json.dumps(state, indent=2) + "\n", "utf-8")


# --------------------------------------------------------------------------- harness


def _files(root: Path, entry: str) -> list[Path]:
    path = root / entry
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    out: list[Path] = []
    for folder, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)  # never descend into them
        out.extend(Path(folder) / f for f in files)
    return sorted(out)


def harness_digest(root: Path, paths: Iterable[str]) -> tuple[str, list[str]]:
    """SHA-256 over every file under ``paths`` (relative to ``root``): each file's path
    and bytes, in sorted order. Returns the digest and the files it covered."""
    h = hashlib.sha256()
    covered: list[str] = []
    for entry in sorted(set(paths)):
        for p in _files(root, entry):
            rel = p.relative_to(root).as_posix()
            if rel in covered:
                continue
            covered.append(rel)
            h.update(rel.encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest(), covered


def check_harness(root: Path, state: dict[str, Any], *, approve: bool) -> str | None:
    """Refuse when the harness changed since the last approval; ``approve`` records the
    current digest instead (the user's step, never an unattended round's). Returns a
    note when it recorded one."""
    paths = [str(p) for p in state.get("harness_paths") or []]
    if not paths:
        raise ClimbError("_state.json lists no harness_paths, so the harness can't be checked")
    sha, covered = harness_digest(root, paths)
    if state.get("harness_sha") == sha:
        return None
    if approve:
        state["harness_sha"] = sha
        return f"harness approved: sha256 {sha[:12]} over {len(covered)} files"
    if state.get("harness_sha") is None:
        raise ClimbError(
            f"no approved harness digest yet (now {sha[:12]} over {len(covered)} files). "
            "Review the harness, then run once with --approve-harness."
        )
    raise ClimbError(
        f"the harness changed since it was approved ({str(state['harness_sha'])[:12]} -> "
        f"{sha[:12]}, over {len(covered)} files under {', '.join(sorted(paths))}). Review "
        "the diff, then re-run with --approve-harness."
    )


# --------------------------------------------------------------------------- cases


def sync_cases(state: dict[str, Any], cases: Sequence[CaseConfig]) -> str | None:
    """Point ``train_ids`` at the dev cases found now (no test split: every dev case is
    read and scored). Refuses a held-out case anywhere in the state. Returns a note when
    the dev set changed, which makes earlier rounds not comparable on the new set."""
    held_out = [c.id for c in cases if c.split != "dev"]
    if held_out:
        raise ClimbError(f"held-out cases can't be climbed: {', '.join(held_out)}")
    ids = [c.id for c in cases]
    named = [*state.get("train_ids", []), *state.get("test_ids", [])]
    stray = sorted(set(named) - set(ids) - set(state.get("retired_ids", [])))
    if state.get("test_ids"):
        raise ClimbError("_state.json has test_ids: the dev split is climbed without a test set")
    before = list(state.get("train_ids", []))
    state["train_ids"] = ids
    state["test_ids"] = []
    if before == ids:
        return None
    added = [i for i in ids if i not in before]
    note = f"dev cases now {', '.join(ids)}"
    if added and before:
        note += (
            f" ({', '.join(added)} joined: rounds before this one did not run "
            f"{'it' if len(added) == 1 else 'them'}; run the best configuration on the "
            "new set before comparing)"
        )
    if stray:
        note += f"; no longer found: {', '.join(stray)}"
    return note


def matching_baseline(flow: Path, case_ids: Sequence[str]) -> Path | None:
    """The latest rules-only Baseline experiment in the flow that ran exactly these
    cases (``baseline/`` first, then ``v<N>/`` in order), or None. When a dev case
    joins, the Baseline is re-run on the new set (free) and becomes the comparison."""
    from migrator.evals import read_manifest

    found: Path | None = None
    numbered = sorted(
        (p for p in flow.glob("v*") if p.name[1:].isdigit()), key=lambda p: int(p.name[1:])
    )
    variants = [flow / "baseline", *numbered]
    for variant in variants:
        if not (variant / "experiment.json").is_file():
            continue
        manifest = read_manifest(variant)
        if manifest.configuration == "baseline" and sorted(manifest.cases) == sorted(case_ids):
            found = variant
    return found


# --------------------------------------------------------------------------- keep rule


def quality(summary: ExperimentSummary) -> dict[str, float]:
    """The keep rule's quality numbers: the clean-run rate and three per-run means."""
    by_id = {m.id: m.mean for m in summary.metrics}
    runs = summary.runs_scored or 1
    return {
        "clean_rate": summary.clean_runs / runs,
        "repair_traps_expected": float(by_id.get("repair_traps_expected") or 0.0),
        "regressions": float(by_id.get("regressions") or 0.0),
        "cheating_hits": float(by_id.get("cheating_hits") or 0.0),
    }


class Verdict(BaseModel):
    keep: bool | None  # None when the two experiments are not comparable
    reason: str
    worse: list[str] = []
    better: list[str] = []
    cheaper: bool = False
    label: Literal["directional"] = "directional"


def keep_verdict(candidate: ExperimentSummary, best: ExperimentSummary) -> Verdict:
    """The user's keep rule: no quality number worse than the best round's, and quality
    better or cost per clean run lower. Same cases required; with n = 1-2 cases the
    verdict is directional, not a published result."""
    if sorted(candidate.cases) != sorted(best.cases):
        return Verdict(
            keep=None,
            reason=f"not comparable: cases {', '.join(candidate.cases)} vs "
            f"{', '.join(best.cases)} (re-run the best configuration on the current dev set)",
        )
    q, b = quality(candidate), quality(best)
    worse, better = [], []
    for key in QUALITY:
        diff = q[key] - b[key]
        if key in LOWER_IS_BETTER:
            diff = -diff
        if diff < -1e-9:
            worse.append(key)
        elif diff > 1e-9:
            better.append(key)
    cc, bc = candidate.cost.per_clean_run_usd, best.cost.per_clean_run_usd
    cheaper = cc is not None and bc is not None and cc < bc
    if worse:
        return Verdict(
            keep=False, reason=f"quality worse: {', '.join(worse)}", worse=worse, better=better
        )
    if better or cheaper:
        parts = ([f"quality better: {', '.join(better)}"] if better else []) + (
            [f"cost per clean run ${cc:.3f} < ${bc:.3f}"] if cheaper and cc and bc else []
        )
        return Verdict(keep=True, reason="; ".join(parts), better=better, cheaper=cheaper)
    cost = f"${cc:.3f} vs ${bc:.3f}" if cc is not None and bc is not None else "undefined"
    return Verdict(
        keep=False,
        reason=f"quality unchanged and cost per clean run not lower ({cost})",
    )


def record_round(
    state: dict[str, Any],
    *,
    variant: str,
    configuration: str,
    digest: str,
    cases: Sequence[str],
    verdict: Verdict | None,
) -> None:
    """Append the round to ``state["rounds"]`` (the orchestrator decides ``best``)."""
    rounds = list(state.get("rounds", []))
    rounds.append(
        {
            "variant": variant,
            "configuration": configuration,
            "configuration_digest": digest,
            "cases": list(cases),
            "verdict": verdict.model_dump() if verdict else None,
        }
    )
    state["rounds"] = rounds
    numbers = [int(r["variant"][1:]) for r in rounds if str(r["variant"]).startswith("v")]
    state["current_round"] = max(numbers, default=0)
