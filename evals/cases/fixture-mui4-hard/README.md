# Fixture case: `fixture-mui4-hard`

The fixture is [`fixtures/mui4-app-hard`](../../../fixtures/mui4-app-hard): a small issue tracker in React 17 + TypeScript 4.9 on Material UI v4 (`@material-ui/core` 4.12.4, `@material-ui/lab` 4.0.0-alpha.61), written on purpose as a second **dev** case with harder agent traps. On the first fixture (`fixture-mui4`), Opus 5.5 at low effort already fixes all 9 agent traps (`docs/results/opus-low-fixture-r2/`), so quality there has no headroom left to climb; this case gives it some.

As for `fixture-mui4`, this README and `traps.yaml` live here, outside the fixture: everything in `fixtures/mui4-app-hard/` is copied into the run's workspace, where the repair agent's `read_file` can reach it, so nothing in the fixture describes the traps (`tests/test_fixture_hard.py` checks this). The fixture has a neutral README of its own.

## What's in the fixture

- `src/screens/`: 6 screens: Board (status tabs and cards), IssueList (table with pagination and loading skeletons), IssueDetail (label picker, comment dialog, undo snackbar), NewIssueDialog (assignee and reviewer pickers, an estimate field with a custom input), Activity (feed with focus management), Reports (range slider, toggle buttons, pagination).
- `src/components/`: the shared pieces those screens import: `LabelPicker`, `personPicker` (shared Autocomplete props), `DurationInput` (a custom `inputComponent`), `dialogFocus` (a helper that spreads Dialog props), `RangeSlider` (a Slider wrapper), `StatusChip` (a `withStyles` Chip).
- `src/theme.ts` (with v4 `props`/`overrides`), `src/App.tsx` (`AppProviders`), `src/data/`.
- `src/screens/__tests__/`: one Testing Library behaviour test file per screen, 16 tests. `src/test-utils.tsx` is a Test file (imported only by tests).
- `CODEOWNERS` for the usage report.

## Traps

15 planted traps (revision 1), each one instance of a breaking change from the vendored v5.18.0 guide:

| Expected layer | Count | What it means |
|---|---|---|
| Rules | 6 | The four official codemods fix it |
| Agent | 9 | The codemods miss or mishandle it, and verify fails after the Baseline |
| Human | 0 | (fixture-mui4 has the human-only trap) |

| Agent trap | Breaking change (guide section) | Caught by | Where the fix goes | Why it is hard |
|---|---|---|---|---|
| `theme-state-selector` | Migrate theme styleOverrides to Emotion › Replace state class names | Board test (computed font-weight) only | `src/theme.ts`, imported by the failing Board | Silent: `'&$selected'` type-checks and doesn't crash; Emotion just matches nothing. The failing screen looks fine. |
| `autocomplete-reason-names` | Autocomplete › Rename reason arguments | 2 IssueDetail tests only | `src/components/LabelPicker.tsx` | The reasons key a `Record<string, …>`, so TypeScript can't flag the old names; labels still change, only the announcement and Undo vanish. |
| `dialog-transition-spread` | Dialog › ✅ Update transition props | IssueDetail focus test only | `src/components/dialogFocus.ts` | Guide says ✅ and the literal case *is* handled (`dialog-transition-literal`); a JSX spread hides it from the codemod and from excess-property checks. |
| `option-equal-spread` | Autocomplete › ✅ Rename getOptionSelected | NewIssueDialog test (aria-selected) only | `src/components/personPicker.ts` | Same ✅ pattern through a shared props object; v5 falls back to identity, which only matters because the signed-in user is a different object. |
| `input-component-ref` | TextField › Forward ref instead of inputRef prop | NewIssueDialog test (estimate read back as `''`) only | `src/components/DurationInput.tsx` | `InputBaseComponentProps` has an index signature, so `props.inputRef` still type-checks; needs `forwardRef`. Shares the screen with `option-equal-spread`: two unrelated causes, two imported files. |
| `root-ref-removed` | RootRef › Remove component | typecheck + lint + Activity focus test | `src/screens/Activity.tsx` | preset-safe turns `<RootRef>` into `<>`, silently dropping the ref; removing the dead import clears tsc and lint but not the test; the ref must move to `List` and be retyped `HTMLUListElement` (ref type specificity). |
| `slider-event-type` | Slider › Update event type (TypeScript) | typecheck | `src/components/RangeSlider.tsx` (failing file of its own, repaired before its caller) | A public prop type of a shared wrapper; the fix must not break `Reports`. |
| `table-pagination-labels` | TablePagination › Customize labels with getItemAriaLabel prop | typecheck + IssueList test | `src/screens/IssueList.tsx` | Deleting the flagged props clears tsc but loses the labels the test finds the buttons by. |
| `chip-variant-wrapped` | Chip › ✅ Rename default to filled | typecheck | `src/components/StatusChip.tsx` | The easy one: a `withStyles` wrapper hides the `Chip` from the codemod. |

Five agent traps are caught only by a behaviour test (type-check and lint pass), five have their fix in a shared module one import away from the failing screen (two more in shared wrappers that fail on their own), and every fix is small (each under the hand-off size limit; `DurationInput` gets `forwardRef` around its existing function rather than a re-indented rewrite, which would be over 40% of that small file). None needs JSS to move off `@mui/styles`.

The rules traps are `create-theme`, `pagination-import`, `pagination-round`, `skeleton-rect`, `dialog-transition-literal` and `autocomplete-option-equal-literal`; the last two are the literal-prop controls for the two spread traps.

Each fix is in [`reference/agent-fixes.yaml`](reference/agent-fixes.yaml), grouped by the failing file whose repair makes it. Where a fix in the failing screen instead of the shared module also works (`dialog-transition-spread`, for one), the trap scores Other layer, as the notes in [`traps.yaml`](traps.yaml) say. The oracle test replays the reference through the whole graph with a scripted model (`tests/test_oracle_hard_slow.py`): clean run, 9/9 agent traps Expected, no guardrail tripped.

## Baseline

Rules only (`docs/results/baseline-hard/`): 13 failures in 7 files, 5 of 12 affected files migrated without a human, 6 rules traps Expected and 9 agent traps Missed.

## Running the fixture

```bash
cd fixtures/mui4-app-hard
npm ci
npm run verify   # tsc --noEmit, eslint --max-warnings 0, jest
```

On v4 everything passes. The test output includes Material UI 4.12's own deprecation warnings (`createMuiTheme`, `RootRef`, Dialog `onEntered`, TextField `rows`); they are expected.

Built and checked on Node 24.14.0 with npm 11.9.0; the case pins Node 20.
