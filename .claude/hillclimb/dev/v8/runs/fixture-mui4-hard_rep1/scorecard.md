# Scorecard: mui4-tracker-app · run 2026-11-10-013210-754

`mui@4->mui@5` · configuration `opus-low-tools-v2` · case `fixture-mui4-hard` · 4 min 5 s · **$0.12** of $0.47 cap

**Clean run: no. Final verify found 2 failures in 1 files.** **11 of 12 affected files migrated without a human (92%)**: 3 by rules, 8 by the repair agent. 0 handed off, 1 unmigrated.

| | This run |
|---|---|
| Clean run | no (2 failures in 1 files) |
| Migrated without a human | 11 / 12 (92%) |
| Hand-offs | 0 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps | 13 expected · 0 other layer · 2 missed · 0 not scored |
| Cost / time | $0.12 · 4 min 5 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/components/LabelPicker.tsx | Migrated by agent | 0 | changed while repairing src/screens/IssueDetail.tsx |
| src/components/RangeSlider.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/components/StatusChip.tsx | Migrated by agent | 0 | 2 attempt(s) |
| src/screens/Activity.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Board.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/IssueDetail.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/IssueList.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/NewIssueDialog.tsx | Unmigrated | 2 | cost cap: the next call (claude-opus-5-5, worst case $0.37) could take this run past its $0.47 cap (spent $0.12) |
| src/theme.ts | Migrated by agent | 0 | changed while repairing src/screens/Board.tsx |
| 3 files | Migrated by rules | 0 | App, DurationInput, Reports |

Changed but not affected: `package-lock.json`, `package.json`.

## Failures

| File | Check | Where | Message |
|---|---|---|---|
| src/screens/NewIssueDialog.tsx | test | NewIssueDialog › assigns new issues to the signed-in user, marked in the list | Error: expect(element).toHaveAttribute("aria-selected", "true") // element.getAttribute("aria-selected") === "true" |
| src/screens/NewIssueDialog.tsx | test | NewIssueDialog › creates the issue with a tidied estimate | Error: expect(jest.fn()).toHaveBeenCalledWith(...expected) |

## Traps (fixture)

| Result | Expected layer | Traps |
|---|---|---|
| Expected | rules | 6: create-theme, pagination-import, pagination-round, skeleton-rect, dialog-transition-literal, autocomplete-option-equal-literal |
| Expected | agent | 7: theme-state-selector, autocomplete-reason-names, dialog-transition-spread, root-ref-removed, slider-event-type, table-pagination-labels, chip-variant-wrapped |
| Missed | agent | 2: option-equal-spread, input-component-ref |

Fixed (their checks now pass at the final verify): theme-state-selector, autocomplete-reason-names, dialog-transition-spread, root-ref-removed, slider-event-type, table-pagination-labels, chip-variant-wrapped.

## Repair

7 failing files, 8 attempts, 30 tool calls. **Stopped by the cost cap:** the next call (claude-opus-5-5, worst case $0.37) could take this run past its $0.47 cap (spent $0.12).

| File | Outcome | Attempts | Tool calls | Patch | Why |
|---|---|---|---|---|---|
| src/components/RangeSlider.tsx | Migrated by agent | 1 | 4 | RangeSlider.tsx 2 |  |
| src/components/StatusChip.tsx | Migrated by agent | 2 | 5 | StatusChip.tsx 1 |  |
| src/screens/Activity.tsx | Migrated by agent | 1 | 4 | Activity.tsx 14 |  |
| src/screens/Board.tsx | Migrated by agent | 1 | 4 | theme.ts 1 |  |
| src/screens/IssueDetail.tsx | Migrated by agent | 1 | 5 | LabelPicker.tsx 2, dialogFocus.ts 1 |  |
| src/screens/IssueList.tsx | Migrated by agent | 1 | 2 | IssueList.tsx 3 |  |
| src/screens/NewIssueDialog.tsx | Unmigrated | 1 | 6 | — | cost cap: the next call (claude-opus-5-5, worst case $0.37) could take this run past its $0.47 cap (spent $0.12) |

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
| Tests failing | 0 | 2 |
| Tests skipped | 0 | 0 |
| Suites failing | 0 of 6 | 1 of 6 |
| Snapshots | 0 | 0 |

## Cost

$0.12 = $0.08 output + $0.00 input + $0.04 cache (reads $0.01, writes $0.02), claude-opus-5-5, 15 calls. Cache reads covered 95% of input tokens. Run cap $0.47; month cap $20.00, this month $4.43 of $20.00. Repair stopped at the cost cap.

Node 20.20.2, npm 10.8.2, migrator 0.1.0.
