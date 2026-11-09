# Experiment summary: opus-low vs baseline · dev split

1 case (fixture-mui4) × 2 runs · configuration `opus-low` (d81d48a907d0) · experiment `dev/v2` · total $0.37

**Migrated without a human: 100% (runs: 100% / 100%) vs 25% baseline. Clean runs: 2 of 2 vs 0 of 2.** Cost per clean run: $0.18 (cost per run: $0.18).

| Metric | opus-low (run 1 / run 2) | Mean | baseline (mean) | Change |
|---|---|---|---|---|
| Clean runs | yes / yes | 2 of 2 | 0 of 2 | +2 |
| Migrated without a human | 100% / 100% | 100% | 25% | +75 pts |
| Hand-offs | 0 / 0 | 0 | 0 | 0 |
| Regressions | 0 / 0 | 0 | 0 | 0 |
| Cheating-check hits | 0 / 0 | 0 | 0 | 0 |
| Cheating-check warnings | 0 / 0 | 0 | 0 | 0 |
| Repair traps expected (of 8) | 8 / 8 | 8 | 0 | +8 |
| Codemod TODOs left | 0 / 0 | 0 | 0 | 0 |
| Failures (final verify) | 0 / 0 | 0 | 15 | -15 |
| Cost per run | $0.23 / $0.14 | $0.18 | $0 | +$0.18 |

With 2 runs, the spread is shown as both values, not a standard deviation.

## Traps across runs

| Trap | Expected layer | Run 1 | Run 2 |
|---|---|---|---|
| createMuiTheme renamed createTheme (`create-theme`) | rules | Expected | Expected |
| Grid justify renamed justifyContent (`grid-justify`) | rules | Expected | Expected |
| fade renamed alpha (`fade-alpha`) | rules | Expected | Expected |
| Autocomplete moved from lab to core (`autocomplete-import`) | rules | Expected | Expected |
| getOptionSelected renamed isOptionEqualToValue (`autocomplete-option-equal`) | rules | Expected | Expected |
| Button color="default" removed (literal) (`button-color-default-literal`) | rules | Expected | Expected |
| theme.spacing returns px strings (template literal) (`spacing-px-template`) | rules | Expected | Expected |
| ExpansionPanel renamed Accordion (`expansion-panel`) | rules | Expected | Expected |
| Link underline default changed from hover to always (`link-underline`) | rules | Expected | Expected |
| TextField default variant changed from standard to outlined (`textfield-default-variant`) | rules | Expected | Expected |
| breakpoints.down(key) is now exclusive (`breakpoint-down`) | rules | Expected | Expected |
| Box system props moved to sx (`box-system-props`) | rules | Expected | Expected |
| Autocomplete renderOption must return the whole option (`autocomplete-render-option`) | agent | Expected | Expected |
| theme.spacing() used in arithmetic (`spacing-arithmetic`) | agent | Expected | Expected |
| Dialog disableBackdropClick removed (`dialog-disable-backdrop-click`) | agent | Expected | Expected |
| Typography srOnly variant removed (`typography-sr-only`) | agent | Expected | Expected |
| Default breakpoint values changed (md 960 -> 900) (`breakpoint-sizes`) | agent | Expected | Expected |
| Button color "default" passed as an expression (`button-color-expression`) | agent | Expected | Expected |
| Button label slot removed; theme override on MuiButton.label is dead (`button-label-override`) | agent | Expected | Expected |
| Select onChange event type is SelectChangeEvent (`select-event-type`) | agent | Expected | Expected |
| @mui/styles makeStyles has no default theme (`styles-needs-theme-provider`) | human | Other layer | Other layer |
| Switch default colour changed from secondary to primary (`switch-default-color`) | visual-only | Not scored | Not scored |

Over all runs: 40 Expected, 2 Not scored, 2 Other layer.

Source: `experiment-summary.json` (this file is rendered from it).
