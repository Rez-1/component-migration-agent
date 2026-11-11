"""The Docker runner's command line and checks (fast: Docker itself is not called).

The slow, real-Docker tests are in ``test_docker_slow.py`` (``pytest -m docker``).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from migrator.execs import (
    NODE_IMAGES,
    DockerRunner,
    SandboxError,
    needs_network,
    node_image,
    settle,
)
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunError, RunOptions, start_run
from tests.fakes import make_mini_repo


def runner(tmp_path: Path) -> DockerRunner:
    return DockerRunner(node_image("20"), read_only=[tmp_path / "tools"], user="501:20")


def mounts(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv) if a == "--mount"]


def test_only_installs_get_a_network() -> None:
    assert needs_network(["npm", "ci", "--no-audit"])
    assert needs_network(["pnpm", "install", "--frozen-lockfile"])
    assert not needs_network("npm ci && curl evil")  # a shell string never does
    assert not needs_network(["npm", "test"])
    assert not needs_network(["node", "codemod.js"])


def test_verify_runs_offline_as_a_non_root_user_in_a_locked_down_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-not-a-real-key")
    ws = tmp_path / "ws"
    ws.mkdir()
    argv = runner(tmp_path).argv(
        "npm run typecheck", ws, name="m1", log_file=tmp_path / "run" / "logs" / "x.log"
    )
    joined = " ".join(argv)
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--user") + 1] == "501:20"
    assert "--read-only" in argv and "--cap-drop ALL" in joined
    assert "no-new-privileges" in joined and "--memory" in argv and "--pids-limit" in argv
    # Only the workspace and the log folder are writable; the tools are read-only.
    ws_r, logs_r, tools_r = (
        ws.resolve(),
        (tmp_path / "run/logs").resolve(),
        (tmp_path / "tools").resolve(),
    )
    assert mounts(argv) == [
        "type=volume,src=migrator-npm-cache,dst=/npm-cache",
        f"type=bind,src={ws_r},dst={ws_r}",
        f"type=bind,src={logs_r},dst={logs_r}",
        f"type=bind,src={tools_r},dst={tools_r},readonly",
    ]
    assert "sk-not-a-real-key" not in joined and "ANTHROPIC" not in joined
    assert NODE_IMAGES["20"] in argv and "@sha256:" in NODE_IMAGES["20"]
    assert argv[-3:] == ["sh", "-c", "npm run typecheck"]


def test_installs_get_the_bridge_network_and_argv_stays_a_list(tmp_path: Path) -> None:
    argv = runner(tmp_path).argv(["npm", "ci", "--no-audit"], tmp_path, name="m2")
    assert argv[argv.index("--network") + 1] == "bridge"
    # The install waits until package.json parses (Docker Desktop's file sharing can show
    # a just-rewritten file truncated), then runs unchanged.
    assert argv[-3:-1] == ["sh", "-c"]
    assert argv[-1].endswith("&& exec npm ci --no-audit")
    assert "JSON.parse" in argv[-1]


def test_installing_the_tools_mounts_only_their_folder(tmp_path: Path) -> None:
    tools = tmp_path / "tools" / "mui-4-to-5-abc"
    tools.mkdir(parents=True)
    argv = runner(tmp_path).argv(["npm", "ci"], tools, name="m3", log_file=tools / "install.log")
    assert [m for m in mounts(argv) if m.startswith("type=bind")] == [
        f"type=bind,src={tools.resolve()},dst={tools.resolve()}"
    ]


def test_node_images_are_pinned_per_major_version() -> None:
    assert node_image("20") == node_image("20.11") == node_image("v20") == node_image(None)
    assert node_image("18").startswith("node:18.20.8-bookworm-slim@sha256:")  # M7
    with pytest.raises(SandboxError, match="no pinned Docker image for Node 14"):
        node_image("14")


def test_a_missing_docker_fails_clearly() -> None:
    with pytest.raises(SandboxError, match="Docker is not available"):
        DockerRunner(node_image("20"), docker="/nonexistent/docker").check()


def test_a_run_in_docker_without_docker_is_refused(
    tmp_path: Path, spec: MigrationSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_docker(self: DockerRunner) -> str:
        raise SandboxError("Docker is not available (test)")

    monkeypatch.setattr(DockerRunner, "check", no_docker)
    repo = make_mini_repo(tmp_path / "repo")
    with pytest.raises(RunError, match="Docker is not available"):
        start_run(RunOptions(repo=repo, spec=spec, run_dir=tmp_path / "run", sandbox="docker"))
    assert not (tmp_path / "run").exists()  # refused before anything ran


def test_settle_waits_only_after_a_recent_host_write(tmp_path: Path) -> None:
    old = tmp_path / "old.json"
    old.write_text("{}")
    past = time.time() - 60
    os.utime(old, (past, past))
    assert settle(tmp_path, 0.3) == 0.0
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "fresh.js").write_text("")  # not watched
    assert settle(tmp_path, 0.3) == 0.0
    (tmp_path / "package.json").write_text("{}")
    assert 0.0 < settle(tmp_path, 0.3) <= 0.3
