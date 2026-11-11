# Migrator: component-library migrations with an LLM repair agent

The Migrator moves a frontend codebase from one component-library version to the next. Each migration is described in a data file ([`migration.toml`](src/migrator/migrations/mui-4-to-5/migration.toml)), not in code. The first one is **Material UI v4 → v5** (React); **Angular Material legacy → MDC** is next (M7), and needs template scanning and Angular's test and build tools. Known patterns go through the official codemods. An LLM repair agent (Claude, through LangChain and LangGraph) fixes only what the codemods leave broken, one failing file at a time. Nothing counts as migrated unless the repo's own type-check, lint and tests pass. Every run produces a measured **scorecard** against a codemods-only **Baseline**.

The words used here (Run, Hand-off, Clean run, Trap, …) are defined in [`CONTEXT.md`](CONTEXT.md).

## Results

All numbers are from real runs, measured by the eval harness in this repo, 2 runs per row.

### On real open-source repos (M6)

Three repos that really made the MUI v4 → v5 move. Each run starts from the commit before the merged migration PR, and the result is scored file by file against that PR. **Dev**, used for tuning: [OpossumUI](https://github.com/opossum-tool/OpossumUI/pull/218) and the [kubeflow/pipelines](https://github.com/kubeflow/pipelines/pull/12925) frontend. **Held-out**, run once with the configuration frozen: the [bcgov/wps](https://github.com/bcgov/wps/pull/1933) `web/` app.

| Repo | Configuration | Clean runs | Migrated without a human | Of those, covered by a test | Against the merged PR: matches / other valid fix / wrong / untouched | Silent misses | Cost per run | Time per run |
|---|---|---|---|---|---|---|---|---|
| OpossumUI (52 files) | Baseline | 0 of 2 | 43 (83%) | 43 | 46 / 1 / 5 / 0 | 3 | $0 | 6 min |
| | Opus 5.5, low effort | **2 of 2** | 43–44 (83–85%) | 43–44 | 46 / 1 / 5 / 0 | 3–4 | $1.05 | 17 min |
| kubeflow (76 files) | Baseline | 0 of 2 | 66 (87%) | 54 | 65 / 2 / 4 / 0 | 0 | $0 | 11 min |
| | Opus 5.5, low effort | **2 of 2** | 68 (89%) | 56 | 66 / 3 / 2 / 0 | 0 | $1.87 | 54 min |
| **wps, held-out** (141 files) | Baseline | 0 of 2 | 127 (90%) | 22 | 103 / 4 / 15 / 1 | 13 † | $0 | 5.5 min |
| | Opus 5.5, low effort | **2 of 2** | 134 (95%) | 27 | 100 / 7 / 15 / 1 | 14 * | $0.55 | 10 min |

- **Baseline:** the codemods and the dependency map only. **Opus:** the M5 winner, with three changes made on the dev repos. It hands off outdated tests with a suggested test change. It fixes failures with one shared cause as one task. On kubeflow and wps, a free check also flags patches that change what a failing test looks at (accessibility attributes, the rendered element). On wps, a Claude Sonnet 5.5 reviewer then decided each flagged patch: never Opus reviewing Opus. The configurations are [`m6-opus-low-v2`](evals/configs/m6-opus-low-v2.toml), [`-v3`](evals/configs/m6-opus-low-v3.toml) and [`-v4`](evals/configs/m6-opus-low-v4.toml).
- **Scoring:** the items are the code files the PR changed that import MUI. A file equal to the PR after formatting matches outright. For the rest, an LLM judge (Opus 5.5, low effort) first labels each change in the PR: needed for v5, styling to make up for v5, or unrelated. It then scores the run's file against the first two. Styling the developers added for v5 and the run left out counts as **wrong**: the owner's rule, since styling is a big part of a UI-library migration. The test files the PR changed are listed as expected hand-offs, because only a human may edit tests.
- **Silent miss:** a file scored *wrong* or *untouched* that passes the repo's own checks and was not handed off. Nothing in the run flags it, so only a reviewer reading the diff would catch it.
- **Coverage:** every file migrated without a human is labelled *covered* or *not covered* by the repo's own tests at the Pre-check. On wps, 22 of the 127 files the codemods migrated were covered.
- **Snapshots:** on kubeflow, 37 snapshot files fail only because v5 renders different markup. The Migrator updates them itself and lists them for a human to look at; the agent never edits them.
- \* **One recorded override.** On wps, the agent gave `makeStyles` a fallback theme, `defaultTheme: createTheme()`, so tests that render without the app's ThemeProvider pass. The judge scored this identical fix "other valid" in `HFIErrorAlert.tsx` and "wrong" in `Day.tsx`. The owner scored both as "other valid fix", in [`overrides.toml`](evals/m6-cases/bcgov-wps/overrides.toml) (who, when, why). The score keeps the judge's own verdict beside it: **15 silent misses by the judge alone.** A second file the judge doubted, for a different reason, was left as judged.
- † **A fix found on the held-out repo, kept out of the table.** The codemods left stray `(` and `)` text inside a new `StyledEngineProvider` in three wps files. The Rules layer now removes it. Re-run after that fix, the Baseline (both repeats agree) scores 105 / 4 / 13 / 1 with **11 silent misses**: two files now match the PR outright, and the third, `WindSpeedCell.tsx`, still misses a font size ([per-file score](docs/results/m6/bcgov-wps-baseline-after-rules-fix-reference-score.md)). The fix came from reading wps's scores, so the table keeps the blind held-out numbers. The Opus row was not re-run.

**The judge against the owner.** The owner rated 20 OpossumUI items blind (from earlier runs of the same configurations), with the judge's verdict and the configuration hidden.

| | Owner and judge agree |
|---|---|
| Round 1, without the labels on the PR's changes | 7 of the 17 items the judge decided (3 of 3 exact matches) |
| Round 2, with the labels shown | 10 of 17; 5 of the 6 items with missing v5 styling |
| Silent misses, Baseline | owner 2, judge 3 |
| Silent misses, each Opus run | owner 4, judge 4 and 5 |

In round 1, every disagreement was the judge saying "wrong". Most of the gap was missing context: the owner couldn't tell which of the PR's changes were for v5. Once the labels were shown, owner and judge nearly agree on silent misses, the number that matters here. The judge is still Opus grading Opus's work, which is why the owner's ratings sit next to its numbers.

**Contamination.** All three PRs were merged before the model's training cutoff (June 2026), so Claude may have seen the developers' fixes. Treat "matches" as an upper bound, the held-out repo included.

What the real repos showed:

- **The agent makes runs clean; it doesn't cut silent misses.** No Baseline run was clean, and every Opus run was. Every file the agent couldn't fix ended as a hand-off with a reason, never as broken code. Examples: "the test reaches the input through v4's IconButton label span, which v5 removed on purpose", or "needs `@mui/x-date-pickers`, which isn't a dependency". The agent migrated 0–1, 2 and 7 more files than the Baseline. Silent misses stayed the same or rose by one (3 → 3–4, 0 → 0, 13 → 14).
- **Silent misses live where the tests don't look.** Kubeflow, where 54 of the 66 files the codemods migrated are covered, has none. Wps, with 22 of 127 covered, has 13–14. On wps they are mostly v5 styling the developers added that nothing checks: font sizes, a label colour, an adornment's position. Three files also had a codemod artifact, stray `(` and `)` text inside `StyledEngineProvider`, which the Rules layer now removes (†). The repo's own checks pass, so neither the codemods nor the agent are told anything is wrong. On low-coverage code the value is a clean run, explained hand-offs and the *not covered* label that tells a reviewer where to look, not fewer silent misses.
- **One pattern to watch: changing app code so theme-less tests pass.** The fallback theme is harmless in the running app, which always has the real theme. But it changes app code to suit how the tests render, which is close to fitting the test. On wps, the agent did this in two files and handed off a third, `Menu.tsx`, with the same root cause. Recorded as a follow-up; nothing built for it yet.
- **The checks are the slow part, not the model.** On kubeflow the model calls are about 3% of a run; the rest is the repo's type-check, lint and tests in Docker. Five speed-ups had to leave the free Baselines' scorecards identical. Four passed: parallel repeats, a cached Pre-check, one long-lived container per run and an incremental type-check. Two Baseline runs went from 11.4 to 3–4 minutes on OpossumUI and from 22.3 to 9.5 on kubeflow. The fifth, `node_modules` in a Docker volume, failed the gate (it broke the codemods) and was dropped.

M6 cost **about $17** of its $30 budget, judge calls and the fork PR's run included. Per-file scores: [OpossumUI](docs/results/m6/opossum-ui-opus-reference-score.md), [kubeflow](docs/results/m6/kubeflow-pipelines-opus-reference-score.md), [wps](docs/results/m6/bcgov-wps-opus-reference-score.md), with the Baseline beside each (`*-baseline-reference-score.md`).

### On planted fixtures (M5)

These cases are purpose-built fixtures with planted **traps** (instances of the guide's breaking changes), so read them as directional.

**Held-out case** (`fixture-mui4-holdout`, a warehouse back office; nothing was tuned on it; run once, at the end):

| Configuration | Clean runs | Migrated without a human | Repair traps fixed | Regressions | Cheating-check hits | Cost per run |
|---|---|---|---|---|---|---|
| Baseline (codemods and dependency map only) | 0 of 2 | 22% | 0 of 6 | 0 | 0 | $0 |
| **Opus 5.5, low effort** (the winner on dev) | **2 of 2** | **89%** | **6 of 6** | 0 | 0 | **$0.12** |

The one file not migrated without a human is the case's human-only trap: a test that checks v4 class names (`.MuiStepIcon-completed`). The test has to change, and the repair agent may not edit tests. In both runs it handed the file off, with that reason. 89% is the highest score possible on this case. [Summary](docs/results/opus-low-holdout/experiment-summary.md).

**Dev split** (`fixture-mui4` and the harder `fixture-mui4-hard`, 2 runs each, 4 runs per row), the hill-climb in [`experiments.md`](experiments.md):

| Configuration | Clean runs | Migrated without a human | Repair traps fixed (mean per run, of 9) | Cost per run | Kept? |
|---|---|---|---|---|---|
| Baseline | 0 of 4 | 29% | 0 | $0 | reference |
| **Opus 5.5, low effort** | **4 of 4** | **96%** | **9** | **$0.21** | **best** |
| Haiku 5.5, high effort | 4 of 4 | 85% | 7 | $0.03 | no |
| Sonnet 5.5, medium effort | 4 of 4 | 90% | 7.75 | $0.14 | no |
| Cascade: Haiku first, then Opus | 4 of 4 | 85% | 7 | $0.11 | no |
| Haiku with Opus as advisor | 4 of 4 | 88% | 7 | $0.17 | no |
| Opus + guide search weighted by the file's components | 3 of 4 * | 94% | 8.5 | $0.21 | no |
| Opus + a parse-check warning in `apply_edit` | 3 of 4 * | 94% | 8.5 | $0.21 | no |

\* In each of these two rounds, the cost limit I set for the round stopped repair before the last run's final file. On the three runs that finished, both matched Opus trap for trap at the same cost, so neither could be kept either way.

What the climb found:

- **The cheaper models fail safely.** Every trap Haiku, Sonnet, the cascade or the advisor missed ended as a **hand-off** (the file goes to a human, with a reason). None ended as a wrong fix that passed verification. So every run was clean, but a human got one or two more files per run.
- **Opus at low effort was already at the ceiling on both dev cases.** Better guide retrieval and a parse-check tool changed nothing. Quality on these cases has no headroom left. The next gains needed harder cases (the real repos above), not more tuning.
- **Caching does most of the cost work.** Cache reads were 55–93% of input tokens. A run that starts with a cold cache costs about $0.23, one right after it about $0.14.
- **The advisor pattern was the least efficient here.** Haiku consulted Opus 5 times in 187 calls. Those 5 consultations cost $0.57 of the round's $0.68, because each one reads the whole conversation at Opus prices.

The whole of M5 (7 paid rounds and the held-out run) cost **$4.55**.

## How it works

One checkpointed LangGraph graph per run:

**Scan → Pre-check → Rules → Verify → Repair → Review → Verify → Report**

- **Scan** parses every file with tree-sitter and counts **usages** of the old library: imports, JSX elements and calls. It also forecasts which ones the codemods won't handle (`usage-report.md`).
- **Pre-check** runs the repo's own type-check, lint and tests before any change, so **pre-existing failures** aren't charged to the run.
- **Rules** is the deterministic layer: the dependency map plus `@mui/codemod` 9.4.0 (`preset-safe` and three more), each run exactly once (they aren't idempotent, so a resumed run never re-runs them).
- **Repair** is the repair agent. It gets one failing file, its failures, the matching sections of the official migration guide (vendored at v5.18.0), and five tools: `read_file`, `search_guide`, `apply_edit`, `run_verify` and `hand_off`. It has up to 3 attempts per file and no shell.
- **Review** pauses at each hand-off with LangGraph `interrupt()`. Its choices are Revert, Keep or Edit. Evals answer automatically, and `migrator resume` continues after a restart.
- **Report** writes the scorecard: the outcome of every affected file, failures, cost, Codemod TODOs, traps (on eval cases), cheating-check results and a PR body.

**Guardrails are in the tools, not only the prompt.** Test files (including setup files, mocks, snapshots and files only tests import), configs, lockfiles and `package.json` can't be written. Edits that add escape hatches (`@ts-ignore`, `eslint-disable`, `any`) are rejected. A patch over 60 lines or 40% of a file is handed off. **Cheating checks** run on the final diff, for example skipped tests, or a test run that ran fewer tests than the Pre-check.

**A migration is data** ([`migration.toml`](src/migrator/migrations/mui-4-to-5/migration.toml)): detection, usage patterns, ordered rule steps, pinned dependencies, guide settings and repair notes. A second library plugs in without code changes (Angular Material is planned).

## Quick start

Requires Python 3.13 with [uv](https://docs.astral.sh/uv/), Node 20 and npm, and Docker (recommended).

```sh
uv sync
uv run migrator init path/to/repo                                   # writes a commented migrate.toml to check
uv run migrator scan path/to/repo --from mui@4 --to mui@5          # usage report, free
uv run migrator migrate path/to/repo --from mui@4 --to mui@5 --dry-run   # Baseline on a throwaway copy, free
```

With an Anthropic API key in the environment:

```sh
uv run migrator migrate path/to/repo --from mui@4 --to mui@5 --config opus-low --max-cost 2
uv run migrator pr path/to/repo/.migrator/runs/<run-id>            # shows the push and PR it would make
```

A real run works in a `git worktree` on a new branch, `migrate/mui-v5`, with one commit per stage. Your working tree is never touched. `migrator pr --open` pushes and opens the PR, but only to a repo you own or a fork of one, never upstream. Details are in [`docs/running.md`](docs/running.md).

Evals:

```sh
uv run migrator eval run --split dev --config baseline              # free
uv run migrator eval run --split dev --config opus-low --max-cost 1.5
uv run migrator eval summary dev/<experiment>
```

## Cost and safety

- **Cost caps are on by default:** $5 per run and $20 per month. They are checked against a local ledger of every model call (`~/.config/migrator/ledger.jsonl`). Before each call, its worst case is checked against what's left. If a call doesn't fit, repair stops, the remaining files end Unmigrated with reason "cost cap", and the run still finishes with a scorecard. The ledger covers one machine, and the cap protects against accidents, not intent. **Set a monthly spend limit in the Anthropic Console:** it's the only cap that covers every machine.
- **Verify runs code an LLM wrote.** The repo's tests import files the repair agent just edited. The Docker sandbox (the default for evals, and `--sandbox auto` for real runs) runs every install, codemod and verify command in a fresh container:
  - a `node:20` image pinned by digest;
  - only the workspace mounted;
  - no network except for package installs, which run before the agent edits anything;
  - your uid, a read-only root filesystem, no capabilities, memory/CPU/process limits;
  - none of your environment variables.

  It doesn't stop the edited code from writing inside the workspace, or from using CPU and memory up to those limits. Without Docker, commands run on your machine with your permissions.
- **Tracing** to LangSmith is off unless `LANGSMITH_TRACING=true`.

## Why these libraries

Each library is here because it does a job that would otherwise be hand-written, not for its own sake.

- **LangGraph** runs the pipeline as one checkpointed graph. The repair loop needs three things it provides: pausing for a human at a hand-off (`interrupt()` with Revert/Keep/Edit), resuming after a crash or restart without re-running the non-idempotent codemods (a SQLite checkpointer for the CLI, in-memory for evals), and conditional edges between stages. Commit nodes sit after stages, never in a node that can pause, so a resume can't commit twice.
- **LangChain** is used only where it fits:
  - `ChatAnthropic` with `bind_tools(strict=True)` for the repair agent;
  - `@tool` functions, with the guardrails inside them;
  - a `BaseRetriever` for the guide, so keyword vs context-weighted retrieval was a configuration value in M5, not a refactor;
  - `init_chat_model`, so comparing Opus, Sonnet and Haiku was a configuration value too.

  Left out on purpose: prompt-template chains around single calls, document loaders, memory classes and agent wrappers on top of LangGraph.

  The research behind this ([`docs/research/langchain-claude-support.md`](docs/research/langchain-claude-support.md)) found that `langchain-anthropic` 1.7.10 supports effort, caching, cache-token usage and strict tools on Opus 5.5, but not the Message Batches API. Batches don't suit a tool loop that needs each answer before the next turn, so that gap costs nothing here.
- **LangSmith** traces each run (`migrator-run`), with every model call nested as `repair <file> · attempt <n>`. Our own ledger stays the record of cost, and LangSmith's figure is a cross-check.
  - Example, a kubeflow/pipelines frontend run from 10 November 2026: [the public trace](https://smith.langchain.com/public/b35c3f39-440e-49ec-96af-624cd02df23a/r/01a1c689-5410-7068-9c76-15c811ebcdaf) (336 child runs, 38 model calls). LangSmith's free plan keeps traces for 14 days, so the link may have expired; screenshots are kept here: [the stage nodes](docs/images/langsmith-trace-stages.png) and [one repair call with its tool calls](docs/images/langsmith-trace-repair-call.png). Local paths are made relative before upload.
  - Every resume after a Review hand-off is its own root trace, grouped with the first by the run's `thread_id` (13 more for this run, without model calls). LangSmith's thread view shows a whole run.
- **The Anthropic SDK** comes in through `langchain-anthropic` and is pinned below 2 (`anthropic<2`): LangChain is tested against 1.x, and a fresh install would otherwise pull 2.x. The advisor tool's per-model cost comes from the raw `usage.iterations`, which LangChain copies into `response_metadata`.
- **tree-sitter** (with `tree-sitter-typescript`) parses TSX for the usage scan and for the parse check in prompt v2. That's fast and exact, with no Node process.
- **`@mui/codemod` 9.4.0**, pinned with its own lockfile, is the deterministic layer: the official transforms, not ours.
- **Typer + Rich** for the CLI, **Pydantic** for configurations and scorecards, **uv** for a locked, reproducible environment, **Docker** for the sandbox.

## Evals

- Cases are in [`evals/cases/`](evals/cases), split into **dev** (climbed on) and **held-out** (run only at milestones). Each case has its traps with the layer expected to handle each: rules, agent or human. A trap's result is Expected, Other layer, or Missed.
- The grader, scorecard and cheating checks are covered by `migrator eval climb`'s harness-integrity gate: the climb refuses to run if they changed since the last approval.
- [`docs/eval-audit.md`](docs/eval-audit.md) lists what the eval can and cannot show.
- Results: [`docs/results/`](docs/results) and [`.claude/hillclimb/dev/`](.claude/hillclimb/dev) (every round's runs, scorecards and repair transcripts).

## Repo layout

| Path | What |
|---|---|
| `src/migrator/` | the tool: CLI, graph, scan, rules, verify, repair, review, report, cost, evals |
| `src/migrator/migrations/mui-4-to-5/` | the migration spec, pinned codemod tools, the vendored guide (MIT) |
| `fixtures/` | the purpose-built target repos with planted traps |
| `evals/` | cases, traps, references and configurations |
| `docs/` | running, eval audit, research, results, build log |

## Licence

MIT, see [`LICENSE`](LICENSE). The vendored Material UI guide is MIT, © Call-Em-All (licence in its folder).
