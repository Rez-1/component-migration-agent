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
from collections.abc import Mapping

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


def flush() -> None:
    """A short-lived CLI must wait for the background upload before it exits."""
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()
    except Exception:  # tracing is optional; never fail a run over it
        pass
