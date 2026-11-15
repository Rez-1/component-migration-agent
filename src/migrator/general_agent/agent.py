"""One general-agent run: a copy of the workspace, Claude Code headless on it, and the
changes copied back (M8).

The agent works in its own copy of the Pre-checked workspace, outside the system temp
folder, with its packages installed for this machine (the Migrator's workspace has
the Docker image's). When it ends, every file it added, changed or deleted (git's view:
ignored files and ``node_modules`` left out) is applied to the Migrator's workspace,
which then goes through the same final Verify, cheating checks and Scoring as a
Migrator run.

Cost and tokens come from Claude Code's own result (``total_cost_usd``, ``modelUsage``)
and are cross-checked against the Migrator's price table. The transcript is kept in the
run folder and audited: any unsandboxed request, and any file tool that touched a path
outside the agent's copy, is recorded on the run.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from migrator.cost import CallRecord, Usage, cost_usd
from migrator.general_agent.errors import GeneralAgentError
from migrator.general_agent.sandbox import AgentPaths

AgentStatus = Literal["completed", "stopped_by_cost", "timed_out", "failed"]
FILE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


# --------------------------------------------------------------------------- the CLI


def find_claude() -> Path:
    """Claude Code's binary: ``MIGRATOR_CLAUDE_BIN``, else ``claude`` on PATH, else the
    copy the Claude desktop app bundles (the PATH entry may be a shell wrapper that
    needs the real HOME, which the agent doesn't get)."""
    env = os.environ.get("MIGRATOR_CLAUDE_BIN")
    if env:
        return Path(env)
    found = shutil.which("claude")
    if found and not _is_script(Path(found)):
        return Path(found).resolve()
    bundled = list(
        (Path.home() / "Library" / "Application Support" / "Claude" / "claude-code").glob(
            "**/claude.app/Contents/MacOS/claude"
        )
    )
    if bundled:
        return _newest(bundled)
    raise GeneralAgentError("Claude Code not found: install it or set MIGRATOR_CLAUDE_BIN")


def _is_script(path: Path) -> bool:
    try:
        return path.resolve().read_bytes()[:2] == b"#!"
    except OSError:
        return False


def _newest(paths: list[Path]) -> Path:
    def version(p: Path) -> tuple[int, ...]:
        for part in p.parts:
            bits = part.split(".")
            if len(bits) == 3 and all(b.isdigit() for b in bits):
                return tuple(int(b) for b in bits)
        return (0,)

    return max(paths, key=version)


def claude_version(binary: Path) -> str:
    done = subprocess.run(
        [str(binary), "--version"], capture_output=True, text=True, timeout=60, check=False
    )
    return done.stdout.strip() or f"unknown (exit {done.returncode})"


# --------------------------------------------------------------------------- the copy


def _git(args: list[str], cwd: Path) -> str:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(cwd),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "migrator",
        "GIT_AUTHOR_EMAIL": "migrator@localhost",
        "GIT_COMMITTER_NAME": "migrator",
        "GIT_COMMITTER_EMAIL": "migrator@localhost",
    }
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise GeneralAgentError(f"git {' '.join(args)}: {done.stderr.strip()[-300:]}")
    return done.stdout


def listed_files(repo: Path) -> list[str]:
    """The repo's files as git sees them (tracked and untracked, ignored ones left out),
    never git's own folder or ``node_modules``. If the agent broke its git repo, every
    file outside those two folders."""
    try:
        out = _git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], repo)
        found = out.split("\0")
    except GeneralAgentError:
        found = []
        for folder, dirs, files in repo.walk():
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".git")]
            found += [(folder / f).relative_to(repo).as_posix() for f in files]
    return sorted(
        p
        for p in found
        if p and not p.startswith(".git/") and "node_modules/" not in p and (repo / p).is_file()
    )


def make_copy(workspace: Path, paths: AgentPaths) -> list[str]:
    """The agent's copy of the workspace, as a git repo with one commit (so the agent
    can use ``git diff``); returns the files it starts with."""
    if paths.repo.exists():
        raise GeneralAgentError(f"{paths.repo} already exists")
    shutil.copytree(
        workspace, paths.repo, ignore=shutil.ignore_patterns("node_modules", ".git"), symlinks=True
    )
    _git(["init", "-q", "-b", "main"], paths.repo)
    _git(["add", "-A"], paths.repo)
    _git(["commit", "-q", "--no-verify", "-m", "The workspace before the migration"], paths.repo)
    return listed_files(paths.repo)


def write_tool_wrappers(paths: AgentPaths, tools: Mapping[str, Path]) -> list[str]:
    """One command per pinned tool (``mui-codemod``) in the agent's ``bin``."""
    names = []
    for name, script in tools.items():
        wrapper = paths.bin / name
        wrapper.write_text(f'#!/bin/sh\nexec node {shlex.quote(str(script))} "$@"\n', "utf-8")
        wrapper.chmod(0o755)
        names.append(name)
    return names


class CopyBack(BaseModel):
    added: list[str] = []
    changed: list[str] = []
    deleted: list[str] = []

    @property
    def all(self) -> list[str]:
        return sorted({*self.added, *self.changed, *self.deleted})


def copy_back(repo: Path, start: list[str], workspace: Path) -> CopyBack:
    """Apply the agent's added, changed and deleted files to the Migrator's workspace."""
    now = listed_files(repo)
    out = CopyBack()
    for path in now:
        src, dst = repo / path, workspace / path
        if not dst.is_file():
            out.added.append(path)
        elif src.read_bytes() != dst.read_bytes():
            out.changed.append(path)
        else:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for path in sorted(set(start) - set(now)):
        if (workspace / path).is_file():
            (workspace / path).unlink()
            out.deleted.append(path)
    return out


# --------------------------------------------------------------------------- running it


class Audit(BaseModel):
    """What the transcript shows the agent did, for the run's record."""

    tool_calls: dict[str, int] = {}
    unsandboxed_requests: int = 0  # Bash calls asking for dangerouslyDisableSandbox
    outside_writes: list[str] = []  # file-tool paths outside the agent's copy
    subagents: int = 0

    @property
    def clean(self) -> bool:
        return not self.unsandboxed_requests and not self.outside_writes


class AgentResult(BaseModel):
    status: AgentStatus
    detail: str = ""
    subtype: str | None = None
    num_turns: int = 0
    duration_s: float = 0.0
    cost_usd: float = 0.0  # Claude Code's own total
    priced_usd: float | None = None  # the same usage at the Migrator's prices
    calls: list[CallRecord] = []  # one per model, for the ledger and the Scorecard
    audit: Audit = Audit()
    transcript: str | None = None


def tool_uses(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("type") != "assistant":
            continue
        for block in (ev.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                out.append(block)
    return out


def audit(events: list[dict[str, Any]], allowed: list[Path]) -> Audit:
    uses = tool_uses(events)
    outside: list[str] = []
    for use in uses:
        args = use.get("input") or {}
        if use.get("name") in FILE_TOOLS:
            target = args.get("file_path") or args.get("notebook_path")
            if target and not any(_inside(Path(target), a) for a in allowed):
                outside.append(str(target))
    return Audit(
        tool_calls=dict(Counter(str(u.get("name")) for u in uses)),
        unsandboxed_requests=sum(
            1
            for u in uses
            if u.get("name") == "Bash" and (u.get("input") or {}).get("dangerouslyDisableSandbox")
        ),
        outside_writes=sorted(set(outside)),
        subagents=sum(1 for u in uses if u.get("name") in ("Task", "Agent")),
    )


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def calls_from(result: dict[str, Any], requested: str) -> list[CallRecord]:
    """One CallRecord per model Claude Code used, from its ``modelUsage``."""
    calls = []
    for model, u in (result.get("modelUsage") or {}).items():
        usage = Usage(
            input_tokens=int(u.get("inputTokens") or 0),
            output_tokens=int(u.get("outputTokens") or 0),
            cache_read_input_tokens=int(u.get("cacheReadInputTokens") or 0),
            cache_creation_input_tokens=int(
                u.get("cacheCreationEphemeral5mInputTokens", u.get("cacheCreationInputTokens")) or 0
            ),
            cache_creation_1h_input_tokens=int(u.get("cacheCreationEphemeral1hInputTokens") or 0),
        )
        calls.append(
            CallRecord(
                model=str(u.get("canonicalModel") or model),
                requested_model=requested,
                usage=usage,
                cost_usd=float(u.get("costUSD") or 0.0),
                stop_reason=str(result.get("stop_reason") or "") or None,
                duration_s=round(float(result.get("duration_ms") or 0) / 1000, 2),
            )
        )
    return calls


def priced(calls: list[CallRecord]) -> float | None:
    """The calls at the Migrator's own prices; None when a model is not in its table."""
    try:
        return round(sum(cost_usd(c.model, c.usage) for c in calls), 6)
    except KeyError:
        return None


def claude_command(
    binary: Path,
    *,
    prompt: str,
    model: str,
    effort: str,
    budget_usd: float,
    settings: Path,
) -> list[str]:
    return [
        str(binary),
        "-p",
        "--bare",
        "--model",
        model,
        "--effort",
        effort,
        "--max-budget-usd",
        f"{budget_usd:.2f}",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--settings",
        str(settings),
        prompt,
    ]


def model_env(model: str, effort: str) -> dict[str, str]:
    """Every model Claude Code may pick, subagents and background helpers included, is
    ``model``; effort fixed; no auto-update or optional traffic during a run."""
    return {
        "CLAUDE_CODE_SUBAGENT_MODEL": model,
        "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "ANTHROPIC_DEFAULT_FABLE_MODEL": model,
        "CLAUDE_CODE_EFFORT_LEVEL": effort,
        "DISABLE_AUTOUPDATER": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }


def run_claude(
    command: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_s: float,
    transcript: Path,
    requested_model: str,
    allowed_writes: list[Path],
) -> AgentResult:
    """Run Claude Code to the end (or the timeout), keeping its stream-json transcript."""
    transcript.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with transcript.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # its process group, so a timeout ends its children too
        )
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    events, noise = read_transcript(transcript)
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    duration = round(time.monotonic() - started, 1)
    found = audit(events, allowed_writes)
    if result is None:
        status: AgentStatus = "timed_out" if timed_out else "failed"
        detail = f"no result after {duration}s" if timed_out else (noise[-1] if noise else "")
        return AgentResult(
            status=status,
            detail=detail[-400:],
            duration_s=duration,
            audit=found,
            transcript=str(transcript),
        )
    calls = calls_from(result, requested_model)
    subtype = str(result.get("subtype") or "")
    if "budget" in subtype:
        status = "stopped_by_cost"
    elif result.get("is_error"):
        status = "failed"
    else:
        status = "completed"
    return AgentResult(
        status=status,
        detail=str(result.get("result") or "")[-2000:],
        subtype=subtype,
        num_turns=int(result.get("num_turns") or 0),
        duration_s=duration,
        cost_usd=float(result.get("total_cost_usd") or 0.0),
        priced_usd=priced(calls),
        calls=calls,
        audit=found,
        transcript=str(transcript),
    )


def read_transcript(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Its JSON events, and any other lines (Claude Code's own errors)."""
    events: list[dict[str, Any]] = []
    noise: list[str] = []
    for line in path.read_text("utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            if line.strip():
                noise.append(line.strip())
            continue
        if isinstance(ev, dict):
            events.append(ev)
    return events, noise


class Unfinished(BaseModel):
    path: str
    reason: str


def read_unfinished(path: Path, repo_files: set[str]) -> tuple[list[Unfinished], str | None]:
    """The files the agent listed as not finished (the setup with the rules), and a
    note when the list is missing or malformed (then it counts as empty)."""
    if not path.is_file():
        return [], "the agent wrote no unfinished-files list"
    try:
        data = json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        return [], f"the unfinished-files list is not JSON: {exc}"
    if not isinstance(data, list):
        return [], "the unfinished-files list is not a JSON array"
    out: list[Unfinished] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            rel = item["path"].removeprefix("./")
            if rel in repo_files:
                out.append(Unfinished(path=rel, reason=str(item.get("reason") or "")[:500]))
    return out, None
