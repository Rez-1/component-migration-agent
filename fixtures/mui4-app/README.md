# mui4-fixture-app

A small React 17 + TypeScript 4.9 app written against Material UI v4 (`@material-ui/core` 4.12.4) **on purpose**. It is the Migrator's fixture: a target repo with known answers, used by the fixture case `evals/cases/fixture-mui4/` and by CI's Baseline integration test. Do not migrate it in place; runs copy it into a workspace.

## What's in it

- `src/screens/`: 10 screens (Dashboard, UsersTable, Settings, AccountDialog, ProfileCard, Search, Faq, Notifications, ResponsiveNav, ProfileForm), written the way a v4 app was: `makeStyles` JSS, theme `props`/`overrides`, `Grid`, `Box` system props, `Autocomplete` from the lab.
- `src/theme.ts`, `src/App.tsx` (with `AppProviders`, the theme shell), `src/index.tsx`, `src/data/`.
- `src/screens/__tests__/`: one Testing Library behaviour test file per screen (19 tests).
- `src/test-utils.tsx`: test helpers (`renderScreen` inside the app shell, `renderComponent` bare, `mockViewportWidth`). It is imported only by tests, so it counts as a **Test file** and the repair agent can't edit it.
- `CODEOWNERS`: teams for the usage report.

## Traps

22 planted traps, each one instance of a breaking change from the official v4 → v5 guide, with the layer expected to handle it:

| Expected layer | Count | What it means |
|---|---|---|
| Rules | 12 | The four official codemods fix it |
| Agent | 8 | The codemods miss or mishandle it, and verify fails after the Baseline (type-check or a test) |
| Human | 1 | The fix belongs in a Test file, so the repair agent should hand it off |
| Visual only | 1 | No check catches it; not scored |

The full list, with guide sections, locations, what catches each one and the results of a hand-run Baseline preview, is in [`evals/cases/fixture-mui4/traps.yaml`](../../evals/cases/fixture-mui4/traps.yaml). Don't move code around without updating the line numbers there.

## Running it

```bash
npm ci
npm run verify   # tsc --noEmit, eslint --max-warnings 0, jest
```

On v4 everything passes. The test output includes Material UI 4.12's own deprecation warnings (`createMuiTheme`, `fade`, `justify`, `ExpansionPanel`, `disableBackdropClick`). They are expected: 4.12 already warns about most of what the traps plant.

The case pins Node 20. The fixture was built and checked on Node 24.14.0 with npm 11.9.0.
