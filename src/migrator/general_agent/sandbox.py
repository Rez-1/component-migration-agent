"""The general agent's sandbox: one policy, written as Claude Code's settings and as
the sandbox runtime's (M8, ``docs/research/claude-code-sandbox.md``).

The agent's shell commands run in Claude Code's own sandbox (Seatbelt on macOS,
bubblewrap on Linux): writes only in the agent's folder, no reads of the key folder or
``~/.ssh``, and the network limited to the package registries. Claude Code itself (the
model API) runs outside it. The Migrator's own host install, before the agent starts,
runs under the same policy through ``srt``, the sandbox runtime Claude Code is built
on. The strict settings close the gaps the research found: no unsandboxed retries,
hosts off the list refused in every permission mode, and a start-up failure stops the
run instead of running unsandboxed. The file tools (Read, Edit, Write) are not
sandboxed, so they get deny rules, and every path they touched is audited afterwards.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from migrator.execs import CommandResult, LocalRunner
from migrator.general_agent.errors import GeneralAgentError

# The only hosts the agent's commands may reach: npm's and yarn v1's registries.
ALLOWED_DOMAINS = ["registry.npmjs.org", "registry.yarnpkg.com"]
# The sandbox runtime, pinned (tested in the research, 13 November 2026).
SRT_PACKAGE = "@anthropic-ai/sandbox-runtime@0.0.81"
KEY_FILE = "anthropic.env"


def key_dir() -> Path:
    return Path.home() / ".config" / "migrator"


class AgentPaths(BaseModel):
    """One general-agent run's folder, outside the system temp folder (which the
    sandbox lets every command write to)."""

    model_config = ConfigDict(frozen=True)

    root: Path

    @property
    def repo(self) -> Path:
        return self.root / "repo"

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def bin(self) -> Path:
        return self.root / "bin"

    @property
    def guide(self) -> Path:
        return self.root / "guide"

    @property
    def probe(self) -> Path:
        return self.root / "probe"

    @property
    def unfinished(self) -> Path:
        return self.root / "unfinished.json"

    @property
    def claude_settings(self) -> Path:
        return self.root / "claude-settings.json"

    @property
    def srt_settings(self) -> Path:
        return self.root / "srt-settings.json"

    def make(self) -> None:
        for path in (self.root, self.home, self.tmp, self.cache, self.bin, self.probe):
            path.mkdir(parents=True, exist_ok=True)


class Policy(BaseModel):
    """What the agent's commands may touch; the same for Claude Code and ``srt``."""

    model_config = ConfigDict(frozen=True)

    paths: AgentPaths
    # Folders the agent must not write, though the sandbox's defaults would let it: the
    # Migrator's workspace (in the system temp folder) and the run folder.
    protected: list[Path]
    real_home: Path

    def deny_read(self) -> list[str]:
        h = self.real_home
        return [str(key_dir()), str(h / ".ssh"), str(h / ".aws"), str(h / ".gnupg")]

    def deny_write(self) -> list[str]:
        return [str(p) for p in self.protected]

    def claude_settings(self, key_helper: Path) -> dict[str, object]:
        """Claude Code's ``--settings``. Rule paths starting ``//`` are absolute (one
        ``/`` would be relative to this file: the research's mistake)."""
        h = self.real_home
        no_read = self.deny_read()
        no_edit_dirs = [
            *no_read,
            *self.deny_write(),
            *(str(h / d) for d in (".config", ".claude", ".local", "Library", "Code")),
            *(str(h / d) for d in ("Documents", "Desktop")),
        ]
        no_edit_files = [
            str(h / f) for f in (".zshrc", ".zprofile", ".bashrc", ".bash_profile", ".profile")
        ]
        return {
            "apiKeyHelper": str(key_helper),
            "permissions": {
                "deny": [
                    *(f"Read(/{p}/**)" for p in no_read),
                    *(f"Edit(/{p}/**)" for p in no_edit_dirs),
                    *(f"Edit(/{p})" for p in no_edit_files),
                    "WebFetch",
                    "WebSearch",
                ]
            },
            "sandbox": {
                "enabled": True,
                "failIfUnavailable": True,
                "allowUnsandboxedCommands": False,
                "autoAllowBashIfSandboxed": True,
                "excludedCommands": [],
                "network": {"allowedDomains": ALLOWED_DOMAINS, "strictAllowlist": True},
                "filesystem": {
                    "denyRead": no_read,
                    "allowWrite": [str(self.paths.root)],
                    "denyWrite": self.deny_write(),
                },
            },
        }

    def srt_settings(self) -> dict[str, object]:
        return {
            "network": {"allowedDomains": ALLOWED_DOMAINS, "deniedDomains": []},
            "filesystem": {
                "denyRead": self.deny_read(),
                "allowWrite": [str(self.paths.root)],
                "denyWrite": self.deny_write(),
            },
        }

    def write(self, key_helper: Path) -> None:
        self.paths.claude_settings.write_text(
            json.dumps(self.claude_settings(key_helper), indent=2) + "\n", "utf-8"
        )
        self.paths.srt_settings.write_text(
            json.dumps(self.srt_settings(), indent=2) + "\n", "utf-8"
        )


def ensure_key_helper(folder: Path) -> Path:
    """A script Claude Code runs (outside the sandbox) to get the API key from the key
    folder, which the agent's commands and file tools cannot read. It holds a path,
    never the key."""
    key = key_dir() / KEY_FILE
    if not key.is_file():
        raise GeneralAgentError(f"no API key file at {key} (ANTHROPIC_API_KEY=...)")
    folder.mkdir(parents=True, exist_ok=True)
    helper = folder / "key-helper.sh"
    helper.write_text(
        "#!/bin/sh\n"
        f"sed -n 's/^ANTHROPIC_API_KEY=//p' {shlex.quote(str(key))}"
        " | tr -d '\"'\"'\"' \\n'\n",
        "utf-8",
    )
    helper.chmod(0o700)
    return helper


def ensure_srt(folder: Path, node_bin: Path) -> Path:
    """The pinned sandbox runtime's CLI, installed once (scripts off) with ``node_bin``."""
    cli = folder / "node_modules" / "@anthropic-ai" / "sandbox-runtime" / "dist" / "cli.js"
    if cli.is_file():
        return cli
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_text('{"private": true}\n', "utf-8")
    done = subprocess.run(
        [
            str(node_bin / "npm"),
            "install",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            SRT_PACKAGE,
        ],
        cwd=folder,
        env={"PATH": f"{node_bin}:/usr/bin:/bin", "HOME": str(folder)},
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0 or not cli.is_file():
        raise GeneralAgentError(f"could not install {SRT_PACKAGE}: {done.stdout[-400:]}")
    return cli


class SrtRunner:
    """A CommandRunner whose commands run under the agent's policy, through ``srt``."""

    def __init__(self, srt_cli: Path, node_bin: Path, settings: Path, env: Mapping[str, str]):
        self.srt = srt_cli
        self.node_bin = node_bin
        self.settings = settings
        self.inner = LocalRunner(base_env=env)

    def run(
        self,
        command: str | Sequence[str],
        cwd: Path,
        *,
        env: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
        log_file: Path | None = None,
    ) -> CommandResult:
        line = command if isinstance(command, str) else shlex.join(command)
        argv = [str(self.node_bin / "node"), str(self.srt), "-s", str(self.settings), "-c", line]
        result = self.inner.run(argv, cwd, env=env, timeout_s=timeout_s, log_file=log_file)
        return result.model_copy(update={"command": line})


def clean_env(
    paths: AgentPaths, node_bin: Path, extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The environment the agent and its commands get: none of the owner's variables,
    a home and temp folder of its own, package caches in its folder."""
    env = {
        "PATH": f"{paths.bin}:{node_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(paths.home),
        "TMPDIR": str(paths.tmp),
        "LANG": "en_US.UTF-8",
        "TERM": "dumb",
        "CI": "true",
        "npm_config_cache": str(paths.cache / "npm"),
        "npm_config_update_notifier": "false",
        "YARN_CACHE_FOLDER": str(paths.cache / "yarn"),
        "NODE_USE_ENV_PROXY": "1",  # Node's own fetch honours the sandbox proxy
    }
    env.update(extra or {})
    return env


def real_home() -> Path:
    return Path.home().resolve()
