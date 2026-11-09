# Eval audit (M2, updated for M3)

**M3 update (9 November 2026, before any paid run).** M3 made 14 of the 16 "not yet" items and 2 of the 4 "fail" items testable on the scripted model; they are updated in place below (marked M3). Findings #2 (oracle) and #3 (README leak) are fixed; #1 (resolution) stands until more cases exist (M6). Tally after M3: 51 pass, 1 partial, 2 fail (#1 and the single synthetic case), 2 not yet, 4 not applicable. The two "not yet" items need real models ("answerable from memory", the first paid runs) and a held-out case (M6). "The mechanism is wired" passes on the oracle only; the paid runs show whether a real model moves the metrics.

Found by the oracle replay: **a scoring bug in trap results.** A rules trap counted as handled only if the Rules layer was the *last* to change its file, so when the repair agent later fixed another trap in the same file (Dashboard: `grid-justify` by Rules, `spacing-arithmetic` by the agent) the rules trap turned Missed; and a handed-off human trap whose test still fails (as it must until a human fixes it) scored Missed, not Expected. Rules traps now ask whether Rules changed the file, and a human trap is Expected once handed off. The Baseline could not show either: nothing changes a file after Rules there.

Also measured on the oracle run: **keyword retrieval puts the right guide section in the first message's top 3 for 6 of 9 failing files.** It misses `Autocomplete › Update renderOption` for Search (the failure's words "label", "span" match the Button sections better), the `theme.spacing` px section for Dashboard, and anything for ResponsiveNav and ProfileCard (their only failures are test messages). The agent can still `search_guide`; this is the baseline for the M5 retrieval experiment.


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
| Reference solution exists and passes | **pass (M3)** | `evals/cases/fixture-mui4/reference/` holds one minimal fix per agent trap and the human fix; `tests/test_oracle_slow.py` replays them through the whole graph (real codemods, tsc, ESLint, Jest; scripted model): clean run, 21 traps Expected, 0 Missed. |
| Ground-truth labels correct | pass | Each trap's expected layer was checked empirically in M0 (Baseline preview, then hand fixes) and again by M1's real Baseline. |
| Where the ground truth came from | pass | Human-written traps, verified by running the codemods; no model outputs used as gold. |
| No annotation artifacts | pass | Checked with a trivial baseline: the null run (no codemods) scores 0 of 12 migrated, 0 clean runs, 21 Missed. A no-op cannot game the headline: configurations can only switch off codemod and script steps, never the dependency bump, so "migrate nothing, verify clean" is impossible (`Configuration.apply_to`). |
| Label leakage in the prompt | **pass (M3)** | The prompt is built from the failing file, its failures, the Rules diff, its imports and the guide, never from `traps.yaml`. The trap-describing README moved out of the fixture (finding #3), and a test fails if any fixture file mentions traps, hand-offs, Test files or the Migrator (`test_nothing_in_the_fixture_describes_the_traps`). Source comments that state intent ("below 960px wide") stay: real repos have them. |
| Answerable from memory | not yet (paid runs) | Applies to the repair agent. The fixture is synthetic, but MUI v4 → v5 is a famous migration, so M3 should expect the model to know the guide; that is the realistic setting, not leakage. |
| Difficulty from the problem, not the prompt | pass (M3, by design) | The first message gives what a developer's CI would show plus the guide sections a keyword lookup finds; it never names the breaking change. Retrieval quality is itself a variable (`retrieval`), and keyword lookup misses some changes (below). |
| Agentic: symptom, not investigation | pass (M3) | The agent gets failures (symptoms) and investigates with read_file and search_guide; nothing tells it which trap it is on. |
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
| Infra failures distinguished from model failures | pass | A run that produced no score goes to `errors.jsonl` with a failure class (`case_rejected`, `rules_failure`, `timeout`, `harness`), never into `results.jsonl`, so it holds no `(case, rep)` slot and resume reruns it. Rules failures are kept apart, as the glossary says. Unit-tested (`test_failed_runs_go_to_the_errors_sidecar_and_resume_reruns_them`). M3: a refusal ends the attempt and hands the file off with reason "refusal" (tested); a reply cut off at `max_tokens` without a tool call is nudged and counts against the tool-call budget (tested). |
| "No answer" is not "negative answer" | pass | A run that crashed or was rejected is not scored as "not clean"; it is not scored. A clean run needs a completed run with a final verify. |
| Clean, isolated state per trial | pass | Each run copies the target repo into a fresh temp workspace (`create_dry_run_workspace`, no `.git`, no `node_modules`), installs with `npm ci`, and deletes it afterwards. The only shared state is the pinned codemod tools cache, installed from a lockfile and read-only to runs. |
| Environment complete and functional | pass | The Pre-check rejects a case whose install fails or whose type-check already fails, before any change, so a broken environment is never scored as a result. |
| Deterministic setup | pass | Both Baseline runs gave identical scorecards outside `meta` (checked by `stable_view`); CI asserts the same against the committed scorecard. |
| Scaffold vs model limitations | pass (M3) | The limits are graph edges, each tested: 3 attempts (`max_attempts`, a configuration value), 15 tool calls per attempt, the patch size limit, the cost cap. Every hand-off and Unmigrated file says which limit ended it, so a scaffold limit is never read as a model failure. |
| Token and context limits won't clip | pass (M3, by construction) | `max_tokens` is 16,000 per call (part of every worst case); a first message is about 1–2K tokens on the fixture and conversations stay far under the 1M context. A cut-off reply is nudged, never parsed as an answer. Check `stop_reason` counts in the first paid runs. |
| Transient errors retried with jittered backoff, recorded | partial (M3) | The Anthropic SDK under ChatAnthropic retries 429/5xx/connection errors with backoff (`max_retries=2`); a call that still fails ends the run as a `harness` error row. The retries themselves are not recorded (only the SDK sees them). |
| Hard per-run wall-clock ceiling | pass | `--timeout-s` (default 1800 s) wraps the command runner in `DeadlineRunner`: every command gets at most the time left, and passing the ceiling records a `timeout` error row. Unit-tested. |
| Served model is the model asked for | pass (M3) | Every call records the requested and the served model (`response_metadata["model_name"]`) in the ledger; a mismatch is a scorecard warning (tested) and `results.jsonl` carries the served model. |
| Eval config matches production config | pass | `eval run` calls the same `dry_run` as `migrator migrate --dry-run`, with the same configuration object; nothing is re-implemented for the eval. |
| Full per-case trajectories saved | pass | Per run: `traces/<case>_rep<k>.json` in the viewer's turn format (every stage, rule step and repaired file), every command's log and the raw ESLint/Jest JSON under `runs/<case>_rep<k>/logs/`, and (M3) each failing file's full conversation under `runs/<case>_rep<k>/repair/`, linked from the scorecard. |
| Multiple trials with variance reported | pass | 2 runs per case by default; the experiment summary shows both values next to the mean (the range from 3 runs). |
| Reproducible over time | pass | Python deps locked (`uv.lock`), Node tools locked, fixture locked, guide pinned; scorecards carry `schema_version` and the configuration digest, and resume refuses a changed configuration. Node 20 (the case's target, used by CI) has not been run locally, only Node 24. |
| Harness tested on known-good and known-bad | **pass (M3)** | Known-bad: the Baseline and the null run. Known-good: the oracle replay (clean run, 21 Expected, 0 Missed, 11 of 12 migrated without a human; 12 of 12 with the human fix). Adversarial agent: every guardrail refuses its edit and says why, and the legitimate fix still lands (`test_every_guardrail_against_an_adversarial_agent`). The replay found a scoring bug (below). |

## 3. Metrics hygiene

| Item | Verdict | Why |
|---|---|---|
| Token accounting from the API | pass (M3) | Tokens come from each response's `usage_metadata`, with langchain-anthropic's folding of cache tokens into `input_tokens` undone and the 5-minute/1-hour write breakdown used when present (tested both ways). |
| Cost from recorded tokens and the row's model | pass (M2 scope) | `cost.cost_usd(model, usage)` prices every token type from a pinned USD table, and refuses an unknown model rather than guessing. The Baseline's $0 is a fact (no model calls, `model_calls: 0`), labelled "no LLM" rather than a silent zero. No judge in this eval. |
| Cache hit rate comparable | pass (M3) | `cache_read_share` = cache reads / all input tokens per run, and a warning when reads stay at 0 after 3 calls (tested). Caches are per model, so a per-attempt model switch starts cold; compare runs of the same configuration. |
| Latency against the right boundaries | pass (M3) | Each call's duration is recorded; `timings_s.model` is the run's model time, next to `repair` (model plus tools, mostly verify) and the Node stages. `latency_s` stays the whole run. |
| Per-call breakdown for agentic evals | pass (M3) | The ledger has one row per call (run, case, file, attempt, requested and served model, tokens by type, USD); tests check its rows sum to the scorecard's cost. |
| Perf reported alongside quality | pass | Cost per run, cost per clean run and time per run sit in the same summary table as the quality metrics, as absolute numbers. |

## 4. Grader design

| Item | Verdict | Why |
|---|---|---|
| Prompt-grader agreement | pass (M3) | The prompt asks for what is graded: the file passes type-check, lint and related tests, nothing else breaks, no escape hatches, and a hand-off when the fix belongs to a human. |
| Grades outcomes, not paths | pass | Outcomes come from the final workspace (verify, old-usage rescan), never from what the agent says. |
| Grade the end state | pass | The run happens in a disposable workspace and is scored on what it left: verify output, usages left, diffs per layer. |
| Not overly rigid | pass | Failure identity ignores line numbers (codemods move code); cheating checks count per file, so moving or rewriting existing code isn't punished (unit-tested). |
| Not too lenient | pass | Wrong-but-plausible "fixes" fail: adversarial patches adding `@ts-ignore`, `@ts-expect-error`, `as any`, an `any` parameter, `as unknown as`, `eslint-disable`, `NODE_ENV === 'test'`, `typeof jest`, `it.skip`, a deleted test, an edited `src/test-utils.tsx` and a changed snapshot all fail the run (`tests/test_checks.py`). |
| Cheat-resistant | pass | The cheating checks above, plus the runner's own totals against the Pre-check (fewer tests, more skipped, changed or obsolete snapshots), plus test files defined on the untouched repo's import graph, so importing `test-utils` from a source file can't make it editable. Guardrails in the tools are M3. |
| Ground truth not reachable by the model | **pass (M3)** | `traps.yaml`, the case README and the reference fixes live in `evals/cases/`, outside the workspace; read_file refuses paths outside the workspace (tested) and the fixture is checked for leaks. |
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
| The mechanism is wired | pass on the oracle (M3); real models after the paid runs | With the reference fixes, migrated-without-a-human goes from 25% to 92% and repair traps from 0 to 8 of 8, so a working agent moves the metrics. Whether Haiku or Opus does is the first paid experiment. |
| Headline recomputes from raw rows | pass | `eval summary` recomputes every number from `results.jsonl` and the scorecards, and refuses when a row and its scorecard disagree (unit-tested). |

## Notes for M3 and M5

- The results layout is the `build-eval` one (one flow per split, `baseline/` and `v<N>/` variants); the skill's lite report builder renders it (`runs/evals/dev/report.html`).
- `hillclimb` expects a train/test split inside one flow, with the **test set scored every round** and its score as the headline. That conflicts with our rule that the held-out split runs only at milestones. For M5, either climb with no split (whole dev set every round, labelled "directional", as the guide allows for small sets) and run held-out only at the milestone, or carve a validation slice out of dev for round selection. Either way, `_state.json`'s `train_ids`/`test_ids` must not contain held-out cases.
