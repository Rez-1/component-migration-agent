# Scorecard: mui4-tracker-app · run 2026-11-10-020103-b23

`mui@4->mui@5` · configuration `haiku-advisor-opus` · case `fixture-mui4-hard` · 5 min 21 s · **$0.02** of $2.74 cap

**Clean run: yes.** **10 of 12 affected files migrated without a human (83%)**: 4 by rules, 6 by the repair agent. 2 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 10 / 12 (83%) |
| Hand-offs | 2 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps | 11 expected · 0 other layer · 4 missed · 0 not scored |
| Cost / time | $0.02 · 5 min 21 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/components/RangeSlider.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/components/StatusChip.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Activity.tsx | Migrated by agent | 0 | 1 attempt(s) |
| src/screens/Board.tsx | Migrated by agent | 0 | 2 attempt(s) |
| src/screens/IssueDetail.tsx | Handed off | 3 | tool-call budget used: 15 calls in attempt 1 without passing run_verify; revert |
| src/screens/IssueList.tsx | Migrated by agent | 0 | 2 attempt(s) |
| src/screens/NewIssueDialog.tsx | Handed off | 2 | patch over the size limit: src/components/DurationInput.tsx would change 16 lines (48% of the file); revert |
| src/theme.ts | Migrated by agent | 0 | changed while repairing src/screens/Board.tsx |
| 4 files | Migrated by rules | 0 | App, DurationInput, LabelPicker, Reports |

Changed but not affected: `package-lock.json`, `package.json`.

## Failures

| File | Check | Where | Message |
|---|---|---|---|
| src/screens/IssueDetail.tsx | test | IssueDetail › adds a label and says so | TestingLibraryElementError: Unable to find an accessible element with the role "alert" |
| src/screens/IssueDetail.tsx | test | IssueDetail › removes a label with Backspace, and Undo brings it back | TestingLibraryElementError: Unable to find an accessible element with the role "alert" |
| src/screens/IssueDetail.tsx | test | IssueDetail › puts the cursor in the comment box once the dialog is open | Error: expect(element).toHaveFocus() |
| src/screens/NewIssueDialog.tsx | test | NewIssueDialog › assigns new issues to the signed-in user, marked in the list | Error: expect(element).toHaveAttribute("aria-selected", "true") // element.getAttribute("aria-selected") === "true" |
| src/screens/NewIssueDialog.tsx | test | NewIssueDialog › creates the issue with a tidied estimate | Error: expect(jest.fn()).toHaveBeenCalledWith(...expected) |

## Traps (fixture)

| Result | Expected layer | Traps |
|---|---|---|
| Expected | rules | 6: create-theme, pagination-import, pagination-round, skeleton-rect, dialog-transition-literal, autocomplete-option-equal-literal |
| Expected | agent | 5: theme-state-selector, root-ref-removed, slider-event-type, table-pagination-labels, chip-variant-wrapped |
| Missed | agent | 4: autocomplete-reason-names, dialog-transition-spread, option-equal-spread, input-component-ref |

Fixed (their checks now pass at the final verify): theme-state-selector, root-ref-removed, slider-event-type, table-pagination-labels, chip-variant-wrapped.

## Repair

7 failing files, 9 attempts, 63 tool calls.
Edits refused by the guardrails: size-limit 1.

| File | Outcome | Attempts | Tool calls | Patch | Why |
|---|---|---|---|---|---|
| src/components/RangeSlider.tsx | Migrated by agent | 1 | 6 | RangeSlider.tsx 2 |  |
| src/components/StatusChip.tsx | Migrated by agent | 1 | 7 | StatusChip.tsx 1 |  |
| src/screens/Activity.tsx | Migrated by agent | 1 | 10 | Activity.tsx 3 |  |
| src/screens/Board.tsx | Migrated by agent | 2 | 9 | theme.ts 1 |  |
| src/screens/IssueDetail.tsx | Handed off | 1 | 15 | LabelPicker.tsx 2, IssueDetail.tsx 1 | tool-call budget used: 15 calls in attempt 1 without passing run_verify (Review: revert) |
| src/screens/IssueList.tsx | Migrated by agent | 2 | 7 | IssueList.tsx 3 |  |
| src/screens/NewIssueDialog.tsx | Handed off | 1 | 9 | personPicker.ts 1, DurationInput.tsx 1 | patch over the size limit: src/components/DurationInput.tsx would change 16 lines (48% of the file) (Review: revert) |

Review list: `src/screens/IssueDetail.tsx`, `src/screens/NewIssueDialog.tsx`.

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
| Tests failing | 0 | 5 |
| Tests skipped | 0 | 0 |
| Suites failing | 0 of 6 | 2 of 6 |
| Snapshots | 0 | 0 |

## Cost

$0.02 = $0.01 output + $0.00 input + $0.01 cache (reads $0.00, writes $0.01), claude-haiku-5-5, 35 calls. Cache reads covered 79% of input tokens. Run cap $2.74; month cap $20.00, this month $5.11 of $20.00.

Node 20.20.2, npm 10.8.2, migrator 0.1.0.
