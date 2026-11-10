# Scorecard: mui4-tracker-app · run 2026-11-09-231832-dfa

`mui@4->mui@5` · configuration `baseline` · case `fixture-mui4-hard` · 54 s · $0 (no LLM) of $5.00 cap

**Clean run: no. Final verify found 13 failures in 7 files.** **5 of 12 affected files migrated without a human (42%)**: 5 by rules, 0 by the repair agent. 0 handed off, 7 unmigrated.

| | This run |
|---|---|
| Clean run | no (13 failures in 7 files) |
| Migrated without a human | 5 / 12 (42%) |
| Hand-offs | 0 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps | 6 expected · 0 other layer · 9 missed · 0 not scored |
| Cost / time | $0 · 54 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/components/RangeSlider.tsx | Unmigrated | 1 | 1 typecheck |
| src/components/StatusChip.tsx | Unmigrated | 1 | 1 typecheck |
| src/screens/Activity.tsx | Unmigrated | 3 | 1 lint, 1 test, 1 typecheck |
| src/screens/Board.tsx | Unmigrated | 1 | 1 test |
| src/screens/IssueDetail.tsx | Unmigrated | 3 | 3 test |
| src/screens/IssueList.tsx | Unmigrated | 2 | 1 test, 1 typecheck |
| src/screens/NewIssueDialog.tsx | Unmigrated | 2 | 2 test |
| 5 files | Migrated by rules | 0 | App, DurationInput, LabelPicker, Reports, theme |

Changed but not affected: `package-lock.json`, `package.json`.

## Failures

| File | Check | Where | Message |
|---|---|---|---|
| src/components/RangeSlider.tsx | typecheck TS2769 | line 27 | No overload matches this call. Overload 1 of 2, '(props: { component: ElementType<any>; } & SliderOwnProps & CommonProps & Omit<any, "cla… |
| src/components/StatusChip.tsx | typecheck TS2322 | line 19 | Type '"default"' is not assignable to type '"filled" \| "outlined" \| undefined'. |
| src/screens/Activity.tsx | lint @typescript-eslint/no-unused-vars | line 9 | 'RootRef' is defined but never used. |
| src/screens/Activity.tsx | test | Activity › adds an update and moves focus to it | Error: expect(element).toHaveFocus() |
| src/screens/Activity.tsx | typecheck TS2305 | line 9 | Module '"@mui/material"' has no exported member 'RootRef'. |
| src/screens/Board.tsx | test | Board › shows the selected status tab in bold | Error: expect(element).toHaveStyle() |
| src/screens/IssueDetail.tsx | test | IssueDetail › adds a label and says so | TestingLibraryElementError: Unable to find an accessible element with the role "alert" |
| src/screens/IssueDetail.tsx | test | IssueDetail › removes a label with Backspace, and Undo brings it back | TestingLibraryElementError: Unable to find an accessible element with the role "alert" |
| src/screens/IssueDetail.tsx | test | IssueDetail › puts the cursor in the comment box once the dialog is open | Error: expect(element).toHaveFocus() |
| src/screens/IssueList.tsx | test | IssueList › pages through the issues five at a time | TestingLibraryElementError: Unable to find an accessible element with the role "button" and name "Previous issues" |
| src/screens/IssueList.tsx | typecheck TS2769 | line 78 | No overload matches this call. Overload 1 of 2, '(props: { component: "div"; } & TablePaginationOwnProps & CommonProps & Omit<Omit<Detail… |
| src/screens/NewIssueDialog.tsx | test | NewIssueDialog › assigns new issues to the signed-in user, marked in the list | Error: expect(element).toHaveAttribute("aria-selected", "true") // element.getAttribute("aria-selected") === "true" |
| src/screens/NewIssueDialog.tsx | test | NewIssueDialog › creates the issue with a tidied estimate | Error: expect(jest.fn()).toHaveBeenCalledWith(...expected) |

## Traps (fixture)

| Result | Expected layer | Traps |
|---|---|---|
| Expected | rules | 6: create-theme, pagination-import, pagination-round, skeleton-rect, dialog-transition-literal, autocomplete-option-equal-literal |
| Missed | agent | 9: theme-state-selector, autocomplete-reason-names, dialog-transition-spread, option-equal-spread, input-component-ref, root-ref-removed, slider-event-type, table-pagination-labels, chip-variant-wrapped |

Every agent and human trap's check still fails at the final verify.

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
| Tests failing | 0 | 8 |
| Tests skipped | 0 | 0 |
| Suites failing | 0 of 6 | 5 of 6 |
| Snapshots | 0 | 0 |

## Cost

$0: this run made no model calls. Run cap $5.00; month cap $20.00.

Node 20.20.2, npm 10.8.2, migrator 0.1.0.
