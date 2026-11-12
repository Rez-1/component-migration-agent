# Migrator: component-library migrations with an AI repair agent

The Migrator moves a frontend codebase from one component-library version to the next. The official codemods run first. Then an AI agent (Claude, through LangChain and LangGraph) fixes only the files that still fail, one at a time. A file counts as migrated only when the repo's own type-check, lint and tests pass.

The first migration is **Material UI (MUI) v4 → v5**, for React. **Angular Material legacy → MDC** is in progress.

## The short version

On three real open-source repos that made the MUI v4 → v5 move:

- **Every agent run was clean, and no codemods-only run was.** A run is clean when every remaining failure is in a file the agent handed to a human, with a reason. For example: "needs `@mui/x-date-pickers`, which isn't a dependency".
- **The agent did not reduce silent misses.** A silent miss is a file that differs from what the developers merged, passes every check the repo has, and was not handed off. Nothing in the run flags it. The agent's count stayed the same as the codemods' or went up by one.
- **The high percentages need a warning.** The codemods alone already migrate 83–90% of the files on these repos, and the agent adds 0 to 7 files on top. On the repo with the fewest tests, "passes the checks" says little.

An agent run cost $0.55 to $1.87. The full results are [below](#results).

On a test app I wrote myself, the numbers looked much better: 89% of the files were migrated without a human, against 22% for the codemods alone, at $0.12 a run. That app was built around the guide's breaking changes and has a test for nearly every one, so 89% is a ceiling for simple code, not a forecast.

## Quick start

You need Python 3.13 with [uv](https://docs.astral.sh/uv/), Node 20 and npm, and Docker (recommended).

```sh
uv sync
uv run migrator init path/to/repo                                        # writes a commented migrate.toml for you to check
uv run migrator scan path/to/repo --from mui@4 --to mui@5                # usage report, free
uv run migrator migrate path/to/repo --from mui@4 --to mui@5 --dry-run   # codemods only, on a throwaway copy, free
```

With an Anthropic API key in the environment:

```sh
uv run migrator migrate path/to/repo --from mui@4 --to mui@5 --config opus-low --max-cost 2
uv run migrator pr path/to/repo/.migrator/runs/<run-id>                  # shows the push and PR it would make
```

A real run works in a `git worktree` on a new branch, `migrate/mui-v5`, with one commit per stage. Your working tree is never touched. `migrator pr --open` pushes and opens the PR, but only to a repo you own or a fork of one, never upstream. More in [`docs/running.md`](docs/running.md).

## How a run works

One LangGraph graph per run, checkpointed so it can resume:

**Scan → Pre-check → Rules → Verify → Repair → Review → Verify → Report**

1. **Scan** counts every use of the old library (imports, JSX elements, calls) with tree-sitter, and predicts which ones the codemods won't handle.
2. **Pre-check** runs the repo's own type-check, lint and tests before any change, so failures that were already there aren't blamed on the run.
3. **Rules** is the part without AI: the dependency map and the official `@mui/codemod` 9.4.0 transforms, each run exactly once. It also undoes codemod changes to the repo's own components (the codemods match by name, so they sometimes edit a home-grown `IconButton` as if it were MUI's) and removes stray `(` `)` text the codemods leave behind.
4. **Repair** gives each failing file to the agent, with its failures and the matching sections of the official migration guide. The agent has up to 3 attempts per file.
5. **Review** pauses at each hand-off so a person can revert, keep or edit the file. Evals answer automatically, and `migrator resume` continues after a restart.
6. **Report** writes the scorecard: how every affected file ended, the failures, the cost, what the codemods left as TODOs, and a PR description.

**The tools enforce the limits, not the prompt**, because "tests pass" is the first thing an agent will game:

| The agent can | The tools block |
|---|---|
| Read files and search the migration guide | Editing tests, mocks, snapshots, configs, lockfiles or `package.json` |
| Edit the failing file and the files it imports | Adding `@ts-ignore`, `as any` or `eslint-disable` |
| Run the repo's type-check, lint and tests | Running terminal commands |
| Hand the file to a human, with a reason | More than 3 attempts per file, or a patch over 60 lines or 40% of the file |

After the run, **cheating checks** read the final diff for gamed success, such as a skipped test or a test run with fewer tests than the Pre-check. A free check also flags agent edits to accessibility attributes or the rendered element in a file whose failure was a test, since that can mean the code was bent to fit an old test. A different model from the agent (Claude Sonnet, not Opus) then decides each flagged patch.

**A migration is a data file**, [`migration.toml`](src/migrator/migrations/mui-4-to-5/migration.toml): how to detect the library, the usage patterns, the ordered rule steps, pinned dependencies, the guide and notes for the agent. Angular Material also needs things MUI didn't: scanning HTML templates, a rule step for Angular schematics, and readers for Angular's build and test tools.

## Results

All numbers come from real runs measured by the eval harness in this repo, 2 runs per row.

### Real open-source repos

Each run starts from the commit before the repo's merged migration PR. The result is compared file by file with that PR.

- **Tuned on:** [OpossumUI](https://github.com/opossum-tool/OpossumUI/pull/218) and the [kubeflow/pipelines](https://github.com/kubeflow/pipelines/pull/12925) frontend.
- **Held out:** the [bcgov/wps](https://github.com/bcgov/wps/pull/1933) `web/` app, run once with the configuration frozen. Nothing was tuned on it.

| Repo | Setup | Clean runs | Migrated without a human | Silent misses | Cost per run | Time per run |
|---|---|---|---|---|---|---|
| OpossumUI (52 files) | Codemods only | 0 of 2 | 43 (83%) | 3 | $0 | 6 min |
| | Opus, low effort | **2 of 2** | 43–44 (83–85%) | 3–4 | $1.05 | 17 min |
| kubeflow (76 files) | Codemods only | 0 of 2 | 66 (87%) | 0 | $0 | 11 min |
| | Opus, low effort | **2 of 2** | 68 (89%) | 0 | $1.87 | 54 min |
| wps, held out (141 files) | Codemods only | 0 of 2 | 127 (90%) | 13 ¹ | $0 | 5.5 min |
| | Opus, low effort | **2 of 2** | 134 (95%) | 14 ² | $0.55 | 10 min |

¹ The stray-parentheses fix in Rules was found by reading wps's results, so the table keeps the blind numbers. Re-run after the fix, the codemods-only score is 11 ([per-file score](docs/results/m6/bcgov-wps-baseline-after-rules-fix-reference-score.md)).<br>
² 15 by the judge alone. I overrode one of its verdicts; [`overrides.toml`](evals/m6-cases/bcgov-wps/overrides.toml) records who, when and why, and the judge's verdict is kept beside it.

**Where the silent misses are.** Test coverage decides them. On kubeflow, 54 of the 66 files the codemods migrated are covered by a test, and there are no silent misses. On wps only 22 of 127 are covered. Its silent misses are mostly styling the developers added by hand to make up for v5's changes: a font size, a label colour, the position of an input adornment. No test checks those, so neither the codemods nor the agent are told anything is wrong. Every migrated file is now labelled *covered* or *not covered* by a test, so a reviewer knows where to look.

**What the agent adds on real code** is a clean run and hand-offs that explain the cause, often with the test change written out for a human to approve. For example: "the test reaches the input through v4's IconButton label span, which v5 removed on purpose". It doesn't find mistakes the repo's own checks can't see.

<details>
<summary>How the scoring works, and the full breakdown</summary>

Each file the PR changed that imports MUI is one scoring item, with one of four results:

- **matches:** the same change as the PR, or an equivalent one;
- **other valid fix:** a different change that works;
- **wrong:** it passes the checks but behaves differently, including v5 styling the developers added and the run left out;
- **untouched:** the PR changed it and the run didn't.

A file equal to the PR after formatting matches outright. For the rest, an LLM judge first labels each of the PR's changes as needed for v5, styling to make up for v5, or unrelated, then scores the run's file against the first two. Test files the PR changed count as expected hand-offs, because only a human may edit tests.

| Repo | Setup | Matches / other valid / wrong / untouched | Migrated files covered by a test |
|---|---|---|---|
| OpossumUI | Codemods only | 46 / 1 / 5 / 0 | 43 of 43 |
| | Opus | 46 / 1 / 5 / 0 | 43–44 of 43–44 |
| kubeflow | Codemods only | 65 / 2 / 4 / 0 | 54 of 66 |
| | Opus | 66 / 3 / 2 / 0 | 56 of 68 |
| wps | Codemods only | 103 / 4 / 15 / 1 | 22 of 127 |
| | Opus | 100 / 7 / 15 / 1 | 27 of 134 |

On kubeflow, 37 snapshot files fail only because v5 renders different markup. The Migrator updates those itself and lists them for a human to review; the agent never edits them.

Per-file scores: [OpossumUI](docs/results/m6/opossum-ui-opus-reference-score.md), [kubeflow](docs/results/m6/kubeflow-pipelines-opus-reference-score.md), [wps](docs/results/m6/bcgov-wps-opus-reference-score.md), each with the codemods-only score beside it (`*-baseline-reference-score.md`).

</details>

**Checking the judge.** I rated 20 OpossumUI items blind, without seeing the judge's verdict or which setup produced the file. At first the judge agreed with me on 7 of the 17 items it decided. Most of the gap was mine: I couldn't tell which of the PR's changes were for v5. With the PR's changes labelled, we agreed on 10 of 17, and nearly agreed on the silent-miss count (Opus runs: me 4, judge 4 and 5). On these runs the judge was Opus grading Opus's work, which is why my ratings sit next to its numbers.

**The model may have seen the answers.** All three PRs were merged before the model's training cutoff (June 2026). Treat "matches" as an upper bound, the held-out repo included.

**The checks are the slow part, not the model.** On kubeflow, model calls are about 3% of a run's time; the rest is the repo's own checks in Docker. Four speed-ups cut two codemods-only runs from 11.4 to 3–4 minutes on OpossumUI and from 22.3 to 9.5 on kubeflow, each kept only if the scorecards stayed identical. A fifth, `node_modules` in a Docker volume, broke the codemods and was dropped.

The real-repo phase cost about $17, judge calls included.

### Test apps with planted traps

Before the real repos, I measured the agent on test apps I wrote myself: small React apps on MUI v4, with **traps** planted from the guide's breaking changes. Each trap names who should handle it: the codemods, the agent or a human. Read these numbers as directional.

**Held out**, a warehouse back office nothing was tuned on, run once at the end:

| Setup | Clean runs | Migrated without a human | Agent traps fixed | Cost per run |
|---|---|---|---|---|
| Codemods only | 0 of 2 | 22% | 0 of 6 | $0 |
| **Opus, low effort** | **2 of 2** | **89%** | **6 of 6** | **$0.12** |

89% is the maximum on this app. The one file left is a test that checks v4 class names; only a human may change tests, and the agent handed it off both times with that reason. [Summary](docs/results/opus-low-holdout/experiment-summary.md).

**Choosing the model.** Seven paid rounds on two other test apps, 4 runs per row (full log in [`experiments.md`](experiments.md)). Measured at commit [`0eddf6e`](https://github.com/Rez-1/component-migration-agent/tree/0eddf6e), the last with the advisor, the Haiku-then-Opus cascade and `eval climb`; reproduce these rows from there. They are left out of the end-of-M7 re-run.

| Setup | Migrated without a human | Agent traps fixed (of 9) | Cost per run |
|---|---|---|---|
| Codemods only | 29% | 0 | $0 |
| **Opus, low effort** | **96%** | **9** | **$0.21** |
| Sonnet, medium effort | 90% | 7.75 | $0.14 |
| Haiku, high effort | 85% | 7 | $0.03 |
| Haiku first, then Opus | 85% | 7 | $0.11 |
| Haiku with Opus as advisor | 88% | 7 | $0.17 |

Every agent run in this table was clean. The cheaper models failed safely: almost every trap they missed ended as a hand-off, so the price of a cheaper model was more human review, not broken code. Opus at low effort was already at the ceiling, and two changes to how the agent searches the guide made no difference. Prompt caching did most of the cost work (55–93% of input tokens were cache reads). All of it cost $4.55.

## Cost and safety

- **Cost caps are on by default:** $5 per run and $20 per month, checked against a local record of every model call (`~/.config/migrator/ledger.jsonl`). Before each call, its worst case is checked against what's left. If it doesn't fit, repair stops, the remaining files end Unmigrated with the reason "cost cap", and the run still finishes with a scorecard. The record covers one machine, so **also set a monthly spend limit in the Anthropic Console**: it's the only cap that covers every machine.
- **Verify runs code an AI wrote**, because the repo's tests import the files the agent just edited. The Docker sandbox (the default for evals, and `--sandbox auto` for real runs) runs every install, codemod and check in a fresh container:
  - a `node:20` image pinned by digest;
  - only the workspace mounted;
  - no network, except for package installs, which run before the agent edits anything;
  - your user id, a read-only root filesystem, no capabilities, and memory, CPU and process limits;
  - none of your environment variables.

  It doesn't stop the edited code from writing inside the workspace, or from using CPU and memory up to those limits. Without Docker, commands run on your machine with your permissions.
- **Tracing** to LangSmith is off unless `LANGSMITH_TRACING=true`.

## Evals

- Cases are in [`evals/cases/`](evals/cases), split into **dev** (tuned on) and **held out** (run only at milestones). Each trap is scored as handled by the expected layer, by another layer, or missed.
- In M5 the grader, the scorecard and the cheating checks were locked while tuning: `migrator eval climb` refused to run if they had changed since the last approval, so a better score couldn't come from a changed ruler. Its rounds are frozen under [`.claude/hillclimb/dev/`](.claude/hillclimb/dev); the command was removed after commit [`0eddf6e`](https://github.com/Rez-1/component-migration-agent/tree/0eddf6e). M6 and M7 tuned with `eval run`.
- [`docs/eval-audit.md`](docs/eval-audit.md) lists what the evals can and cannot show.
- Results are in [`docs/results/`](docs/results) and [`.claude/hillclimb/dev/`](.claude/hillclimb/dev) (every round's runs, scorecards and agent transcripts).

Evals from the command line:

```sh
uv run migrator eval run --split dev --config baseline                   # codemods only, free
uv run migrator eval run --split dev --config opus-low --max-cost 1.5
uv run migrator eval summary dev/<experiment>
```

The terms used across the repo (Run, Hand-off, Clean run, Trap, Baseline, …) are defined in [`CONTEXT.md`](CONTEXT.md). "Baseline" is the codemods-only setup.

## Why these libraries

Each library does a job that would otherwise be hand-written.

- **LangGraph** runs the pipeline as one checkpointed graph. The repair loop needs three things it provides: pausing for a human at a hand-off (`interrupt()`), resuming after a crash without re-running the codemods (which aren't safe to run twice), and conditional edges between stages. Commits happen after stages, never inside a step that can pause, so a resume can't commit twice.
- **LangChain**, only where it fits:
  - `ChatAnthropic` with `bind_tools(strict=True)` for the agent;
  - `@tool` functions, with the guardrails inside them;
  - a `BaseRetriever` for the guide, so trying another search method was a configuration value, not a refactor;
  - `init_chat_model`, so comparing Opus, Sonnet and Haiku was a configuration value too.

  Left out on purpose: prompt-template chains around single calls, document loaders, memory classes and agent wrappers on top of LangGraph. The research behind this is in [`docs/research/langchain-claude-support.md`](docs/research/langchain-claude-support.md).
- **LangSmith** traces each run, with every model call nested as `repair <file> · attempt <n>`. The Migrator's own record stays the source of truth for cost. A kubeflow run from 10 November 2026: [the public trace](https://smith.langchain.com/public/b35c3f39-440e-49ec-96af-624cd02df23a/r/01a1c689-5410-7068-9c76-15c811ebcdaf) (kept for 14 days on LangSmith's free plan), plus screenshots of [the stages](docs/images/langsmith-trace-stages.png) and [one repair call with its tool calls](docs/images/langsmith-trace-repair-call.png).
- **The Anthropic SDK** comes in through `langchain-anthropic`, pinned below 2 because LangChain is tested against 1.x.
- **tree-sitter** parses TSX for the usage scan: fast and exact, with no Node process.
- **`@mui/codemod` 9.4.0**, pinned with its own lockfile: the official transforms, not ours.
- **Typer and Rich** for the CLI, **Pydantic** for configurations and scorecards, **uv** for a locked environment, **Docker** for the sandbox.

## Repo layout

| Path | What |
|---|---|
| `src/migrator/` | the tool: CLI, graph, scan, rules, verify, repair, review, report, cost, evals |
| `src/migrator/migrations/mui-4-to-5/` | the migration spec, pinned codemod tools, the vendored guide (MIT) |
| `fixtures/` | the test apps with planted traps |
| `evals/` | cases, traps, reference scores and configurations |
| `docs/` | running the tool, the eval audit, research and results |

## Licence

MIT, see [`LICENSE`](LICENSE). The vendored Material UI guide is MIT, © Call-Em-All (licence in its folder).
