# Experiment summary: baseline · dev split

1 case (fixture-mui4) × 2 runs · configuration `baseline` (73a3262d088d) · experiment `dev/baseline` · total $0

**Migrated without a human: 25% (runs: 25% / 25%). Clean runs: 0 of 2.** Cost per clean run: — (no clean runs) (cost per run: $0).

| Metric | baseline (run 1 / run 2) | Mean |
|---|---|---|
| Clean runs | no / no | 0 of 2 |
| Migrated without a human | 25% / 25% | 25% |
| Hand-offs | 0 / 0 | 0 |
| Regressions | 0 / 0 | 0 |
| Cheating-check hits | 0 / 0 | 0 |
| Cheating-check warnings | 0 / 0 | 0 |
| Repair traps expected (of 8) | 0 / 0 | 0 |
| Codemod TODOs left | 0 / 0 | 0 |
| Failures (final verify) | 15 / 15 | 15 |
| Cost per run | $0 / $0 | $0 |

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
| Autocomplete renderOption must return the whole option (`autocomplete-render-option`) | agent | Missed | Missed |
| theme.spacing() used in arithmetic (`spacing-arithmetic`) | agent | Missed | Missed |
| Dialog disableBackdropClick removed (`dialog-disable-backdrop-click`) | agent | Missed | Missed |
| Typography srOnly variant removed (`typography-sr-only`) | agent | Missed | Missed |
| Default breakpoint values changed (md 960 -> 900) (`breakpoint-sizes`) | agent | Missed | Missed |
| Button color "default" passed as an expression (`button-color-expression`) | agent | Missed | Missed |
| Button label slot removed; theme override on MuiButton.label is dead (`button-label-override`) | agent | Missed | Missed |
| Select onChange event type is SelectChangeEvent (`select-event-type`) | agent | Missed | Missed |
| @mui/styles makeStyles has no default theme (`styles-needs-theme-provider`) | human | Missed | Missed |
| Switch default colour changed from secondary to primary (`switch-default-color`) | visual-only | Not scored | Not scored |

Over all runs: 24 Expected, 18 Missed, 2 Not scored.

Source: `experiment-summary.json` (this file is rendered from it).
