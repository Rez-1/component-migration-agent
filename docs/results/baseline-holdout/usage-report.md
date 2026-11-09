# Usage report: warehouse-back-office

`mui@4->mui@5` · 20 files scanned

**9 affected files, 132 usages of `@material-ui/*`, 0 of the new library.** The official codemods are expected to handle 91 of the 132 usages (69%). 41 usages in 8 files touch breaking changes the guide doesn't mark as codemod-handled, so expect repair work there.

> The split is a forecast from the guide's ✅ markers: a JSX element or call is counted for repair when its symbol has any unmarked breaking change, whether or not the file uses the changed prop. Import statements count as codemod-handled.

## By team

| Team | Affected files | Usages | Expected repair |
|---|---|---|---|
| @team-fulfilment | 3 | 61 | 13 usages in 3 files |
| @team-stock | 2 | 32 | 11 usages in 2 files |
| @team-customer-care | 1 | 16 | 7 usages in 1 file |
| @team-ops-platform | 2 | 16 | 6 usages in 1 file |
| @team-catalogue | 1 | 7 | 4 usages in 1 file |

## Most-used symbols

| Symbol | Module | Usages | Files | Guide says |
|---|---|---|---|---|
| Typography | @material-ui/core | 22 | 8 | Remove srOnly variant; Remove color and style override keys |
| Paper | @material-ui/core | 11 | 5 | Change dark mode background opacity |
| TableCell | @material-ui/core | 11 | 1 | — |
| makeStyles | @material-ui/core/styles | 6 | 3 | ✅ Update makeStyles import |
| TextField | @material-ui/core | 5 | 2 | ✅ Update default variant; ✅ Rename rowsMax; ✅ Replace rows with minRows; Forward ref instead of inputRef prop; Rename marginDense and inputMarginDense classes; Update InputAdornment position prop |
| Button | @material-ui/core | 4 | 2 | ✅ Remove default color prop; Remove span and label |
| Grid | @material-ui/core | 4 | 1 | ✅ Rename justify prop; ✅ Remove align and justify props and classes; Change negative margins |
| TableRow | @material-ui/core | 4 | 1 | — |
| Theme | @material-ui/core/styles | 3 | 3 | Default background colors; ✅ Breakpoint behavior; Breakpoint sizes; ✅ Replace theme.breakpoints.width; Update theme.palette.augmentColor helper; Remove theme.typography.round helper |
| AppBar | @material-ui/core | 2 | 1 | Fix z-index issues; Replace color prop for dark mode |

(top 10 of 40 symbols; full list in `usage-report.json`)

## Files

| File | Team | Usages | Expected repair |
|---|---|---|---|
| src/App.tsx | @team-ops-platform | 14 | appbar/fix-z-index-issues, appbar/replace-color-prop-for-dark-mode, cssbaseline/update-body-font-size (+8) |
| src/screens/ReturnForm.tsx | @team-customer-care | 16 | button/remove-span-and-label, checkbox/set-to-primary-by-default, checkbox/update-css-class-names (+7) |
| src/screens/ProductTags.tsx | @team-catalogue | 7 | autocomplete/remove-debug-prop, autocomplete/rename-reason-arguments, autocomplete/update-renderoption (+5) |
| src/screens/OrdersTable.tsx | @team-fulfilment | 33 | paper/change-dark-mode-background-opacity, table/rename-default-padding-prop-value, tablepagination/customize-labels-with-getitemarialabel-prop (+4) |
| src/screens/ShipmentTracker.tsx | @team-fulfilment | 11 | paper/change-dark-mode-background-opacity, stepper/remove-built-in-padding, stepper/update-component-structure (+2) |
| src/screens/OrderDialog.tsx | @team-fulfilment | 17 | button/remove-span-and-label, dialog/remove-withmobiledialog-component, typography/remove-color-and-style-override-keys (+1) |
| src/screens/StockSummary.tsx | @team-stock | 17 | grid/change-negative-margins, paper/change-dark-mode-background-opacity, typography/remove-color-and-style-override-keys (+1) |
| src/screens/Inventory.tsx | @team-stock | 15 | paper/change-dark-mode-background-opacity, typography/remove-color-and-style-override-keys, typography/remove-sronly-variant |
| src/theme.ts | @team-ops-platform | 2 | — |
