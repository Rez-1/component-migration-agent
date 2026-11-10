# Usage report: mui4-fixture-app

`mui@4->mui@5` · 26 files scanned

**12 affected files, 186 usages of `@material-ui/*`, 0 of the new library.** The official codemods are expected to handle 129 of the 186 usages (69%). 57 usages in 11 files touch breaking changes the guide doesn't mark as codemod-handled, so expect repair work there.

> The split is a forecast from the guide's ✅ markers: a JSX element or call is counted for repair when its symbol has any unmarked breaking change, whether or not the file uses the changed prop. Import statements count as codemod-handled.

## By team

| Team | Affected files | Usages | Expected repair |
|---|---|---|---|
| @team-platform | 5 | 72 | 17 usages in 4 files |
| @team-insights | 2 | 45 | 14 usages in 2 files |
| @team-accounts | 3 | 44 | 15 usages in 3 files |
| @team-discovery | 2 | 25 | 11 usages in 2 files |

## Most-used symbols

| Symbol | Module | Usages | Files | Guide says |
|---|---|---|---|---|
| Typography | @material-ui/core | 32 | 9 | Remove srOnly variant; Remove color and style override keys |
| Button | @material-ui/core | 12 | 5 | ✅ Remove default color prop; Remove span and label |
| makeStyles | @material-ui/core/styles | 12 | 6 | ✅ Update makeStyles import |
| TextField | @material-ui/core | 8 | 4 | ✅ Update default variant; ✅ Rename rowsMax; ✅ Replace rows with minRows; Forward ref instead of inputRef prop; Rename marginDense and inputMarginDense classes; Update InputAdornment position prop |
| TableCell | @material-ui/core | 7 | 1 | — |
| Paper | @material-ui/core | 6 | 3 | Change dark mode background opacity |
| Theme | @material-ui/core/styles | 6 | 6 | Default background colors; ✅ Breakpoint behavior; Breakpoint sizes; ✅ Replace theme.breakpoints.width; Update theme.palette.augmentColor helper; Remove theme.typography.round helper |
| Grid | @material-ui/core | 4 | 1 | ✅ Rename justify prop; ✅ Remove align and justify props and classes; Change negative margins |
| List | @material-ui/core | 4 | 2 | — |
| ListItem | @material-ui/core | 4 | 2 | — |

(top 10 of 53 symbols; full list in `usage-report.json`)

## Files

| File | Team | Usages | Expected repair |
|---|---|---|---|
| src/screens/ResponsiveNav.tsx | @team-platform | 29 | appbar/fix-z-index-issues, appbar/replace-color-prop-for-dark-mode, iconbutton/remove-span-and-label (+7) |
| src/screens/Settings.tsx | @team-accounts | 15 | box/remove-clone-prop, box/replace-render-prop-with-sx, button/remove-span-and-label (+7) |
| src/screens/ProfileForm.tsx | @team-platform | 16 | button/remove-span-and-label, select/remove-selectmenu-slot, select/replace-labelwidth-prop (+6) |
| src/screens/Search.tsx | @team-discovery | 10 | autocomplete/remove-debug-prop, autocomplete/rename-reason-arguments, autocomplete/update-renderoption (+5) |
| src/screens/UsersTable.tsx | @team-insights | 28 | button/remove-span-and-label, table/rename-default-padding-prop-value, textfield/forward-ref-instead-of-inputref-prop (+4) |
| src/screens/Faq.tsx | @team-discovery | 15 | expansionpanel/update-event-type-typescript, expansionpaneldetails/remove-display-flex, expansionpanelsummary/remove-iconbuttonprops-prop (+3) |
| src/screens/AccountDialog.tsx | @team-accounts | 16 | button/remove-span-and-label, dialog/remove-withmobiledialog-component, textfield/forward-ref-instead-of-inputref-prop (+2) |
| src/screens/Dashboard.tsx | @team-insights | 17 | grid/change-negative-margins, paper/change-dark-mode-background-opacity, typography/remove-color-and-style-override-keys (+1) |
| src/screens/Notifications.tsx | @team-platform | 21 | button/remove-span-and-label, paper/change-dark-mode-background-opacity, typography/remove-color-and-style-override-keys (+1) |
| src/App.tsx | @team-platform | 4 | cssbaseline/update-body-font-size, cssbaseline/update-styled-engine, @mui-styles/update-themeprovider-import |
| src/screens/ProfileCard.tsx | @team-accounts | 13 | typography/remove-color-and-style-override-keys, typography/remove-sronly-variant |
| src/theme.ts | @team-platform | 2 | — |
