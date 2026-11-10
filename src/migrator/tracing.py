"""LangSmith tracing (ticket #3): switched on by environment variables only.

Tracing is off unless the environment turns it on; nothing in the code or the
configuration does. LangChain and LangGraph then trace with no code changes:

    export LANGSMITH_TRACING=true
    export LANGSMITH_API_KEY=...
    # newer, agent-based workspaces:
    export LANGSMITH_AGENT_ID=<agent-id>
    export LANGSMITH_AGENT_ENVIRONMENT=local
    # older, project-based workspaces (and self-hosted):
    export LANGSMITH_PROJECT=mui-migrate

What the Migrator adds is names and metadata, so a run and one repair attempt are easy
to find: the graph's root run is ``migrator-run`` with the run id, case, configuration,
mode and sandbox as metadata (and ``thread_id``, which groups the first invoke and each
resume into one LangSmith thread); every model call is a child run named ``repair
<file> · attempt <n>`` with the file, attempt and model added. Each CLI command flushes
the traces before it exits.

Cost: the Migrator's own ledger (``migrator.cost``) is the only cost it counts. LangSmith
computes a cost of its own from the same token counts; it is a cross-check in the UI,
never added to a scorecard or the ledger, so nothing is counted twice.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

# The switches LangSmith itself reads (LANGCHAIN_* are the older names).
_SWITCHES = (
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING",
)


class TracingSettings(BaseModel):
    enabled: bool
    api_key_set: bool  # whether a key is set; its value is never read into the Migrator
    project: str | None = None
    agent_id: str | None = None
    agent_environment: str | None = None
    endpoint: str | None = None


def _get(env: Mapping[str, str], name: str) -> str | None:
    for prefix in ("LANGSMITH_", "LANGCHAIN_"):
        value = env.get(prefix + name)
        if value is not None and value.strip():
            return value.strip()
    return None


def tracing_settings(env: Mapping[str, str] | None = None) -> TracingSettings:
    """What the environment says about tracing, the way LangSmith reads it."""
    env = os.environ if env is None else env
    switch = next((env[k] for k in _SWITCHES if env.get(k, "").strip()), "")
    return TracingSettings(
        enabled=switch.strip() == "true",
        api_key_set=bool(_get(env, "API_KEY")),
        project=_get(env, "PROJECT"),
        agent_id=_get(env, "AGENT_ID"),
        agent_environment=_get(env, "AGENT_ENVIRONMENT"),
        endpoint=_get(env, "ENDPOINT"),
    )


def describe(settings: TracingSettings) -> str | None:
    """One line for the CLI when tracing is on (None when it is off)."""
    if not settings.enabled:
        return None
    if settings.agent_id:
        where = f"agent {settings.agent_id}" + (
            f" ({settings.agent_environment})" if settings.agent_environment else ""
        )
    elif settings.project:
        where = f"project {settings.project}"
    else:
        where = "the default project"
    line = f"LangSmith tracing on: {where}" + (
        f" at {settings.endpoint}" if settings.endpoint else ""
    )
    if not settings.api_key_set:
        line += ". Warning: LANGSMITH_API_KEY is not set, so traces will not upload"
    return line + "."


# --------------------------------------------------------------------------- privacy

# Absolute local paths: home folders and the temp folders runs work in (macOS and Linux).
_ABSOLUTE = re.compile(r"""(?:/private)?/(?:Users|home|var/folders|tmp|root)/[^\s"'`<>|)\]},;]*""")


def _variants(path: Path) -> list[str]:
    text = str(path.resolve())
    out = {text, str(path)}
    if text.startswith("/private/"):
        out.add(text.removeprefix("/private"))
    return sorted(out, key=len, reverse=True)


def redact_text(text: str, roots: Sequence[Path] = ()) -> str:
    """``text`` with absolute local paths made relative or dropped (M6): a path in one of
    ``roots`` (the repo the CLI runs in) becomes relative to it, a run's workspace
    ``<workspace>/...``, anything else ``<local path>``."""
    anchors = [(v, root) for root in roots for v in _variants(root)]

    def one(m: re.Match[str]) -> str:
        path = m.group(0)
        for prefix, _root in anchors:
            if path == prefix:
                return "."
            if path.startswith(prefix.rstrip("/") + "/"):
                return path[len(prefix.rstrip("/")) + 1 :]
        marker = "/workspace"
        if marker in path:
            rest = path.split(marker, 1)[1]
            return "<workspace>" + rest
        return "<local path>"

    return _ABSOLUTE.sub(one, text)


def redact(value: Any, roots: Sequence[Path] = ()) -> Any:
    """``redact_text`` over every string in a JSON-like value (keys included)."""
    if isinstance(value, str):
        return redact_text(value, roots)
    if isinstance(value, dict):
        return {redact(k, roots): redact(v, roots) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, roots) for v in value]
    return value


def install_redaction(roots: Sequence[Path] | None = None) -> bool:
    """When tracing is on, make LangChain's tracer use a LangSmith client that redacts
    absolute local paths from every run's inputs, outputs and metadata before upload
    (M6: the first public trace showed /Users/... and /var/folders/... paths). Returns
    whether it was installed. Never fails a run."""
    if not tracing_settings().enabled:
        return False
    try:
        import langsmith
        import langsmith.run_trees as rt

        base = list(roots) if roots is not None else [Path.cwd()]

        def hide(data: dict[str, Any]) -> dict[str, Any]:
            result = redact(data, base)
            return result if isinstance(result, dict) else data

        rt._CLIENT = langsmith.Client(hide_inputs=hide, hide_outputs=hide, hide_metadata=hide)
        return True
    except Exception:
        return False


def flush() -> None:
    """A short-lived CLI must wait for the background upload before it exits."""
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()
    except Exception:  # tracing is optional; never fail a run over it
        pass
