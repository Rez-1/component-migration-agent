# Eval audit (M2)

The M2 acceptance check: the `claude-api` skill's `eval-audit` checklist, item by item, against the harness as built (`migrator eval run` / `eval summary`, the cheating checks, the scorecard). Done on 9 November 2026, after a real 2-run Baseline experiment (`docs/results/baseline-experiment/`) and a "null" experiment with every codemod switched off.

**Verdicts:** pass, fail (with what was done about it), or **not yet**: the item only means something once the repair agent exists (M3), or needs more cases (M6). M2 has no LLM, so every model-side item is honest "not yet", not a pass.

**Summary.** Of 60 items: 36 pass, 4 fail, 16 not yet, 4 not applicable, plus one bug found and fixed during the audit. The 4 fails come down to two open findings (#1 and #2 below) and one known limit (a single synthetic case; real repos are M6). Finding #3 is a "not yet" that must be fixed before M3. Most serious first:

1. **No resolution for decisions yet.** The dev split has one case. With 1 case × 2 runs, the noise floor on the clean-run rate is about ±70 points (`1/sqrt(n·R)`), so no M3 comparison on the dev split can be read as more than a demo until more cases exist (brief: 8 dev cases). The fixture's per-trap scores (8 repair traps per run) give finer signal than the binary headline and should be what M3 reports alongside it.
2. **No oracle run.** The harness has been run on known-bad (the Baseline and the null run) but not on known-good: a run with the hand-written fixes from M0's preview should score a clean run with 8 of 8 repair traps Expected. The fixes were made in a scratch copy and not kept. M3 should commit them as a reference patch and replay it through a fake repair agent before the first paid run.
3. **The fixture's README is in the workspace.** `fixtures/mui4-app/README.md` is copied into every workspace and says how many traps there are, that the human trap's fix lives in a test file, and where `traps.yaml` is. In M2 nothing reads it; in M3 the repair agent's `read_file` could. Before M3: keep fixture documentation out of the workspace, or limit `read_file` to source files.

Fixed during the audit: **trap scoring on crashed suites.** The null run scored 3 traps "Other layer" although nothing had touched their files: their test suites crashed on import, so the specific test never ran and its check never "fired". A crashed suite now counts as the check firing, and a file no layer changed scores Missed (commit `f15d170`). The null run now scores 21 Missed, 1 Not scored; the Baseline is unchanged.

## 1. Task design

| Item | Verdict | Why |
|---|---|---|
| Tier 1: programmatic checks over the full set | pass | One case; `case.toml` and `traps.yaml` are schema-validated on load (Pydantic, `extra="forbid"` for cases). 22 traps, 22 distinct ids. |
| Tier 2: stratified close read | pass | The whole set is one case with 22 traps; every trap was read and hand-checked in M0 and re-checked by the M1 Baseline (15 of 15 `caught_by` checks fire). |
| Tier 3: per-case LLM auditor | not applicable | One case, hand-audited; no reason to pay for an auditor. |
| Unambiguous success criteria | pass | Clean run and the outcomes are mechanical (verify output, old-usage rescan); trap results follow fixed rules in `report.score_trap`. |
| Reference solution exists and passes | **fail (open, #2)** | M0 showed hand fixes turn verify green, but they were not kept, so no oracle runs through the harness. |
| Ground-truth labels correct | pass | Each trap's expected layer was checked empirically in M0 (Baseline preview, then hand fixes) and again by M1's real Baseline. |
| Where the ground truth came from | pass | Human-written traps, verified by running the codemods; no model outputs used as gold. |
| No annotation artifacts | pass | Checked with a trivial baseline: the null run (no codemods) scores 0 of 12 migrated, 0 clean runs, 21 Missed. A no-op cannot game the headline: configurations can only switch off codemod and script steps, never the dependency bump, so "migrate nothing, verify clean" is impossible (`Configuration.apply_to`). |
| Label leakage in the prompt | not yet | There is no prompt in M2. See finding #3 for what the agent could read in M3. |
| Answerable from memory | not yet | Applies to the repair agent. The fixture is synthetic, but MUI v4 → v5 is a famous migration, so M3 should expect the model to know the guide; that is the realistic setting, not leakage. |
| Difficulty from the problem, not the prompt | not yet | No prompt yet. |
| Agentic: symptom, not investigation | not yet | M3 decides what the agent is given (by design: the failing file and its failures, as a user's CI would show). |
| Realistic distribution and shape | **fail (open, known)** | One synthetic app. Real repos with merged migration PRs are M6. Stated in the experiment summary as a fixture-only result. |
| Difficulty headroom | pass | Baseline: 25% migrated without a human, 0 of 8 repair traps, not clean. Lots of headroom; not saturated. |
| Saturation | pass | Far from the ceiling. |
| Class balance | not applicable | Not a classification eval. |
| Both-directions coverage | pass | The human trap checks that the agent hands off instead of fixing; cheating checks catch over-eager "fixes"; the null run checks that doing nothing scores nothing. |
| One capability per case | pass | Traps are scored one by one, so a run that fails can say which breaking change it missed. |
| Inverted items as a smoke test | pass | The null-vs-Baseline comparison found the crashed-suite scoring bug (fixed above). |
| Staleness | pass | The guide is vendored at a pinned tag (`v5.18.0`, commit recorded) and the codemod at 9.4.0 with a lockfile; nothing live. |
| Generated cases: fix the generator | not applicable | Hand-built fixture. |

## 2. Harness design

| Item | Verdict | Why |
|---|---|---|
| Infra failures distinguished from model failures | pass | A run that produced no score goes to `errors.jsonl` with a failure class (`case_rejected`, `rules_failure`, `timeout`, `harness`), never into `results.jsonl`, so it holds no `(case, rep)` slot and resume reruns it. Rules failures are kept apart, as the glossary says. Unit-tested (`test_failed_runs_go_to_the_errors_sidecar_and_resume_reruns_them`). Truncation and refusals: not yet (M3). |
| "No answer" is not "negative answer" | pass | A run that crashed or was rejected is not scored as "not clean"; it is not scored. A clean run needs a completed run with a final verify. |
| Clean, isolated state per trial | pass | Each run copies the target repo into a fresh temp workspace (`create_dry_run_workspace`, no `.git`, no `node_modules`), installs with `npm ci`, and deletes it afterwards. The only shared state is the pinned codemod tools cache, installed from a lockfile and read-only to runs. |
| Environment complete and functional | pass | The Pre-check rejects a case whose install fails or whose type-check already fails, before any change, so a broken environment is never scored as a result. |
| Deterministic setup | pass | Both Baseline runs gave identical scorecards outside `meta` (checked by `stable_view`); CI asserts the same against the committed scorecard. |
| Scaffold vs model limitations | not yet | Max attempts, tools and step limits arrive with M3. Configurations make each one a variable. |
| Token and context limits won't clip | not yet | No model calls in M2. |
| Transient errors retried with jittered backoff, recorded | not yet | No API calls in M2. `ErrorRow` already carries model and usage for billed-but-failed attempts. |
| Hard per-run wall-clock ceiling | pass | `--timeout-s` (default 1800 s) wraps the command runner in `DeadlineRunner`: every command gets at most the time left, and passing the ceiling records a `timeout` error row. Unit-tested. |
| Served model is the model asked for | not yet | No model in M2. `results.jsonl` has a `model` field to fill from the responses, and the M3 runner must assert it. |
| Eval config matches production config | pass | `eval run` calls the same `dry_run` as `migrator migrate --dry-run`, with the same configuration object; nothing is re-implemented for the eval. |
| Full per-case trajectories saved | pass (M2 scope) | Per run: `traces/<case>_rep<k>.json` in the viewer's turn format (every stage and rule step as a tool call and result, the scorecard as the last turn), plus every command's log and the raw ESLint/Jest JSON under `runs/<case>_rep<k>/logs/`. The repair agent's messages join the trace in M3. |
| Multiple trials with variance reported | pass | 2 runs per case by default; the experiment summary shows both values next to the mean (the range from 3 runs). |
| Reproducible over time | pass | Python deps locked (`uv.lock`), Node tools locked, fixture locked, guide pinned; scorecards carry `schema_version` and the configuration digest, and resume refuses a changed configuration. Node 20 (the case's target, used by CI) has not been run locally, only Node 24. |
| Harness tested on known-good and known-bad | **fail (open, #2)** | Known-bad: yes (Baseline; null run, after the fix: 0%, 21 Missed, 0 clean). Known-good: no oracle yet. Cheating checks were tested on both sides: clean patches pass, adversarial ones fail. |

## 3. Metrics hygiene

| Item | Verdict | Why |
|---|---|---|
| Token accounting from the API | not yet | `Usage` mirrors the API's fields, including cache writes by TTL; filled from responses in M3. |
| Cost from recorded tokens and the row's model | pass (M2 scope) | `cost.cost_usd(model, usage)` prices every token type from a pinned USD table, and refuses an unknown model rather than guessing. The Baseline's $0 is a fact (no model calls, `model_calls: 0`), labelled "no LLM" rather than a silent zero. No judge in this eval. |
| Cache hit rate comparable | not yet | The scorecard has `cache_read_share`; meaningful from M3. |
| Latency against the right boundaries | not yet | `latency_s` is the whole run (installs included). With a model, M3 should record model time separately from Node time. |
| Per-call breakdown for agentic evals | not yet | The M3 ledger records every model call (run, file, attempt, tokens, cost). |
| Perf reported alongside quality | pass | Cost per run, cost per clean run and time per run sit in the same summary table as the quality metrics, as absolute numbers. |

## 4. Grader design

| Item | Verdict | Why |
|---|---|---|
| Prompt-grader agreement | not yet | No prompt yet; M3's prompt asks for verify to pass without escape hatches, which is what is graded. |
| Grades outcomes, not paths | pass | Outcomes come from the final workspace (verify, old-usage rescan), never from what the agent says. |
| Grade the end state | pass | The run happens in a disposable workspace and is scored on what it left: verify output, usages left, diffs per layer. |
| Not overly rigid | pass | Failure identity ignores line numbers (codemods move code); cheating checks count per file, so moving or rewriting existing code isn't punished (unit-tested). |
| Not too lenient | pass | Wrong-but-plausible "fixes" fail: adversarial patches adding `@ts-ignore`, `@ts-expect-error`, `as any`, an `any` parameter, `as unknown as`, `eslint-disable`, `NODE_ENV === 'test'`, `typeof jest`, `it.skip`, a deleted test, an edited `src/test-utils.tsx` and a changed snapshot all fail the run (`tests/test_checks.py`). |
| Cheat-resistant | pass | The cheating checks above, plus the runner's own totals against the Pre-check (fewer tests, more skipped, changed or obsolete snapshots), plus test files defined on the untouched repo's import graph, so importing `test-utils` from a source file can't make it editable. Guardrails in the tools are M3. |
| Ground truth not reachable by the model | not yet (#3) | `traps.yaml` lives outside the workspace; the fixture README inside it describes the traps. Fix before M3. |
| Spot-check the failures | pass | All 15 Baseline failures and all 22 trap results were read; each failure sits in its trap's file (asserted by the slow test). |
| Deterministic grader | pass | The grader is code; two runs gave identical scorecards. |
| Atomic checks over holistic scores | pass | The grade is a dict: clean run, migrated share, repair traps expected, cheating hits, regressions; traps are scored one by one. |
| Aggregation matches the question | pass | Means for shares; cheating checks are fail-on-any per run (one hit and the run is not clean). |
| Partial credit doesn't make a degenerate policy optimal | pass | Handing everything off scores 0% migrated without a human, shown next to Clean run; doing nothing scores 0% and not clean (null run). |
| Handles large outputs | pass | Parsers read the runners' JSON files, not truncated console output; scorecard messages are cut only in the markdown table, never in the JSON. |
| LLM judge items (position, verbosity, self-preference, rubric, calibration, negatives) | not applicable | No LLM judge. An M5 judge for diff quality would need all of them. |

## 5. Can it detect the change?

| Item | Verdict | Why |
|---|---|---|
| Noise floor vs headroom vs smallest change worth acting on | **fail (open, #1)** | 1 dev case × 2 runs: about ±70 points on clean-run rate. Headroom is large (Baseline 0 of 2 clean, 0 of 8 repair traps), but only a large effect is visible. More cases (M6) are the lever; per-trap scores help before then. |
| Train and test from the same population | not yet | No held-out case exists yet; `split = "dev"` is the only value in use. |
| The mechanism is wired | not yet | The mechanism is the repair agent (M3). The Rules mechanism is wired: switching the codemods off drops migrated-without-a-human from 25% to 0% and failures from 15 to 45. |
| Headline recomputes from raw rows | pass | `eval summary` recomputes every number from `results.jsonl` and the scorecards, and refuses when a row and its scorecard disagree (unit-tested). |

## Notes for M3 and M5

- The results layout is the `build-eval` one (one flow per split, `baseline/` and `v<N>/` variants); the skill's lite report builder renders it (`runs/evals/dev/report.html`).
- `hillclimb` expects a train/test split inside one flow, with the **test set scored every round** and its score as the headline. That conflicts with our rule that the held-out split runs only at milestones. For M5, either climb with no split (whole dev set every round, labelled "directional", as the guide allows for small sets) and run held-out only at the milestone, or carve a validation slice out of dev for round selection. Either way, `_state.json`'s `train_ids`/`test_ids` must not contain held-out cases.
