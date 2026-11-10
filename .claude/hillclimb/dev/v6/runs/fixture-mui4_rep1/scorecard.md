# Scorecard: mui4-fixture-app · run 2026-11-10-003813-fe2

`mui@4->mui@5` · configuration `cascade-haiku-opus` · case `fixture-mui4` · 7 min 15 s · **$0.10** of $1.07 cap

**Clean run: yes.** **9 of 12 affected files migrated without a human (75%)**: 2 by rules, 7 by the repair agent. 3 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 9 / 12 (75%) |
| Hand-offs | 3 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps | 20 expected · 0 other layer · 2 missed · 1 not scored |
| Cost / time | $0.10 · 7 min 15 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/screens/AccountDialog.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Dashboard.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Faq.tsx | Handed off | 1 | the repair agent handed off: The Faq.tsx migration to Accordion/AccordionSummary/AccordionDetails is correct for v5, but the failing test is a snapshot test. The committed snapshot in src/screens/__tests__/__snapshots__/Faq.test.tsx.snap still has v4 markup (MuiExpansionPanelSummary-* classes, MuiIconButton expand icon), so it can only pass after a human reviews and regenerates that snapshot. Snapshots are off-limits to the repair agent, and matching the old classes in the component would be wrong.; revert |
| src/screens/Notifications.tsx | Handed off | 1 | tool-call budget used: 15 calls in attempt 1 without passing run_verify; revert |
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
| src/screens/Notifications.tsx | typecheck TS2769 | line 39 | No overload matches this call. Overload 1 of 2, '(props: { component: "span"; } & TypographyOwnProps & CommonProps & Omit<Omit<DetailedHT… |
| src/screens/Search.tsx | test | Search › suggests matching cities with their country | TestingLibraryElementError: Unable to find an accessible element with the role "option" |
| src/screens/Search.tsx | test | Search › selects Amsterdam | TestingLibraryElementError: Unable to find an accessible element with the role "option" and name `/Amsterdam/` |
| src/screens/Search.tsx | typecheck TS2339 | line 42 | Property 'label' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'. |
| src/screens/Search.tsx | typecheck TS2339 | line 43 | Property 'country' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'. |

## Traps (fixture)

| Result | Expected layer | Traps |
|---|---|---|
| Expected | rules | 12: create-theme, grid-justify, fade-alpha, autocomplete-import, autocomplete-option-equal, button-color-default-literal, spacing-px-template, expansion-panel, link-underline, textfield-default-variant, breakpoint-down, box-system-props |
| Expected | agent | 7: spacing-arithmetic, dialog-disable-backdrop-click, breakpoint-sizes, button-color-expression, button-label-override, select-event-type, styles-needs-theme-provider |
| Expected | human | 1: faq-snapshot-markup |
| Missed | agent | 2: autocomplete-render-option, typography-sr-only |
| Not scored | visual-only | 1: switch-default-color |

Fixed (their checks now pass at the final verify): spacing-arithmetic, dialog-disable-backdrop-click, breakpoint-sizes, button-color-expression, button-label-override, select-event-type, styles-needs-theme-provider.

## Repair

10 failing files, 12 attempts, 78 tool calls.

| File | Outcome | Attempts | Tool calls | Patch | Why |
|---|---|---|---|---|---|
| src/theme.ts | Migrated by agent | 2 | 6 | theme.ts 1 |  |
| src/screens/AccountDialog.tsx | Migrated by agent | 1 | 3 | AccountDialog.tsx 9 |  |
| src/screens/Dashboard.tsx | Migrated by agent | 1 | 7 | Dashboard.tsx 2 |  |
| src/screens/Faq.tsx | Handed off | 1 | 3 | — | the repair agent handed off: The Faq.tsx migration to Accordion/AccordionSummary/AccordionDetails is correct for v5, but the failing test is a snapshot test. The committed snapshot in src/screens/__tests__/__snapshots__/Faq.test.tsx.snap still has v4 markup (MuiExpansionPanelSummary-* classes, MuiIconButton expand icon), so it can only pass after a human reviews and regenerates that snapshot. Snapshots are off-limits to the repair agent, and matching the old classes in the component would be wrong. (Review: revert) |
| src/screens/Notifications.tsx | Handed off | 1 | 15 | Notifications.tsx 15 | tool-call budget used: 15 calls in attempt 1 without passing run_verify (Review: revert) |
| src/screens/ProfileCard.tsx | Migrated by agent | 1 | 10 | ProfileCard.tsx 2 |  |
| src/screens/ProfileForm.tsx | Migrated by agent | 1 | 3 | ProfileForm.tsx 2 |  |
| src/screens/ResponsiveNav.tsx | Migrated by agent | 1 | 10 | ResponsiveNav.tsx 1 |  |
| src/screens/Search.tsx | Handed off | 1 | 15 | Search.tsx 4 | tool-call budget used: 15 calls in attempt 1 without passing run_verify (Review: revert) |
| src/screens/Settings.tsx | Migrated by agent | 2 | 6 | Settings.tsx 1 |  |

Review list: `src/screens/Faq.tsx`, `src/screens/Notifications.tsx`, `src/screens/Search.tsx`.

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

$0.10 = $0.03 output + $0.00 input + $0.07 cache (reads $0.01, writes $0.06), claude-haiku-5-5 $0.03 (51 calls); claude-opus-5-5 $0.07 (3 calls), 54 calls. Cache reads covered 80% of input tokens. Run cap $1.07; month cap $20.00, this month $2.53 of $20.00.

Node 20.20.2, npm 10.8.2, migrator 0.1.0.
