# M6 plan: real repos

Agreed with the project owner on 10 November 2026. This is the brief for the session that builds M6. Words in **bold** are defined in [`CONTEXT.md`](../CONTEXT.md). The candidate research is in [`research/m6-candidate-repos.md`](research/m6-candidate-repos.md).

## Why M6

The M0–M5 results come from three small fixture apps we wrote ourselves (750–1,100 lines, 20–27 files), with tests for nearly every **Trap** and almost no custom code around MUI. Real codebases have home-grown wrapper layers, patterns the migration guide doesn't cover, and far fewer tests. Fewer tests matters most: verify passes more easily, so **Silent misses** become likely, even for Opus. The 89% held-out result is a ceiling for simple code, not a forecast. M6 measures the real thing, and lower numbers are an expected, useful result.

## Done means

- 3 real repos run end to end, 2 runs each, with the winning M5 configuration (Opus 5.5, low effort) and the Baseline:
  - **dev:** the kubeflow/pipelines frontend ([#12925](https://github.com/kubeflow/pipelines/pull/12925)) and OpossumUI ([#218](https://github.com/opossum-tool/OpossumUI/pull/218));
  - **held-out:** bcgov/wps `web/` ([#1933](https://github.com/bcgov/wps/pull/1933)). Nothing is tuned on it; it runs once, at the end.
- Each run is scored against the repo's merged migration PR (below), and the results go in the README next to the Baseline.
- One real PR, opened with `migrator pr --open` on the owner's **own fork** of whichever dev repo runs cleanest. Never to the upstream project.
- The README states plainly that these reference PRs predate the model's training cutoff (June 2026), so the model may have seen them. If budget is left, Backstage tekton ([community-plugins#9533](https://github.com/backstage/community-plugins/pull/9533), merged 30 June 2026) is a fourth, uncontaminated check; it's a yarn 4 monorepo, so its setup is heavier.

## Scoring against a reference PR

- **Scoring items:** every source file the reference PR changed that imports MUI (lockfiles and formatting-only changes ignored, as decided on 9 November). Each item gets one result:
  - **matches:** the same change or an equivalent one;
  - **other valid fix:** a different change that works;
  - **wrong:** it type-checks and passes the tests but behaves differently;
  - **untouched:** the reference changed it and the run didn't.
  A *wrong* or *untouched* item while verify passes is a real-repo **Silent miss**.
- **Deterministic first:** the diff comparison settles the clear cases. **An LLM judge** decides between *other valid fix* and *wrong*. The owner rates about 20 items by hand to check the judge agrees; build a small rating page for that after the first dev repo has run.
- **Out of scope in the reference:** changes beyond the migration (for example `makeStyles` → `sx`/`styled`, unrelated dependency bumps, refactors) are ignored, not counted as misses, and listed in the scorecard.
- **Test coverage:** Pre-check runs the tests with coverage once. Each file migrated without a human is labelled *covered* or *not covered* by a test, and the README shows both numbers.

## Harness changes

- **Real-repo cases:** clone at the reference PR's base commit into a git-ignored cache (decided on 9 November); the `case.toml` names the repo, commit, sub-folder, reference PR, runner and Node version.
- **Node version per case:** OpossumUI and wps need Node 16 (OpossumUI also needs `ELECTRON_SKIP_BINARY_DOWNLOAD=1` and `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`); kubeflow uses Node 22. The Docker sandbox is pinned to Node 20 today, so the image must follow the case.
- **Runners:** kubeflow uses Vitest 4 (supported in the code but never exercised by a case); OpossumUI and wps use Jest under CRA, with yarn v1.
- **Snapshot tests:** MUI v5 changes class names, so snapshots fail even when the migration is right (kubeflow's PR updated 39 `.snap` files). When a file's only failures are snapshot mismatches, the Migrator itself (never the agent) updates those snapshots and lists each one in the PR for a human to approve. They count as **snapshots to review**, not as failures or hand-offs. Every other test change stays blocked, and the cheating checks still run.
- **Extra dependency upgrades:** an optional per-repo list in `migrate.toml` / `case.toml`, written by a human, never by the LLM. For wps, fill it from the reference PR (devexpress grid v2 → v3, the date-picker change).
- **Expected hand-offs:** some failures can only be fixed in test code (OpossumUI's reference PR edited `test-helpers/`). Those stay hand-offs.

## Budget

- **$30 for all of M6.** New M6 configuration files carry the caps: **$8 per run**, **$50 per month** (the Anthropic Console limit was raised to match on 10 November). Don't edit the M2–M5 configuration files: the caps are part of each configuration's digest, and changing them would detach those results.
- **Runs must finish.** Before a run starts, reserve its whole worst case (estimated from the number of failing files after Rules). If the remaining budget doesn't cover it, the run doesn't start. In M5, a round cap that was too tight stopped two runs halfway; that must not happen again.
- Measure the real cost of one run on the first repo before budgeting the others.
- Every paid round needs the owner's approval, given directly in the build session. If a single run exceeds $2, stop and ask.

## Order of work

1. One repo end to end first: OpossumUI (the smallest reference PR). Baseline, then one agent run. Fix whatever breaks (clone, Node 16, yarn, CRA Jest).
2. Reference scoring, the coverage labels and the snapshot policy, tested on that repo.
3. kubeflow (Vitest, snapshots), then the judge and the owner's 20 ratings.
4. The paid dev runs; then wps, held-out, once.
5. README results with the caveats; the fork PR; `docs/blog-log.md` (kept local) updated at every step.

## Stop and ask the owner

Paid runs, the 20 ratings, opening the fork PR, pushing, and anything that would change scoring after results exist. Don't put API keys in GitHub, and keep client names out of the repo.
