# Scorecard: mui4-fixture-app · run 2026-11-10-014527-934

`mui@4->mui@5` · configuration `haiku-advisor-opus` · case `fixture-mui4` · 8 min 38 s · **$0.27** of $3.16 cap

**Clean run: yes.** **11 of 12 affected files migrated without a human (92%)**: 2 by rules, 9 by the repair agent. 1 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 11 / 12 (92%) |
| Hand-offs | 1 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps | 22 expected · 0 other layer · 0 missed · 1 not scored |
| Cost / time | $0.27 · 8 min 38 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/screens/AccountDialog.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Dashboard.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Faq.tsx | Handed off | 1 | the repair agent handed off: The failing test is a snapshot test, and its .snap file still holds the v4 output (MuiExpansionPanelSummary-* classes, expandIcon IconButton markup). Migrated v5 AccordionSummary renders different classes and structure, so no code change in Faq.tsx can match it without faking v4 class names. The snapshot is off-limits to me, so a human needs to review the v5 output and regenerate it (jest -u for this test). Side note: the Link underline="hover" added by the codemod keeps v4 behaviour and is fine.; revert |
| src/screens/Notifications.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/ProfileCard.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/ProfileForm.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/ResponsiveNav.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Search.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Settings.tsx | Migrated by agent | 0 | 2 attempt(s) |
| src/theme.ts | Migrated by agent | 0 | 2 attempt(s) |
| 2 files | Migrated by rules | 0 | App, UsersTable |

Changed but not affected: `package-lock.json`, `package.json`.

## Failures

| File | Check | Where | Message |
|---|---|---|---|
| src/screens/Faq.tsx | test | Faq › renders a question header with its expand icon | Error: expect(received).toMatchSnapshot() |

## Traps (fixture)

| Result | Expected layer | Traps |
|---|---|---|
| Expected | rules | 12: create-theme, grid-justify, fade-alpha, autocomplete-import, autocomplete-option-equal, button-color-default-literal, spacing-px-template, expansion-panel, link-underline, textfield-default-variant, breakpoint-down, box-system-props |
| Expected | agent | 9: autocomplete-render-option, spacing-arithmetic, dialog-disable-backdrop-click, typography-sr-only, breakpoint-sizes, button-color-expression, button-label-override, select-event-type, styles-needs-theme-provider |
| Expected | human | 1: faq-snapshot-markup |
| Not scored | visual-only | 1: switch-default-color |

Fixed (their checks now pass at the final verify): autocomplete-render-option, spacing-arithmetic, dialog-disable-backdrop-click, typography-sr-only, breakpoint-sizes, button-color-expression, button-label-override, select-event-type, styles-needs-theme-provider.

## Repair

10 failing files, 12 attempts, 74 tool calls.

| File | Outcome | Attempts | Tool calls | Patch | Why |
|---|---|---|---|---|---|
| src/theme.ts | Migrated by agent | 2 | 5 | theme.ts 1 |  |
| src/screens/AccountDialog.tsx | Migrated by agent | 1 | 5 | AccountDialog.tsx 9 |  |
| src/screens/Dashboard.tsx | Migrated by agent | 1 | 7 | Dashboard.tsx 2 |  |
| src/screens/Faq.tsx | Handed off | 1 | 3 | — | the repair agent handed off: The failing test is a snapshot test, and its .snap file still holds the v4 output (MuiExpansionPanelSummary-* classes, expandIcon IconButton markup). Migrated v5 AccordionSummary renders different classes and structure, so no code change in Faq.tsx can match it without faking v4 class names. The snapshot is off-limits to me, so a human needs to review the v5 output and regenerate it (jest -u for this test). Side note: the Link underline="hover" added by the codemod keeps v4 behaviour and is fine. (Review: revert) |
| src/screens/Notifications.tsx | Migrated by agent | 1 | 8 | Notifications.tsx 2 |  |
| src/screens/ProfileCard.tsx | Migrated by agent | 1 | 13 | ProfileCard.tsx 5 |  |
| src/screens/ProfileForm.tsx | Migrated by agent | 1 | 3 | ProfileForm.tsx 10 |  |
| src/screens/ResponsiveNav.tsx | Migrated by agent | 1 | 7 | ResponsiveNav.tsx 1 |  |
| src/screens/Search.tsx | Migrated by agent | 1 | 15 | Search.tsx 4 |  |
| src/screens/Settings.tsx | Migrated by agent | 2 | 8 | Settings.tsx 1 |  |

Review list: `src/screens/Faq.tsx`.

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
| Tests failing | 0 | 1 |
| Tests skipped | 0 | 0 |
| Suites failing | 0 of 10 | 1 of 10 |
| Snapshots | 1 | 1 |

## Cost

$0.27 = $0.10 output + $0.00 input + $0.16 cache (reads $0.00, writes $0.16), claude-haiku-5-5 $0.03 (54 calls); claude-opus-5-5 $0.24 (2 calls), 54 calls. Cache reads covered 79% of input tokens. Run cap $3.16; month cap $20.00, this month $4.93 of $20.00.

Node 20.20.2, npm 10.8.2, migrator 0.1.0.
