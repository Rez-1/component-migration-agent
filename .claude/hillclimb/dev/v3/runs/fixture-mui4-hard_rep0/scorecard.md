# Scorecard: mui4-tracker-app · run 2026-11-09-233046-c13

`mui@4->mui@5` · configuration `opus-low` · case `fixture-mui4-hard` · 4 min 11 s · **$0.22** of $0.69 cap

**Clean run: yes.** **12 of 12 affected files migrated without a human (100%)**: 2 by rules, 10 by the repair agent. 0 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 12 / 12 (100%) |
| Hand-offs | 0 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps | 15 expected · 0 other layer · 0 missed · 0 not scored |
| Cost / time | $0.22 · 4 min 11 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/components/DurationInput.tsx | Migrated by agent | 0 | changed while repairing src/screens/NewIssueDialog.tsx |
| src/components/LabelPicker.tsx | Migrated by agent | 0 | changed while repairing src/screens/IssueDetail.tsx |
| src/components/RangeSlider.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/components/StatusChip.tsx | Migrated by agent | 0 | 2 attempt(s) |
| src/screens/Activity.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Board.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/IssueDetail.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/IssueList.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/NewIssueDialog.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/theme.ts | Migrated by agent | 0 | changed while repairing src/screens/Board.tsx |
| 2 files | Migrated by rules | 0 | App, Reports |

Changed but not affected: `package-lock.json`, `package.json`.

## Traps (fixture)

| Result | Expected layer | Traps |
|---|---|---|
| Expected | rules | 6: create-theme, pagination-import, pagination-round, skeleton-rect, dialog-transition-literal, autocomplete-option-equal-literal |
| Expected | agent | 9: theme-state-selector, autocomplete-reason-names, dialog-transition-spread, option-equal-spread, input-component-ref, root-ref-removed, slider-event-type, table-pagination-labels, chip-variant-wrapped |

Fixed (their checks now pass at the final verify): theme-state-selector, autocomplete-reason-names, dialog-transition-spread, option-equal-spread, input-component-ref, root-ref-removed, slider-event-type, table-pagination-labels, chip-variant-wrapped.

## Repair

7 failing files, 8 attempts, 30 tool calls.

| File | Outcome | Attempts | Tool calls | Patch | Why |
|---|---|---|---|---|---|
| src/components/RangeSlider.tsx | Migrated by agent | 1 | 4 | RangeSlider.tsx 2 |  |
| src/components/StatusChip.tsx | Migrated by agent | 2 | 4 | StatusChip.tsx 1 |  |
| src/screens/Activity.tsx | Migrated by agent | 1 | 4 | Activity.tsx 3 |  |
| src/screens/Board.tsx | Migrated by agent | 1 | 4 | theme.ts 1 |  |
| src/screens/IssueDetail.tsx | Migrated by agent | 1 | 5 | LabelPicker.tsx 2, dialogFocus.ts 1 |  |
| src/screens/IssueList.tsx | Migrated by agent | 1 | 2 | IssueList.tsx 3 |  |
| src/screens/NewIssueDialog.tsx | Migrated by agent | 1 | 7 | personPicker.ts 1, DurationInput.tsx 5 |  |

## Cheating checks

No hits and no warnings on repair-agent patches.

Reported, not failing (only repair-agent patches can fail a run):

| File | Layer | Check | Detail |
|---|---|---|---|
| src/App.tsx | rules | escape-hatch:eslint-disable | an `eslint-disable` comment: 0 -> 1 |

9 test files checked.

## Rule steps

| # | Step | Status | Changed | Detail |
|---|---|---|---|---|
| 1 | install | skipped | 0 | packages already installed for this package.json |
| 2 | codemod preset-safe | ok | 12 | 12 ok, 0 unchanged |
| 3 | codemod variant-prop | ok | 0 | 0 ok, 12 unchanged |
| 4 | codemod link-underline-hover | ok | 0 | 0 ok, 12 unchanged |
| 5 | codemod box-sx-prop | ok | 0 | 0 ok, 12 unchanged |
| 6 | format | ok | 0 | eslint --fix on 12 files |
| 7 | dependencies | ok | 1 | -@material-ui/core +@mui/material@5.18.0 +@mui/styles@5.18.0 +@emotion/react@11.14.0 +@emotion/styled@11.14.1 -@material-ui/icons +@mui/icons-material@5.18.0 -@material-ui/lab +@mui/lab@5.0.0-alpha.177 |
| 8 | install | ok | 1 | npm install --no-audit --no-fund |

## Pre-check and tests

Pre-check: ok, 0 Pre-existing failures.

| | Pre-check | Final verify |
|---|---|---|
| Tests run | 16 | 16 |
| Tests failing | 0 | 0 |
| Tests skipped | 0 | 0 |
| Suites failing | 0 of 6 | 0 of 6 |
| Snapshots | 0 | 0 |

## Cost

$0.22 = $0.08 output + $0.00 input + $0.14 cache (reads $0.01, writes $0.13), claude-opus-5-5, 16 calls. Cache reads covered 68% of input tokens. Run cap $0.69; month cap $20.00, this month $1.52 of $20.00.

Node 20.20.2, npm 10.8.2, migrator 0.1.0.
