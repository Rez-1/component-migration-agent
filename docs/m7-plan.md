# M7 plan: Angular Material legacy → MDC

Agreed with the project owner on 11 November 2026, in two planning rounds. This is the brief for the session that builds M7. Words in **bold** are defined in [`CONTEXT.md`](../CONTEXT.md). The research is in [`research/m7-candidate-repos.md`](research/m7-candidate-repos.md) (the repos) and [`research/m7-angular-tooling.md`](research/m7-angular-tooling.md) (the schematic, readers, Docker, template parsing, the visual check, and where the code is tied to MUI). Decisions made before planning are in [`m7-notes.md`](m7-notes.md).

## Why M7

Everything so far is one library: MUI v4 → v5, in React and TSX. The README says "a second library plugs in without code changes", but nothing has proved it. M7 adds a second **migration** in a different framework: Angular Material's legacy components → the MDC-based ones (`ng generate @angular/material:mdc-migration`). It is a hard second case for three reasons:
- most usage lives in HTML templates and SCSS, not in TypeScript;
- the deterministic layer is an Angular schematic, not a jscodeshift codemod;
- the migration is mostly styling (`.mat-*` → `.mat-mdc-*`, density, typography, theme mixins), which type-check, lint and tests barely see.

Wherever M7 needs code changes outside the spec, that is a finding to report honestly. It is not something to hide.

## Done means

- The Angular **migration spec** (`migrations/angular-material-legacy-to-mdc/migration.toml`) is written with `migrator spec new`, checked with `migrator spec check` and the `add-migration` skill. It is the tools' first real use.
- **One Angular fixture** with traps (dev only) runs end to end: Baseline, then the agent.
- **3 real repos**, 2 runs each, with the frozen M7 configuration and the Baseline:
  - **dev:** [MaibornWolff/codecharta#3226](https://github.com/MaibornWolff/codecharta/pull/3226) `visualization/` (Angular 15.1, all legacy, Jest, 77% of Material components have a spec) and [kubermatic/dashboard#6629](https://github.com/kubermatic/dashboard/pull/6629) `modules/web/` (Angular 16, Jest, about 12% covered, 225 SCSS selectors on internal classes MDC removes);
  - **held-out:** [valitydev/dashboard#127](https://github.com/valitydev/dashboard/pull/127) (Angular 15.2, Karma, migrated by hand, about 20% covered). Fallback: [Health-Education-England/tis-revalidation-v2#1255](https://github.com/Health-Education-England/tis-revalidation-v2/pull/1255).
- **The visual check** works on the MUI fixtures and at least one M6 repo, and then on the Angular cases.
- README results next to the Baseline, with the same caveats as M6. **All three reference PRs were merged in 2023–2024, before the model's training cutoff** (no clean post-June-2026 PR exists), so "matches" is an upper bound.
- A fork PR only if budget is left, and only with the owner's OK.

## Scope

- **Legacy → MDC on Angular 15 or 16.** Both ship the `legacy-*` entry points and the same schematic; the guide is [`guides/v15-mdc-migration.md`](https://github.com/angular/components/blob/15.2.9/guides/v15-mdc-migration.md) pinned at tag `15.2.9`. The schematic runs from the repo's own installed `@angular/material`.
- **The v14 → v15 `ng update` is out of scope.** A case starts from a repo already on 15 or 16. If a reference PR also did the bump, the case starts at the bumped commit, or the bump is a human-written dependency step in `case.toml`; otherwise the case is skipped.
- **Detection** checks usage (legacy imports or `mat.legacy-*` mixins). The major version alone can't tell legacy from MDC.

## Setup first (after M6, before Angular)

From [`m7-notes.md`](m7-notes.md):
- **Three model levels, independent of provider:** **strong** (repair; Claude: Opus 5.5), **balanced** (the test-fitting reviewer and the eval judge; Sonnet 5.5) and **fast** (cheap helpers; Haiku 5.5), in LangChain's `provider:model` form. **balanced must differ from strong.** M6's configuration files stay frozen.
- **Every model needs a price**, or the Migrator refuses to run it. **Provider features are declared**: effort, prompt caching, strict tool schemas. A missing feature is turned off and reported, never a mid-run failure.
- **Proved with unit tests and a fake provider.** A paid run on another provider is a stretch goal, and needs the owner's key and approval.
- **The judge moves to Sonnet 5.5.** It is re-checked on the 20 OpossumUI items the owner already rated blind, with the labels shown (as in round 2). Opus agreed on 10 of 17. If Sonnet agrees on 8 or fewer, the owner sees the disagreements before it judges anything in M7. M6's README numbers stay on the Opus judge.
  - **Result (11 November, $0.12):** Sonnet agreed on 7 of 17, Opus on 10. But on *wrong* vs *not wrong*, the split that decides silent misses, Sonnet agreed on 14 of 17 and Opus on 11. Seven of Sonnet's ten disagreements are *matches* vs *other valid fix*. Its real miss: it called the two `describeChild` test-fitting patches harmless.
  - **The owner's decision:** Sonnet is the M7 judge, with the j2 prompt unchanged (no tuning on the 17 check items). Every M7 result reports the judge's agreement with the owner on *wrong* vs *not wrong* next to the four-way count. The README names the `describeChild` weakness.

## Spec tooling

- `migrator spec new <name>`: a folder with a commented `migration.toml` template.
- `migrator spec check`: the guide loads and splits into sections, the codemods or schematics resolve, and the pins exist.
- An `add-migration` Claude Code skill that drives the research, fills in the spec, runs `spec check` and runs a Baseline on a sample repo. **The rules live in the CLI; the skill only guides.**

## The visual check (built on MUI first)

- A static build is served and Playwright (Python) takes screenshots of a **hand-picked list of pages in `case.toml`** (or `migrate.toml`). A pixel diff (odiff or pixelmatch) compares them. Network calls are stubbed. Fonts, animations and the clock are pinned, so the screenshots are stable.
- **In evals**, the run's build is compared with the **reference PR's own build**: before vs after mostly shows MDC's new spacing everywhere. **In real runs**, the reviewer sees ranked before/after pairs.
- **A visual difference is not a verdict.** It flags the page and the files behind it as **visual changes to review** in the scorecard and PR, like M6's snapshots to review, and it is evidence for the judge.
- Built on the MUI fixtures first (`fixture-mui4` has a visual-only trap), then on whichever M6 dev repo serves offline with the least work. **If serving a real repo takes more than about a day, v1 covers only repos that serve offline**, and the README says so. Estimate: 4–6 days.

## Angular plumbing

- **Template scanning:** pin `tree-sitter-angular` v0.9.2 from git (`tree-sitter-html` breaks on `{{ }}`). Inline `template:` strings are parsed with positions shifted into the `.ts` file. **Usages** now include template elements and attributes (`<mat-…>`, `mat-button`) and SCSS mixins and selectors.
- **A `schematic` rule step kind:** it runs `ng generate @angular/material:mdc-migration --components=all --interactive=false` exactly once (not idempotent) and reads its log, because it exits 0 even when it fails. "Failed to process" lines for single files send those files to repair. "Unable to migrate project" is a **Rules failure**. `TODO(mdc-migration)` comments count as **Codemod TODOs**. `ToolsConfig` becomes optional, since the schematic comes from the repo.
- **Readers:**
  - type-check: `ng build`, with a new reader for template errors (`file.html:l:c - error NG8001`) and Sass errors (`tsc` does not check templates);
  - lint: `ng lint` in ESLint's JSON format, when the repo has a lint target;
  - Karma: a wrapper config in `.migrator/` (headless Chrome with `--no-sandbox`, an inline JSON reporter, `--include` for narrow runs), so the repo's own config is never edited. Unknown-element console errors (`NG0304`) count as failures;
  - Jest (jest-preset-angular): the existing reader.
- **Docker:** images keyed by (Node, browser): Node plus Debian's Chromium, **built locally from a Dockerfile and keyed by its hash**. Nothing is pushed to a registry. Add a Node 18 pin.
- **A component is one repair unit:** a failing component's `.ts`, `.html` and `.scss` are repaired together. The patch size limit applies to all three together.
- **Guardrails:**
  - new escape hatches: `NO_ERRORS_SCHEMA`, `CUSTOM_ELEMENTS_SCHEMA` and `$any(`;
  - `angular.json` and `karma.conf.*` can't be written;
  - `::ng-deep` stays allowed, because real migrations use it;
  - specs that query internal `.mat-*` classes are handed off with a suggested test change, with the balanced-level reviewer on flagged patches, as in M6;
  - test-file detection learns Karma (`*.spec.ts`, `test.ts`) and jest-preset-angular configs.
- **Prompts:** the reviewer and judge prompts lose their hard-coded MUI wording and take it from the spec. The guide lookup maps module paths and template tags to `###` component sections under "Comprehensive List of Changes".
- **`migrator init`** learns `angular.json`: projects, build/test/lint targets, the Karma or Jest runner.

## The Angular fixture

- About 10 components on Angular 15 with legacy imports, Karma/Jasmine (so the Karma reader is built and tested on dev, not first on the held-out repo), a custom theme SCSS, `::ng-deep .mat-*` overrides, a shared wrapper component, an inline template, specs that query `.mat-` classes, and one human-only trap. Rules, agent and human traps, as in M3–M5.
- A visual-only trap, such as an internal-class override that silently stops styling, so the visual check has a known answer.

## Scoring against a reference PR

As in M6, with the items widened for Angular:
- **Scoring items:** every `.ts`, `.html` and `.scss` file the reference PR changed that is tied to Material. That means it imports it, uses `mat-` in a template, or has `.mat-*` selectors or Material mixins. SCSS files are items because styling is most of this migration.
- The four results: *matches*, *other valid fix*, *wrong* and *untouched*. The judge labels each change in the PR first. **Missing v5-style compensation (here: MDC compensation) counts as wrong.**
- **Out-of-scope hunks** are listed and ignored. On codecharta, that is the theme colour change and the new logo.
- Test files the PR changed are listed as expected hand-offs.
- **The owner rates about 15 codecharta items blind** on the M6 rating page after the first dev repo runs, because SCSS-heavy items are new to the judge.

## Budget

- **$30 for all of M7.** New M7 configuration files carry **$8 per run** and **$50 per month**. Don't edit M2–M6 configuration files: the caps are part of each digest.
- **Runs must finish.** Each run reserves its whole worst case before it starts, and doesn't start if the budget doesn't cover it. The per-run hard stop is the Migrator's own cost guard.
- Measure the cost of one run on the first real repo before budgeting the others. kubermatic is large.
- Every paid round needs the owner's approval, given directly in the build session. **If a single run exceeds $2, stop and ask.**

## Held-out rules

valitydev is tuned on nothing and runs once, at the end, with the configuration frozen. A fix found from its scores stays out of its table, like wps's †.

## Order of work

1. **Setup:** three model levels, prices, declared features; the Sonnet judge re-check (cents, with approval).
2. **`migrator spec new` / `spec check`** and the `add-migration` skill.
3. **The visual check v1** on the MUI fixtures, then one M6 dev repo.
4. **Angular plumbing:** template scan, schematic step, readers, Chromium image, component repair unit, guardrails, `init`.
5. **The Angular fixture** and its `migration.toml`, written with the skill. Baseline, then the agent.
6. **codecharta, then kubermatic:** Baseline first, measure one run's cost, the owner's ~15 ratings, then the paid dev runs.
7. **valitydev held-out** once; README results with the caveats; the fork PR only if there's budget, with the owner's OK. `docs/blog-log.md` (kept local) is updated at every step.

## Stop and ask the owner

Paid runs, the ratings, any scoring change once results exist, pushing, opening PRs and forking. No API keys in GitHub, and no client names in the repo. Keys live in `~/.config/migrator/anthropic.env` and `langsmith.env` and are never printed. Never commit `docs/blog-log.md` or `docs/project-story.md`. Leave `docs/blog-drafts/` alone.

## Changes while building (11 November)

Recorded here as they happened; none changes a result.

- **Template scanning uses a tokenizer, not tree-sitter-angular.** The grammar's v0.9.2 Python package builds without its external scanner (`setup.py` leaves out `scanner.c`), so it can't be loaded. The scan only needs a template's `mat-*` elements and attributes and where they are, so a small quote-aware tokenizer does it (`scan/assets.py`). Template usages are reported but don't make a file affected: an element doesn't say whether it is legacy or MDC.
- **Leftovers are failures.** Legacy code still compiles in 15 and 16, so a file the schematic didn't migrate would pass every check and count as migrated. With `leftovers_fail`, every Verify after Rules also reports imports of `legacy-*` entry points and `mat.legacy-*` mixins as failures for repair. **The owner's decision (11 November): the schematic's notes are failures too**: `TODO(mdc-migration)` (a stylesheet rule on a legacy internal class, which is where styling compensation lives) and the slider's `TODO: The '...'`. The agent restyles or removes the rule. Deleting only the comment doesn't count: if the rule under it is still unchanged, that is a failure (`stale-rule`). `ng update`'s `TODO(v15)` is out of scope.
- **The repair scope follows Angular's links:** a component, its template and stylesheets, and the module that declares it.
- **The visual check on MUI** covers the fixtures and kubeflow. OpossumUI (an Electron renderer) and wps (behind Keycloak) don't serve offline without heavy stubbing. Kubeflow is served with its own mock API, which lags its frontend, so list pages render an error banner, the same in every capture.
- **Parked for the real-repo scoring step:** the judge prompt and the scoring items are MUI-specific (hunk kinds, the JSS policy, only `.ts` files importing `@mui`). Angular needs its own judge prompt and items that include templates and stylesheets.
