# Fixture case: `fixture-angular15`

The fixture is [`fixtures/angular15-app`](../../../fixtures/angular15-app): a small issue-tracker app ("triage board") on Angular 15.2 and Angular Material 15.2, with every Material import on the `@angular/material/legacy-*` entry points, the way `ng update` to 15 leaves an app. It is the Angular migration's target repo with known answers. Don't migrate it in place: runs copy it into a workspace.

This README lives here, outside the fixture, on purpose. Everything in the fixture is copied into each run's workspace, where the repair agent can read it, so nothing in the fixture may describe the traps.

## What's in the fixture

- **Pages:** 10 components behind 5 routes (issues, issue detail, board, team, settings), plus a dialog.
- **A shared layer:** a `SharedModule` that re-exports a `MaterialModule` of 16 legacy modules, a `search-box` wrapper around a form field and a `confirm-button` wrapper around a button.
- **Theming:** a custom theme (`src/app/theme/_triage-theme.scss`) with legacy theme and typography mixins in `src/styles.scss`, and `::ng-deep` overrides of legacy internal classes in four component stylesheets.
- **An inline template** (`label-editor.component.ts`) and an inline stylesheet (`app.component.ts`).
- **Tests:** 30 Karma/Jasmine specs in 11 files, in a fixed order; `ng lint` with angular-eslint.

## Traps

21 planted traps (revision 2), each one instance of a change from the official MDC migration guide, with the layer expected to handle it:

| Expected layer | Count | What it means |
|---|---|---|
| Rules | 9 | The `mdc-migration` schematic handles it |
| Agent | 11 | The schematic misses it, mishandles it, or leaves a note for it; a check fails after the Baseline (`ng build`, a spec, or a leftover) |
| Human | 1 | The fix belongs in a spec, a Test file, so the agent should hand it off |

Four agent traps are stylesheet rules on legacy internal classes, which the schematic marks with `TODO(mdc-migration)`. These were visual-only in revision 1. On 11 November the owner decided the agent resolves these notes, so they became agent traps. One of them is a false alarm: a rule on `<mat-radio-button>` itself, which MDC keeps. Its right fix removes only the note.

The full list, with guide sections, locations, what catches each one and the Baseline preview, is in [`traps.yaml`](traps.yaml). The known-good fixes are in [`reference/`](reference/): `agent-fixes.yaml` (find-and-replace edits per failing file) and `human-fix.yaml` (the spec change).

Oracle check (11 November): Baseline, then every reference fix and the human fix, leaves 0 failures. All 30 specs pass, lint is clean, and there are no leftovers or stale rules.

## Running the fixture

Node 18 (Angular 15 supports 14.20, 16.13 and 18.10 or later):

```bash
cd fixtures/angular15-app
npm ci
npx ng build && npx ng lint && npx ng test --watch=false --browsers=ChromeHeadlessCI
```
