# M5 experiments: hill-climbing on the dev split

## Purpose

M5 tunes the repair agent's configuration against the eval, with two targets (the user's decision, 9 November 2026):

1. **Cost per clean run at equal quality** on the current fixture: make cheaper models, cascades and lighter context succeed where Opus 5.5 at low effort already does (2 of 2 clean, 9 of 9 repair traps, $0.20 per clean run).
2. **Quality on a harder dev case** (`fixture-mui4-hard`), so quality has headroom to climb.

Every result here is **directional**: one or two dev cases × 2 runs. The held-out case (`fixture-mui4-holdout`) runs once, at the end of M5, and nothing here is tuned on it.

## Method

The loop is the `claude-api` skill's `hillclimb` procedure (read → propose → apply → run → record, state on disk, harness-integrity gate), adapted to our splits.

**The same as the skill**

- State on disk in the skill's layout: `.claude/hillclimb/dev/` holds `_state.json`, `metrics.md`, `narrative.md` and one folder per round (`baseline/`, `v1/`, `v2/`, …) with `results.jsonl`, `summary.json`, `traces/`, `change.md` and `change.patch`. The eval runner writes there directly (`--results-dir .claude/hillclimb`), so there is no copy step and the skill's report builder reads it as is.
- One change per round, one configuration per change. Every candidate below is selectable by configuration alone, and its configuration digest differs, so a resumed experiment refuses a changed configuration.
- The harness-integrity gate: `migrator eval climb` hashes `harness_paths` (the grader and scorecard, the cheating checks, verify parsers, the old-usage scan, the eval runner and this loop's code, cost accounting, the guardrails, the vendored guide, the traps and every case, the fixtures, the Baseline configuration, `uv.lock`) and refuses to run when the digest differs from the one the user last approved with `--approve-harness`. It is a change detector, not a security boundary: what bounds an unattended run is the command the user allows.
- Approval per round (`approve_each_round: true`): a round runs only with `--approved`, which the orchestrator passes after the user said yes to that round's change and cost.
- The headline is recomputed from raw rows every round (`eval summary`), and each round's runs keep their full transcripts (the repair conversations) for the analysis step.

**What differs, and why**

| Skill | Here | Why |
|---|---|---|
| Train/test split inside the flow; test scored every round and is the headline | No split: every dev case is read and scored each round; `train_ids` = the dev cases, `test_ids` = `[]` | With 1–2 dev cases, a test slice would be one case or none. The skill's "small set" mode: score everything, label it directional. |
| The held-out number comes from the test slice | The held-out split runs **once**, at the end: `migrator eval run --split held-out --config <winner>` | Our held-out case is a separate app nobody tuning may read. It never appears in `_state.json` (`eval climb` refuses a held-out case and a non-empty `test_ids`). |
| Fixed case set | Dev cases are discovered each round (`fixture-mui4-hard` joined while this was being set up) | A new dev case joins by adding it, not by editing the loop. When the set changes, `eval climb` says so, and rounds are compared only on the same cases (see the Budget's step 0). |
| A Node runner scaffold (`run-eval.mjs`) | `migrator eval climb`, which wraps `eval run` and `eval summary` | Our runner already writes the build-eval layout. The wrapper adds the gate, dev-only discovery, the per-round approval, the resolved scope with a cost estimate, and the keep verdict. |
| `best` picked on the test score | `best` picked by the keep rule below, against the best round so far | The user's rule, on dev. |

## Keep rule

A change is **kept** when quality is no worse than the best round's — clean runs, repair traps Expected, regressions, cheating-check hits — and either quality improves or cost per clean run drops. Otherwise it is reverted. (`keep_verdict` in `src/migrator/evals/hillclimb.py`; `eval climb` prints it, the orchestrator records the decision.)

Two caveats to read with every verdict, without changing the rule:

- **Quality noise.** With 4 runs (2 cases × 2), the clean-run noise floor is about ±50 points; a one-run change in clean runs is not a signal by itself. Per-trap results are finer-grained and are in each round's summary.
- **Cost noise.** Measured on opus-low: a run that starts with a cold cache cost $0.23–0.25, the next run within 5 minutes $0.14 (cache reads of the shared prefix). So run order alone moves cost per run by about 40%. A cost-only "keep" of less than about 30% should be marked "within noise" in the log's note.

## Budget

Each round is 2 runs on each dev case (4 runs with two dev cases), approved one at a time. The month cap is $20 on this machine (ledger: $0.79 spent so far in November). Caps per run stay at the configuration's $5; pass each round's `--max-cost` from the Planned table's upper estimate.

How to run a round (the orchestrator, after the user's OK):

```sh
# once, by the user, after reviewing the harness:
uv run migrator eval climb --config opus-low --dry-run --approve-harness
# every round: check the scope and estimate for free, then run it
uv run migrator eval climb --config <name> --dry-run
uv run migrator eval climb --config <name> --max-cost <usd> --approved
# at the end of M5, once:
uv run migrator eval run --split held-out --config <winner> --repeats 2 --max-cost <usd>
```

**Step 0, before any candidate.** `fixture-mui4-hard` has joined the dev split, and the best round so far (`v1`, opus-low) ran only `fixture-mui4`. Re-run the Baseline (free) and opus-low on the full dev set first, and make that opus-low round `best`; the keep rule refuses to compare rounds on different case sets ("not comparable").

## Candidates

Each is one configuration in `evals/configs/` (one change from opus-low, except the model comparison, which changes the model). Digests are the configurations' own.

| Configuration | Digest | The change | Notes |
|---|---|---|---|
| `opus-low` | `d81d48a907d0` | (the best so far, M3) | Opus 5.5, effort low, prompt v1, keyword retrieval |
| `haiku-high` | `e5c67aa24399` | Haiku 5.5, effort high | haiku-debug's knobs, as a reported experiment (haiku-debug ran on fixture revision 1) |
| `sonnet-medium` | `820a5876cf8d` | Sonnet 5.5, effort medium | The skill's starting point for agentic coding on Sonnet 5.5 (its effort levels were recalibrated) |
| `cascade-haiku-opus` | `451f9f193600` | Attempt 1 Haiku 5.5 (high), attempts 2–3 Opus 5.5 (low) | New `attempt_efforts`. Each call's worst case is priced at that attempt's model; the scorecard shows cost per model; an escalation starts a cold cache (caches belong to one model) |
| `opus-low-context` | `672db259cecb` | Retrieval `keyword-context` | The failing file's own components weigh more, and the JSX props around the failing lines join the query. Offline: 6 of 9 vs 5 of 9 (below) |
| `opus-low-imports` | `93892fe0988a` | Retrieval `keyword-imports` | The component weighting alone. Offline: no change in hits (5 of 9), so not worth a paid round on its own |
| `opus-low-tools-v2` | `a1af159053c1` | Prompt and tools v2 | `apply_edit` warns when the edited file no longer parses (tree-sitter) and keeps the edit; the scorecard counts the warnings |
| `haiku-advisor-opus` | `6ebdd151e98d` | Haiku 5.5 (high) with Opus 5.5 as advisor | Prompt `v1-advisor` (one paragraph on when to consult). At most 2 consultations of 4,000 tokens per request |
| `embeddings` retrieval | — | not built | See "Embeddings" below |

Retrieval and tools changes are written on top of opus-low. If a cheaper model or the cascade wins first, the orchestrator writes the same change on top of the winner (one new configuration file) rather than stacking it on opus-low.

### Offline retrieval metric (free)

`migrator eval retrieval .claude/hillclimb/dev/baseline/runs/fixture-mui4_rep0` rebuilds, for each repair trap whose file fails after Rules, the guide ranking the first message would show, and checks whether the trap's guide section is among the top 3 (shown in full). The trap labels only score the ranking; the retriever never sees them. Measured on the committed Baseline run of `fixture-mui4` (dev):

| Trap | File | keyword | keyword-imports | keyword-context |
|---|---|---|---|---|
| `autocomplete-render-option` | `Search.tsx` | miss (#14) | miss (#4) | **hit** (#1) |
| `spacing-arithmetic` | `Dashboard.tsx` | miss (#6) | miss (#6) | miss (#6) |
| `dialog-disable-backdrop-click` | `AccountDialog.tsx` | **hit** (#2) | **hit** (#2) | **hit** (#2) |
| `typography-sr-only` | `Notifications.tsx` | **hit** (#1) | **hit** (#1) | **hit** (#1) |
| `breakpoint-sizes` | `ResponsiveNav.tsx` | miss (#27) | miss (#19) | miss (#19) |
| `button-color-expression` | `Settings.tsx` | **hit** (#1) | **hit** (#1) | **hit** (#1) |
| `button-label-override` | `theme.ts` | **hit** (#2) | **hit** (#3) | **hit** (#3) |
| `select-event-type` | `ProfileForm.tsx` | **hit** (#1) | **hit** (#1) | **hit** (#1) |
| `styles-needs-theme-provider` | `ProfileCard.tsx` | not ranked | not ranked | not ranked |
| **Top-3 hit rate** | | **5 of 9** | **5 of 9** | **6 of 9** |

Reading it: the Search miss came from the failing line's words ("label", "span", "option") matching every component's "span and label" change. Weighting the file's own components moves renderOption from #14 to #4, not into the top 3; adding the prop the failing line sits in (`renderOption`) puts it first. The three remaining misses have no words to find: Dashboard's failure is a type error on arithmetic (`theme.spacing(1) * 3`), and ResponsiveNav and ProfileCard fail only in tests whose messages don't name the API. The M3 audit counted 6 of 9 *failing files* on the oracle run; this table counts *repair traps* on the Baseline run, so its keyword baseline is 5 of 9. This metric is measured on the dev case, so a gain still has to hold on held-out; and the agent can always `search_guide`, so a top-3 miss is not a failed repair (M3's opus-low fixed all 9 traps with keyword retrieval).

### Embeddings (a later option, not built)

An embeddings retriever fits the same `BaseRetriever` interface, but nothing that runs locally for free is light: a local model needs `sentence-transformers` (with PyTorch, about 2 GB) or `fastembed` (onnxruntime) plus a one-time download of model weights (about 100 MB, e.g. a small BGE model) from Hugging Face, and an API (Voyage) is paid and online. Over 204 guide sections either works; it is left for later because the offline table shows the misses are about *what to search for* (the failure gives no API words), which embeddings of the same query would not fix. `retrieval = "embeddings"` is refused at run time with this reason.

### Advisor tool: verdict

**Supported without hacks, implemented** (`haiku-advisor-opus`). The installed `langchain-anthropic` 1.7.10 passes `advisor_20260301` through `bind_tools` as a server tool, adds the `advisor-tool-2026-03-01` beta header itself, and keeps `advisor_tool_result` blocks when the conversation is replayed. Haiku 5.5 executor with an Opus 5.5 advisor is a valid pair (the skill's pairing table). What we had to add, in our own code:

- **Cost.** The advisor's tokens bill at Opus rates, and LangChain's `usage_metadata` does not separate them; the raw `usage.iterations` (copied into `response_metadata`) does. Each iteration is priced at its own model, the advisor's share is a ledger row of its own, and the scorecard shows cost per model. Whether the top-level `usage` also counts the advisor's tokens is not documented; pricing per iteration is right either way. Not yet checked against a real response (no paid calls): the first advisor run should compare the ledger with the Console.
- **The cap.** Each call's worst case adds `max_uses` consultations, each reading the whole conversation plus the executor's output at the advisor's cache-write price and writing `max_tokens` at its output price.
- **Limits.** Opus 5.5's advice comes back encrypted (`advisor_redacted_result`): it is replayed, never readable, so the transcripts can't show *why* an advised fix worked. And the skill's own cost guidance warns that the consult rate is the fragile variable and that on its coding benchmark the advisor bought about what more effort did: compare it with `haiku-high` and `sonnet-medium` before reading anything into it.

## Planned

Estimates for one round (2 runs on each of the 2 dev cases = 4 runs), from the ledger (5 paid runs on `fixture-mui4`: 4 opus-low, 1 haiku-debug) and the pinned price table (`PRICES_CHECKED = 2026-11-09`: Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per million tokens, cache reads $0.20/$0.20/$0.01). `fixture-mui4-hard` has not run yet, so it is assumed to cost about what `fixture-mui4` does; it may well cost more, which is why the upper estimate is the one to pass as `--max-cost`.

| Round | Configuration | Per run (estimate) | Round of 4 runs | Pre-flight says | Basis |
|---|---|---|---|---|---|
| 0a | `baseline` (full dev set) | $0 | $0 | $0 | Rules only |
| 0b | `opus-low` (full dev set, the new best) | $0.14–0.25 | $0.60–1.00 | $0.76 | 4 measured runs: $0.23, $0.14, $0.25, $0.14 |
| 1 | `haiku-high` | $0.03–0.05 | $0.12–0.20 | $0.12 | 1 measured run: $0.03 (59 calls, 13 attempts) |
| 2 | `sonnet-medium` | $0.08–0.18 | $0.32–0.72 | $0.40 | opus-low's tokens at Sonnet prices ($0.08–0.13), up to 2× output for medium effort |
| 3 | `cascade-haiku-opus` | $0.05–0.25 | $0.20–1.00 | $0.18 | Haiku attempts ($0.002 each) + escalations on Opus that re-read the conversation cold (~$0.05 each, Haiku needed attempt 2 on 3 of 9 files); the pre-flight prices escalations at Opus's warm average, so it is the low end |
| 4 | `opus-low-context` | $0.14–0.25 | $0.60–1.00 | $0.76 | As opus-low (same model; the first message may be slightly longer) |
| 5 | `opus-low-tools-v2` | $0.14–0.25 | $0.60–1.00 | $0.76 | As opus-low |
| 6 | `haiku-advisor-opus` | $0.30–1.70 | $1.20–6.80 | $3.43 | Haiku's run (59 calls, 8.7K prompt tokens per call) with an Opus consultation on 20–50% of calls at $0.02–0.06 each; a guess until the first run measures the consult rate |
| — | `opus-low-imports` | $0.14–0.25 | $0.60–1.00 | $0.76 | Not recommended: no offline gain |
| | **All of 0–6** | | **$3.6–11.7** | **$6.4** | |
| End | held-out, the winner × 2 runs | | ~$0.1–0.5 | | Depends on the winner |

Suggested order: 0a, 0b (re-baseline), then the cheap model comparison (1, 2, 3) because it serves target 1 directly, then 4 and 5 on top of whichever wins, then 6 last (the most expensive and least inspectable). Every round still needs the user's OK.

## Experiment log

Filled in by the orchestrator, one row per round. "Dev results" = clean runs, repair traps Expected, regressions, cheating hits (per case when there are two); "cost" = cost per clean run (and per run). All rows are directional.

| id | date | change | configuration | dev results | cost | kept? | note |
|---|---|---|---|---|---|---|---|
