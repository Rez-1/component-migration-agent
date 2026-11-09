# Scorecard: warehouse-back-office · run baseline-holdout-a

`mui@4->mui@5` · configuration `baseline` · case `fixture-mui4-holdout` · 32 s · $0 (no LLM) of $5.00 cap

**Clean run: no. Final verify found 16 failures in 7 files.** **2 of 9 affected files migrated without a human (22%)**: 2 by rules, 0 by the repair agent. 0 handed off, 7 unmigrated.

| | This run |
|---|---|
| Clean run | no (16 failures in 7 files) |
| Migrated without a human | 2 / 9 (22%) |
| Hand-offs | 0 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 1 |
| Traps | 8 expected · 0 other layer · 7 missed · 1 not scored |
| Cost / time | $0 · 32 s |

## Files

| File | Outcome | Failures | Note |
|---|---|---|---|
| src/screens/Inventory.tsx | Unmigrated | 1 | 1 typecheck |
| src/screens/OrderDialog.tsx | Unmigrated | 4 | 1 test, 3 typecheck |
| src/screens/OrdersTable.tsx | Unmigrated | 2 | 1 test, 1 typecheck |
| src/screens/ProductTags.tsx | Unmigrated | 4 | 2 test, 2 typecheck |
| src/screens/ReturnForm.tsx | Unmigrated | 3 | 2 test, 1 typecheck |
| src/screens/ShipmentTracker.tsx | Unmigrated | 1 | 1 test |
| src/screens/StockSummary.tsx | Unmigrated | 1 | 1 typecheck |
| 2 files | Migrated by rules | 0 | App, theme |

Changed but not affected: `package-lock.json`, `package.json`.

## Failures

| File | Check | Where | Message |
|---|---|---|---|
| src/screens/Inventory.tsx | typecheck TS2339 | line 9 | Property 'gutters' does not exist on type 'Mixins'. |
| src/screens/OrderDialog.tsx | test | OrderDialog › takes the whole screen on a small tablet (700px wide) | Error: expect(element).toHaveClass("MuiDialog-paperFullScreen") |
| src/screens/OrderDialog.tsx | typecheck TS7006 | line 13 | Parameter 'WrappedComponent' implicitly has an 'any' type. |
| src/screens/OrderDialog.tsx | typecheck TS7006 | line 13 | Parameter 'props' implicitly has an 'any' type. |
| src/screens/OrderDialog.tsx | typecheck TS2558 | line 52 | Expected 0 type arguments, but got 1. |
| src/screens/OrdersTable.tsx | test | OrdersTable › pages through the orders | TestingLibraryElementError: Unable to find an accessible element with the role "button" and name "Next page" |
| src/screens/OrdersTable.tsx | typecheck TS2769 | line 71 | No overload matches this call. Overload 1 of 2, '(props: { component: ElementType<any>; } & TablePaginationOwnProps & CommonProps & Omit<… |
| src/screens/ProductTags.tsx | test | ProductTags › stores a new tag lower-case and hyphenated | Error: expect(jest.fn()).toHaveBeenLastCalledWith(...expected) |
| src/screens/ProductTags.tsx | test | ProductTags › says which tag was removed | TestingLibraryElementError: Unable to find an accessible element with the role "status" |
| src/screens/ProductTags.tsx | typecheck TS2367 | line 33 | This comparison appears to be unintentional because the types 'AutocompleteChangeReason' and '"create-option"' have no overlap. |
| src/screens/ProductTags.tsx | typecheck TS2367 | line 36 | This comparison appears to be unintentional because the types 'AutocompleteChangeReason' and '"remove-option"' have no overlap. |
| src/screens/ReturnForm.tsx | test | ReturnForm › logs a return with its reason | Error: MUI: The color provided to augmentColor(color) is invalid. |
| src/screens/ReturnForm.tsx | test | ReturnForm › sends damaged items to inspection | Error: MUI: The color provided to augmentColor(color) is invalid. |
| src/screens/ReturnForm.tsx | typecheck TS2345 | line 9 | Argument of type '{ main: string; }' is not assignable to parameter of type 'PaletteAugmentColorOptions'. Object literal may only specify… |
| src/screens/ShipmentTracker.tsx | test | ShipmentTracker › marks the finished stages as done | Error: expect(received).toHaveLength(expected) |
| src/screens/StockSummary.tsx | typecheck TS2362 | line 16 | The left-hand side of an arithmetic operation must be of type 'any', 'number', 'bigint' or an enum type. |

## Traps (fixture)

| Result | Expected layer | Traps |
|---|---|---|
| Expected | rules | 8: create-theme, palette-type-mode, circular-progress-determinate, table-cell-padding-normal, chip-variant-filled, avatar-variant-circular, skeleton-lab-rect, textfield-max-rows |
| Missed | agent | 6: spacing-arithmetic-half, pagination-item-aria-label, with-mobile-dialog, mixins-gutters, autocomplete-reason-names, palette-augment-color |
| Missed | human | 1: stepper-state-classes |
| Not scored | visual-only | 1: checkbox-default-color |

Every agent and human trap's check still fails at the final verify.

## Cheating checks

No hits and no warnings on repair-agent patches.

Reported, not failing (only repair-agent patches can fail a run):

| File | Layer | Check | Detail |
|---|---|---|---|
| src/App.tsx | rules | escape-hatch:eslint-disable | an `eslint-disable` comment: 0 -> 1 |

10 test files checked.

## Rule steps

| # | Step | Status | Changed | Detail |
|---|---|---|---|---|
| 1 | install | skipped | 0 | packages already installed for this package.json |
| 2 | codemod preset-safe | ok | 9 | 9 ok, 0 unchanged |
| 3 | codemod variant-prop | ok | 2 | 2 ok, 7 unchanged |
| 4 | codemod link-underline-hover | ok | 0 | 0 ok, 9 unchanged |
| 5 | codemod box-sx-prop | ok | 0 | 0 ok, 9 unchanged |
| 6 | format | ok | 0 | eslint --fix on 9 files |
| 7 | dependencies | ok | 1 | -@material-ui/core +@mui/material@5.18.0 +@mui/styles@5.18.0 +@emotion/react@11.14.0 +@emotion/styled@11.14.1 -@material-ui/icons +@mui/icons-material@5.18.0 -@material-ui/lab +@mui/lab@5.0.0-alpha.177 |
| 8 | install | ok | 1 | npm install --no-audit --no-fund |

## Pre-check and tests

Pre-check: ok, 0 Pre-existing failures.

| | Pre-check | Final verify |
|---|---|---|
| Tests run | 15 | 15 |
| Tests failing | 0 | 7 |
| Tests skipped | 0 | 0 |
| Suites failing | 0 of 7 | 5 of 7 |
| Snapshots | 0 | 0 |

## Cost

$0: this run made no model calls. Run cap $5.00; month cap $20.00.

Node 24.14.0, npm 11.9.0, migrator 0.1.0.
