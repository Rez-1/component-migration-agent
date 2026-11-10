# Experiment summary: opus-low vs baseline · held-out split

1 case (fixture-mui4-holdout) × 2 runs · configuration `opus-low` (d81d48a907d0) · experiment `held-out/v1` · total $0.24

**Migrated without a human: 89% (runs: 89% / 89%) vs 22% baseline. Clean runs: 2 of 2 vs 0 of 2.** Cost per clean run: $0.12 (cost per run: $0.12).

| Metric | opus-low (run 1 / run 2) | Mean | baseline (mean) | Change |
|---|---|---|---|---|
| Clean runs | yes / yes | 2 of 2 | 0 of 2 | +2 |
| Migrated without a human | 89% / 89% | 89% | 22% | +67 pts |
| Hand-offs | 1 / 1 | 1 | 0 | +1 |
| Regressions | 0 / 0 | 0 | 0 | 0 |
| Cheating-check hits | 0 / 0 | 0 | 0 | 0 |
| Cheating-check warnings | 0 / 0 | 0 | 0 | 0 |
| Repair traps expected (of 6) | 6 / 6 | 6 | 0 | +6 |
| Codemod TODOs left | 1 / 1 | 1 | 1 | 0 |
| Failures (final verify) | 1 / 1 | 1 | 16 | -15 |
| Cost per run | $0.17 / $0.07 | $0.12 | $0 | +$0.12 |

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

Source: `experiment-summary.json` (this file is rendered from it).
