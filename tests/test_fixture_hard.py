"""The second dev fixture (fixtures/mui4-app-hard): fast checks on its files and case.

The slow end-to-end oracle replay is in ``tests/test_oracle_hard_slow.py``.
"""

from __future__ import annotations

import yaml

from migrator.config import load_case, load_traps
from tests.conftest import REPO_ROOT
from tests.test_repair import GLOSSARY_WORDS, TRAP_WORDS

FIXTURE_HARD = REPO_ROOT / "fixtures" / "mui4-app-hard"
CASE_HARD = REPO_ROOT / "evals" / "cases" / "fixture-mui4-hard"


def test_nothing_in_the_hard_fixture_describes_the_traps() -> None:
    """As for fixture-mui4: the whole fixture is copied into the workspace, where
    read_file can reach it, so no file may describe the traps."""
    leaks = []
    for path in sorted(FIXTURE_HARD.rglob("*")):
        if "node_modules" in path.parts or not path.is_file() or path.name == "package-lock.json":
            continue
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if TRAP_WORDS.search(line) or GLOSSARY_WORDS.search(line):
                leaks.append(f"{path.relative_to(FIXTURE_HARD)}:{i}: {line.strip()}")
    assert leaks == []
    assert not (FIXTURE_HARD / "traps.yaml").exists()


def test_the_hard_case_loads_as_a_dev_case() -> None:
    case = load_case(CASE_HARD / "case.toml")
    assert case.split == "dev"
    traps = load_traps(CASE_HARD / "traps.yaml")
    raw = yaml.safe_load((CASE_HARD / "traps.yaml").read_text())
    layers = [t.expected_layer for t in traps.traps]
    assert {k: layers.count(k) for k in raw["counts"]} == raw["counts"]
    assert len({t.id for t in traps.traps}) == len(traps.traps)
    for trap in traps.traps:
        assert (FIXTURE_HARD / trap.location.file).is_file(), trap.id
        if trap.expected_layer == "agent":
            assert trap.checks(), trap.id  # every agent trap fails verify when left


def test_the_hard_reference_covers_every_agent_trap_minimally() -> None:
    fixes = yaml.safe_load((CASE_HARD / "reference" / "agent-fixes.yaml").read_text())
    traps = load_traps(CASE_HARD / "traps.yaml")
    agent = {t.id: t for t in traps.traps if t.expected_layer == "agent"}
    assert sorted(t for f in fixes["files"] for t in f["traps"]) == sorted(agent)
    for entry in fixes["files"]:
        for trap_id in entry["traps"]:
            # the trap's file is the failing file or one the edits change
            touched = {e["path"] for e in entry["edits"]}
            assert agent[trap_id].location.file in touched, trap_id
        changed = sum(
            max(len(e["old"].splitlines()), len(e["new"].splitlines())) for e in entry["edits"]
        )
        assert changed <= 30, entry["path"]  # far below the 60-line hand-off limit
