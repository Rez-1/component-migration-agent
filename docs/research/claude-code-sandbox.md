# Can Claude Code's sandbox replace a network-restricted Docker container for M8?

Investigated on 13 November 2026, Claude Code 2.1.321 on macOS (Darwin 25.6), for M8 Part A (Migrator vs Claude Code run headless). The question: can the general agent's own commands run under Claude Code's built-in sandbox instead of a Docker container with an egress proxy, which we'd have to build? Scoring still runs Verify in our existing Docker sandbox afterwards.

**Short answer: mostly yes.** The sandbox is enforced by the OS and its domain allow-list does what we need. Out of the box it is not strict enough, though. Four defaults have to be changed, and two gaps fall outside the sandbox: the file tools, and Node 16 on the host. Details are under the questions below.

## Answers

| # | Question | Answer |
|---|---|---|
| 1 | What it enforces on macOS | **Yes, enforced by the OS (Seatbelt)**, but only for Bash commands and their child processes. The Read/Edit/Write/WebFetch tools are governed by permission rules, not by the sandbox. |
| 2 | Holds in headless mode | **Partial.** The sandbox still applies under `-p` and bypass. But with default settings the agent can retry a blocked command unsandboxed, and in `bypassPermissions` a host that isn't on the list is *allowed* without a prompt. Settings close both gaps. Not tested end to end: the paid run failed on an expired login (see Experiment 2). |
| 3 | Allow-list only the API and the registries | **Yes.** Tested: `registry.npmjs.org`, `registry.yarnpkg.com` and `api.anthropic.com` worked, and everything else got a 403 at the proxy or had no route. Node's built-in `fetch` ignores the proxy, so it fails even for allowed hosts. npm and yarn are fine. |
| 4 | Secrets | **Partial.** `denyRead` blocked the dummy secret, `~/.config/migrator` and `~/.ssh` (tested). Reads are open by default, so these must be listed. Environment variables are passed through to commands by default (tested), and the Read tool ignores `denyRead`. Both have fixes. |
| 5 | Model, effort, spend stop, cost report | **Yes.** `--model`, `--effort low`, `CLAUDE_CODE_SUBAGENT_MODEL` + `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`, `ANTHROPIC_DEFAULT_HAIKU_MODEL` for background calls, `--max-budget-usd`, `--max-turns`. The JSON result carries `total_cost_usd`, `usage` and `modelUsage` (keys seen in a real result). |
| 6 | Practical fit | **Partial.** Docker can't run inside the sandbox, but it doesn't need to: Verify runs afterwards, outside. Node 16 is the real problem. The host has Node 24 and no version manager, so the agent would run OpossumUI's and wps's `yarn`/`jest`/`tsc` on the wrong Node unless we put Node 16 on its PATH. The installed `node_modules` would also be built for macOS, while Verify runs on Linux. |

### 1. What it enforces on macOS

- macOS uses Seatbelt (`sandbox-exec` with a profile generated for each command). Linux uses bubblewrap. All network traffic goes through a local proxy. Seatbelt only lets the command reach that proxy's localhost port, so a program that ignores the proxy has no route out. [sandboxing], [sandbox-runtime README]
- It is off by default (`sandbox.enabled: true` turns it on). If it can't start, it **fails open**: commands then run without a sandbox, unless `sandbox.failIfUnavailable: true` is set. [sandboxing]
- Writes are allowed by default in the working folder, the temp folder and `--add-dir` paths. Some paths stay protected even inside it, such as `.claude`, `.git/hooks`, `.git/config` and `.zshrc`. **Reads are allowed everywhere** except paths listed in `filesystem.denyRead`. [sandboxing]
- Child processes stay inside: "Restrictions apply to the entire process tree" [README]. Tested with `node` writing and reading files, plus `npm`, `curl` and `nc` (Experiment 1).
- **Scope:** "Read, Edit, Write, WebFetch, and WebSearch follow permission rules instead", and "A denyRead entry doesn't stop the Read tool" [sandboxing]. So the file tools need their own `permissions.deny` rules, or `permissions.blockReadsOutsideWorkingDirectories`.

### 2. Headless mode and escape hatches

- Approving sandboxed commands automatically (`autoAllowBashIfSandboxed`, on by default) is independent of the permission mode. Bypass only removes prompts; it doesn't turn the sandbox off. [sandboxing]
- **Escape hatch:** after a block, the model may retry the command with `dangerouslyDisableSandbox: true`. In `bypassPermissions` that retry runs with no prompt. `sandbox.allowUnsandboxedCommands: false` makes Claude Code ignore the parameter. [sandboxing]
- **Hosts not on the list:** what happens depends on the permission mode. Manual mode prompts, `dontAsk` refuses, and **`bypassPermissions` allows the host without a prompt**. `sandbox.network.strictAllowlist` (or `allowManagedDomainsOnly` in managed settings) refuses them in every mode. [sandboxing]. Both setting names exist in this CLI build (checked in the binary).
- `excludedCommands` runs matching commands with full access. We should leave it empty.
- Settings can be pinned with `--settings <file>` together with `--setting-sources project`. Managed settings can't be overridden at all. One trap: in `-p` mode, "Settings files that fail validation are silently ignored" (`claude --help`). A typo in the sandbox block would therefore run with no sandbox at all, so `failIfUnavailable: true` and a probe check before each run are a must.

### 3. Network allow-list

- Entries are hostnames, optionally with a port. A leading `*.` wildcard is supported, and wildcards anywhere else have no effect. `deniedDomains` is checked first. The proxy filters on the hostname and doesn't decrypt TLS, so domain fronting is a stated risk. [sandboxing]
- Claude Code's own API calls come from the main process, which isn't sandboxed. So `api.anthropic.com` is only needed on the list if the agent's commands call it, and they shouldn't. Leave it off.
- `registry.npmjs.org` + `registry.yarnpkg.com` cover npm and yarn v1. `github.com` and `codeload.github.com` would be needed only for git dependencies; leave them off and see whether the installs break.

### 4. Secrets

- Home folder reads are open by default, including `~/.ssh` and `~/.aws` [sandboxing]. Tested: `denyRead` on `~/.config/migrator`, `~/.ssh` and a dummy secret folder blocked `cat`, `ls` and `node` reads.
- Environment variables: "Sandboxed commands inherit Claude Code's environment, including any secrets" [sandboxing]. Tested: a dummy variable was visible inside the sandbox. Fix: `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` (strips credentials from subprocesses) or `sandbox.credentials.envVars` with `mode: "deny"`. Better still, don't export the key at all.
- How to pass the key: use `apiKeyHelper` in the `--settings` file, as a script that reads the key from `~/.config/migrator/`. The helper runs in the main process, outside the sandbox, so `denyRead` on that folder doesn't stop it, and the agent's commands still can't read the file. Then add `permissions.deny` for `Read(~/.config/migrator/**)` and `Read(~/.ssh/**)` so the Read tool can't open them either. Alternatively, `--bare` with `ANTHROPIC_API_KEY` plus env scrubbing. Whether the agent can read the OAuth token in the Keychain was not tested; using a key helper avoids the question.

### 5. Models and cost

- Main model: `--model claude-opus-5-5` (overrides the `model` setting and `ANTHROPIC_MODEL`). Effort: `--effort low`. `CLAUDE_CODE_EFFORT_LEVEL=low` overrides it, so set both or unset the variable. [cli-reference], [model-config]
- Subagents: `CLAUDE_CODE_SUBAGENT_MODEL=claude-opus-5-5` + `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (ignores the frontmatter of built-in agents). Background "small fast" calls: `ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-opus-5-5` (the old `ANTHROPIC_SMALL_FAST_MODEL` is deprecated). [sub-agents], [env-vars]. Whether every helper really used Opus can be checked afterwards: `modelUsage` lists each model used.
- Spend stop: `--max-budget-usd` (print mode only; checked against a client-side estimate; subagent spend counts). `--max-turns` as a second limit. [cli-reference]
- `--output-format json` returns `total_cost_usd`, `usage` (excludes subagents), `modelUsage` (per model, with cost and tokens), `num_turns`, `permission_denials` and `subagent_stats`. These are the keys of a real result from Experiment 2. The costs are client-side estimates, not billing data. [cost-tracking]

### 6. Practical fit

- **Docker inside the sandbox:** blocked (tested: the daemon wasn't reachable), and the docs call it "incompatible". Not needed, because Verify runs after the agent finishes, outside its sandbox.
- **Node 16 (OpossumUI, wps):** the host has Node 24.14 only, with no nvm, fnm or volta. The agent's `yarn install`, `jest` and `tsc` must run on Node 16, or the repo's test runs will disagree with Verify. Fix: download a Node 16 binary into a folder outside the repo and put it first on the agent's `PATH` (yarn v1 through corepack or `npm i -g yarn@1` in that folder). kubeflow needs Node 22 the same way.
- **macOS vs Linux:** packages the agent installs are built for darwin. Verify must do a clean `yarn install`/`npm ci` in its Linux container from the agent's lockfile, never reuse the agent's `node_modules`. Check that the Verify image does this.
- **Jest:** use `--no-watchman`, since watchman is incompatible with the sandbox [sandboxing]. CRA's `react-scripts test` uses watchman when it's installed.
- Noise: Node inside the sandbox printed many "failed to copy trust settings of system certificate" lines. They're harmless but will clutter the agent's logs.

## Experiments

### Experiment 1 (free): `srt`, the sandbox runtime Claude Code uses

`@anthropic-ai/sandbox-runtime@0.0.81` was installed into a scratch folder with `--ignore-scripts`. The setup: a throwaway `exp/work` folder as the working directory, a dummy secret `exp/secret/dummy.env` outside it, and a second dummy file at `~/.config/migrator/zz-sandbox-dummy.env`, removed afterwards. No real key was read or printed.

Settings (`srt -s settings.json`):

```json
{
  "network": {"allowedDomains": ["api.anthropic.com","registry.npmjs.org","registry.yarnpkg.com"], "deniedDomains": []},
  "filesystem": {"denyRead": ["<exp>/secret", "~/.config/migrator", "~/.ssh"], "allowWrite": ["<exp>/work"], "denyWrite": []}
}
```

The probe script ran each check and printed ALLOWED or blocked by exit code:

| Check | No sandbox | In `srt` |
|---|---|---|
| `cat` dummy secret outside folder | ALLOWED | blocked |
| `cat ~/.config/migrator/` dummy | ALLOWED | blocked |
| `ls ~/.ssh` | ALLOWED | blocked |
| `head -c1 ~/.zshrc` (not denied) | ALLOWED | ALLOWED (reads are open by default) |
| write inside work folder | ALLOWED | ALLOWED |
| write outside (`exp/`, `~/`) | ALLOWED | blocked |
| `node -e` writes outside / reads secret | ALLOWED | blocked |
| `curl https://example.com`, `https://github.com` | ALLOWED | blocked (`CONNECT tunnel failed, response 403`) |
| `nc -z 1.1.1.1 443` (raw TCP) | ALLOWED | blocked |
| `node` built-in `fetch('https://example.com')` | ALLOWED | blocked |
| `node` built-in `fetch` to registry.npmjs.org | ok | **fails** (`ENOTFOUND`: fetch ignores the proxy); works with `NODE_USE_ENV_PROXY=1` |
| `curl https://api.anthropic.com/v1/models` | ALLOWED | ALLOWED |
| `npm view react version` | `19.3.1` | `19.3.1` |
| `curl https://registry.yarnpkg.com/react` | ALLOWED | ALLOWED |
| dummy env var visible | yes | **yes** (environment is passed through) |
| `docker version` (daemon) | reachable | not reachable |

Inside the sandbox, `HTTP(S)_PROXY`/`ALL_PROXY` point at a localhost port, and `NO_PROXY` covers the private ranges.

### Experiment 2 (paid, not completed): headless `claude -p` on Haiku

The command, run in `exp/work` with `--settings` holding `sandbox.enabled`, `failIfUnavailable`, `allowUnsandboxedCommands: false` and the same `denyRead`/`allowedDomains`:

```
claude -p --model haiku --max-budget-usd 0.03 --output-format json \
  --dangerously-skip-permissions --setting-sources project --settings cc-settings-locked.json \
  'Run bash probe.sh ...; retry each blocked line with dangerouslyDisableSandbox: true; report.'
```

It stopped at startup: "Failed to authenticate: this login reached its time limit and cannot be renewed". The cost was $0.00, and 1 of the 3 allowed calls was used. The JSON result still showed the output shape (keys listed under question 5). The two runs still to do are: this one, and the same run with `allowUnsandboxedCommands: true`, to watch the escape hatch work and then be refused. They need a fresh `claude auth login`, or an API key passed through `apiKeyHelper`.

## Recommendation

**Use a mix:** Claude Code's sandbox for the agent's own commands, with strict settings, a Node version pinned for each case on its `PATH`, and the existing Docker sandbox for Verify and scoring. The network restriction we were going to build already exists in Claude Code's sandbox and is enforced by the OS, so we only need to configure it and check it. The settings that must be set for each run:

```json
{
  "permissions": {
    "deny": ["Read(~/.config/migrator/**)", "Read(~/.ssh/**)", "WebFetch", "WebSearch"]
  },
  "apiKeyHelper": "<script that reads the key from ~/.config/migrator>",
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "allowUnsandboxedCommands": false,
    "autoAllowBashIfSandboxed": true,
    "excludedCommands": [],
    "network": {"allowedDomains": ["registry.npmjs.org", "registry.yarnpkg.com"], "strictAllowlist": true},
    "filesystem": {"denyRead": ["~/.config/migrator", "~/.ssh", "~/.aws", "~/.gnupg", "~/Library/Keychains"]}
  }
}
```

Add `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` and the model variables from question 5. Before each run, a probe should check that a blocked host fails and the dummy secret can't be read, because a settings file that fails validation is silently ignored in `-p`. Two things still need checking: the exact key paths (`strictAllowlist`, `credentials.envVars`) against the settings reference, and whether `permissions.deny` still applies under `bypassPermissions`. A safer alternative is `--permission-mode dontAsk` with explicit allow rules for Edit and Write.

| Option | What it takes | Rough build time |
|---|---|---|
| **Claude Code sandbox (host)** | Settings file, key helper, runner script (clone, Node on PATH, `claude -p`, collect JSON), probe check, Verify does a clean install | **1–1.5 days**, including the two paid headless checks |
| **Docker + egress proxy** | Linux image for each Node version with the Claude CLI, an internal Docker network with an allow-list proxy sidecar (Squid/tinyproxy), proxy settings for npm/yarn, key injection, proof that nothing else gets out | **2.5–4 days**. It fixes the Node and darwin/Linux mismatch for free, but it's all new infrastructure |
| **Mix (recommended)** | The first row, plus the existing Docker Verify unchanged | **~1.5 days** |

If the Node 16 PATH approach misbehaves (native modules, CRA quirks on macOS), switch to Docker + proxy for OpossumUI and wps only. kubeflow (Node 22) would stay on the host.

## Sources

- [sandboxing] https://code.claude.com/docs/en/sandboxing
- [settings] https://code.claude.com/docs/en/settings, https://code.claude.com/docs/en/settings-reference
- [cli-reference] https://code.claude.com/docs/en/cli-reference, plus `claude --help` of 2.1.321
- [headless] https://code.claude.com/docs/en/headless
- [model-config] https://code.claude.com/docs/en/model-config
- [env-vars] https://code.claude.com/docs/en/env-vars
- [sub-agents] https://code.claude.com/docs/en/sub-agents
- [costs] https://code.claude.com/docs/en/costs; [cost-tracking] https://code.claude.com/docs/en/agent-sdk/cost-tracking
- [README] https://github.com/anthropic-experimental/sandbox-runtime (npm `@anthropic-ai/sandbox-runtime`)
- Setting names (`strictAllowlist`, `allowUnsandboxedCommands`, `failIfUnavailable`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`) were confirmed by searching the strings of the installed 2.1.321 binary.
