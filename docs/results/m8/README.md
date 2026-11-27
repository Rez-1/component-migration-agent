# M8 results: a general agent on the same three repos

Claude Code, run headless on Opus 5.5 at low effort (the Migrator's repair-agent model and effort), on the same base commits, with the vendored guide and the pinned codemods. Two setups:

- **plain** ([`plain-v1.md`](../../../src/migrator/general_agent/prompts/plain-v1.md)): the repo, the guide and the codemods. No rules about tests.
- **rules** ([`rules-v1.md`](../../../src/migrator/general_agent/prompts/rules-v1.md)): the same, plus the Migrator's limits written into the prompt (don't edit tests, snapshots, configs or lockfiles; no `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`, `as any` or `eslint-disable`), and a list of every file it couldn't finish, with a reason.

Both prompts were written and committed before the first run and never tuned. The Migrator's prompt was tuned on OpossumUI and kubeflow. Scan, Pre-check, the final Verify, the cheating checks and Scoring are the Migrator's own. How the agent is sandboxed is in [`claude-code-sandbox.md`](../../research/claude-code-sandbox.md).

## Files

| Repo | Setup | Experiment | Summary | Per-file scores |
|---|---|---|---|---|
| OpossumUI | plain | `dev/v7` | [summary](opossum-ui-plain-experiment-summary.md) | [run 1](opossum-ui-plain-run1-reference-score.md), [run 2](opossum-ui-plain-run2-reference-score.md) |
| | rules | `dev/v8` | [summary](opossum-ui-rules-experiment-summary.md) | [run 1](opossum-ui-rules-run1-reference-score.md), [run 2](opossum-ui-rules-run2-reference-score.md) |
| kubeflow | plain | `dev/v10` | [summary](kubeflow-pipelines-plain-experiment-summary.md) | [run 1](kubeflow-pipelines-plain-run1-reference-score.md), [run 2](kubeflow-pipelines-plain-run2-reference-score.md) |
| | rules | `dev/v11` | [summary](kubeflow-pipelines-rules-experiment-summary.md) | [run 1](kubeflow-pipelines-rules-run1-reference-score.md), [run 2](kubeflow-pipelines-rules-run2-reference-score.md) |
| wps, held out | plain | `held-out/v4` | [summary](bcgov-wps-plain-experiment-summary.md) | [run 1](bcgov-wps-plain-run1-reference-score.md), [run 2](bcgov-wps-plain-run2-reference-score.md) |
| | rules | `held-out/v5` | [summary](bcgov-wps-rules-experiment-summary.md) | [run 1](bcgov-wps-rules-run1-reference-score.md), [run 2](bcgov-wps-rules-run2-reference-score.md) |

The summaries are written with `migrator eval summary --stable`; the per-file scores come from `migrator eval score-reference`, with the Sonnet 5.5 judge, as for M7's rows.

## Read with these in mind

- **Few runs.** 2 runs per row, 12 in all. A difference of one or two files is noise; only a difference in kind (clean or not, cheating or not, several files) is a result.
- **wps ran once.** Both setups ran on wps after the prompts and the scoring code were frozen, once each, with no re-runs. No run hit its cost stop.
- **One scoring change, made after the first results.** In a Migrator run a line the codemods write (preset-safe's `eslint-disable-next-line` over the theme augmentation, for example) is part of the Rules layer and only a note. The general agent runs the codemods itself, so at first the same line failed its run. The owner approved a fix on 19 November 2026, before the kubeflow and wps runs: the cheating checks now start from what the pinned codemods alone write to the untouched workspace (`general_agent/baseline.py`), except in files the agent put back as they were. The two OpossumUI experiments ran before the fix and were re-scored with `migrator eval rescore`, which calls no model and first checks that the old method reproduces each run's recorded findings exactly (all four did). That changed OpossumUI plain from 4 hits a run to 3, and OpossumUI rules from 0 of 2 clean to 1 of 2.
- **Three wps runs were judged twice.** In wps plain runs 1 and 2 and wps rules run 1, the agent wrote its own `makeStyles` wrapper (in `src/app/` or `src/utils/`) that passes the app theme as the default theme, as v4 did, and pointed every file at it. The judge reads one file at a time and at first never saw the wrapper, so it called the same import "other valid fix" in about 60 files and "wrong" in others: 25 to 27 "wrong" verdicts a run, 14 to 16 of them naming no other problem. The judge now also sees any new file the run wrote that the scored file imports (`run_helpers` in `evals/reference.py`); files that import none keep their cached verdicts, so no other run, and no Migrator run, changed. Judged again, the three runs have 9, 11 and 12 silent misses, and every remaining "wrong" names a real miss (a `variant="standard"`, a font size, `StyledEngineProvider injectFirst`). The per-file scores here are the new ones. Re-judging cost $1.74.
- **Different judges on wps.** The Migrator's wps row is M6's blind result, scored by the Opus judge; these runs are scored by Sonnet 5.5. The Sonnet judge also puts 3 of wps's items out of scope (122 items, where M6 scored 123).
- **The model may have seen the answers.** All three PRs were merged before Opus 5.5's training cutoff.
