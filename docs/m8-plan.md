# M8 plan: the general-agent comparison, exact claims, and how this was built

**Agreed with the project owner, 15 November 2026** (see "Decided by the owner"). Nothing is built until the owner says to start. Words in **bold** are defined in [`CONTEXT.md`](../CONTEXT.md).

## Why M8

An outside review of the public repo (11 November) found three gaps that weaken what M6 shows. None is about Angular, so M7 doesn't close them.

1. **The only comparison is codemods only.** The first question from anyone who works with LLMs is: why not give a general coding agent the repo and the migration guide? There is no answer yet. Without one, M6 shows that the Migrator fails safely. It doesn't show that its design (codemods first, one file at a time, limits in the tools) beats the obvious alternative.
2. **Two claims in the README aren't exactly true.** Honest reporting is the project's main strength, so an inexact claim costs more than a weak number.
   - "wps, run once with the configuration frozen." The run folders show two agent runs on wps. The first (11 November, 08:54) exposed a harness bug: on macOS, a failing `month.test.tsx` was charged to `month.tsx` when only `Month.tsx` exists, so repair never queued ten files. Commit `72cd5e0` fixed it, with the owner's approval, and the second run (09:15) is the one in the table. The configuration didn't change, but it wasn't one run.
   - The three rows of the real-repo table use three configurations: `m6-opus-low-v2` (OpossumUI), `-v3` (kubeflow) and `-v4` (wps). Each was the frozen configuration when its repo ran. The table reads as one setup.
3. **The repo doesn't say how it was built.** Every commit is co-authored by Claude, and the first 108 landed in three days. A developer sees that in the log before reading anything else. Saying it first, with what the owner decided and what was delegated, is stronger than leaving it to be found.

## Done means

- **Part A.** A general coding agent has run on the three M6 repos, 2 runs each, and is scored by the same harness as the Migrator: **Clean run**, files migrated, files left failing, cheating-check hits, **Silent misses**, the four results against the merged PR, cost and time. The README shows it next to the **Baseline** and the Migrator, whichever way the result goes.
- **Part B.** Every claim about how the held-out repo was run is exact. All three repos have Migrator numbers on one configuration. The scorecards behind every README number are in the repo.
- **Part C.** The README has a short "How this was built" section, in the owner's words.

## Part A: the general-agent comparison

### What is compared

| Setup | What it is |
|---|---|
| Codemods only | The **Baseline**, as in M6. Free. |
| The Migrator | Codemods, then the repair agent, on one configuration (see Part B). |
| General agent, plain | A general coding agent with a shell, given the repo and the guide and asked to migrate it. No rules about tests. |
| General agent, with the rules | The same, with the Migrator's limits written into the prompt: don't edit tests, snapshots, configs or lockfiles; no `@ts-ignore`, `as any` or `eslint-disable`; list every file you couldn't finish, with a reason. |

The two general-agent setups test two different README claims. The plain one tests whether the pipeline is worth building at all. The one with the rules tests "the tools enforce the limits, not the prompt": if an agent that is only *told* the rules keeps them, that claim is weaker than the README says.

### Fairness rules

- **The same model and effort** as the Migrator's repair agent: Opus 5.5, low effort. Otherwise the comparison is between models, not designs.
- **The same starting point:** the case's base commit, dependencies installed.
- **The same materials:** the vendored migration guide (v5.18.0) in the workspace, and the pinned `@mui/codemod` available to run. The guide tells the reader to run the codemods, so a general agent may. That is fair: knowing to run them is part of the job.
- **The same sandbox limits** where they can apply: only the workspace mounted, none of the owner's environment variables, the same memory and CPU limits. The agent needs the model API, and it needs the package registry to change dependencies. How to allow those two and nothing else is the first build question.
- **One prompt per setup, written and committed before the first run, and never tuned.** The Migrator's prompt was tuned on OpossumUI and kubeflow, and the README must say so next to the comparison: the general agent gets no tuning, the Migrator got some.
- **A cost stop per run**, like `stop_run_usd`. A run that hits it is scored as it stands and marked "stopped by cost".

### Scoring

The general agent's final workspace goes through the same steps as a Migrator run after Repair:

- **Verify** in the sandbox: the repo's own type-check, lint and tests.
- **File outcomes.** A general agent has no hand-off, so a file ends *migrated* (no old usages, no failures) or *left failing*. In the setup with the rules, a file the agent listed with a reason counts as handed off.
- **Clean run:** every failure is in a listed file, and no cheating check hits.
- **Cheating checks on the final diff**, unchanged: edited tests, skipped tests, escape hatches, a test run with fewer tests than the Pre-check. For the plain setup these are reported, not treated as rule-breaking: it was never told. They are the measure of what "make the tests pass" does without limits.
- **Against the merged PR:** the same items, the same judge, the same rule that missing v5 styling counts as wrong. **Silent misses** as in M6.
- **Cost and time**, from the agent's own usage report, cross-checked where possible.

This needs one new piece of code: scoring a workspace the Migrator didn't produce. The grader, the cheating checks and the reference scorer stay as they are, and the harness-integrity gate must still pass.

### Written down before any run

To keep the reading honest, these are fixed now:

- **If the general agent matches or beats the Migrator** on files migrated and silent misses, with no cheating hits: the README says so in the short version, and the Migrator's remaining case is cost, time and repeatability. That is a real finding, and it is published.
- **If the plain agent migrates more but with cheating hits** (edited tests, escape hatches): the hits are the result. Count them, show two or three, and compare the setup with the rules.
- **If the agent with the rules keeps them:** "limits in the tools, not the prompt" is restated as defence in depth, not as a need.
- With 3 repos and 2 runs each, a difference of one or two files is noise. Only a difference in kind (clean or not, cheating or not, several files) is read as a result.

### Held-out

wps is no longer blind for the Migrator, and the README says so (Part B). It is still blind for the general agent. So: both general-agent setups run on OpossumUI and kubeflow first, the prompts and the scoring code are frozen, and then wps runs. A re-run after a harness bug is allowed, and it is **reported as a re-run**, with the reason, in the same table.

## Part B: exact claims

**Free, and first:**

- **Reword the wps claim** in the README: two agent runs, the harness bug between them, which run is in the table, and that the configuration was the same. Add the same finding to [`eval-audit.md`](eval-audit.md).
- **Say in the table which configuration each row used**, until the re-runs below replace it.
- **Publish the scorecards behind the README's real-repo numbers.** `runs/` is ignored by git, so today only the per-file scores are public. Copy each reported run's `scorecard.json`, `results.jsonl` and `experiment.json` (no logs, no local paths) to `docs/results/m6/`.
- **A claims table**, `docs/results/claims.md`: every number in the README's results section, and the file it comes from. A test recomputes the real-repo table from the committed scorecards and fails when the README disagrees.

**Paid:**

- **Re-run the Migrator on OpossumUI and kubeflow with the wps configuration** (`m6-opus-low-v4`, unchanged), 2 runs each, so all three rows are one setup. From M6's costs this is about $6. The old rows stay in the collapsed details, labelled with their configurations.
- **Time.** From M6's runs: OpossumUI 16–18 minutes a run, kubeflow 50–58, wps 10. The two repeats of a repo can run in parallel, as wps's did. The machine has 10 cores and each sandbox may use 4, so kubeflow's pair and OpossumUI's pair together already ask for more cores than there are. Expect about an hour for both repos side by side, and don't add more runs next to kubeflow: a slow machine can turn into test timeouts, which would spoil the result.
- **Which judge.** M6's table used the Opus judge. M7 moved the judge to Sonnet 5.5, so that no model grades its own work. Everything scored in M8 (the re-runs and the general agent) should use one judge. See the open decisions.

## Part C: how this was built

A README section of 100–150 words, first person, drafted for the owner to rewrite:

- **The facts:** built with Claude Code, starting 9 November 2026; every commit is co-authored by Claude; the dates and the commit count, taken from `git log` on the day it is written.
- **What the owner decided.** The plans and commit messages record these as "the owner's decision". For example: the rule that missing v5 styling counts as wrong; a held-out repo and what may be learnt from it; the budgets and the per-run stops; that a different model must review flagged patches; the one judge override and that the judge's own number stays beside it; what was dropped (the fifth speed-up, the advisor setup).
- **What was delegated:** the code, the tests, the research notes and the first drafts of these documents.
- **What is unaudited.** If not every one of the tests has been read by a person, say so.

The private notes (`docs/blog-log.md`, `docs/project-story.md`) are sources for the owner, never quoted or linked.

## Budget

- **$30 for all of M8**, as a proposal: about $6 for the Migrator re-runs, the rest for the general agent and the judge.
- A general agent's cost per run is unknown, and probably several times the Migrator's, because it reads the whole repo and runs the checks itself. **Measure one plain run on OpossumUI first**, with a $5 stop, before planning the other eleven.
- If the full grid (2 setups × 3 repos × 2 runs) doesn't fit, the setup with the rules runs on all three repos and the plain one on OpossumUI only.
- New M8 configuration files; M2–M7 files stay frozen.

## Order of work

1. **Part B, free:** the README wording, the audit entry, the published scorecards, the claims table and its test.
2. **Part C:** the draft section, for the owner to rewrite.
3. **Scoring a workspace from outside the Migrator**, with tests on the scripted model and a hand-made workspace. The integrity gate must pass.
4. **The general-agent runner:** the container, the two prompts (committed before any run), the cost stop.
5. **One plain run on OpossumUI** to measure cost. Stop and report to the owner.
6. **OpossumUI and kubeflow:** both general-agent setups, and the Migrator re-runs on `m6-opus-low-v4`.
7. **Freeze, then wps:** both general-agent setups.
8. **README:** the comparison table, what it shows, and the caveats (tuning, contamination, sample size). `docs/blog-log.md` (kept local) is updated at every step.

Steps 1 and 2 touch only the README and `docs/`. Steps 3 to 7 touch `src/migrator/evals/` and need paid runs.

## Stop and ask the owner

Paid runs, any scoring change once results exist, pushing, and opening PRs. Keys stay in `~/.config/migrator/` and are never printed. Never commit `docs/blog-log.md` or `docs/project-story.md`.

## Decided by the owner

- **One final re-run on the final code (11 November).** At the end of M7, every dev and real-repo result in the README is re-run on the final code, so all published numbers come from one version. **wps keeps its blind held-out result**, and any re-run of it is labelled as a re-run, with the reason. Changes found in the meantime (the Verify refactor's known gaps, Vitest's narrow verify first) land as their own changes before that re-run; they don't wait for separate measurement. Refactors still have to be behaviour-neutral by their own gates.

- **The M8 decisions (15 November).** All seven were agreed as proposed:
  1. **The general agent** is Claude Code run headless, on Opus 5.5 at low effort, with its subagents forced onto the same model (`CLAUDE_CODE_SUBAGENT_MODEL` with `_FORCE=1`). Cost comes from its own JSON report (`total_cost_usd`, `modelUsage`).
  2. **The sandbox is the mix** from [`research/claude-code-sandbox.md`](research/claude-code-sandbox.md): the agent's commands run in Claude Code's own sandbox on the host, with the strict settings and a probe before every run that checks blocking still works. Scoring stays in the existing Docker **Verify**. OpossumUI and wps get a Node 16 binary first on the agent's path; if that misbehaves, those two fall back to Docker with a network filter.
  3. **Both general-agent setups**, with the fallback in the budget section.
  4. **The judge is Sonnet 5.5** for every M8 row. The M6 table stays as it was scored.
  5. **Part B's paid re-run is dropped.** The end-of-M7 re-run on the final code already puts all three rows on one configuration. Part B keeps its free items.
  6. **The budget is $30**, with the $5 stop on the first measured plain run. Paid M8 runs start only after M7's final re-run has been paid for, because both count against the same $50 monthly cap; slipping into the next month is fine.
  7. **When:** steps 1 and 2 are free and can go first; steps 3 and 4 run in their own git worktree; the paid steps 5 to 7 wait for M7. M8 rebases onto M7's README. **Nothing is built until the owner says to start.**
