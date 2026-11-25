# Experiment summary: opus-low vs baseline · held-out split

2026-11-17 · 1 case (fixture-mui4-holdout) × 2 runs · configuration `opus-low` (44820b26d105) · experiment `held-out/v4` · total $0.23

**Migrated without a human: 89% (runs: 89% / 89%) vs 22% baseline. Clean runs: 2 of 2 vs 0 of 2.** Cost per clean run: $0.11 (cost per run: $0.11).

| Metric | opus-low (run 1 / run 2) | Mean | baseline (mean) | Change |
|---|---|---|---|---|
| Clean runs | yes / yes | 2 of 2 | 0 of 2 | +2 |
| Migrated without a human | 89% / 89% | 89% | 22% | +67 pts |
| Hand-offs | 1 / 1 | 1 | 0 | +1 |
| Regressions | 0 / 0 | 0 | 0 | 0 |
| Cheating-check hits | 0 / 0 | 0 | 0 | 0 |
| Cheating-check warnings | 0 / 0 | 0 | 0 | 0 |
| Repair traps expected (of 6) | 6 / 6 | 6 | 0 | +6 |
| Repair traps expected (share) | 100% / 100% | 100% | 0% | +100 pts |
| Silent misses (a human should look) | 0 / 0 | 0 | 0 | 0 |
| Possible test-fitting edits (a human should look) | 1 / 1 | 1 | — |  |
| Codemod false positives undone by Rules | 1 / 1 | 1 | 0 | +1 |
| Hand-offs for possible test-fitting | 0 / 0 | 0 | — |  |
| Codemod TODOs left | 1 / 1 | 1 | 1 | 0 |
| Failures (final verify) | 1 / 1 | 1 | 16 | -15 |
| Cost per run | $0.07 / $0.16 | $0.12 | $0 | +$0.12 |
| Time per run | 5:59 / 5:25 | 5:42 | 1:01 | |

With 2 runs, the spread is shown as both values, not a standard deviation.

## Traps across runs

| Trap | Expected layer | Run 1 | Run 2 |
|---|---|---|---|
| createMuiTheme renamed createTheme (`create-theme`) | rules | Expected | Expected |
| theme.palette.type renamed mode (`palette-type-mode`) | rules | Expected | Expected |
| CircularProgress variant static renamed determinate (`circular-progress-determinate`) | rules | Expected | Expected |
| TableCell padding="default" renamed normal (`table-cell-padding-normal`) | rules | Expected | Expected |
| Chip variant="default" renamed filled (`chip-variant-filled`) | rules | Expected | Expected |
| Avatar variant="circle" renamed circular (`avatar-variant-circular`) | rules | Expected | Expected |
| Skeleton moved from lab to core; variant rect renamed rectangular (`skeleton-lab-rect`) | rules | Expected | Expected |
| TextField rowsMax renamed maxRows (`textfield-max-rows`) | rules | Expected | Expected |
| theme.spacing() divided by two (`spacing-arithmetic-half`) | agent | Expected | Expected |
| TablePagination back/next button text props replaced by getItemAriaLabel (`pagination-item-aria-label`) | agent | Expected | Expected |
| withMobileDialog removed; the codemod's stand-in never goes full screen (`with-mobile-dialog`) | agent | Expected | Expected |
| theme.mixins.gutters() removed (`mixins-gutters`) | agent | Expected | Expected |
| Autocomplete onChange reasons renamed to camelCase (`autocomplete-reason-names`) | agent | Expected | Expected |
| theme.palette.augmentColor takes { color, name } (`palette-augment-color`) | agent | Expected | Expected |
| Step icons use global state classes; the test's v4 class selectors must change (`stepper-state-classes`) | human | Expected | Expected |
| Checkbox default colour changed from secondary to primary (`checkbox-default-color`) | visual-only | Not scored | Not scored |

Over all runs: 30 Expected, 2 Not scored.

Scorecards: `v4/runs/fixture-mui4-holdout_rep0/scorecard.json`, `v4/runs/fixture-mui4-holdout_rep1/scorecard.json`.
