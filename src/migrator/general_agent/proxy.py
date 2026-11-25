"""The general agent's network proxy: HTTPS tunnels to the allowed hosts, nothing else.

Both sandboxes (Claude Code's and ``srt``'s) send their commands' traffic through a
proxy. Their own proxy loses the last bytes of a download when the server closes the
connection after its answer (sandbox-runtime 0.0.81 to 0.0.83, Claude Code 2.1.325):
yarn v1 asks for that close, so every package install failed. Their settings take an
outside proxy instead (``network.httpProxyPort``); this is it.

It answers only ``CONNECT host:443`` for a host on the list and passes the encrypted
bytes through untouched, closing each direction only once the other side has finished
(``write_eof``), so nothing queued is lost. Plain HTTP, other ports, other hosts and
SOCKS are refused. Every decision is logged, so a run shows what its commands tried to
reach. It listens on 127.0.0.1 only, on a port the system picks.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from migrator.general_agent.errors import GeneralAgentError

HEAD_LIMIT = 16 * 1024
HEAD_TIMEOUT_S = 10.0
DIAL_TIMEOUT_S = 30.0
CHUNK = 64 * 1024


class ProxyEntry(BaseModel):
    at: str
    target: str  # "host:port", or the first line of a refused request
    allowed: bool
    reason: str | None = None
    sent: int = 0  # bytes from the command to the host
    received: int = 0  # bytes from the host to the command


class ProxySummary(BaseModel):
    allowed: int
    refused: dict[str, int]  # target -> times refused
    # allowed target -> times the host could not be reached, or a tunnel broke part-way
    failed: dict[str, int]


def summarise(entries: Sequence[ProxyEntry]) -> ProxySummary:
    refused: dict[str, int] = {}
    failed: dict[str, int] = {}
    ok = 0
    for e in entries:
        if not e.allowed:
            refused[e.target] = refused.get(e.target, 0) + 1
        elif e.reason:
            failed[e.target] = failed.get(e.target, 0) + 1
        else:
            ok += 1
    return ProxySummary(allowed=ok, refused=refused, failed=failed)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class AllowlistProxy:
    """The proxy, on its own thread and event loop: ``with AllowlistProxy(...) as p``."""

    def __init__(
        self, allowed: Sequence[str], log: Path | None = None, *, upstream_port: int = 443
    ):
        self.allowed = {h.lower() for h in allowed}
        self.upstream_port = upstream_port  # 443; a test's local server otherwise
        self.log = log
        self.port = 0
        self._entries: list[ProxyEntry] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[Any]] = set()

    # -- lifecycle -------------------------------------------------------------------

    def start(self) -> int:
        loop = asyncio.new_event_loop()
        self._loop = loop
        self._thread = threading.Thread(target=loop.run_forever, name="agent-proxy", daemon=True)
        self._thread.start()
        try:
            self._server = asyncio.run_coroutine_threadsafe(
                asyncio.start_server(self._accept, "127.0.0.1", 0, limit=HEAD_LIMIT), loop
            ).result(timeout=10)
        except Exception as exc:
            self.stop()
            raise GeneralAgentError(f"the agent's proxy could not start: {exc}") from exc
        self.port = self._server.sockets[0].getsockname()[1]
        if self.log is not None:
            self.log.parent.mkdir(parents=True, exist_ok=True)
            self.log.write_text("", "utf-8")
        return self.port

    def stop(self) -> None:
        loop = self._loop
        if loop is None:
            return

        async def shutdown() -> None:
            if self._server is not None:
                self._server.close()
            for task in list(self._tasks):
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if loop.is_running():
            asyncio.run_coroutine_threadsafe(shutdown(), loop).result(timeout=10)
            loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=10)
        loop.close()
        self._loop = None

    def __enter__(self) -> AllowlistProxy:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # -- record ----------------------------------------------------------------------

    def entries(self) -> list[ProxyEntry]:
        with self._lock:
            return list(self._entries)

    def summary(self) -> ProxySummary:
        return summarise(self.entries())

    def _record(self, entry: ProxyEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            if self.log is not None:
                with self.log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.model_dump()) + "\n")

    # -- connections -----------------------------------------------------------------

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._tasks.add(task)
        try:
            await self._handle(reader, writer)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001 (one connection's failure never stops the proxy)
            self._record(
                ProxyEntry(at=_now(), target="(connection)", allowed=False, reason=repr(exc))
            )
        finally:
            self._tasks.discard(task)
            writer.close()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEAD_TIMEOUT_S)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
            self._record(ProxyEntry(at=_now(), target="(not an HTTP request)", allowed=False))
            return
        line = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = line.split()
        if len(parts) != 3 or parts[0].upper() != "CONNECT":
            await self._refuse(writer, line[:200], "only HTTPS tunnels (CONNECT) are allowed")
            return
        host, _, port_text = parts[1].rpartition(":")
        host = host.strip("[]").lower()
        target = f"{host}:{port_text}"
        if host not in self.allowed or port_text != "443":
            await self._refuse(writer, target, "host is not on the allow list")
            return
        try:
            up_reader, up_writer = await asyncio.wait_for(
                asyncio.open_connection(host, self.upstream_port, limit=CHUNK), DIAL_TIMEOUT_S
            )
        except (OSError, TimeoutError) as exc:
            self._record(ProxyEntry(at=_now(), target=target, allowed=True, reason=str(exc)))
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return
        counts = [0, 0]  # sent, received: kept even when the proxy stops mid-tunnel
        broke: list[str] = []  # a side whose connection failed mid-tunnel
        try:
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(
                _pump(reader, up_writer, counts, 0, broke, "command"),
                _pump(up_reader, writer, counts, 1, broke, "host"),
            )
        finally:
            up_writer.close()
            self._record(
                ProxyEntry(
                    at=_now(),
                    target=target,
                    allowed=True,
                    reason="; ".join(broke) or None,
                    sent=counts[0],
                    received=counts[1],
                )
            )

    async def _refuse(self, writer: asyncio.StreamWriter, target: str, reason: str) -> None:
        self._record(ProxyEntry(at=_now(), target=target, allowed=False, reason=reason))
        body = f"migrator proxy: {reason}\n".encode()
        writer.write(
            b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\nConnection: close\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        await writer.drain()


async def _pump(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    counts: list[int],
    i: int,
    broke: list[str],
    side: str,
) -> None:
    """Copy one direction to its end, then pass the end on (after what is queued). A
    connection that fails part-way is recorded; what came through is still delivered."""
    try:
        while data := await reader.read(CHUNK):
            writer.write(data)
            await writer.drain()
            counts[i] += len(data)
    except (ConnectionError, OSError) as exc:
        broke.append(f"the {side} side broke off: {exc!r}")
    finally:
        try:
            if writer.can_write_eof() and not writer.is_closing():
                writer.write_eof()
        except (ConnectionError, OSError):
            pass
