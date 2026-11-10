# M7 notes: Angular Material legacy → MDC

Decisions and open questions collected before M7 is planned. M7 gets its own planning round after M6, so that M6's lessons on scoring real code shape it.

## Decided

- **Writing a migration spec gets tooling** (10 November 2026). An app developer never writes `migration.toml`: it ships with the Migrator, one per supported migration, and `migrator init` (built in M6) writes the per-repo `migrate.toml`. Contributors who add a new migration get:
  - `migrator spec new <name>`: a folder with a commented `migration.toml` template;
  - `migrator spec check`: validates a spec (the guide loads and splits into sections, the codemods or schematics resolve, the pins exist);
  - an `add-migration` Claude Code skill that drives the research (guide source and version, codemods and their order, pins, repair notes), fills in the spec, runs `spec check` and a Baseline on a sample repo. The rules live in the CLI; the skill only guides.
  The Angular spec is written with these tools, so M7 is their first real use.

- **Three model levels, independent of provider** (10 November 2026). Built after M6 and before M7, as part of the setup work with `migrator init`. M6 keeps its frozen configuration.
  - The configuration names roles, never a model: **strong** (the repair agent; Claude: Opus 5.5), **balanced** (the test-fitting reviewer and the eval judge; Claude: Sonnet 5.5) and **fast** (cheap helper tasks; Claude: Haiku 5.5). Any provider fills the same three levels in LangChain's `provider:model` form.
  - **balanced must be a different model from strong**, so no role reviews or judges its own model's work. The eval judge therefore moves from Opus to the balanced level, and is re-checked against the owner's ratings when it does.
  - **Every model needs a price.** The cost cap can't work without one, so the Migrator refuses to run a model with no price rather than run without a cap.
  - **Provider features are declared, not assumed:** effort levels, prompt caching, strict tool schemas. Where a model lacks one, the Migrator turns it off and says so, rather than failing mid-run.
  - M7 is the first chance to test it with a model outside Claude, if the owner wants that.

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
