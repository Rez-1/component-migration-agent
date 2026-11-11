# Running the Migrator: real runs, pull requests, the sandbox and tracing

How a normal run lands its changes (ticket #9), how a pull request is opened (ticket #10 and the brief's PR rule), where commands run (ticket #15) and how LangSmith tracing is switched on (ticket #3). Built in M4.

## Setting up a repo: `migrator init`

```sh
migrator init path/to/repo            # writes path/to/repo/migrate.toml
migrator init path/to/repo --stdout   # prints it instead
```

It reads the repo's files and writes a commented `migrate.toml` for you to check: the package manager (from the lockfile), the Node major (`.nvmrc`, `.node-version`, then `package.json` `engines.node`), the test runner (Vitest, Jest, or CRA's `react-scripts`, which runs Jest), the verify commands from the `package.json` scripts, the source globs from the file types under `src/`, and install-only environment variables for dependencies that download binaries at install (Electron, Playwright, Cypress, Puppeteer). Every value has a comment saying which file it came from. Anything it can't detect is written as a `TODO` line and printed. No LLM, no network.

It never picks a lint script that runs `--fix` (verify must not change files), adds `--watchAll=false` to a `react-scripts test` script, and treats a Node version the sandbox has no pinned image for as a TODO. It never overwrites an existing `migrate.toml` without `--force`.

The verify commands decide what counts as migrated, so read them: a test script that skips part of the suite, or a lint script with a different config, changes every result.

## Dry run or real run

| | `migrator migrate <repo> --from mui@4 --to mui@5 --dry-run` | `migrator migrate <repo> --from mui@4 --to mui@5` |
|---|---|---|
| Workspace | a throwaway copy (no `.git`, no `node_modules`) | a `git worktree` of the repo's last commit, on a new branch |
| Your repo | never touched | never touched: only a new branch appears |
| Result | scorecard and PR body in `runs/<run-id>/` | the branch `migrate/mui-v5` with one commit per stage, plus run files in `<repo>/.migrator/runs/<run-id>/` |
| Used by | evals, CI, trying it out | migrating for real |

Evals only make dry runs; `start_run` refuses a real run in eval mode.

## Real runs

```sh
cd my-app                     # the repo root, with a clean working tree
migrator migrate . --from mui@4 --to mui@5 --config opus-low --max-cost 2
```

**It refuses to start** when the folder is not the root of a git repo, the repo has no commits, the working tree has uncommitted changes or untracked files (the migration starts from the last commit, so they would silently be left out), or the branch already exists (delete it, or pick another with `--branch`). The Migrator's own `.migrator/` folder never counts as a change.

**The worktree** lives outside the repo, in `~/.cache/migrator/worktrees/<repo>-<run-id>/` (`MIGRATOR_CACHE_DIR` moves it), so your own `tsc`, ESLint and Jest never see a second copy of the sources. It is removed when the run ends (`--keep-workspace` keeps it); the branch stays. A run paused at Review keeps its worktree until `migrator resume` finishes it.

**One commit per stage**, each made by its own graph node after the stage, with a message that says what the stage did:

1. `Migrate mui@4 to mui@5: Rules (codemods and dependency map)`: every rule step that changed something, and the Codemod TODOs left.
2. `Migrate mui@4 to mui@5: repair agent fixes in N files`: each fixed file with its attempts and model, the files handed off (whose patches are *not* in this commit), the model calls and cost.
3. `Migrate mui@4 to mui@5: changes made at Review`: only when a human edited files or kept an agent patch at Review.

A stage that changed nothing makes no commit (the Baseline has no agent commit), and a run that committed nothing at all (rejected at the Pre-check, or a Rules failure) deletes its empty branch, so it doesn't block the next run. If a run crashes, its worktree and branch stay for inspection; the refusal on the next run names the `git worktree remove` and `git branch -D` to run. Each message ends with `Migrator-Run: <run-id>` and `Migrator-Stage: <stage>` trailers. Before committing, a commit node looks for its own trailers on the branch, so a crash between the commit and the checkpoint, or a resume, never commits a stage twice. Commit nodes never pause, and nothing with a side effect runs before the Review node's `interrupt()` (ticket #11).

**What a commit contains:** everything that changed in the worktree, except `node_modules` and `.migrator/`, whatever the repo's `.gitignore` says. Commits use your git identity and skip the repo's hooks: a pre-commit hook would run repo code on the host, outside the sandbox.

**Run files** (usage report, scorecard, PR body, logs, the checkpoint database) go in `<repo>/.migrator/runs/<run-id>/`. They are never in a commit (the worktree is elsewhere). Add `.migrator/` to `.gitignore` or `.git/info/exclude` to keep them out of `git status`; the CLI reminds you if git doesn't ignore it.

`migrator resume <run-id>` works from the repo root (it looks in `.migrator/runs/`), or pass the run folder.

## Opening a pull request: a separate, flagged step

```sh
migrator pr .migrator/runs/<run-id>            # shows what it would do; runs nothing
migrator pr .migrator/runs/<run-id> --open     # pushes the branch and opens the PR
migrator pr ... --open --draft --remote origin --base main
```

A run never opens a PR by itself. Without `--open` the command prints the push and the `gh pr create` command, the title and the body file, and makes no network call. With `--open` it checks the rule below first, then runs `git push <remote> <branch>` and `gh pr create`, and records the PR's URL in `run.json` (a second `--open` is refused).

**The rule** (the brief: PRs only to your own repos or forks, never upstream, never during evals):

1. Only a finished real run: dry runs, eval runs, runs paused at Review and runs that made no commits are refused.
2. The remote must be on GitHub, and its owner must be the account `gh` is logged in as (`gh api user`). Your repos and your forks pass. Anyone else's repo, including an organisation's, is refused before anything is pushed; push it yourself if you mean to.
3. The PR is created with an explicit `--repo <you>/<name> --head <branch> --base <base>`, because in a fork `gh pr create` would otherwise propose the PR to the upstream repo.

**The PR body** is `pr-body.md` in the run folder, written for every run (dry runs too) and rendered from `scorecard.json`, which stays the source: the scorecard's headline and table, the hand-off checklist (one task per handed-off file with the agent's reason and its remaining failures, then the Unmigrated files), the Codemod TODOs as tasks, the stage commits and the cost line.

## Models: three levels, any provider

A configuration names **model levels**, not models: **strong** (the repair agent), **balanced** (the test-fitting reviewer and the eval judge) and **fast** (cheap helper tasks). Its `[models]` table says which model fills each level; without one, the levels are Claude's:

```toml
[models]
strong = "claude-opus-5-5"
balanced = "claude-sonnet-5-5"   # must be a different model from strong
fast = "claude-haiku-5-5"

[repair]
attempt_models = ["strong", "strong", "strong"]
reviewer_model = "balanced"
```

Three rules hold before anything runs:

- **Every model has a price.** The cost cap prices each call's worst case first, so a model with no price is refused. Prices and features live in the model table, [`src/migrator/models.toml`](../src/migrator/models.toml), checked against the provider's pricing page.
- **No model reviews or judges its own work.** balanced must differ from strong, the reviewer from every repair model, and `migrator eval score-reference --judge` (balanced by default) from every model that wrote the runs' code.
- **Provider features are declared, not assumed.** Each model lists what it supports: effort levels, prompt caching, strict tool schemas, structured output and the advisor tool. What a configuration asks for and its model lacks is turned off before the run, printed as `Turned off: ...` and recorded in the scorecard's `meta.features_off`. The one exception is the advisor tool, which is refused, because turning it off would change what the configuration measures.

To use another provider, add its models to your own table, `~/.config/migrator/models.toml` (or the file `MIGRATOR_MODELS` names), in LangChain's `provider:model` form, with their prices. Then install its LangChain package (`uv add langchain-openai`, for example) and set its API key in the environment:

```toml
[[model]]
id = "openai:<model>"
price = { input = 1.25, output = 10.0, cache_read = 0.125 }   # USD per million tokens
efforts = ["low", "medium", "high"]
structured_output = true
strict_tools = true
```

Claude models keep their bare ids (`claude-opus-5-5`), so ledgers and scorecards from before the levels still line up. Configurations written before M7 name models directly and keep their digests.

## Adding a migration: `migrator spec`

Migration specs ship with the Migrator, one per supported migration, so an app developer never writes one. To add one:

```sh
uv run migrator spec new <name> --from lib@4 --to lib@5 --library "Library name"
uv run migrator spec check <name> --network
```

`spec new` writes a commented `migration.toml` in `src/migrator/migrations/<name>/`, plus `guide/SOURCE.md` and `tools/package.json` to fill in. `spec check` is the rulebook. It checks that:
- the spec loads and has no TODO left;
- the vendored guide is there with its `SOURCE.md` and splits into sections at the configured heading levels;
- the guide is pinned to a full commit;
- the dependency map pins exact versions;
- each codemod's tool is pinned in the tools lockfile;
- the rule steps come in an order that can work.

With `--network` it also confirms the commit on GitHub and every pin on npm. The `add-migration` Claude Code skill (`.claude/skills/add-migration/`) walks through the research each field needs. The rules stay in the CLI: the skill only guides.

## The sandbox: where commands run

Verify and the repair agent's `run_verify` run the repo's type-check, lint and tests, and the tests import files the repair agent just edited. So **Verify executes code an LLM wrote**, with whatever permissions the runner has. The guardrails limit which files the agent can edit and block escape hatches, but not what the edited code does when it runs.

`--sandbox docker` runs every install, codemod and verify command in a fresh container:

- the `node` image pinned by digest per Node major (`NODE_IMAGES` in `migrator/execs.py`; Node 20, from `case.toml` or `migrate.toml`'s `node`);
- only the command's folder mounted (the workspace), the run's log folder (where Verify's JSON reports land), the codemod tools read-only, and an npm cache volume;
- the network off (`--network none`) for everything except package installs, which run before the repair agent edits anything;
- your uid, not root; a read-only root filesystem with a `/tmp` tmpfs; all capabilities dropped; `no-new-privileges`; memory, CPU and process limits;
- a clean environment: none of your environment variables (API keys, tokens) reach the container.

What it does not protect against: the agent-edited code can still write anything inside the workspace and the log folder, and use the CPU and memory up to the limits. Installs run with a network, as they do on your machine (`npm ci` runs the packages' install scripts). Git runs on the host, never in the container.

Defaults: **evals use Docker** (`migrator eval run --sandbox local` opts out); **`migrator migrate` uses `--sandbox auto`**: Docker when it is running, otherwise local with a printed warning. `--sandbox docker` fails at the start if Docker is not available. The unit tests and CI's Baseline job run locally; CI's `docker` job runs the Baseline in the sandbox.

One Docker Desktop quirk the runner works around: its file sharing (virtiofs on macOS) caches file attributes for up to a second, so a file the host rewrote just before a container starts can be read there with its old length. The first sandboxed Baseline failed this way (`npm install` read a truncated `package.json`). The runner waits until the newest file in the workspace is 1.1 s old before it starts a container.

## LangSmith tracing

Off by default; switched on by environment variables only, never by code or configuration:

```sh
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=...
# Newer, agent-based workspaces:
export LANGSMITH_AGENT_ID=<agent-id>
export LANGSMITH_AGENT_ENVIRONMENT=local
# Older, project-based workspaces and self-hosted LangSmith:
export LANGSMITH_PROJECT=mui-migrate
# Outside the US region, for example:
export LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
```

When tracing is on, the CLI prints where traces go. What you see in LangSmith:

- each graph invoke is a trace whose root run is `migrator-run`, with `run_id`, `case`, `configuration`, `repo`, `mode`, `sandbox` and `migrator_version` as metadata and `config:…`, `mode:…`, `case:…` tags. `thread_id` metadata (the run id) groups the first invoke and every resume after Review into one LangSmith thread;
- each graph node is a child run (`scan`, `rules`, `agent`, `tools`, `commit_rules`, …);
- each model call is a child of the `agent` node named `repair <file> · attempt <n>`, with `file`, `attempt` and `requested_model` metadata and a `file:<path>` tag, so one repair attempt is a filter away.

Every CLI command flushes the traces before it exits. Cost is counted once, by the Migrator's own ledger (`~/.config/migrator/ledger.jsonl`); LangSmith's computed cost for the same calls is a cross-check in its UI and is never added to a scorecard. LangSmith's free plan: 1 seat, 5k traces a month, 14-day retention.
