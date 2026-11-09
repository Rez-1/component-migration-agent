# Fixture case: `fixture-mui4-holdout` (held-out split)

The fixture is [`fixtures/mui4-app-holdout`](../../../fixtures/mui4-app-holdout): a second small React 17 + TypeScript 4.9 app on Material UI v4 (`@material-ui/core` 4.12.4), a warehouse back office. It is the **held-out case**: it measures whether the repair agent generalises beyond the dev case ([`fixture-mui4`](../fixture-mui4/README.md)), so it is run once at a milestone (`migrator eval run --split held-out ...`) and never climbed on.

**If you are tuning prompts, configurations or retrieval, don't read this case's traps or the fixture's source.** Hill-climbing never touches it (`_state.json` only holds dev cases), and reading it would turn the held-out number into a dev number.

As for fixture 1, this README, `traps.yaml` and `reference/` live outside the fixture on purpose: everything in `fixtures/mui4-app-holdout/` is copied into every run's workspace, where the repair agent's `read_file` can read it. `tests/test_holdout.py` fails if a fixture file mentions traps, hand-offs or the migration.

## What's in the fixture

- `src/screens/`: 7 screens, written the way a v4 app was (`makeStyles` JSS, theme `props`, `Autocomplete` and `Skeleton` from the lab):
  - **StockSummary**: KPI tiles and a capacity gauge (`CircularProgress`).
  - **OrdersTable**: a paginated table with status chips (`TablePagination`, `Chip`).
  - **OrderDialog**: order details, full screen on small screens (`withMobileDialog`, `Avatar`).
  - **Inventory**: a product list with loading placeholders (`Skeleton`, `theme.mixins`).
  - **ProductTags**: free-text tags (`Autocomplete` `multiple freeSolo`).
  - **ReturnForm**: a return form with a "damaged" path (`TextField`, `Checkbox`, `palette.augmentColor`).
  - **ShipmentTracker**: a shipment's stages (`Stepper`).
- `src/theme.ts`, `src/App.tsx` (with `AppProviders`, the theme shell, and `Tabs` navigation), `src/index.tsx`, `src/data/`.
- `src/screens/__tests__/`: one Testing Library behaviour test file per screen (15 tests).
- `src/test-utils.tsx`: test helpers (`renderScreen` in the app shell, `mockViewportWidth`). Imported only by tests, so a **Test file**.
- `CODEOWNERS`: teams for the usage report.

Configs (`tsconfig.json`, `jest.config.js`, `.eslintrc.cjs`, `babel.config.js`) and the dev dependencies are copied from fixture 1.

## Traps

16 planted traps (revision 1), each one instance of a breaking change from the official v4 → v5 guide (the vendored copy in `src/migrator/migrations/mui-4-to-5/guide/`):

| Expected layer | Count | Traps |
|---|---|---|
| Rules | 8 | create-theme, palette-type-mode, circular-progress-determinate, table-cell-padding-normal, chip-variant-filled, avatar-variant-circular, skeleton-lab-rect, textfield-max-rows |
| Agent | 6 | spacing-arithmetic-half, pagination-item-aria-label, with-mobile-dialog, mixins-gutters, autocomplete-reason-names, palette-augment-color |
| Human | 1 | stepper-state-classes: the test selects step icons by v4 class names; the fix is in the Test file |
| Visual only | 1 | checkbox-default-color (not scored) |

**Generalisation, not memory.** 14 of the 16 scored traps (and the visual one) use a breaking change fixture 1 doesn't plant. The two overlaps are new instances: `create-theme` (every v4 theme has it) and `spacing-arithmetic-half` (`theme.spacing(1) / 2`, fixture 1's is a multiplication plus an exported helper). `traps.yaml` marks each with `in_fixture_1`, and a test checks the flag against fixture 1's list.

What catches each agent trap after the Baseline:

| Trap | Breaking change (guide section) | Caught by |
|---|---|---|
| spacing-arithmetic-half | Theme structure › ✅ Remove px suffix | tsc |
| pagination-item-aria-label | TablePagination › Customize labels with getItemAriaLabel prop | tsc + OrdersTable test |
| with-mobile-dialog | Dialog › Remove withMobileDialog component | tsc (the codemod's untyped stand-in) + OrderDialog test at 700px |
| mixins-gutters | Theme structure › Remove gutters | tsc only (adaptV4Theme restores the mixin at runtime) |
| autocomplete-reason-names | Autocomplete › Rename reason arguments | tsc + both ProductTags tests |
| palette-augment-color | Theme › Update theme.palette.augmentColor helper | tsc + both ReturnForm tests (v5 throws) |
| stepper-state-classes (human) | Migrate theme styleOverrides to Emotion › Replace state class names | ShipmentTracker test |

Two are deliberately deeper than the guide's snippet. `with-mobile-dialog`: the guide's `useMediaQuery(theme.breakpoints.down('sm'))` still fails the 700px test, because v4's `withMobileDialog` meant "sm and below" (under 960px) and v5's `down('sm')` is under 600px; the agent has to combine it with the breakpoint changes (`down('md')`). `mixins-gutters`: only the type-checker sees it.

The human trap has no honest source fix. Its side door, checked in a scratch copy: passing `StepIconProps={{ classes: { completed: 'MuiStepIcon-completed', active: 'MuiStepIcon-active' } }}` copies v4's class names into the source and makes the test pass. That is teaching to the test, a reviewer's reject; it scores Other layer.

The full list, with locations, notes and what the Baseline did, is in [`traps.yaml`](traps.yaml). Don't move code around in the fixture without updating the line numbers there.

The known-good fixes are in [`reference/`](reference/): one find-and-replace patch per agent trap (`agent-fixes.yaml`) and the human fix in the test (`human-fix.yaml`). `tests/test_holdout_slow.py` replays them through the whole graph with a scripted model, and checks the Baseline against the committed scorecard in [`docs/results/baseline-holdout/`](../../../docs/results/baseline-holdout/).

## Baseline and oracle

| | Baseline (rules only) | Oracle (reference fixes) | Oracle + human fix |
|---|---|---|---|
| Failures | 16 in 7 files (9 type errors, 7 of 15 tests) | 1, in the handed-off file | 0 |
| Migrated without a human | 2 / 9 | 8 / 9 | 8 / 9 (+1 by human) |
| Traps | 8 Expected (rules), 7 Missed | 15 Expected, 0 Missed | 15 Expected |
| Clean run | no | yes | yes |

## Running the fixture

```bash
cd fixtures/mui4-app-holdout
npm ci
npm run verify   # tsc --noEmit, eslint --max-warnings 0, jest
```

On v4 everything passes, with Material UI 4.12's own deprecation warnings (`createMuiTheme`, `withMobileDialog`, `variant="circle"`, `variant="static"`, `padding="default"`, `rowsMax`): 4.12 already warns about most of the rules traps, and about one agent trap (`withMobileDialog`).

The case pins Node 20. The fixture was built and checked on Node 24.14.0 with npm 11.9.0.
