"""The held-out fixture case (``evals/cases/fixture-mui4-holdout``): its data, no LLM, no Node.

The case is a second purpose-built app that the hill-climb never sees; these checks keep
its trap list, its oracle and the fixture itself honest. The slow runs are in
``tests/test_holdout_slow.py``.
"""

from __future__ import annotations

import yaml

from migrator.config import load_case, load_traps
from tests.conftest import FIXTURE_CASE, REPO_ROOT
from tests.test_repair import GLOSSARY_WORDS, TRAP_WORDS

HOLDOUT = REPO_ROOT / "fixtures" / "mui4-app-holdout"
HOLDOUT_CASE = REPO_ROOT / "evals" / "cases" / "fixture-mui4-holdout"


def test_nothing_in_the_holdout_fixture_describes_the_traps() -> None:
    """The same rule as fixture-mui4's (M2 audit, finding #3): every fixture file is
    copied into the workspace, where read_file can reach it."""
    leaks = []
    for path in sorted(HOLDOUT.rglob("*")):
        if "node_modules" in path.parts or not path.is_file() or path.name == "package-lock.json":
            continue
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if TRAP_WORDS.search(line) or GLOSSARY_WORDS.search(line) or "migrat" in line.lower():
                leaks.append(f"{path.relative_to(HOLDOUT)}:{i}: {line.strip()}")
    assert leaks == []
    assert not (HOLDOUT / "traps.yaml").exists()
    assert not (HOLDOUT / "reference").exists()


def test_the_holdout_case_is_held_out() -> None:
    case = load_case(HOLDOUT_CASE / "case.toml")
    assert (case.id, case.split, case.source) == (
        "fixture-mui4-holdout",
        "held-out",
        "fixtures/mui4-app-holdout",
    )
    assert case.traps_path() == HOLDOUT_CASE / "traps.yaml"


def test_holdout_traps_load_and_each_scored_trap_has_a_check() -> None:
    traps = load_traps(HOLDOUT_CASE / "traps.yaml").traps
    layers = [t.expected_layer for t in traps]
    assert {layer: layers.count(layer) for layer in set(layers)} == {
        "rules": 8,
        "agent": 6,
        "human": 1,
        "visual-only": 1,
    }
    for trap in traps:
        assert (HOLDOUT / trap.location.file).is_file(), trap.id
        if trap.expected_layer in ("agent", "human"):
            assert trap.checks(), trap.id
        else:
            assert trap.checks() == [], trap.id


def test_holdout_mostly_plants_breaking_changes_fixture_1_does_not() -> None:
    """At least half the breaking changes differ from fixture-mui4's, so the case
    measures generalisation, not memory; ``in_fixture_1`` must say so truthfully."""

    holdout = yaml.safe_load((HOLDOUT_CASE / "traps.yaml").read_text("utf-8"))["traps"]
    dev_traps = yaml.safe_load((FIXTURE_CASE / "traps.yaml").read_text("utf-8"))["traps"]
    dev = {t["breaking_change"]["section"] for t in dev_traps}
    for trap in holdout:
        assert trap["in_fixture_1"] == (trap["breaking_change"]["section"] in dev), trap["id"]
    shared = [t for t in holdout if t["in_fixture_1"]]
    assert len(shared) * 2 < len(holdout)


def test_the_holdout_oracle_covers_every_agent_trap() -> None:
    fixes = yaml.safe_load((HOLDOUT_CASE / "reference" / "agent-fixes.yaml").read_text())
    human = yaml.safe_load((HOLDOUT_CASE / "reference" / "human-fix.yaml").read_text())
    traps = load_traps(HOLDOUT_CASE / "traps.yaml").traps
    agent = {t.id for t in traps if t.expected_layer == "agent"}
    assert {t for f in fixes["files"] for t in f["traps"]} == agent
    for entry in fixes["files"]:
        assert all(e["path"] == entry["path"] for e in entry["edits"]), entry["path"]
    (human_trap,) = [t for t in traps if t.expected_layer == "human"]
    assert human["handed_off"] == human_trap.location.file
    assert all("__tests__" in e["path"] for e in human["edits"])  # a Test file
