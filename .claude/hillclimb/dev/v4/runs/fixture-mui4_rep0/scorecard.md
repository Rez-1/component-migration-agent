# Scorecard: mui4-fixture-app · run 2026-11-09-233952-df3

`mui@4->mui@5` · configuration `haiku-high` · case `fixture-mui4` · 8 min 32 s · **$0.03** of $0.40 cap

**Clean run: yes.** **10 of 12 affected files migrated without a human (83%)**: 2 by rules, 8 by the repair agent. 2 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 10 / 12 (83%) |
| Hand-offs | 2 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps | 21 expected · 0 other layer · 1 missed · 1 not scored |
| Cost / time | $0.03 · 8 min 32 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/screens/AccountDialog.tsx | Migrated by agent | 0 | 2 attempt(s) |
| src/screens/Dashboard.tsx | Migrated by agent | 0 | 2 attempt(s) |
| src/screens/Faq.tsx | Handed off | 1 | the repair agent handed off: The failing snapshot in src/screens/__tests__/__snapshots__/Faq.test.tsx.snap still encodes the v4 DOM (MuiExpansionPanelSummary classes and an IconButton expand-icon wrapper). The migrated AccordionSummary correctly renders MuiAccordionSummary classes and a div wrapper, so the test can only pass once a human reviews and updates that snapshot, which is a test file I'm not allowed to change.; revert |
| src/screens/Notifications.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/ProfileCard.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/ProfileForm.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/ResponsiveNav.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Search.tsx | Handed off | 4 | tool-call budget used: 15 calls in attempt 1 without passing run_verify; revert |
| src/screens/Settings.tsx | Migrated by agent | 0 | 2 attempt(s) |
| src/theme.ts | Migrated by agent | 0 | 2 attempt(s) |
| 2 files | Migrated by rules | 0 | App, UsersTable |

Changed but not affected: `package-lock.json`, `package.json`.

## Failures

| File | Check | Where | Message |
|---|---|---|---|
| src/screens/Faq.tsx | test | Faq › renders a question header with its expand icon | Error: expect(received).toMatchSnapshot() |
| src/screens/Search.tsx | test | Search › suggests matching cities with their country | TestingLibraryElementError: Unable to find an accessible element with the role "option" |
| src/screens/Search.tsx | test | Search › selects Amsterdam | TestingLibraryElementError: Unable to find an accessible element with the role "option" and name `/Amsterdam/` |
| src/screens/Search.tsx | typecheck TS2339 | line 42 | Property 'label' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'. |
| src/screens/Search.tsx | typecheck TS2339 | line 43 | Property 'country' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'. |

## Traps (fixture)

| Result | Expected layer | Traps |
|---|---|---|
| Expected | rules | 12: create-theme, grid-justify, fade-alpha, autocomplete-import, autocomplete-option-equal, button-color-default-literal, spacing-px-template, expansion-panel, link-underline, textfield-default-variant, breakpoint-down, box-system-props |
| Expected | agent | 8: spacing-arithmetic, dialog-disable-backdrop-click, typography-sr-only, breakpoint-sizes, button-color-expression, button-label-override, select-event-type, styles-needs-theme-provider |
| Expected | human | 1: faq-snapshot-markup |
| Missed | agent | 1: autocomplete-render-option |
| Not scored | visual-only | 1: switch-default-color |

Fixed (their checks now pass at the final verify): spacing-arithmetic, dialog-disable-backdrop-click, typography-sr-only, breakpoint-sizes, button-color-expression, button-label-override, select-event-type, styles-needs-theme-provider.

## Repair

10 failing files, 14 attempts, 77 tool calls.

| File | Outcome | Attempts | Tool calls | Patch | Why |
|---|---|---|---|---|---|
| src/theme.ts | Migrated by agent | 2 | 6 | theme.ts 1 |  |
| src/screens/AccountDialog.tsx | Migrated by agent | 2 | 5 | AccountDialog.tsx 7 |  |
| src/screens/Dashboard.tsx | Migrated by agent | 2 | 8 | Dashboard.tsx 2 |  |
| src/screens/Faq.tsx | Handed off | 1 | 3 | — | the repair agent handed off: The failing snapshot in src/screens/__tests__/__snapshots__/Faq.test.tsx.snap still encodes the v4 DOM (MuiExpansionPanelSummary classes and an IconButton expand-icon wrapper). The migrated AccordionSummary correctly renders MuiAccordionSummary classes and a div wrapper, so the test can only pass once a human reviews and updates that snapshot, which is a test file I'm not allowed to change. (Review: revert) |
| src/screens/Notifications.tsx | Migrated by agent | 1 | 9 | Notifications.tsx 14 |  |
| src/screens/ProfileCard.tsx | Migrated by agent | 1 | 11 | ProfileCard.tsx 9 |  |
| src/screens/ProfileForm.tsx | Migrated by agent | 1 | 3 | ProfileForm.tsx 10 |  |
| src/screens/ResponsiveNav.tsx | Migrated by agent | 1 | 10 | ResponsiveNav.tsx 1 |  |
| src/screens/Search.tsx | Handed off | 1 | 15 | Search.tsx 3 | tool-call budget used: 15 calls in attempt 1 without passing run_verify (Review: revert) |
| src/screens/Settings.tsx | Migrated by agent | 2 | 7 | Settings.tsx 1 |  |

Review list: `src/screens/Faq.tsx`, `src/screens/Search.tsx`.

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
| Tests failing | 0 | 3 |
| Tests skipped | 0 | 0 |
| Suites failing | 0 of 10 | 2 of 10 |
| Snapshots | 1 | 1 |

## Cost

$0.03 = $0.02 output + $0.00 input + $0.01 cache (reads $0.00, writes $0.01), claude-haiku-5-5, 54 calls. Cache reads covered 80% of input tokens. Run cap $0.40; month cap $20.00, this month $1.66 of $20.00.

Node 20.20.2, npm 10.8.2, migrator 0.1.0.
