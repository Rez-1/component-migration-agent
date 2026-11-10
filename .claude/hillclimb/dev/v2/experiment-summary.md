# Experiment summary: baseline · dev split

2026-11-09 · 2 cases (fixture-mui4, fixture-mui4-hard) × 2 runs · configuration `baseline` (73a3262d088d) · experiment `dev/v2` · total $0

**Migrated without a human: 29% (runs: 17% to 42%). Clean runs: 0 of 4.** Cost per clean run: — (no clean runs) (cost per run: $0).

| Metric | baseline (runs) | Mean |
|---|---|---|
| Clean runs | no to no | 0 of 4 |
| Migrated without a human | 17% to 42% | 29% |
| Hand-offs | 0 to 0 | 0 |
| Regressions | 0 to 0 | 0 |
| Cheating-check hits | 0 to 0 | 0 |
| Cheating-check warnings | 0 to 0 | 0 |
| Repair traps expected | 0 to 0 | 0 |
| Codemod TODOs left | 0 to 0 | 0 |
| Failures (final verify) | 13 to 16 | 14.5 |
| Cost per run | $0 to $0 | $0 |
| Time per run | 0:54 to 1:05 | 0:59 |

The spread is the range over the runs (min to max), not a standard deviation.

## Traps across runs

| Case | Trap | Expected layer | Run 1 | Run 2 |
|---|---|---|---|---|
| fixture-mui4 | createMuiTheme renamed createTheme (`create-theme`) | rules | Expected | Expected |
| fixture-mui4 | Grid justify renamed justifyContent (`grid-justify`) | rules | Expected | Expected |
| fixture-mui4 | fade renamed alpha (`fade-alpha`) | rules | Expected | Expected |
| fixture-mui4 | Autocomplete moved from lab to core (`autocomplete-import`) | rules | Expected | Expected |
| fixture-mui4 | getOptionSelected renamed isOptionEqualToValue (`autocomplete-option-equal`) | rules | Expected | Expected |
| fixture-mui4 | Button color="default" removed (literal) (`button-color-default-literal`) | rules | Expected | Expected |
| fixture-mui4 | theme.spacing returns px strings (template literal) (`spacing-px-template`) | rules | Expected | Expected |
| fixture-mui4 | ExpansionPanel renamed Accordion (`expansion-panel`) | rules | Expected | Expected |
| fixture-mui4 | Link underline default changed from hover to always (`link-underline`) | rules | Expected | Expected |
| fixture-mui4 | TextField default variant changed from standard to outlined (`textfield-default-variant`) | rules | Expected | Expected |
| fixture-mui4 | breakpoints.down(key) is now exclusive (`breakpoint-down`) | rules | Expected | Expected |
| fixture-mui4 | Box system props moved to sx (`box-system-props`) | rules | Expected | Expected |
| fixture-mui4 | Autocomplete renderOption must return the whole option (`autocomplete-render-option`) | agent | Missed | Missed |
| fixture-mui4 | theme.spacing() used in arithmetic (`spacing-arithmetic`) | agent | Missed | Missed |
| fixture-mui4 | Dialog disableBackdropClick removed (`dialog-disable-backdrop-click`) | agent | Missed | Missed |
| fixture-mui4 | Typography srOnly variant removed (`typography-sr-only`) | agent | Missed | Missed |
| fixture-mui4 | Default breakpoint values changed (md 960 -> 900) (`breakpoint-sizes`) | agent | Missed | Missed |
| fixture-mui4 | Button color "default" passed as an expression (`button-color-expression`) | agent | Missed | Missed |
| fixture-mui4 | Button label slot removed; theme override on MuiButton.label is dead (`button-label-override`) | agent | Missed | Missed |
| fixture-mui4 | Select onChange event type is SelectChangeEvent (`select-event-type`) | agent | Missed | Missed |
| fixture-mui4 | @mui/styles makeStyles has no default theme (`styles-needs-theme-provider`) | agent | Missed | Missed |
| fixture-mui4 | Accordion markup changed; the question header snapshot must be re-recorded (`faq-snapshot-markup`) | human | Missed | Missed |
| fixture-mui4 | Switch default colour changed from secondary to primary (`switch-default-color`) | visual-only | Not scored | Not scored |
| fixture-mui4-hard | createMuiTheme renamed createTheme (`create-theme`) | rules | Expected | Expected |
| fixture-mui4-hard | Pagination (and ToggleButtonGroup) moved from lab to core (`pagination-import`) | rules | Expected | Expected |
| fixture-mui4-hard | Pagination shape "round" renamed "circular" (`pagination-round`) | rules | Expected | Expected |
| fixture-mui4-hard | Skeleton moved from lab, variant "rect" renamed "rectangular" (`skeleton-rect`) | rules | Expected | Expected |
| fixture-mui4-hard | Dialog onEntered moved into TransitionProps (literal prop) (`dialog-transition-literal`) | rules | Expected | Expected |
| fixture-mui4-hard | getOptionSelected renamed isOptionEqualToValue (literal prop) (`autocomplete-option-equal-literal`) | rules | Expected | Expected |
| fixture-mui4-hard | Theme override uses the JSS state reference &$selected, dead under Emotion (`theme-state-selector`) | agent | Missed | Missed |
| fixture-mui4-hard | Autocomplete onChange reasons renamed (select-option -> selectOption) (`autocomplete-reason-names`) | agent | Missed | Missed |
| fixture-mui4-hard | Dialog onEntered passed through a helper's spread, which the codemod can't see (`dialog-transition-spread`) | agent | Missed | Missed |
| fixture-mui4-hard | getOptionSelected in a shared props object, which the codemod can't see (`option-equal-spread`) | agent | Missed | Missed |
| fixture-mui4-hard | Custom inputComponent must forward ref; inputRef is no longer passed (`input-component-ref`) | agent | Missed | Missed |
| fixture-mui4-hard | RootRef removed; the codemod's fragment drops the ref (`root-ref-removed`) | agent | Missed | Missed |
| fixture-mui4-hard | Slider onChange event is a native Event (shared wrapper's prop type) (`slider-event-type`) | agent | Missed | Missed |
| fixture-mui4-hard | TablePagination back/nextIconButtonText removed; use getItemAriaLabel (`table-pagination-labels`) | agent | Missed | Missed |
| fixture-mui4-hard | Chip variant "default" renamed "filled", behind a withStyles wrapper (`chip-variant-wrapped`) | agent | Missed | Missed |

Over all runs: 36 Expected, 38 Missed, 2 Not scored.

Scorecards: `v2/runs/fixture-mui4_rep0/scorecard.json`, `v2/runs/fixture-mui4_rep1/scorecard.json`, `v2/runs/fixture-mui4-hard_rep0/scorecard.json`, `v2/runs/fixture-mui4-hard_rep1/scorecard.json`.
