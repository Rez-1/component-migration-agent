# Experiment summary: opus-low-context vs baseline · dev split

2026-11-10 · 2 cases (fixture-mui4, fixture-mui4-hard) × 2 runs · configuration `opus-low-context` (672db259cecb) · experiment `dev/v7` · total $0.84

**Migrated without a human: 94% (runs: 92% to 100%) vs 29% baseline. Clean runs: 3 of 4 vs 0 of 4.** Cost per clean run: $0.28 (cost per run: $0.21).

| Metric | opus-low-context (runs) | Mean | baseline (mean) | Change |
|---|---|---|---|---|
| Clean runs | no to yes | 3 of 4 | 0 of 4 | +3 |
| Migrated without a human | 92% to 100% | 94% | 29% | +65 pts |
| Hand-offs | 0 to 1 | 0.5 | 0 | +0.5 |
| Regressions | 0 to 0 | 0 | 0 | 0 |
| Cheating-check hits | 0 to 0 | 0 | 0 | 0 |
| Cheating-check warnings | 0 to 0 | 0 | 0 | 0 |
| Repair traps expected | 7 to 9 | 8.5 | 0 | +8.5 |
| Codemod TODOs left | 0 to 0 | 0 | 0 | 0 |
| Failures (final verify) | 0 to 2 | 1 | 14.5 | -13.5 |
| Cost per run | $0.10 to $0.25 | $0.21 | $0 | +$0.21 |
| Time per run | 3:58 to 5:36 | 4:53 | 0:59 | |

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
| fixture-mui4 | Autocomplete renderOption must return the whole option (`autocomplete-render-option`) | agent | Expected | Expected |
| fixture-mui4 | theme.spacing() used in arithmetic (`spacing-arithmetic`) | agent | Expected | Expected |
| fixture-mui4 | Dialog disableBackdropClick removed (`dialog-disable-backdrop-click`) | agent | Expected | Expected |
| fixture-mui4 | Typography srOnly variant removed (`typography-sr-only`) | agent | Expected | Expected |
| fixture-mui4 | Default breakpoint values changed (md 960 -> 900) (`breakpoint-sizes`) | agent | Expected | Expected |
| fixture-mui4 | Button color "default" passed as an expression (`button-color-expression`) | agent | Expected | Expected |
| fixture-mui4 | Button label slot removed; theme override on MuiButton.label is dead (`button-label-override`) | agent | Expected | Expected |
| fixture-mui4 | Select onChange event type is SelectChangeEvent (`select-event-type`) | agent | Expected | Expected |
| fixture-mui4 | @mui/styles makeStyles has no default theme (`styles-needs-theme-provider`) | agent | Expected | Expected |
| fixture-mui4 | Accordion markup changed; the question header snapshot must be re-recorded (`faq-snapshot-markup`) | human | Expected | Expected |
| fixture-mui4 | Switch default colour changed from secondary to primary (`switch-default-color`) | visual-only | Not scored | Not scored |
| fixture-mui4-hard | createMuiTheme renamed createTheme (`create-theme`) | rules | Expected | Expected |
| fixture-mui4-hard | Pagination (and ToggleButtonGroup) moved from lab to core (`pagination-import`) | rules | Expected | Expected |
| fixture-mui4-hard | Pagination shape "round" renamed "circular" (`pagination-round`) | rules | Expected | Expected |
| fixture-mui4-hard | Skeleton moved from lab, variant "rect" renamed "rectangular" (`skeleton-rect`) | rules | Expected | Expected |
| fixture-mui4-hard | Dialog onEntered moved into TransitionProps (literal prop) (`dialog-transition-literal`) | rules | Expected | Expected |
| fixture-mui4-hard | getOptionSelected renamed isOptionEqualToValue (literal prop) (`autocomplete-option-equal-literal`) | rules | Expected | Expected |
| fixture-mui4-hard | Theme override uses the JSS state reference &$selected, dead under Emotion (`theme-state-selector`) | agent | Expected | Expected |
| fixture-mui4-hard | Autocomplete onChange reasons renamed (select-option -> selectOption) (`autocomplete-reason-names`) | agent | Expected | Expected |
| fixture-mui4-hard | Dialog onEntered passed through a helper's spread, which the codemod can't see (`dialog-transition-spread`) | agent | Expected | Expected |
| fixture-mui4-hard | getOptionSelected in a shared props object, which the codemod can't see (`option-equal-spread`) | agent | Expected | Missed |
| fixture-mui4-hard | Custom inputComponent must forward ref; inputRef is no longer passed (`input-component-ref`) | agent | Expected | Missed |
| fixture-mui4-hard | RootRef removed; the codemod's fragment drops the ref (`root-ref-removed`) | agent | Expected | Expected |
| fixture-mui4-hard | Slider onChange event is a native Event (shared wrapper's prop type) (`slider-event-type`) | agent | Expected | Expected |
| fixture-mui4-hard | TablePagination back/nextIconButtonText removed; use getItemAriaLabel (`table-pagination-labels`) | agent | Expected | Expected |
| fixture-mui4-hard | Chip variant "default" renamed "filled", behind a withStyles wrapper (`chip-variant-wrapped`) | agent | Expected | Expected |

Over all runs: 72 Expected, 2 Missed, 2 Not scored.

Scorecards: `v7/runs/fixture-mui4_rep0/scorecard.json`, `v7/runs/fixture-mui4_rep1/scorecard.json`, `v7/runs/fixture-mui4-hard_rep0/scorecard.json`, `v7/runs/fixture-mui4-hard_rep1/scorecard.json`.
