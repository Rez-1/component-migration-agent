"""LangSmith tracing (ticket #3): environment variables only, off by default.

No test talks to LangSmith: tracing is either off, collected in memory by LangChain's
run collector, or sent to a mocked client.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import langsmith
import langsmith.run_trees as rt
import langsmith.utils as ls_utils
import pytest
from langchain_core.tracers.run_collector import RunCollectorCallbackHandler
from langchain_core.tracers.schemas import Run

from migrator import tracing
from migrator.cost import Ledger
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunOptions, RunResult, start_run
from tests.conftest import FakeRunner
from tests.fakes import FakeToolchain, ScriptedChatModel, factory_for, make_mini_repo
from tests.test_graph import DASH, GOOD, THEME, configuration

SWITCHES = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_TRACING",
)


def clear_env_cache() -> None:
    """LangSmith caches the environment variables it reads."""
    getattr(ls_utils.get_env_var, "cache_clear")()  # noqa: B009 (an lru_cache attribute)


@pytest.fixture(autouse=True)
def no_tracing_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in (*SWITCHES, "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY", "LANGSMITH_PROJECT"):
        monkeypatch.delenv(name, raising=False)
    clear_env_cache()
    yield
    clear_env_cache()


def run_graph(
    tmp_path: Path, spec: MigrationSpec, callbacks: list[Any] | None = None
) -> tuple[RunResult, Ledger]:
    repo = make_mini_repo(tmp_path / "repo")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    result = start_run(
        RunOptions.model_validate(
            {
                "repo": repo,
                "spec": spec,
                "run_dir": tmp_path / "run",
                "configuration": configuration(),
                "tools_cache": tmp_path / "cache",
                "run_id": "r1",
            }
        ),
        FakeRunner(FakeToolchain()),
        model_factory=factory_for(ScriptedChatModel(script=GOOD)),
        ledger=ledger,
        callbacks=callbacks,
    )
    assert isinstance(result, RunResult)
    return result, ledger


def walk(run: Run) -> Iterator[Run]:
    yield run
    for child in run.child_runs:
        yield from walk(child)


def test_tracing_settings_come_from_the_environment_only() -> None:
    assert tracing.tracing_settings({}).enabled is False
    assert tracing.describe(tracing.tracing_settings({})) is None
    agent = tracing.tracing_settings(
        {
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "x",
            "LANGSMITH_AGENT_ID": "migrator",
            "LANGSMITH_AGENT_ENVIRONMENT": "local",
        }
    )
    assert tracing.describe(agent) == "LangSmith tracing on: agent migrator (local)."
    project = tracing.tracing_settings(
        {"LANGCHAIN_TRACING_V2": "true", "LANGSMITH_PROJECT": "mui-migrate"}
    )
    line = tracing.describe(project)
    assert line is not None and line.startswith("LangSmith tracing on: project mui-migrate")
    assert "LANGSMITH_API_KEY is not set" in line
    assert tracing.tracing_settings({"LANGSMITH_TRACING": "false"}).enabled is False


def test_with_tracing_off_no_client_is_made(
    tmp_path: Path, spec: MigrationSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_a: Any, **_k: Any) -> None:
        raise AssertionError("a LangSmith client was created with tracing off")

    monkeypatch.setattr(langsmith.Client, "__init__", refuse)
    monkeypatch.setattr(rt, "_CLIENT", None)
    result, _ = run_graph(tmp_path, spec)
    assert result.scorecard.status == "completed"
    tracing.flush()  # nothing to flush, and no error


def test_a_repair_attempt_is_a_named_child_of_the_run_trace(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    collector = RunCollectorCallbackHandler()
    result, ledger = run_graph(tmp_path, spec, callbacks=[collector])
    roots = collector.traced_runs
    assert roots and {r.name for r in roots} == {"migrator-run"}
    root = roots[0]
    assert root.extra["metadata"]["run_id"] == "r1"
    assert root.extra["metadata"]["thread_id"] == "r1"
    assert root.extra["metadata"]["configuration"] == "opus-low"
    assert "config:opus-low" in (root.tags or [])

    llm_runs = [run for r in roots for run in walk(r) if run.run_type == "llm"]
    names = [run.name for run in llm_runs]
    assert f"repair {THEME} · attempt 1" in names and f"repair {DASH} · attempt 1" in names
    for run in llm_runs:
        meta = run.extra["metadata"]
        # Inherited from the run, and added per call: easy to filter on in LangSmith.
        assert meta["run_id"] == "r1" and meta["configuration"] == "opus-low"
        assert meta["file"] in run.name and meta["attempt"] == 1
        assert f"file:{meta['file']}" in (run.tags or [])
        assert run.trace_id in {r.trace_id for r in roots}  # inside a run's trace

    # One ledger row per model call, with tracing attached as well: nothing counted twice.
    calls = result.scorecard.cost.model_calls
    assert len(llm_runs) == calls == len(ledger.rows())
    assert result.scorecard.cost.total_usd == pytest.approx(sum(r.cost_usd for r in ledger.rows()))


def test_the_environment_switch_traces_to_the_client_and_flushes(
    tmp_path: Path, spec: MigrationSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = MagicMock(spec=langsmith.Client)
    monkeypatch.setattr(rt, "_CLIENT", client)  # what LangChain's tracer will use
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_PROJECT", "migrator-tests")
    clear_env_cache()
    run_graph(tmp_path, spec)
    tracing.flush()
    posted = [c.kwargs.get("name") for c in client.create_run.call_args_list]
    assert "migrator-run" in posted
    assert f"repair {THEME} · attempt 1" in posted
    client.flush.assert_called()


ABSOLUTE = re.compile(r"(?:/private)?/(?:Users|home|var/folders|tmp|root)/")


def test_a_traced_run_sends_no_absolute_local_paths(
    tmp_path: Path, spec: MigrationSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M6: LangSmith gets every run's inputs, outputs and metadata through the client's
    hide functions; after them, nothing may name a home or temp folder."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key-not-real")
    clear_env_cache()
    monkeypatch.setattr(rt, "_CLIENT", None)
    assert tracing.install_redaction([tmp_path])
    client = rt._CLIENT
    assert client is not None
    monkeypatch.setenv("LANGSMITH_TRACING", "false")  # collect locally, upload nothing
    clear_env_cache()
    collector = RunCollectorCallbackHandler()
    run_graph(tmp_path, spec, callbacks=[collector])
    payloads: list[Any] = []
    for root in collector.traced_runs:
        for run in walk(root):
            payloads += [run.inputs, run.outputs or {}, (run.extra or {}).get("metadata", {})]
    raw = json.dumps(payloads, default=str)
    assert ABSOLUTE.search(raw), "the run state should carry absolute paths to redact"
    # The client's own hide functions, in the order the payloads were collected.
    hides = (client._hide_run_inputs, client._hide_run_outputs, client._hide_run_metadata)
    hidden = [hides[i % 3](p) for i, p in enumerate(payloads)]
    leaked = ABSOLUTE.findall(json.dumps(hidden, default=str))
    assert leaked == []


def test_redaction_keeps_paths_useful() -> None:
    root = Path("/Users/someone/Code/tool")
    text = (
        "run_dir=/Users/someone/Code/tool/runs/m6/r1 ws=/var/folders/ab/T/migrator-x/workspace/"
        "src/A.tsx other=/Users/someone/.cache/migrator/x"
    )
    assert tracing.redact_text(text, [root]) == (
        "run_dir=runs/m6/r1 ws=<workspace>/src/A.tsx other=<local path>"
    )
