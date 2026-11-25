"""The general agent (M8): Claude Code, headless, migrating a repo on its own.

The comparison M8 Part A asks for: instead of the Migrator's Rules, Repair and Review,
give a general coding agent the repo, the vendored guide and the pinned codemods, and
ask it to migrate. Two setups: ``plain``, and ``rules`` (the Migrator's limits written
into the prompt, plus a list of unfinished files, each a Hand-off). The prompts are
``prompts/<setup>-<version>.md``, committed before any run and never tuned.

``run_general_agent`` does one run, between the Migrator's Pre-check and its final
Verify (``migrator.run.stages.general_agent``):

1. a copy of the workspace for the agent, its packages installed for this machine with
   the case's pinned Node, under the sandbox policy (``sandbox``);
2. the probe: the sandbox still blocks what it must (``probe``);
3. Claude Code on the copy, with a cost stop and a time limit (``agent``);
4. its changes applied to the Migrator's workspace.

See ``docs/research/claude-code-sandbox.md`` for why the sandbox is set up this way.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from migrator.config import ResolvedRepoConfig
from migrator.configuration import GeneralAgentSettings
from migrator.cost import CallRecord
from migrator.general_agent.agent import (
    AgentResult,
    CopyBack,
    Unfinished,
    claude_command,
    claude_version,
    copy_back,
    find_claude,
    make_copy,
    model_env,
    read_unfinished,
    run_claude,
    write_tool_wrappers,
)
from migrator.general_agent.errors import GeneralAgentError
from migrator.general_agent.hostnode import ensure_node
from migrator.general_agent.probe import (
    ProbeResult,
    require_probe,
    run_probe,
    run_shell_probe,
    with_proxy_checks,
)
from migrator.general_agent.proxy import AllowlistProxy, ProxySummary
from migrator.general_agent.rehearsal import RehearsalStep, rehearsal_steps, run_rehearsal
from migrator.general_agent.sandbox import (
    ALLOWED_DOMAINS,
    AgentPaths,
    Policy,
    SrtRunner,
    clean_env,
    ensure_key_helper,
    ensure_srt,
    host_install,
    real_home,
)
from migrator.migrations import MigrationSpec
from migrator.rules import tools_cache_root
from migrator.workspace import install_command

PROMPTS = Path(__file__).parent / "prompts"
# srt itself runs on this Node, whatever the case's.
SRT_NODE = "22"

__all__ = [
    "AgentRun",
    "GeneralAgentError",
    "agent_home",
    "ensure_agent_runnable",
    "render_prompt",
    "run_general_agent",
]


def agent_home() -> Path:
    return tools_cache_root() / "general-agent"


def ensure_agent_runnable(settings: GeneralAgentSettings) -> None:
    """Refuse before any run: no Claude Code, or no prompt for the setup and version."""
    prompt_path(settings)
    find_claude()


def prompt_path(settings: GeneralAgentSettings) -> Path:
    path = PROMPTS / f"{settings.setup}-{settings.prompt_version}.md"
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in PROMPTS.glob("*.md")))
        raise GeneralAgentError(f"no general-agent prompt {path.name} (known: {known})")
    return path


def render_prompt(
    settings: GeneralAgentSettings,
    spec: MigrationSpec,
    config: ResolvedRepoConfig,
    paths: AgentPaths,
    tools: list[str],
) -> str:
    codemod_bin = tools[0] if tools else "(none)"
    first = next((s for s in spec.rule_steps if s.kind == "codemod"), None)
    example = (
        f"{codemod_bin} {first.args[0]} src" if first is not None and first.args else codemod_bin
    )
    verify = config.verify
    return (
        prompt_path(settings)
        .read_text("utf-8")
        .format(
            library_name=spec.library_name,
            from_version=spec.from_version,
            to_version=spec.to_version,
            guide_title=spec.guide_title,
            guide_tag=spec.guide.tag,
            guide_dir=paths.guide,
            codemod_name=spec.codemod_name,
            codemod_bin=codemod_bin,
            codemod_example=example,
            package_manager=config.package_manager,
            typecheck=verify.typecheck or "(none)",
            lint=verify.lint or "(none)",
            test=verify.test or "(none)",
            unfinished_file=paths.unfinished,
        )
    )


class AgentRun(BaseModel):
    """One general-agent run, as the run state keeps it (``state["general_agent"]``)."""

    status: str  # "ok" (the agent ran; see agent.status) or "failed" (it never started)
    reason: str | None = None
    setup: str
    model: str
    effort: str
    prompt: str | None = None  # the prompt file's name
    claude_version: str | None = None
    agent_folder: str | None = None
    probe: ProbeResult | None = None
    host_install: str | None = None  # the agent's copy, on this machine
    reinstall: str | None = None  # the Migrator's workspace, when the agent changed packages
    agent: AgentResult | None = None
    unfinished: list[Unfinished] = []
    unfinished_note: str | None = None
    copied_back: CopyBack | None = None
    proxy: ProxySummary | None = None  # what the agent's commands tried to reach
    rehearsal: list[RehearsalStep] | None = None  # a rehearsal's steps, in place of a model
    codemod_baseline: str | None = None  # the cheating checks' baseline: what happened

    def calls(self) -> list[CallRecord]:
        """Every model call of the run, the probe's included."""
        return [
            *(self.probe.calls if self.probe else []),
            *(self.agent.calls if self.agent else []),
        ]


Say = Callable[[str, str], None]


def run_general_agent(
    *,
    settings: GeneralAgentSettings,
    spec: MigrationSpec,
    config: ResolvedRepoConfig,
    workspace: Path,
    run_id: str,
    run_dir: Path,
    tools_dir: Path | None,
    budget_usd: float,
    say: Say,
    claude: Path | None = None,
    home: Path | None = None,
) -> AgentRun:
    """Set up, probe, run the agent and copy its changes back into ``workspace``."""
    assert settings.setup and settings.model and settings.effort
    base = AgentRun(
        status="failed", setup=settings.setup, model=settings.model, effort=settings.effort
    )
    folder = (home or agent_home()) / "runs" / run_id
    paths = AgentPaths(root=folder)
    record = run_dir / "general-agent"
    proxy = AllowlistProxy(ALLOWED_DOMAINS, record / "proxy.jsonl")
    try:
        binary = claude or find_claude()
        base.claude_version = claude_version(binary)
        base.prompt = prompt_path(settings).name
        base.agent_folder = str(folder)
        paths.make()
        cache = home or agent_home()
        node_bin = ensure_node(config.node, cache / "node", config.package_manager)
        srt_bin = ensure_node(SRT_NODE, cache / "node")
        srt = ensure_srt(cache / "srt", srt_bin)
        policy = Policy(
            paths=paths,
            protected=[workspace.parent, run_dir],
            real_home=real_home(),
            proxy_port=proxy.start(),
        )
        policy.write(ensure_key_helper(cache))
        start = make_copy(workspace, paths)
        shutil.copytree(spec.guide_dir(), paths.guide)
        tools = write_tool_wrappers(paths, _tool_scripts(spec, tools_dir))
        env = clean_env(paths, node_bin, config.install_env)
        say("General agent", f"installing packages in the agent's copy (Node {config.node})")
        command = install_command(config.package_manager, True, config.install_flags)
        runner = SrtRunner(srt, srt_bin, paths.srt_settings, env)
        base.host_install = host_install(
            paths=paths,
            command=command,
            env=env,
            proxy_port=policy.proxy_port,
            sandboxed=runner,
            log_dir=run_dir / "logs",
        )
        say("General agent", "probing the sandbox")
        model_vars = model_env(settings.model, settings.effort)
        if settings.rehearsal:
            probe = run_shell_probe(runner, paths, policy.protected)
        else:
            probe = run_probe(
                binary, paths, {**env, **model_vars}, policy.protected, record / "probe.jsonl"
            )
        base.probe = with_proxy_checks(probe, proxy.entries())
        require_probe(base.probe)
        prompt = render_prompt(settings, spec, config, paths, tools)
        record.mkdir(parents=True, exist_ok=True)
        (record / "prompt.md").write_text(prompt, "utf-8")
        if settings.rehearsal:
            say("General agent", "rehearsal: a fixed script in place of Claude Code")
            result, base.rehearsal = run_rehearsal(
                runner,
                paths,
                rehearsal_steps(spec, config, tools),
                record / "rehearsal",
                settings.timeout_s,
            )
        else:
            left = round(budget_usd - base.probe.cost_usd, 2)
            say(
                "General agent",
                f"Claude Code on {settings.model}, effort {settings.effort}, stop at ${left:.2f}",
            )
            result = _run_agent(
                binary, settings, prompt, left, paths, {**env, **model_vars}, record
            )
    except GeneralAgentError as exc:
        return base.model_copy(update={"reason": str(exc), "proxy": proxy.summary()})
    finally:
        proxy.stop()
    say(
        "General agent",
        f"{result.status} after {result.num_turns} turns, ${result.cost_usd:.2f}, "
        f"{result.duration_s:.0f}s",
    )
    summary = proxy.summary()
    if summary.refused:
        say("General agent", f"the proxy refused: {', '.join(sorted(summary.refused))}")
    back = copy_back(paths.repo, start, workspace)
    unfinished: list[Unfinished] = []
    note = None
    if settings.setup == "rules":
        unfinished, note = read_unfinished(paths.unfinished, set(back.all) | set(start))
    return base.model_copy(
        update={
            "status": "ok",
            "agent": result,
            "copied_back": back,
            "unfinished": unfinished,
            "unfinished_note": note,
            "proxy": summary,
        }
    )


def _run_agent(
    binary: Path,
    settings: GeneralAgentSettings,
    prompt: str,
    budget_usd: float,
    paths: AgentPaths,
    env: dict[str, str],
    record: Path,
) -> AgentResult:
    assert settings.model and settings.effort
    return run_claude(
        claude_command(
            binary,
            prompt=prompt,
            model=settings.model,
            effort=settings.effort,
            budget_usd=budget_usd,
            settings=paths.claude_settings,
        ),
        cwd=paths.repo,
        env=env,
        timeout_s=settings.timeout_s,
        transcript=record / "transcript.jsonl",
        requested_model=settings.model,
        allowed_writes=[paths.root],  # the sandbox's own write limit
    )


def _tool_scripts(spec: MigrationSpec, tools_dir: Path | None) -> dict[str, Path]:
    if spec.tools is None or tools_dir is None:
        return {}
    return {name: tools_dir / rel for name, rel in spec.tools.bins.items()}
