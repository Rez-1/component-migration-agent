"""The general agent (M8): its sandbox settings, the probe's verdicts, one Claude Code
run read from its transcript, the copy and copy-back, and a whole run through the
Migrator's Pre-check, final Verify and Scoring with a scripted agent.

No test calls a model or downloads anything: Claude Code is a shell script that prints
a stream-json transcript, and the agent in the whole run is a function that edits the
workspace.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

import pytest

from migrator.configuration import Configuration, GeneralAgentSettings
from migrator.cost import Ledger
from migrator.general_agent import AgentRun, render_prompt, run_general_agent
from migrator.general_agent.agent import (
    AgentResult,
    CopyBack,
    Unfinished,
    audit,
    claude_command,
    copy_back,
    make_copy,
    read_unfinished,
    run_claude,
)
from migrator.general_agent.probe import ProbeResult, judge, outside_target, probe_script
from migrator.general_agent.sandbox import AgentPaths, Policy
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunOptions, RunResult, start_run
from tests.conftest import FakeRunner
from tests.fakes import FakeToolchain, make_mini_repo

MODEL = "claude-opus-5-5"


def settings(setup: str = "rules") -> GeneralAgentSettings:
    return GeneralAgentSettings.model_validate(
        {"enabled": True, "setup": setup, "model": MODEL, "effort": "low", "prompt_version": "v1"}
    )


def configuration(setup: str = "rules") -> Configuration:
    return Configuration.model_validate(
        {
            "name": f"m8-agent-{setup}",
            "general_agent": settings(setup).model_dump(),
            "cost": {"max_run_usd": 8.0, "max_month_usd": 50.0, "stop_run_usd": 5.0},
        }
    )


# --------------------------------------------------------------------------- configuration


def test_a_general_agent_configuration_needs_a_stop_and_no_repair() -> None:
    assert configuration().uses_llm
    assert configuration().models_used() == [MODEL]
    with pytest.raises(ValueError, match="stop_run_usd"):
        Configuration.model_validate(
            {"name": "x", "general_agent": settings().model_dump(), "cost": {}}
        )
    with pytest.raises(ValueError, match="setup"):
        GeneralAgentSettings.model_validate({"enabled": True, "model": MODEL})


def test_the_digest_leaves_the_section_out_when_it_is_off() -> None:
    plain = Configuration(name="baseline")
    off = Configuration.model_validate({"name": "baseline", "general_agent": {"enabled": False}})
    assert plain.digest() == off.digest()
    assert configuration("plain").digest() != configuration("rules").digest()


# --------------------------------------------------------------------------- sandbox


def test_the_settings_lock_the_sandbox_and_deny_with_absolute_rules(tmp_path: Path) -> None:
    paths = AgentPaths(root=tmp_path / "agent")
    home = tmp_path / "home"
    policy = Policy(
        paths=paths, protected=[tmp_path / "ws", tmp_path / "run"], real_home=home, proxy_port=4321
    )
    data: dict[str, Any] = policy.claude_settings(tmp_path / "key-helper.sh")
    sandbox = data["sandbox"]
    assert sandbox["enabled"] and sandbox["failIfUnavailable"]
    assert sandbox["allowUnsandboxedCommands"] is False
    assert sandbox["excludedCommands"] == []
    # Both sandboxes send every command's traffic through the Migrator's proxy.
    assert sandbox["network"] == {
        "allowedDomains": ["registry.npmjs.org", "registry.yarnpkg.com"],
        "httpProxyPort": 4321,
        "socksProxyPort": 4321,
        "strictAllowlist": True,
    }
    assert policy.srt_settings()["network"] == {
        "allowedDomains": ["registry.npmjs.org", "registry.yarnpkg.com"],
        "httpProxyPort": 4321,
        "socksProxyPort": 4321,
        "deniedDomains": [],
    }
    assert sandbox["filesystem"]["allowWrite"] == [str(paths.root)]
    assert str(tmp_path / "ws") in sandbox["filesystem"]["denyWrite"]
    deny = data["permissions"]["deny"]
    # One "/" would be relative to the settings file: every path rule starts "//".
    assert all(r.startswith(("Read(//", "Edit(//")) for r in deny if "(" in r)
    assert f"Read(/{home}/.ssh/**)" in deny
    assert f"Edit(/{home}/.zshrc)" in deny
    assert "WebFetch" in deny and "WebSearch" in deny
    assert data["apiKeyHelper"] == str(tmp_path / "key-helper.sh")


# --------------------------------------------------------------------------- probe


def _probe_events(secret: Path, written: Path, *, tried: bool = True) -> list[dict[str, Any]]:
    uses = [{"type": "tool_use", "name": "Bash", "input": {"command": "sh probe.sh"}}]
    if tried:
        uses += [
            {"type": "tool_use", "name": "Read", "input": {"file_path": str(secret)}},
            {"type": "tool_use", "name": "Write", "input": {"file_path": str(written)}},
            {
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": f"cat {secret}", "dangerouslyDisableSandbox": True},
            },
        ]
    return [{"type": "assistant", "message": {"content": uses}}]


def _probe_case(tmp_path: Path) -> tuple[list[tuple[str, str, bool]], Path, Path, Path, Path]:
    checks = [("blocked host", "curl example.com", False), ("registry", "curl registry", True)]
    results = tmp_path / "results.txt"
    results.write_text("blocked host=refused\nregistry=ran\n")
    transcript = tmp_path / "probe.jsonl"
    transcript.write_text("{}\n")
    return checks, results, tmp_path / "secret.env", tmp_path / "written.txt", transcript


def test_the_probe_passes_only_when_every_check_holds(tmp_path: Path) -> None:
    checks, results, secret, written, transcript = _probe_case(tmp_path)
    ok = judge(
        checks, results, _probe_events(secret, written), "TOKEN", secret, written, transcript
    )
    assert set(ok.values()) == {"ok"}

    results.write_text("blocked host=ran\nregistry=ran\n")
    bad = judge(
        checks, results, _probe_events(secret, written), "TOKEN", secret, written, transcript
    )
    assert bad["blocked host"] == "ran, wanted refused"


def test_the_probe_fails_when_the_model_skips_a_step_or_the_marker_leaks(tmp_path: Path) -> None:
    checks, results, secret, written, transcript = _probe_case(tmp_path)
    skipped = judge(
        checks,
        results,
        _probe_events(secret, written, tried=False),
        "T",
        secret,
        written,
        transcript,
    )
    assert skipped["unsandboxed retry refused"] == "the model never tried it"
    transcript.write_text('{"leak": "MIGRATOR-PROBE-abc"}\n')
    leaked = judge(
        checks,
        results,
        _probe_events(secret, written),
        "MIGRATOR-PROBE-abc",
        secret,
        written,
        transcript,
    )
    assert leaked["marker stayed secret"] != "ok"
    written.write_text("x")
    assert (
        judge(checks, results, _probe_events(secret, written), "T", secret, written, transcript)[
            "Write tool denied in the key folder"
        ]
        == "file was written"
    )


def test_the_probe_script_records_ran_or_refused(tmp_path: Path) -> None:
    import subprocess

    out = tmp_path / "results.txt"
    script = probe_script([("yes", "true", True), ("no", "false", False)], out)
    subprocess.run(["sh", "-c", script], check=True)
    assert out.read_text().splitlines() == ["yes=ran", "no=refused"]
    assert outside_target(AgentPaths(root=tmp_path / "r1")).parent == Path.home()


def test_the_probe_retries_what_must_get_through_but_not_what_must_be_refused(
    tmp_path: Path,
) -> None:
    import subprocess

    out = tmp_path / "results.txt"
    flaky = tmp_path / "flaky"  # fails the first time, then works: one dropped connection
    once = tmp_path / "once"  # works the first time only: never retried into a pass
    checks = [
        ("reachable", f"test -e {flaky} || {{ touch {flaky}; false; }}", True),
        ("blocked", f"test -e {once} || {{ touch {once}; false; }}", False),
    ]
    subprocess.run(["sh", "-c", probe_script(checks, out)], check=True)
    assert out.read_text().splitlines() == ["reachable=ran", "blocked=refused"]


# --------------------------------------------------------------------------- one Claude run


def fake_claude(
    tmp_path: Path, events: list[dict[str, Any]], *, sleep: int = 0, edit: str = ""
) -> Path:
    """A ``claude`` that runs ``edit`` in its working directory, then prints ``events``."""
    lines = "\n".join(json.dumps(e) for e in events)
    script = tmp_path / "claude"
    script.write_text(
        f"#!/bin/sh\n{edit}\nsleep {sleep}\ncat <<'EOF'\n{lines}\nnot json: a warning\nEOF\n"
    )
    script.chmod(0o755)
    return script


def result_event(**extra: Any) -> dict[str, Any]:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": 7,
        "duration_ms": 1200,
        "stop_reason": "end_turn",
        "total_cost_usd": 0.42,
        "result": "Done.",
        "modelUsage": {
            MODEL: {
                "inputTokens": 100,
                "outputTokens": 2000,
                "cacheReadInputTokens": 50000,
                "cacheCreationInputTokens": 3000,
                "cacheCreationEphemeral5mInputTokens": 3000,
                "cacheCreationEphemeral1hInputTokens": 0,
                "costUSD": 0.42,
                "canonicalModel": MODEL,
            }
        },
        **extra,
    }


def _run(tmp_path: Path, binary: Path, timeout_s: float = 30) -> AgentResult:
    cwd = tmp_path / "repo"
    cwd.mkdir(exist_ok=True)
    return run_claude(
        [str(binary)],
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin"},
        timeout_s=timeout_s,
        transcript=tmp_path / "t.jsonl",
        requested_model=MODEL,
        allowed_writes=[cwd],
    )


def test_a_run_reads_cost_tokens_and_the_audit_from_the_transcript(tmp_path: Path) -> None:
    uses = [
        {"type": "tool_use", "name": "Bash", "input": {"command": "yarn test"}},
        {
            "type": "tool_use",
            "name": "Edit",
            "input": {"file_path": str(tmp_path / "repo" / "a.ts")},
        },
        {"type": "tool_use", "name": "Write", "input": {"file_path": "/etc/oops"}},
        {
            "type": "tool_use",
            "name": "Bash",
            "input": {"command": "x", "dangerouslyDisableSandbox": True},
        },
        {"type": "tool_use", "name": "Task", "input": {"prompt": "help"}},
    ]
    events = [{"type": "assistant", "message": {"content": uses}}, result_event()]
    result = _run(tmp_path, fake_claude(tmp_path, events))
    assert result.status == "completed" and result.num_turns == 7
    assert result.cost_usd == 0.42 and result.calls[0].usage.output_tokens == 2000
    assert result.calls[0].usage.cache_read_input_tokens == 50000
    assert result.priced_usd is not None and result.priced_usd > 0
    assert result.audit.tool_calls == {"Bash": 2, "Edit": 1, "Write": 1, "Task": 1}
    assert result.audit.unsandboxed_requests == 1 and result.audit.subagents == 1
    assert result.audit.outside_writes == ["/etc/oops"] and not result.audit.clean


def test_the_cost_stop_and_the_timeout_are_told_apart(tmp_path: Path) -> None:
    stopped = _run(
        tmp_path,
        fake_claude(tmp_path, [result_event(subtype="error_max_budget_usd", is_error=True)]),
    )
    assert stopped.status == "stopped_by_cost"
    slow = _run(tmp_path, fake_claude(tmp_path, [result_event()], sleep=20), timeout_s=1)
    assert slow.status == "timed_out" and slow.calls == []


def test_the_command_is_headless_bare_and_capped(tmp_path: Path) -> None:
    argv = claude_command(
        tmp_path / "claude",
        prompt="go",
        model=MODEL,
        effort="low",
        budget_usd=4.996,
        settings=tmp_path / "s.json",
    )
    joined = shlex.join(argv)
    for part in (
        "-p",
        "--bare",
        "--effort low",
        "--max-budget-usd 5.00",
        "stream-json",
        "--settings",
    ):
        assert part in joined
    assert argv[-1] == "go"


# --------------------------------------------------------------------------- copy and copy-back


def test_the_copy_and_copy_back_move_only_the_agents_changes(tmp_path: Path) -> None:
    ws = make_mini_repo(tmp_path / "ws")
    (ws / "node_modules" / "x").mkdir(parents=True)
    (ws / "node_modules" / "x" / "index.js").write_text("v4")
    (ws / ".gitignore").write_text("build/\n")
    paths = AgentPaths(root=tmp_path / "agent")
    paths.make()
    start = make_copy(ws, paths)
    assert "src/theme.ts" in start and not any("node_modules" in p for p in start)
    repo = paths.repo
    (repo / "src" / "theme.ts").write_text("import { createTheme } from '@mui/material/styles';\n")
    (repo / "src" / "new.ts").write_text("export {};\n")
    (repo / "src" / "App.tsx").unlink()
    (repo / "build").mkdir()
    (repo / "build" / "out.js").write_text("ignored")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "darwin.node").write_text("binary")
    back = copy_back(repo, start, ws)
    assert back == CopyBack(added=["src/new.ts"], changed=["src/theme.ts"], deleted=["src/App.tsx"])
    assert (ws / "src" / "theme.ts").read_text().startswith("import { createTheme }")
    assert not (ws / "src" / "App.tsx").exists() and not (ws / "build").exists()
    assert (ws / "node_modules" / "x" / "index.js").read_text() == "v4"


def test_the_unfinished_list_keeps_only_real_files(tmp_path: Path) -> None:
    path = tmp_path / "unfinished.json"
    assert read_unfinished(path, set())[1] == "the agent wrote no unfinished-files list"
    path.write_text(json.dumps([{"path": "./src/a.ts", "reason": "r"}, {"path": "nope.ts"}, "x"]))
    assert read_unfinished(path, {"src/a.ts"}) == ([Unfinished(path="src/a.ts", reason="r")], None)
    path.write_text("{")
    assert "not JSON" in (read_unfinished(path, set())[1] or "")


def test_copy_back_survives_a_broken_git_repo(tmp_path: Path) -> None:
    ws = make_mini_repo(tmp_path / "ws")
    paths = AgentPaths(root=tmp_path / "agent")
    paths.make()
    start = make_copy(ws, paths)
    import shutil

    shutil.rmtree(paths.repo / ".git")
    (paths.repo / "src" / "theme.ts").write_text("changed\n")
    assert copy_back(paths.repo, start, ws).changed == ["src/theme.ts"]


def test_audit_allows_the_agents_own_folders(tmp_path: Path) -> None:
    inside = tmp_path / "repo" / "src" / "a.ts"
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Write", "input": {"file_path": str(inside)}}
                ]
            },
        }
    ]
    assert audit(events, [tmp_path / "repo"]).clean


# --------------------------------------------------------------------------- the prompt


@pytest.mark.parametrize("setup", ["plain", "rules"])
def test_the_prompt_is_filled_in(setup: str, tmp_path: Path, spec: MigrationSpec) -> None:
    from migrator.config import ResolvedRepoConfig, VerifyCommands

    config = ResolvedRepoConfig(
        package_manager="yarn",
        lockfile="yarn.lock",
        node="16",
        install_flags=[],
        source_globs=["src/**/*.tsx"],
        exclude=[],
        runner="jest",
        verify=VerifyCommands(typecheck="tsc", lint="eslint src", test="jest"),
    )
    paths = AgentPaths(root=tmp_path / "agent")
    text = render_prompt(settings(setup), spec, config, paths, ["mui-codemod"])
    assert text.startswith("Migrate this repository from Material UI v4 to v5.")
    assert "mui-codemod v5.0.0/preset-safe src" in text and "`jest`" in text
    assert str(paths.guide) in text
    assert (str(paths.unfinished) in text) == (setup == "rules")
    assert "{" not in text.replace('[{"path"', "")


# --------------------------------------------------------------------------- the glue


def test_run_general_agent_copies_the_agents_work_back(
    tmp_path: Path, spec: MigrationSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    import migrator.general_agent as ga

    ws = make_mini_repo(tmp_path / "ws" / "workspace")
    monkeypatch.setattr(ga, "ensure_node", lambda *_a, **_k: Path("/usr/bin"))
    monkeypatch.setattr(ga, "ensure_srt", lambda *_a: tmp_path / "srt.js")
    monkeypatch.setattr(ga, "ensure_key_helper", lambda folder: folder / "key-helper.sh")

    class Ok:
        def __init__(self, *_a: Any) -> None: ...

        def run(self, command: Any, cwd: Path, **_k: Any) -> Any:
            return FakeRunner().run(command, cwd)

    monkeypatch.setattr(ga, "SrtRunner", Ok)
    probe = ProbeResult(ok=True, checks={"x": "ok"}, cost_usd=0.003)
    monkeypatch.setattr(ga, "run_probe", lambda *_a: probe)
    monkeypatch.setattr(ga, "with_proxy_checks", lambda p, _e: p)
    monkeypatch.setattr(ga, "host_install", lambda **_k: "installed")
    edit = (
        "sed -i.bak 's/createMuiTheme/createTheme/' src/theme.ts && rm src/theme.ts.bak && "
        'echo \'[{"path": "src/screens/ProfileCard.tsx", "reason": "makeStyles"}]\''
        " > ../unfinished.json"
    )
    binary = fake_claude(tmp_path, [result_event()], edit=edit)
    monkeypatch.setattr(ga, "claude_version", lambda _b: "2.1.321 (Claude Code)")
    from migrator.config import ResolvedRepoConfig, VerifyCommands

    config = ResolvedRepoConfig(
        package_manager="npm",
        lockfile="package-lock.json",
        node="20",
        install_flags=[],
        source_globs=["src/**/*.tsx", "src/**/*.ts"],
        exclude=[],
        runner="jest",
        verify=VerifyCommands(typecheck="tsc", lint="eslint src", test="jest"),
    )
    run = run_general_agent(
        settings=settings("rules"),
        spec=spec,
        config=config,
        workspace=ws,
        run_id="r1",
        run_dir=tmp_path / "run",
        tools_dir=tmp_path / "tools",
        budget_usd=5.0,
        say=lambda *_a: None,
        claude=binary,
        home=tmp_path / "agent-home",
    )
    assert run.status == "ok", run.reason
    assert run.copied_back == CopyBack(changed=["src/theme.ts"])
    assert "createTheme" in (ws / "src" / "theme.ts").read_text()
    assert run.unfinished == [Unfinished(path="src/screens/ProfileCard.tsx", reason="makeStyles")]
    assert run.agent is not None and run.agent.cost_usd == 0.42
    assert [c.cost_usd for c in run.calls()] == [0.42]  # the fake probe made no calls
    prompt = (tmp_path / "run" / "general-agent" / "prompt.md").read_text()
    assert "mui-codemod" in prompt
    # The prompt's budget left the probe's cost aside.
    assert (tmp_path / "agent-home" / "runs" / "r1" / "guide" / "migration-v4.md").is_file()


# --------------------------------------------------------------------------- a whole run


def test_a_whole_run_scores_the_agents_workspace(
    tmp_path: Path, spec: MigrationSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-check, the scripted agent, the reinstall, the final Verify and Scoring."""
    import migrator.run.stages.general_agent as stage

    def scripted(**kw: Any) -> AgentRun:
        ws: Path = kw["workspace"]
        theme = ws / "src" / "theme.ts"
        theme.write_text(
            theme.read_text().replace("@material-ui/core/styles", "@mui/material/styles")
        )
        test = ws / "src" / "screens" / "__tests__" / "ProfileCard.test.tsx"
        test.write_text(test.read_text().replace("it(", "it.skip("))
        pkg = json.loads((ws / "package.json").read_text())
        pkg["dependencies"]["@mui/material"] = "5.18.0"
        (ws / "package.json").write_text(json.dumps(pkg))
        from migrator.cost import CallRecord, Usage

        call = CallRecord(
            model=MODEL, requested_model=MODEL, usage=Usage(output_tokens=10), cost_usd=1.25
        )
        return AgentRun(
            status="ok",
            setup="rules",
            model=MODEL,
            effort="low",
            agent=AgentResult(status="completed", cost_usd=1.25, calls=[call]),
            copied_back=CopyBack(
                changed=[
                    "package.json",
                    "src/theme.ts",
                    "src/screens/__tests__/ProfileCard.test.tsx",
                ]
            ),
            unfinished=[Unfinished(path="src/screens/UsersTable.tsx", reason="not done")],
        )

    import migrator.general_agent as ga

    monkeypatch.setattr(stage, "run_general_agent", scripted)
    monkeypatch.setattr(ga, "find_claude", lambda: Path("/nonexistent/claude"))  # CI has none
    repo = make_mini_repo(tmp_path / "repo")
    runner = FakeRunner(FakeToolchain())
    ledger = Ledger(tmp_path / "ledger.jsonl")
    result = start_run(
        RunOptions(
            repo=repo,
            spec=spec,
            run_dir=tmp_path / "run",
            configuration=configuration("rules"),
            tools_cache=tmp_path / "cache",
            run_id="r1",
        ),
        runner,
        ledger=ledger,
    )
    assert isinstance(result, RunResult)
    card = result.scorecard
    assert card.status == "completed"
    files = {f.path: f for f in card.files}
    assert files["src/theme.ts"].layer == "agent"
    assert files["src/screens/UsersTable.tsx"].outcome == "Handed off"
    assert files["src/App.tsx"].outcome == "Unmigrated"  # nobody changed it
    # Claude Code's own figure per model, and the total from the tokens at the
    # Migrator's prices (10 output tokens here): the cross-check.
    assert [m.cost_usd for m in card.cost.by_model] == [1.25]
    assert card.cost.total_usd == card.cost.output_usd > 0
    assert [r.cost_usd for r in ledger.rows()] == [1.25]
    # The skipped test is a cheating-check hit, and the agent's packages were installed
    # again in the sandbox (npm install: the lockfile wasn't updated).
    assert card.cheating is not None and card.cheating.hits
    assert any(c.startswith("npm install") for c in runner.commands)
    assert not any("preset-safe" in c for c in runner.commands)  # no Rules stage
    saved = json.loads((tmp_path / "run" / "general-agent" / "run.json").read_text())
    assert saved["status"] == "ok"
