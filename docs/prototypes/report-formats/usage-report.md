# Usage report: mui4-fixture-app

> PROTOTYPE. Mock numbers for the fixture, to react to. Not real output.

`mui@4 → mui@5` · commit `3f9c2e1` · scanned 2026-11-09 14:02 · 31 files scanned

**12 affected files, 87 usages of `@material-ui/*`, 0 of `@mui/*`.** The official codemods are expected to handle 62 of the 87 usages (71%). 25 usages in 8 files touch breaking changes the guide doesn't mark as codemod-handled, so expect repair work there.

## By team

| Team | Affected files | Usages | Expected repair |
|---|---|---|---|
| @team-accounts | 3 | 27 | 11 usages in 3 files |
| @team-insights | 2 | 19 | 6 usages in 2 files |
| @team-discovery | 2 | 16 | 5 usages in 1 file |
| @team-platform | 5 | 25 | 3 usages in 2 files |

## Most-used symbols

| Symbol | Module | Usages | Files | Guide says |
|---|---|---|---|---|
| makeStyles | @material-ui/core/styles | 9 | 8 | Moves to @mui/styles ✅; needs a ThemeProvider (not codemod-handled) |
| Typography | @material-ui/core | 14 | 9 | `srOnly` variant removed |
| Button | @material-ui/core | 8 | 4 | ✅ `color="default"` removed (literal values only) |
| Grid | @material-ui/core | 6 | 2 | ✅ `justify` → `justifyContent` |
| Autocomplete | @material-ui/lab | 2 | 1 | ✅ moved to core; `renderOption` signature changed |
| createMuiTheme | @material-ui/core/styles | 1 | 1 | ✅ renamed `createTheme` |

(top 6 of 34 symbols; full list in `usage-report.json`)

## Files

| File | Team | Usages | Expected repair |
|---|---|---|---|
| src/screens/AccountDialog.tsx | @team-accounts | 11 | `disableBackdropClick` removed |
| src/screens/Settings.tsx | @team-accounts | 9 | Button `color` as an expression |
| src/screens/Search.tsx | @team-discovery | 9 | Autocomplete `renderOption` |
| src/screens/Dashboard.tsx | @team-insights | 10 | `theme.spacing()` arithmetic |
| src/theme.ts | @team-platform | 6 | `MuiButton.label` override; breakpoint values |
| … 7 more | | | |
