"""The Docker sandbox for real (``pytest -m docker``): needs a running Docker and the
network once, to pull the pinned node image and install the fixture's packages.

The Baseline on the fixture inside Docker (Node 20, the case's declared version) must
score exactly the committed expected scorecard, which was recorded on the local Node 24.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrator.config import load_case
from migrator.execs import DockerRunner, docker_available, node_image
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunOptions, dry_run
from migrator.report import stable_view
from tests.conftest import FIXTURE, FIXTURE_CASE, REPO_ROOT

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not docker_available(), reason="needs a running Docker"),
]


def test_the_container_is_offline_non_root_and_read_only(tmp_path: Path) -> None:
    runner = DockerRunner(node_image("20"))
    offline = runner.run(
        ["node", "-e", "require('dns').lookup('registry.npmjs.org', e => process.exit(e ? 0 : 1))"],
        tmp_path,
    )
    assert offline.ok, "a verify command could resolve a host name"
    assert runner.run(["id", "-u"], tmp_path).output.strip() != "0"
    assert not runner.run(["touch", "/etc/x"], tmp_path).ok  # read-only root filesystem
    assert not runner.run(["ls", str(Path.home())], tmp_path).ok  # only the workspace is mounted
    wrote = runner.run("echo hi > out.txt", tmp_path)
    assert wrote.ok and (tmp_path / "out.txt").read_text() == "hi\n"


def test_the_baseline_in_docker_scores_the_committed_scorecard(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    result = dry_run(
        RunOptions(
            repo=FIXTURE,
            spec=spec,
            run_dir=tmp_path / "run",
            case=load_case(FIXTURE_CASE / "case.toml"),
            sandbox="docker",
        )
    )
    card = result.scorecard
    assert card.meta.sandbox == "docker"
    assert card.meta.node_version is not None and card.meta.node_version.startswith("20.")
    expected = json.loads((REPO_ROOT / "docs/results/baseline/scorecard.json").read_text())
    assert stable_view(card) == stable_view(expected)
    logs = tmp_path / "run" / "logs"
    assert "network bridge" in (logs / "precheck-install.log").read_text()
    for name in ("verify-typecheck.log", "verify-lint.log", "verify-test.log"):
        assert "network none" in (logs / name).read_text(), name
