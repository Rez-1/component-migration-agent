# Experiment summary: haiku-debug vs baseline · dev split

1 case (fixture-mui4) × 1 run · configuration `haiku-debug` (b46cc8b4c918) · experiment `dev/v1` · total $0.03

**Migrated without a human: 75% (runs: 75%) vs 25% baseline. Clean runs: 1 of 1 vs 0 of 2.** Cost per clean run: $0.03 (cost per run: $0.03).

| Metric | haiku-debug (runs) | Mean | baseline (mean) | Change |
|---|---|---|---|---|
| Clean runs | yes | 1 of 1 | 0 of 2 | +1 |
| Migrated without a human | 75% | 75% | 25% | +50 pts |
| Hand-offs | 3 | 3 | 0 | +3 |
| Regressions | 0 | 0 | 0 | 0 |
| Cheating-check hits | 0 | 0 | 0 | 0 |
| Cheating-check warnings | 0 | 0 | 0 | 0 |
| Repair traps expected (of 8) | 5 | 5 | 0 | +5 |
| Codemod TODOs left | 0 | 0 | 0 | 0 |
| Failures (final verify) | 8 | 8 | 15 | -7 |
| Cost per run | $0.03 | $0.03 | $0 | +$0.03 |

One run, so there is no spread yet (the brief asks for 2 runs per case).

## Traps across runs

| Trap | Expected layer | Run 1 |
|---|---|---|
| createMuiTheme renamed createTheme (`create-theme`) | rules | Expected |
| Grid justify renamed justifyContent (`grid-justify`) | rules | Expected |
| fade renamed alpha (`fade-alpha`) | rules | Expected |
| Autocomplete moved from lab to core (`autocomplete-import`) | rules | Expected |
| getOptionSelected renamed isOptionEqualToValue (`autocomplete-option-equal`) | rules | Expected |
| Button color="default" removed (literal) (`button-color-default-literal`) | rules | Expected |
| theme.spacing returns px strings (template literal) (`spacing-px-template`) | rules | Expected |
| ExpansionPanel renamed Accordion (`expansion-panel`) | rules | Expected |
| Link underline default changed from hover to always (`link-underline`) | rules | Expected |
| TextField default variant changed from standard to outlined (`textfield-default-variant`) | rules | Expected |
| breakpoints.down(key) is now exclusive (`breakpoint-down`) | rules | Expected |
| Box system props moved to sx (`box-system-props`) | rules | Expected |
| Autocomplete renderOption must return the whole option (`autocomplete-render-option`) | agent | Missed |
| theme.spacing() used in arithmetic (`spacing-arithmetic`) | agent | Expected |
| Dialog disableBackdropClick removed (`dialog-disable-backdrop-click`) | agent | Expected |
| Typography srOnly variant removed (`typography-sr-only`) | agent | Expected |
| Default breakpoint values changed (md 960 -> 900) (`breakpoint-sizes`) | agent | Expected |
| Button color "default" passed as an expression (`button-color-expression`) | agent | Missed |
| Button label slot removed; theme override on MuiButton.label is dead (`button-label-override`) | agent | Missed |
| Select onChange event type is SelectChangeEvent (`select-event-type`) | agent | Expected |
| @mui/styles makeStyles has no default theme (`styles-needs-theme-provider`) | human | Expected |
| Switch default colour changed from secondary to primary (`switch-default-color`) | visual-only | Not scored |

Over all runs: 18 Expected, 3 Missed, 1 Not scored.

Source: `experiment-summary.json` (this file is rendered from it).
