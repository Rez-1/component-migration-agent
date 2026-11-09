# Experiment summary: opus-low vs baseline · dev split

> PROTOTYPE. Mock numbers, to react to. Not real output.

2026-11-09 · 1 case (fixture) × 2 runs · configuration `opus-low` · total $5.98

**Migrated without a human: 79% (runs: 75%, 83%) vs 33% baseline. Clean runs: 1 of 2 vs 0 of 2.** Cost per clean run: $5.98 (cost per run: $2.99).

| Metric | opus-low (run 1 / run 2) | Mean | Baseline (mean) | Change |
|---|---|---|---|---|
| Clean runs | no / yes | 1 of 2 | 0 of 2 | +1 |
| Migrated without a human | 75% / 83% | 79% | 33% | +46 pts |
| Hand-offs | 2 / 1 | 1.5 | — | |
| Regressions | 1 / 0 | 0.5 | 0 | +0.5 |
| Cheating-check hits | 0 / 0 | 0 | — | |
| Repair traps expected (of 8) | 7 / 7 | 7 | 0 | +7 |
| Cost per run | $2.97 / $3.01 | $2.99 | $0 | |
| Time per run | 6:12 / 7:01 | 6:37 | 1:48 | |

## Traps across runs

| Trap | Expected layer | Run 1 | Run 2 |
|---|---|---|---|
| Autocomplete `renderOption` signature | repair | Expected | Expected |
| `theme.spacing()` arithmetic | repair | Expected | Expected |
| `disableBackdropClick` behaviour | repair | Expected | Missed |
| Typography `srOnly` | repair | Missed | Expected |
| `columnsFor` breakpoint values | repair | Expected | Expected |
| ProfileCard ThemeProvider | human | Expected | Expected |
| … 16 more | | | |

With 2 runs, the spread is shown as both values, not a standard deviation.
