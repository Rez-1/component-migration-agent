# Usage report: mui4-tracker-app

`mui@4->mui@5` · 24 files scanned

**12 affected files, 157 usages of `@material-ui/*`, 0 of the new library.** The official codemods are expected to handle 116 of the 157 usages (74%). 41 usages in 9 files touch breaking changes the guide doesn't mark as codemod-handled, so expect repair work there.

> The split is a forecast from the guide's ✅ markers: a JSX element or call is counted for repair when its symbol has any unmarked breaking change, whether or not the file uses the changed prop. Import statements count as codemod-handled.

## By team

| Team | Affected files | Usages | Expected repair |
|---|---|---|---|
| @team-issues | 5 | 84 | 24 usages in 4 files |
| @team-planning | 3 | 39 | 10 usages in 3 files |
| @team-collab | 1 | 21 | 4 usages in 1 file |
| @team-platform | 3 | 13 | 3 usages in 1 file |

## Most-used symbols

| Symbol | Module | Usages | Files | Guide says |
|---|---|---|---|---|
| Typography | @material-ui/core | 14 | 6 | Remove srOnly variant; Remove color and style override keys |
| Button | @material-ui/core | 13 | 4 | ✅ Remove default color prop; Remove span and label |
| makeStyles | @material-ui/core/styles | 12 | 6 | ✅ Update makeStyles import |
| TextField | @material-ui/core | 11 | 4 | ✅ Update default variant; ✅ Rename rowsMax; ✅ Replace rows with minRows; Forward ref instead of inputRef prop; Rename marginDense and inputMarginDense classes; Update InputAdornment position prop |
| TableCell | @material-ui/core | 8 | 1 | — |
| Theme | @material-ui/core/styles | 6 | 6 | Default background colors; ✅ Breakpoint behavior; Breakpoint sizes; ✅ Replace theme.breakpoints.width; Update theme.palette.augmentColor helper; Remove theme.typography.round helper |
| Autocomplete | @material-ui/lab | 5 | 2 | ✅ Update import; Remove debug prop; Update renderOption; ✅ Rename closeIcon to clearIcon; Rename reason arguments; ✅ Rename getOptionSelected |
| Dialog | @material-ui/core | 4 | 2 | ✅ Update transition props; ✅ Remove disableBackdropClick prop; Remove withMobileDialog component; ✅ Remove disableTypography prop |
| DialogActions | @material-ui/core | 4 | 2 | — |
| DialogContent | @material-ui/core | 4 | 2 | — |

(top 10 of 42 symbols; full list in `usage-report.json`)

## Files

| File | Team | Usages | Expected repair |
|---|---|---|---|
| src/screens/IssueDetail.tsx | @team-issues | 24 | button/remove-span-and-label, dialog/remove-withmobiledialog-component, paper/change-dark-mode-background-opacity (+6) |
| src/screens/NewIssueDialog.tsx | @team-issues | 23 | autocomplete/remove-debug-prop, autocomplete/rename-reason-arguments, autocomplete/update-renderoption (+5) |
| src/screens/Activity.tsx | @team-collab | 21 | button/remove-span-and-label, rootref/remove-component, textfield/forward-ref-instead-of-inputref-prop (+4) |
| src/components/LabelPicker.tsx | @team-issues | 6 | autocomplete/remove-debug-prop, autocomplete/rename-reason-arguments, autocomplete/update-renderoption (+3) |
| src/screens/Board.tsx | @team-planning | 16 | tab/remove-span-and-wrapper, tab/update-default-minwidth-and-maxwidth, tabs/update-default-indicatorcolor-and-textcolor-prop-values (+3) |
| src/screens/IssueList.tsx | @team-issues | 30 | table/rename-default-padding-prop-value, tablepagination/customize-labels-with-getitemarialabel-prop, tablepagination/move-custom-class-on-input-to-select (+3) |
| src/components/RangeSlider.tsx | @team-planning | 4 | slider/refactor-css, slider/replace-valuelabelcomponent-and-thumbcomponent-props, slider/update-event-type-typescript (+2) |
| src/App.tsx | @team-platform | 8 | button/remove-span-and-label, cssbaseline/update-body-font-size, cssbaseline/update-styled-engine (+1) |
| src/screens/Reports.tsx | @team-planning | 19 | togglebutton/remove-span-and-label, typography/remove-color-and-style-override-keys, typography/remove-sronly-variant |
| src/components/DurationInput.tsx | @team-issues | 1 | — |
| src/components/StatusChip.tsx | @team-platform | 3 | — |
| src/theme.ts | @team-platform | 2 | — |
