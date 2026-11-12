"""Scoring goldens (issue #17): runs whose evidence and Scorecard are kept, so Scoring
can be checked on replayed runs. Each golden is a folder under ``tests/data/scoring/``
with the run's ``report-input.json`` and ``expected.json``, the ``stable_view`` of the
Scorecard that run wrote.

Capturing is opt-in. ``MIGRATOR_CAPTURE_SCORING=<folder> uv run pytest ...`` saves every
run a test makes (see ``conftest.py``); ``python -m tests.scoring_goldens <run dir>
<golden dir>`` saves one run folder, such as a Docker Baseline's. Machine paths (the
run folder, the test's temp folder, this checkout) are replaced by placeholders in both files, so a
golden reads the same on every machine.

The set (captured on 11 November 2026, before Scoring moved to ``migrator.scoring``):
``graph-*`` from the fake-toolchain graph tests, ``oracle-*`` from the scripted oracle
runs on the fixtures (``-m slow``, no model), ``docker-baseline-*`` from the Baseline
(``--config baseline``, no model) in Docker on the three MUI fixture cases and the
Angular fixture, and ``synthetic-*``, evidence built by hand from ``test_report``'s
inputs for what no free run reaches: a cheating-check hit, a Rules failure, Rules that
never ran, a rejected Pre-check.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from migrator.run.stages.report import EVIDENCE_FILE
from migrator.scoring import stable_view

GOLDENS = Path(__file__).parent / "data" / "scoring"
EXPECTED = "expected.json"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _placeholders(text: str, paths: dict[str, Path]) -> str:
    # Longest first, so a folder inside another one gets its own name.
    pairs = {str(p.resolve()): name for name, p in paths.items()}
    pairs.update({str(p): name for name, p in paths.items()})
    for raw in sorted(pairs, key=len, reverse=True):
        text = text.replace(raw, pairs[raw])
    return text


def save_golden(run_dir: Path, dest: Path, paths: dict[str, Path] | None = None) -> None:
    """Copy one run's evidence and its Scorecard's stable view to ``dest``."""
    names = {"<repo>": REPO_ROOT, "<run>": run_dir, **(paths or {})}
    card = json.loads((run_dir / "scorecard.json").read_text("utf-8"))
    expected = json.dumps(stable_view(card), indent=2, ensure_ascii=False) + "\n"
    evidence = (run_dir / EVIDENCE_FILE).read_text("utf-8")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / EVIDENCE_FILE).write_text(_placeholders(evidence, names), "utf-8")
    (dest / EXPECTED).write_text(_placeholders(expected, names), "utf-8")


if __name__ == "__main__":
    save_golden(Path(sys.argv[1]), Path(sys.argv[2]))
