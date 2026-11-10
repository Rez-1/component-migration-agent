# Scorecard: mui4-fixture-app · run 2026-11-10-003043-4b7

`mui@4->mui@5` · configuration `cascade-haiku-opus` · case `fixture-mui4` · 7 min 25 s · **$0.13** of $1.20 cap

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
| Cost / time | $0.13 · 7 min 25 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/screens/AccountDialog.tsx | Migrated by agent | 0 | 2 attempt(s) |
| src/screens/Dashboard.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Faq.tsx | Handed off | 1 | the repair agent handed off: The failing assertion is a snapshot of the v4 markup (MuiExpansionPanelSummary classes, v4 IconButton expand wrapper). The v5 AccordionSummary renders different classes and structure, so the code is migrated correctly and the only way to pass is to update the snapshot, which is a test artifact I'm not allowed to change. A human should review the new render and regenerate that snapshot (jest -u for this test).; revert |
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

10 failing files, 13 attempts, 72 tool calls.

| File | Outcome | Attempts | Tool calls | Patch | Why |
|---|---|---|---|---|---|
| src/theme.ts | Migrated by agent | 2 | 5 | theme.ts 1 |  |
| src/screens/AccountDialog.tsx | Migrated by agent | 2 | 5 | AccountDialog.tsx 9 |  |
| src/screens/Dashboard.tsx | Migrated by agent | 1 | 7 | Dashboard.tsx 2 |  |
| src/screens/Faq.tsx | Handed off | 1 | 3 | — | the repair agent handed off: The failing assertion is a snapshot of the v4 markup (MuiExpansionPanelSummary classes, v4 IconButton expand wrapper). The v5 AccordionSummary renders different classes and structure, so the code is migrated correctly and the only way to pass is to update the snapshot, which is a test artifact I'm not allowed to change. A human should review the new render and regenerate that snapshot (jest -u for this test). (Review: revert) |
| src/screens/Notifications.tsx | Migrated by agent | 1 | 6 | Notifications.tsx 14 |  |
| src/screens/ProfileCard.tsx | Migrated by agent | 1 | 11 | ProfileCard.tsx 4 |  |
| src/screens/ProfileForm.tsx | Migrated by agent | 1 | 3 | ProfileForm.tsx 10 |  |
| src/screens/ResponsiveNav.tsx | Migrated by agent | 1 | 11 | ResponsiveNav.tsx 1 |  |
| src/screens/Search.tsx | Handed off | 1 | 15 | Search.tsx 3 | tool-call budget used: 15 calls in attempt 1 without passing run_verify (Review: revert) |
| src/screens/Settings.tsx | Migrated by agent | 2 | 6 | Settings.tsx 1 |  |

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

$0.13 = $0.03 output + $0.00 input + $0.10 cache (reads $0.01, writes $0.09), claude-haiku-5-5 $0.03 (43 calls); claude-opus-5-5 $0.10 (6 calls), 49 calls. Cache reads covered 77% of input tokens. Run cap $1.20; month cap $20.00, this month $2.43 of $20.00.

Node 20.20.2, npm 10.8.2, migrator 0.1.0.
