# M7 notes: Angular Material legacy → MDC

Decisions and open questions collected before M7 is planned. M7 gets its own planning round after M6, so that M6's lessons on scoring real code shape it.

## Decided

- **Writing a migration spec gets tooling** (10 November 2026). An app developer never writes `migration.toml`: it ships with the Migrator, one per supported migration, and `migrator init` (built in M6) writes the per-repo `migrate.toml`. Contributors who add a new migration get:
  - `migrator spec new <name>`: a folder with a commented `migration.toml` template;
  - `migrator spec check`: validates a spec (the guide loads and splits into sections, the codemods or schematics resolve, the pins exist);
  - an `add-migration` Claude Code skill that drives the research (guide source and version, codemods and their order, pins, repair notes), fills in the spec, runs `spec check` and a Baseline on a sample repo. The rules live in the CLI; the skill only guides.
  The Angular spec is written with these tools, so M7 is their first real use.

## Already known

- Guide source: Angular's `guides/v15-mdc-migration.md`, pinned to tag `15.2.9` (it is gone from `main`). Its component sections are `###` headings under "Comprehensive List of Changes", with no codemod markers (see `research/migration-guide-source.md`).
- The migration runs as a schematic (`ng generate @angular/material:mdc-migration`), which leaves TODO comments where it gives up.

## To build

- Scanning Angular HTML templates, where most Angular Material usage lives.
- A rule step type for Angular schematics.
- Readers for `ng build` and the test runners Angular apps use (often Karma/Jasmine in headless Chrome, inside Docker).
- An Angular fixture app with traps, and real Angular 14/15 repos that migrated in one reviewable PR.

## Open

- **A visual check** (screenshots before and after, compared automatically). The MDC migration is mostly styling: class names (`.mat-*` → `.mat-mdc-*`), density, typography, theme SCSS. Verify sees almost none of it, and missing v5-style compensation counts as *wrong* (the owner's rule, decided in M6). Recommended: yes, possibly built first for MUI as part of finishing M6, then reused.
