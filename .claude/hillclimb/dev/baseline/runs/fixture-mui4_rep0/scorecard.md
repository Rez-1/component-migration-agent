# Scorecard: mui4-fixture-app · run 2026-11-09-205947-821

`mui@4->mui@5` · configuration `baseline` · case `fixture-mui4` · 27 s · $0 (no LLM) of $5.00 cap

**Clean run: no. Final verify found 16 failures in 10 files.** **2 of 12 affected files migrated without a human (17%)**: 2 by rules, 0 by the repair agent. 0 handed off, 10 unmigrated.

| | This run |
|---|---|
| Clean run | no (16 failures in 10 files) |
| Migrated without a human | 2 / 12 (17%) |
| Hand-offs | 0 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps | 12 expected · 0 other layer · 10 missed · 1 not scored |
| Cost / time | $0 · 27 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/screens/AccountDialog.tsx | Unmigrated | 1 | 1 test |
| src/screens/Dashboard.tsx | Unmigrated | 2 | 2 typecheck |
| src/screens/Faq.tsx | Unmigrated | 1 | 1 test |
| src/screens/Notifications.tsx | Unmigrated | 1 | 1 typecheck |
| src/screens/ProfileCard.tsx | Unmigrated | 1 | 1 test |
| src/screens/ProfileForm.tsx | Unmigrated | 1 | 1 typecheck |
| src/screens/ResponsiveNav.tsx | Unmigrated | 1 | 1 test |
| src/screens/Search.tsx | Unmigrated | 4 | 2 test, 2 typecheck |
| src/screens/Settings.tsx | Unmigrated | 3 | 2 test, 1 typecheck |
| src/theme.ts | Unmigrated | 1 | 1 typecheck |
| 2 files | Migrated by rules | 0 | App, UsersTable |

Changed but not affected: `package-lock.json`, `package.json`.

## Failures

| File | Check | Where | Message |
|---|---|---|---|
| src/screens/AccountDialog.tsx | test | AccountDialog › stays open, keeping what was typed, when the user clicks outside it | TestingLibraryElementError: Unable to find an accessible element with the role "dialog" and name "Delete your account?" |
| src/screens/Dashboard.tsx | typecheck TS2362 | line 12 | The left-hand side of an arithmetic operation must be of type 'any', 'number', 'bigint' or an enum type. |
| src/screens/Dashboard.tsx | typecheck TS2322 | line 22 | Type 'string' is not assignable to type 'number'. |
| src/screens/Faq.tsx | test | Faq › renders a question header with its expand icon | Error: expect(received).toMatchSnapshot() |
| src/screens/Notifications.tsx | typecheck TS2769 | line 39 | No overload matches this call. Overload 1 of 2, '(props: { component: "span"; } & TypographyOwnProps & CommonProps & Omit<Omit<DetailedHT… |
| src/screens/ProfileCard.tsx | test | ProfileCard › shows the name, role, email and initials | TypeError: theme.spacing is not a function |
| src/screens/ProfileForm.tsx | typecheck TS2322 | line 64 | Type '(event: React.ChangeEvent<{    name?: string;    value: unknown;}>) => void' is not assignable to type '(event: SelectChangeEvent<"… |
| src/screens/ResponsiveNav.tsx | test | ResponsiveNav › uses a menu on a small tablet (920px wide) | Error: Unable to find role="button" and name "Open menu" |
| src/screens/Search.tsx | test | Search › suggests matching cities with their country | TestingLibraryElementError: Unable to find an accessible element with the role "option" |
| src/screens/Search.tsx | test | Search › selects Amsterdam | TestingLibraryElementError: Unable to find an accessible element with the role "option" and name `/Amsterdam/` |
| src/screens/Search.tsx | typecheck TS2339 | line 42 | Property 'label' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'. |
| src/screens/Search.tsx | typecheck TS2339 | line 43 | Property 'country' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'. |
| src/screens/Settings.tsx | test | Settings › enables Save only after a change, and saves the new preferences | TypeError: Cannot read properties of undefined (reading 'dark') |
| src/screens/Settings.tsx | test | Settings › shows button text in sentence case, as the theme asks | TypeError: Cannot read properties of undefined (reading 'dark') |
| src/screens/Settings.tsx | typecheck TS2769 | line 61 | No overload matches this call. Overload 1 of 3, '(props: { href: string; } & ButtonOwnProps & Omit<ButtonBaseOwnProps, "classes"> & Commo… |
| src/theme.ts | typecheck TS2322 | line 16 | Type '{ label: { textTransform: string; }; }' is not assignable to type 'Partial<OverridesStyleRules<keyof ButtonClasses, "MuiButton", un… |

## Traps (fixture)

| Result | Expected layer | Traps |
|---|---|---|
| Expected | rules | 12: create-theme, grid-justify, fade-alpha, autocomplete-import, autocomplete-option-equal, button-color-default-literal, spacing-px-template, expansion-panel, link-underline, textfield-default-variant, breakpoint-down, box-system-props |
| Missed | agent | 9: autocomplete-render-option, spacing-arithmetic, dialog-disable-backdrop-click, typography-sr-only, breakpoint-sizes, button-color-expression, button-label-override, select-event-type, styles-needs-theme-provider |
| Missed | human | 1: faq-snapshot-markup |
| Not scored | visual-only | 1: switch-default-color |

Every agent and human trap's check still fails at the final verify.

## Cheating checks

No hits and no warnings on repair-agent patches.

Reported, not failing (only repair-agent patches can fail a run):

| File | Layer | Check | Detail |
|---|---|---|---|
| src/App.tsx | rules | escape-hatch:eslint-disable | an `eslint-disable` comment: 0 -> 1 |

14 test files checked.

## Rule steps

| # | Step | Status | Changed | Detail |
|---|---|---|---|---|
| 1 | install | skipped | 0 | packages already installed for this package.json |
| 2 | codemod preset-safe | ok | 12 | 12 ok, 0 unchanged |
| 3 | codemod variant-prop | ok | 1 | 1 ok, 11 unchanged |
| 4 | codemod link-underline-hover | ok | 1 | 1 ok, 11 unchanged |
| 5 | codemod box-sx-prop | ok | 1 | 1 ok, 11 unchanged |
| 6 | format | ok | 0 | eslint --fix on 12 files |
| 7 | dependencies | ok | 1 | -@material-ui/core +@mui/material@5.18.0 +@mui/styles@5.18.0 +@emotion/react@11.14.0 +@emotion/styled@11.14.1 -@material-ui/icons +@mui/icons-material@5.18.0 -@material-ui/lab +@mui/lab@5.0.0-alpha.177 |
| 8 | install | ok | 1 | npm install --no-audit --no-fund |

## Pre-check and tests

Pre-check: ok, 0 Pre-existing failures.

| | Pre-check | Final verify |
|---|---|---|
| Tests run | 20 | 20 |
| Tests failing | 0 | 8 |
| Tests skipped | 0 | 0 |
| Suites failing | 0 of 10 | 6 of 10 |
| Snapshots | 1 | 1 |

## Cost

$0: this run made no model calls. Run cap $5.00; month cap $20.00.

Node 24.14.0, npm 11.9.0, migrator 0.1.0.
