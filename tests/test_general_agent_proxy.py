"""M8: the general agent's proxy, the rehearsal and the probe's proxy checks.

The proxy exists because the sandboxes' own proxy lost the end of a download when the
server closed the connection after its answer; the first test is that case.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from migrator.config import ResolvedRepoConfig, VerifyCommands
from migrator.execs import CommandResult
from migrator.general_agent.probe import ProbeResult, proxy_checks, with_proxy_checks
from migrator.general_agent.proxy import AllowlistProxy, ProxyEntry, summarise
from migrator.general_agent.rehearsal import (
    add_packages_command,
    rehearsal_steps,
    run_rehearsal,
)
from migrator.general_agent.sandbox import AgentPaths
from migrator.migrations import MigrationSpec

BODY = bytes(range(256)) * 4096  # 1 MiB


@pytest.fixture
def closing_server() -> Iterator[int]:
    """A server that sends BODY and closes at once: what lost bytes before."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    port = srv.getsockname()[1]

    def serve() -> None:
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            conn.recv(1024)
            conn.sendall(BODY)
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    yield port
    srv.close()


def _connect(port: int, target: str) -> tuple[socket.socket, bytes]:
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = s.recv(1)
        if not chunk:
            break
        head += chunk
    return s, head


def _read_all(s: socket.socket) -> bytes:
    out = b""
    while chunk := s.recv(65536):
        out += chunk
    return out


def test_a_tunnel_delivers_every_byte_when_the_server_closes(
    closing_server: int, tmp_path: Path
) -> None:
    log = tmp_path / "proxy.jsonl"
    with AllowlistProxy(["localhost"], log, upstream_port=closing_server) as proxy:
        for _ in range(5):
            s, head = _connect(proxy.port, "localhost:443")
            assert head.startswith(b"HTTP/1.1 200")
            s.sendall(b"GET / HTTP/1.1\r\nConnection: close\r\n\r\n")
            assert _read_all(s) == BODY
            s.close()
    entries = proxy.entries()  # after stop: every tunnel has closed and been recorded
    assert len(entries) == 5
    assert all(e.allowed and e.received == len(BODY) for e in entries)
    assert len(log.read_text().splitlines()) == 5


def test_hosts_off_the_list_other_ports_plain_http_and_socks_are_refused(
    tmp_path: Path,
) -> None:
    with AllowlistProxy(["registry.npmjs.org"]) as proxy:
        for target in ("example.com:443", "registry.npmjs.org:80"):
            s, head = _connect(proxy.port, target)
            assert head.startswith(b"HTTP/1.1 403"), target
            s.close()
        s = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
        s.sendall(b"GET http://registry.npmjs.org/ HTTP/1.1\r\nHost: x\r\n\r\n")
        assert _read_all(s).startswith(b"HTTP/1.1 403")
        s.close()
        s = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
        s.sendall(b"\x05\x01\x00")  # a SOCKS5 greeting
        s.shutdown(socket.SHUT_WR)
        assert _read_all(s) == b""
        s.close()
    summary = proxy.summary()
    assert summary.allowed == 0
    assert set(summary.refused) == {
        "example.com:443",
        "registry.npmjs.org:80",
        "GET http://registry.npmjs.org/ HTTP/1.1",
        "(not an HTTP request)",
    }


def test_an_allowed_host_that_cannot_be_reached_is_a_failure_not_a_refusal() -> None:
    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()  # nothing listens there now
    with AllowlistProxy(["localhost"], upstream_port=port) as proxy:
        s, head = _connect(proxy.port, "localhost:443")
        assert head.startswith(b"HTTP/1.1 502")
        s.close()
    summary = proxy.summary()
    assert summary.failed == {"localhost:443": 1} and not summary.refused


def test_the_probe_needs_the_proxy_to_have_refused_and_carried() -> None:
    base = ProbeResult(ok=True, checks={"blocked host": "ok"}, cost_usd=0.0)
    good = [
        ProxyEntry(at="t", target="example.com:443", allowed=False, reason="off the list"),
        ProxyEntry(at="t", target="registry.npmjs.org:443", allowed=True, received=10),
    ]
    assert with_proxy_checks(base, good).ok
    # No record of either: the sandbox did not send its traffic through the proxy.
    bad = with_proxy_checks(base, [])
    assert not bad.ok
    assert set(proxy_checks([]).values()) == {
        "no refusal in its record",
        "no registry tunnel in its record",
    }
    assert summarise(good).refused == {"example.com:443": 1}


# --------------------------------------------------------------------------- rehearsal


def _config(pm: str, flags: list[str] | None = None) -> ResolvedRepoConfig:
    return ResolvedRepoConfig(
        package_manager=pm,
        lockfile="yarn.lock" if pm == "yarn" else "package-lock.json",
        node="16",
        install_flags=flags or [],
        source_globs=["src/**/*.tsx"],
        exclude=[],
        runner="jest",
        verify=VerifyCommands(typecheck="tsc --noEmit", lint="eslint src", test="jest"),
    )


def test_the_rehearsal_adds_the_new_packages_with_the_repos_manager(
    spec: MigrationSpec,
) -> None:
    yarn = add_packages_command(spec, _config("yarn", ["--ignore-engines"]))
    assert yarn is not None
    assert yarn.startswith("yarn add @mui/material@5.18.0 ")
    assert yarn.endswith("--ignore-engines")
    npm = add_packages_command(spec, _config("npm"))
    assert npm is not None and npm.startswith("npm install --save @mui/material@5.18.0 ")


def test_the_rehearsal_runs_the_codemod_packages_and_checks_in_order(
    spec: MigrationSpec,
) -> None:
    steps = rehearsal_steps(spec, _config("yarn"), ["/agent/bin/mui-codemod"])
    assert [name for name, _ in steps] == ["codemod", "add packages", "typecheck", "lint", "test"]
    assert steps[0][1] == "/agent/bin/mui-codemod v5.0.0/preset-safe src"
    assert steps[2][1] == "tsc --noEmit"


def test_the_rehearsal_records_every_step_and_stops_at_its_time_limit(tmp_path: Path) -> None:
    class Timed:
        def __init__(self, seconds: float) -> None:
            self.seconds = seconds
            self.ran: list[str] = []

        def run(self, command: str, cwd: Path, **_k: Any) -> CommandResult:
            self.ran.append(command)
            return CommandResult(
                command=command,
                cwd=str(cwd),
                exit_code=1 if command == "lint" else 0,
                output="out " * 1000,
                duration_s=self.seconds,
            )

    paths = AgentPaths(root=tmp_path)
    steps = [("typecheck", "tsc"), ("lint", "lint"), ("test", "jest")]
    runner = Timed(1.0)
    agent, done = run_rehearsal(runner, paths, steps, tmp_path / "logs", 60)  # type: ignore[arg-type]
    assert agent.status == "completed" and agent.cost_usd == 0 and not agent.calls
    assert [s.exit_code for s in done] == [0, 1, 0]
    assert all(len(s.tail) <= 1500 for s in done)
    slow = Timed(40.0)
    agent, done = run_rehearsal(slow, paths, steps, tmp_path / "logs", 60)  # type: ignore[arg-type]
    assert agent.status == "timed_out" and slow.ran == ["tsc", "lint"]


def test_the_cost_preflight_counts_a_general_agent_run_at_its_stop(tmp_path: Path) -> None:
    from migrator.cost import Ledger, LedgerPreflight, PlannedExperiment

    pre = LedgerPreflight(Ledger(tmp_path / "ledger.jsonl"))
    plan = PlannedExperiment(
        configuration="m8-agent-plain",
        uses_llm=True,
        runs=2,
        max_cost_usd=10.0,
        attempt_models=["claude-opus-5-5"],
        per_run_usd=5.0,
    )
    assert pre.check(plan).estimated_usd == 10.0 and pre.check(plan).ok
    over = pre.check(plan.model_copy(update={"max_cost_usd": 9.0}))
    assert not over.ok and "2 runs x $5.00 stop" in over.reason


def test_the_host_install_fetches_outside_with_scripts_off_then_runs_them_sandboxed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from migrator.general_agent import sandbox

    outside: list[tuple[list[str], dict[str, str]]] = []

    class Outside:
        def __init__(self, base_env: dict[str, str]) -> None:
            self.env = base_env

        def run(self, command: list[str], cwd: Path, **_k: Any) -> CommandResult:
            outside.append((command, self.env))
            return CommandResult(
                command=" ".join(command), cwd=str(cwd), exit_code=0, output="", duration_s=1
            )

    class Inside:
        def __init__(self) -> None:
            self.ran: list[str] = []

        def run(self, command: str, cwd: Path, **_k: Any) -> CommandResult:
            self.ran.append(command)
            return CommandResult(
                command=command, cwd=str(cwd), exit_code=0, output="", duration_s=1
            )

    monkeypatch.setattr(sandbox, "LocalRunner", Outside)
    inside = Inside()
    done = sandbox.host_install(
        paths=AgentPaths(root=tmp_path),
        command=["yarn", "install", "--frozen-lockfile"],
        env={"PATH": "/bin"},
        proxy_port=4321,
        sandboxed=inside,  # type: ignore[arg-type]
        log_dir=tmp_path,
    )
    ((command, env),) = outside
    assert command == ["yarn", "install", "--frozen-lockfile", "--ignore-scripts"]
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:4321" and env["NO_PROXY"] == ""
    assert inside.ran == [sandbox.INSTALL_SCRIPTS]
    assert "exited 0" in done
