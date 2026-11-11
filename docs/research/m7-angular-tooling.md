# M7 research: Angular tooling for the legacy → MDC migration

Research for M7 (Angular Material legacy → MDC, Angular 15). Checked on 2026-11-11 against the angular/components source at tag `15.2.9`, npm and PyPI. Where a fact comes from memory of the tools rather than a source read today, it says **(check on the fixture)**.

Sources read:

- Schematic: [`src/material/schematics/ng-generate/mdc-migration/`](https://github.com/angular/components/tree/15.2.9/src/material/schematics/ng-generate/mdc-migration) at 15.2.9: `index.ts`, `schema.json`, `rules/index.ts`, `rules/theming-styles.ts`, `rules/template-migration.ts`, `rules/tree-traversal.ts`, `rules/ts-migration/runtime-migration.ts`, and the component rules for button, card, chips, form-field, slider and typography-hierarchy.
- The v15 update migration: [`src/material/schematics/ng-update/migrations/legacy-components-v15/index.ts`](https://github.com/angular/components/blob/15.2.9/src/material/schematics/ng-update/migrations/legacy-components-v15/index.ts) and [`migration.json`](https://github.com/angular/components/blob/15.2.9/src/material/schematics/migration.json).
- The guide: [`guides/v15-mdc-migration.md`](https://github.com/angular/components/blob/15.2.9/guides/v15-mdc-migration.md) at 15.2.9.
- npm: `@angular/cli@15.2.11`, `@angular/core@15.2.10`, `@angular/material@15.2.9`, `karma-junit-reporter`, `odiff-bin`, `pixelmatch`, `playwright`.
- PyPI: `tree-sitter-html`, `tree-sitter-language-pack`, `tree-sitter-angular` (not there); GitHub `dlvandenberg/tree-sitter-angular`.
- This repo: `src/migrator/{scan,verify,repair,checks,migrations}/`, `rules.py`, `execs.py`, `false_positives.py`, `init.py`, `configuration.py`, `cost.py`, `evals/reference.py`, `pipeline.py`.

## 1. The mdc-migration schematic

### How it is invoked

- The command is `ng generate @angular/material:mdc-migration`. The collection entry is `mdcMigration`, alias `mdc-migration`, in `src/material/schematics/collection.json`.
- It has **two options only**: `--components` (an array) and `--directory` (alias `-d`). There is **no `--tsconfig` option**, at 15.0.0, 15.2.9 or 16.2.14.
- `--components` takes `all` or names from this list: autocomplete, button, card, checkbox, chips, dialog, form-field, input, list, menu, optgroup, option, paginator, progress-bar, progress-spinner, radio, select, slide-toggle, slider, snack-bar, table, tabs, tooltip.
- Some components always move together. Asking for any of autocomplete, form-field, input, option, optgroup or select migrates all six (`migrationGroups` in `index.ts`).
- Both options have an `x-prompt`. The CLI only prompts for options you did not pass, and never prompts when stdin is not a TTY or with `--interactive=false`. A blank directory means the whole workspace.
- A non-interactive call: `npx ng generate @angular/material:mdc-migration --components=all --interactive=false`. Add `--directory=src/app/shared` for a partial run. Set `NG_CLI_ANALYTICS=false` so the CLI never asks about analytics **(check on the fixture)**.
- The tsconfig comes from `angular.json`. For every project, the schematic reads the `build` and `test` targets' `tsConfig` (`getTargetTsconfigPath`). A project with neither is skipped with the warning `Skipping migration for project <name>. Unable to determine 'tsconfig.json' file in workspace config.`

### What it needs

- **An Angular CLI workspace.** Without `angular.json` it logs `Could not find workspace configuration file.` and does nothing.
- **`node_modules` installed, with `@angular/material` 15.** `ng generate` loads the collection from the repo's own `node_modules/@angular/material/schematics`. The schematic also imports `@angular/cdk/schematics`, `@angular/compiler` and TypeScript from there.
- It builds a TypeScript program from each tsconfig and uses the type checker to match references to imported symbols. So the repo's types must resolve.
- The `ng` binary can be the repo's own `node_modules/.bin/ng` (the safest choice: the same CLI version as the workspace). `npx @angular/cli@15 generate ...` also works, but it still loads the collection from the repo's `node_modules`, and it downloads the CLI (network). Use the repo's binary.
- Run it from the folder that holds `angular.json` (in a monorepo, the app folder).

### What it rewrites

The schematic runs three migrations over every project (`ThemingStylesMigration`, `TemplateMigration`, `RuntimeCodeMigration`):

- **TypeScript:** import paths and names lose `legacy`. `@angular/material/legacy-button` becomes `@angular/material/button`; `MatLegacyButtonModule` becomes `MatButtonModule`. It renames references to those symbols in the file, and handles `import()` calls and `import('...')` types. It also migrates inline `template:` and `styles:` in `@Component` decorators. Only files in the build and test tsconfigs are seen.
- **Templates** (`templateUrl` files and inline templates, parsed with `@angular/compiler`'s `parseTemplate`):
  - `<mat-form-field appearance="legacy|standard">`: the attribute is removed.
  - `<mat-card>`: gets `appearance="outlined"`.
  - Chips: `<mat-chip-list>` becomes `<mat-chip-grid>` with `<mat-chip-row>` (when it holds an input) or `<mat-chip-listbox>` with `<mat-chip-option>`.
  - Slider: a rewrite to `<mat-slider><input matSliderThumb></mat-slider>`, moving `value` and the `input`/`change` bindings to the input.
  - Typography classes in `class="..."` and `[class.x]` bindings are renamed (`mat-display-4` → `mat-headline-1`, …, `mat-body-1` → `mat-body-2`). This one always runs, whatever `--components` says.
- **Styles** (every `.css` and `.scss` under the project root, plus inline styles; parsed with postcss-scss):
  - Theme mixins: `mat.legacy-button-theme` becomes `mat.button-theme`, `mat.fab-theme` and `mat.icon-button-theme`, and the same for the other components and their `-color` / `-typography` mixins. `mat.all-legacy-component-themes` and `mat.legacy-core` are replaced too.
  - `mat.define-legacy-typography-config` becomes `mat.define-typography-config`, with its levels renamed.
  - Class selectors: `.mat-button` becomes `.mat-mdc-button`, `.mat-stroked-button` becomes `.mat-mdc-outlined-button`, and so on.
- It only touches what is named. It does **not** change component behaviour, sizes or density.

### The TODO comments it leaves (exact text)

| Where | Text |
|---|---|
| SCSS, a rule on a component's internal class (`.mat-button-wrapper`, `.mat-form-field-infix`, …) | `/* TODO(mdc-migration): The following rule targets internal classes of <component> that may no longer apply for the MDC version. */` |
| SCSS, partial migration, a cross-cutting mixin | `/* TODO(mdc-migration): Remove <mixin> once all legacy components are migrated */` |
| SCSS, typography config, the removed `input` level | `/* TODO(mdc-migration): No longer supported. Use \`body-1\` instead. <original> */` |
| HTML, slider (`invert`, `vertical`, `tickInterval`, `valueText`) | `<!-- TODO: The '<name>' property no longer exists -->` |
| HTML, slider `displayValue` | `<!-- TODO: The 'displayValue' property no longer exists. Use 'displayWith' instead. -->` |

- The guide says to search for `TODO(mdc-migration):`. The slider comments **do not** have that tag; they are plain `TODO:` HTML comments.
- `ng update @angular/material@15` leaves its own marker in SCSS: `// TODO(v15): As of v15 mat.legacy-core no longer includes default typography styles.`

### Log lines and exit code

- Failures are logged, not thrown. On a failure it logs `Unable to migrate project. See errors above.` and the command still exits 0.
- Per-file failures: `Failed to process template: <path> (see error above).`, `Failed to process stylesheet: <path> (see error above).` and `Failed to process file: <path> (see error above).` The file is then left as it was.
- Success ends with `Successfully migrated the project.` The CLI prints one `UPDATE <path> (<n> bytes)` line per changed file, and `Nothing to be done.` when nothing changed **(check on the fixture)**.

### Is it idempotent?

**No. Run it exactly once, like the MUI codemods.**

- The typography renames are a chain: `subheading-1` → `body-1` and `body-1` → `body-2`. They run on every run (a "permanent" migrator). A second run turns the `mat-body-1` the first run wrote into `mat-body-2`, in templates and in stylesheets.
- The internal-class TODO comment has no check for an existing one, so a second run adds it again.
- The TS import renames are safe to repeat: names without `legacy` are left alone.

### What it does not migrate

- **Components with no MDC version are out of scope.** They had no `legacy-` entry point in v15: expansion panel, sidenav, toolbar, datepicker, stepper, sort, tree, badge, bottom sheet, button toggle, grid list, icon, divider.
- **Strings in TypeScript.** Class names in test queries (`By.css('.mat-button-wrapper')`, `querySelector('.mat-form-field-infix')`) and in `panelClass` are not changed. Neither are calls to APIs that changed (the guide's "API changes" for chips, list, menu, snack bar and tabs).
- **Styling compensation.** It changes no spacing, size or density. The guide says sizes, colours and spacing "change slightly across the board".
- **Internal-class overrides.** A rule on an internal class gets a TODO, not a fix.
- **Template APIs other than the five above.** For example `floatLabel="never"` on a form field, or list and menu API changes. The guide's "Comprehensive List of Changes" has them; the schematic doesn't.
- **Files outside the build and test tsconfigs.** A template is found only through a component in the program. A stray `.html` is skipped. (Stylesheets are the exception: every `.css`/`.scss` under the project root is processed.)

### What this means for the Migrator

- **A new rule step kind, `schematic`.** The `codemod` step can't run it as it is. It runs `node <tools cache>/<bin>` and parses jscodeshift's `OKK`/`NOC`/`ERR` lines, and it fails when it saw 0 files. The schematic needs the repo's own `ng`, the repo's `node_modules` and the workspace root as cwd. Its success shows in `UPDATE` lines and its failure in `Failed to process …` lines, not in the exit code.
- Suggested shape: `kind = "schematic"`, `collection = "@angular/material"`, `name = "mdc-migration"`, `args = ["--components=all", "--interactive=false"]`. It runs offline, after `install`. `{files}` does not apply; `--directory` can stand in for a partial run.
- **`ToolsConfig` must be optional.** This spec needs no pinned tools workspace.
- **Run once.** The `_codemods_run_once` validator must cover schematic steps, and a resumed run must never re-run it (the typography chain).
- **Codemod TODOs must be found in `.html` and `.scss`.** `find_codemod_todos` uses the TS/TSX tree-sitter parser's comments, so it won't see `<!-- TODO: ... -->` or `/* TODO(mdc-migration) */`. Markers for this spec: `TODO(mdc-migration)`, `TODO(v15)` and the slider's `TODO: The '`.
- Preconditions: `angular.json` exists, and `@angular/material` and `@angular/cdk` are at 15.

## 2. Order of operations

### What a real app does

1. On v14: `ng update @angular/core@15 @angular/cli@15`.
2. `ng update @angular/material@15` (with `@angular/cdk`). Material's `migration-v15` (version `15.0.0-0`) runs and moves the app onto the legacy components:
   - imports move to `legacy-*` and the symbols are aliased so the code keeps its names: `import {MatLegacyButtonModule as MatButtonModule} from '@angular/material/legacy-button'`;
   - `@angular/material/core` imports are split: the legacy symbols (option, optgroup and friends) go to `@angular/material/legacy-core`;
   - SCSS: `mat.button-theme` becomes `mat.legacy-button-theme`, and `mat.core()` becomes `mat.all-legacy-component-typographies`, `mat.legacy-typography-hierarchy` and `mat.legacy-core()`, with a `// TODO(v15)` comment;
   - `@angular/material-experimental/mdc-*` imports move to `@angular/material/*`.
   The app now runs on v15 and looks the same.
3. `ng generate @angular/material:mdc-migration`. Then the TODOs, the tests and the styling by hand.

- `ng update` needs network (it reads the registry and installs), `angular.json`, and a clean git tree unless you pass `--allow-dirty`. It refuses a jump of more than one major.
- Angular 15 supports Node `^14.20.0 || ^16.13.0 || >=18.10.0` (engines of `@angular/core` 15.2.10 and `@angular/cli` 15.2.11). Angular's own compatibility table lists 14, 16 and 18 for v15. Node 18 is the safe choice.

### A repo on 14 vs a repo on 15 with legacy imports

| | v14 | v15, legacy |
|---|---|---|
| `package.json` | `@angular/material` `^14` | `@angular/material` `^15` |
| TS imports | `@angular/material/button`, `MatButtonModule` | `@angular/material/legacy-button`, `MatLegacyButtonModule as MatButtonModule` |
| SCSS | `mat.core()`, `mat.button-theme(...)` | `mat.legacy-core()`, `mat.legacy-button-theme(...)`, `TODO(v15)` comment |
| Templates | unchanged | unchanged (same selectors) |
| DOM and classes | `.mat-button`, `.mat-form-field-*` | the same |

- After the MDC migration, the imports look like v14's again (`@angular/material/button`), but the package is 15 and the DOM is new.
- So **the major version alone doesn't tell old from new.** A v15 app can be legacy, MDC or half and half (the guide allows it per `NgModule`).

### Recommendation for the spec

- **Make M7's spec legacy → MDC on v15 only:** from `angular-material@15-legacy` to `angular-material@15`. It is one version jump with one official tool, like `mui@4 → mui@5`. The Rules stage is the schematic, a format step and nothing else; there is no dependency map.
- Detection needs a usage check, not only a major version: `@angular/material` at 15 **and** at least one import matching `^@angular/material/legacy-` (or a `mat.legacy-` mixin).
- **Leave the v14 → v15 bump for a second spec**, `angular-material@14 → @15-legacy`. It is rules only (`ng update` twice), and it needs network during the Rules stage, which the sandbox allows today only for installs. The two specs could run back to back.
- For eval cases, start real repos at the commit after their `ng update` to 15. Many repos did the bump and the MDC switch in one PR. For those, materialise the case by running `ng update` first and scoring only the MDC part, or wait for the second spec.

### What this means for the Migrator

- `Detection` needs an optional usage pattern (`legacy_modules`) beside `packages` and `major`.
- `id`, `from` and `to` need a form that is not just `<library>@<major>`, such as `angular-material@15-legacy`. `pipeline.default_branch` makes `migrate/angular-material-v15-legacy`-style names from `to`; check it still reads well.
- A `node = "18"` image pin is needed (see topic 4).

## 3. Verify readers

### `ng build`, `tsc` and `ngc`

- **Plain `tsc -p tsconfig.app.json` does not type-check templates.** Only the Angular compiler does: `ng build`, or `ngc -p tsconfig.app.json` from `@angular/compiler-cli`. Template errors are what this migration causes (`'mat-chip-list' is not a known element`), so the type-check must be `ng build` or `ngc`.
- Template diagnostics have `NG` codes. NG8001 is an unknown element, NG8002 an unknown property binding (`Can't bind to 'x' since it isn't a known property of 'y'`), NG8003 an unknown reference target. Type errors inside template expressions come back as `TS` codes with the `.html` file and line.
- `ng build` (webpack builder, Angular 15) prints the pretty format, with the `.html` file and a pointer back to the component **(check on the fixture)**:

  ```
  Error: src/app/tags/tags.component.html:3:5 - error NG8001: 'mat-chip-list' is not a known element:
  1. If 'mat-chip-list' is an Angular component, then verify that it is part of this module.
  ...

    src/app/tags/tags.component.ts:6:16
      6   templateUrl: './tags.component.html',
                       ~~~~~~~~~~~~~~~~~~~~~~~
      Error occurs in the template of component TagsComponent.
  ```

- TS errors in `ng build` use the same `file:line:col - error TSnnnn:` form, also prefixed `Error: `.
- Sass errors look different. They start `./src/styles.scss - Error: Module build failed (from ./node_modules/sass-loader/...)`, then `SassError: <message>`, a code frame with `╷ │ ╵`, and a location line `  src/styles.scss 12:3  root stylesheet`. They matter here because the schematic rewrites theme mixins.
- For speed, `ngc -p tsconfig.app.json` type-checks without bundling. Whether it honours `--noEmit` on 15, and which of the two formats it prints, should be checked on the fixture. Pointing `--outDir` into `.migrator/` works either way.
- `ng build` with `"aot": true` (the default since v12) runs full template checks. With `strictTemplates` off ("basic" or "full" mode), unknown elements and properties are still reported, but fewer expression types are checked.

### `ng lint` (angular-eslint)

- `ng lint` only works when `angular.json` has a `lint` target, usually `@angular-eslint/builder:lint`. Without one, the CLI offers to add angular-eslint, which a non-TTY run can't answer. `migrator init` must check for the target first.
- The builder takes `--format json` and `--output-file <path>` (also `--force` and `--max-warnings`). The JSON is ESLint's own format, so `parse_eslint_json` reads it.
- Template rules run on `.html` files through `@angular-eslint/template-parser`, so lint failures can be in templates. Their `filePath` is the `.html`.
- Older repos may still have TSLint, which `ng lint` no longer runs since v12. Treat that as "no lint".

### Karma + Jasmine

- `ng test` runs Karma through the `@angular-devkit/build-angular:karma` builder. Useful flags on 15: `--watch=false`, `--browsers=ChromeHeadless`, `--karma-config=<file>`, `--include=<glob>` (run only some spec files), `--code-coverage`, `--source-map`.
- **Chrome in Docker needs `--no-sandbox`.** The container drops all capabilities and sets `no-new-privileges`, so Chrome's own sandbox can't start. It also needs `--disable-dev-shm-usage` (or a bigger `--shm-size`), because Docker's `/dev/shm` is 64 MB.
- Many repos only list `browsers: ['Chrome']` in `karma.conf.js`. Some set `process.env.CHROME_BIN = require('puppeteer').executablePath()`. Puppeteer downloads Chrome on install, has no Linux arm64 build, and keeps it under `HOME` (which is `/tmp` in our containers and is thrown away).
- **Getting per-test results without editing the repo's config.** Configs are guarded, so the Migrator should not touch `karma.conf.js`. Instead, write a wrapper in `.migrator/karma.migrator.cjs`:
  - it `require`s the repo's `karma.conf.js` and calls it with `config`;
  - it sets `browsers` to a custom launcher based on `ChromeHeadless` with `--no-sandbox --disable-dev-shm-usage`, `singleRun: true`, and resets `CHROME_BIN` to the image's Chromium;
  - it adds a small inline reporter. A Karma reporter is an object with `onSpecComplete(browser, result)` (`result.suite` is the describe chain, `result.description` the `it`, `result.success`, `result.skipped`, `result.log` the failure messages with stacks) and `onBrowserLog`. It writes one JSON file, like Jest's `--json`.
  - Run it as `ng test --watch=false --karma-config=.migrator/karma.migrator.cjs`.
  - This needs no npm package. `karma-junit-reporter` 2.0.1 (last published 2022) gives JUnit XML, but it must be installed and its test cases have no file path either.
- **Mapping a failing test to its spec file.** Karma runs one webpack bundle, so results carry no file path. Three ways, best first:
  1. the failure's stack: with source maps on (the default for `ng test`), frames point at the spec, such as `at UserContext.<anonymous> (src/app/tags/tags.component.spec.ts:31:22)` **(check the exact frame text on the fixture)**;
  2. the top-level `describe('TagsComponent', ...)` name, looked up in the `*.spec.ts` files with tree-sitter (names are nearly always unique);
  3. to be sure, re-run with `--include=<that spec>`. This is also how `run_verify` can run only the related tests, in place of Jest's `--findRelatedTests`.
- **Unknown elements in tests are not failures by default.** In TestBed, `'mat-chip-list' is not a known element` is a console error (`NG0304`), not a thrown error, unless the repo set `errorOnUnknownElements: true` (added in v14). The reporter should collect browser console lines with `NG0303`/`NG0304` and report them as failures of that spec's component, or the tests will pass on a broken template.
- When the test bundle fails to compile, Karma runs no tests. The compile errors print in the `ng build` format above, so the same parser reads them.
- Coverage: `--code-coverage` with `karma-coverage` (in the default Angular 15 config). The wrapper can add a `json-summary` reporter so `read_coverage` keeps working.

### Jest (jest-preset-angular)

- `jest-preset-angular` (13.x for Angular 15) runs Angular tests under Jest with jsdom. `jest --json --outputFile=... --testLocationInResults` works as it does now, and `testResults[].name` is the spec file.
- Some repos run Jest through `ng test` with `@angular-builders/jest`. Whether that builder passes `--json` through should be checked on a real repo. Calling `npx jest` directly is safer.
- The same `NG0304` console-error point applies.

### What this means for the Migrator

- `parse_tsc` only matches `file(line,col): error TSnnnn:`. It needs the pretty form `file:line:col - error (TS|NG)nnnn:` with an optional `Error: ` prefix, `NG` codes, and the indented `Error occurs in the template of component X` block (which names the `.ts`).
- A Sass error reader: the message from `SassError:` and the file from the `path line:col  root stylesheet` line.
- `Runner` is `Literal["jest", "vitest"]`. It needs `"karma"`, with the wrapper config, the JSON reporter, `--include` for narrow runs and the console-error rule.
- `migrator init` detects runners from `jest`, `vitest` or `react-scripts` in `package.json`, and the type-check from `tsc` scripts. For Angular it must read `angular.json`: `architect.build`, `architect.test.builder` (karma or jest), `architect.lint`. The type-check default becomes `ng build` (or `ngc -p <build tsConfig>`), not `npx tsc --noEmit`.
- `incremental_typecheck` rewrites `tsc` calls; it does nothing for `ng build`. A full `ng build` of a mid-size app takes about 0.5–2 minutes, so the `ngc` path is worth measuring.
- `subject_candidates` maps `x.component.spec.ts` to `x.component.ts`, which is right. But template failures land on `x.component.html` and style failures on `x.component.scss`, so Repair needs the component's three files as one unit (topic 7).

## 4. Docker

### Which image

- The pinned `node:*-bookworm-slim` images have no browser. Options for headless Chrome:
  - **`node:18-bookworm-slim` + Debian's `chromium` package** (`apt-get install chromium fonts-liberation`). Debian builds Chromium for amd64 and arm64, so it runs on Apple Silicon too. Google Chrome has no Linux arm64 build. Roughly 230 MB for the base plus 350–400 MB for Chromium and its libraries on disk **(estimate)**. `CHROME_BIN=/usr/bin/chromium`.
  - `zenika/alpine-chrome:with-node`: small (about 200 MB compressed), popular for Karma in CI. But it is musl-based, and its Node version is fixed by the image, which doesn't fit "Node by major".
  - `mcr.microsoft.com/playwright:v1.x-jammy`: Node plus Chromium, Firefox and WebKit with fonts, about 2 GB. Too big for verify, but it is the natural image for a visual check (topic 6).
- Recommended: **one Dockerfile per (Node major, browser)**, starting `FROM node:18.x-bookworm-slim@sha256:...`, installing `chromium` and adding a wrapper `/usr/local/bin/chromium-ci` that runs `chromium --no-sandbox --disable-dev-shm-usage "$@"`. Set `CHROME_BIN=/usr/local/bin/chromium-ci`. Then even a repo's own `browsers: ['ChromeHeadless']` works unchanged. Pin the Debian packages through `snapshot.debian.org` so a rebuild gives the same Chromium.

### Can the current sandbox take it?

- `execs.py` keys images by Node major only: `NODE_IMAGES = {"16": ..., "20": ..., "22": ...}`, each a `node:*-bookworm-slim` pinned by digest. `node_image(node)` picks one from the RepoConfig's `node`, and `DockerRunner.check()` pulls it if missing. There is no image build step.
- M6 added Node 16 and 22 the same way: a new digest in the dict. That works for Node 18, but not for "Node 18 with Chromium", which is not an image on Docker Hub.
- What fits the existing design:
  - The key becomes (node major, extras), for example `("18", "chromium")`, from the RepoConfig (`node = "18"`, `browser = "chromium"`), or from the runner (karma means chromium).
  - The image is either built locally from a Dockerfile shipped in the repo (tagged by the Dockerfile's hash, built on first use with network, then reused), or built once and pushed to a registry and pinned by digest like the others. The second keeps "pull by digest" and is simpler to trust.
- Under the current flags:
  - `--read-only` root and `HOME=/tmp` on a tmpfs: Chromium writes its profile to a temp dir, which is fine.
  - `--network none`: Karma's server and the browser talk over loopback inside the container, which works without a network. Fonts from `fonts.googleapis.com` won't load. That doesn't matter for Karma, but it does for screenshots.
  - `--cap-drop ALL` and `no-new-privileges`: this is why `--no-sandbox` is needed. Don't add capabilities.
  - `/dev/shm` is 64 MB: use `--disable-dev-shm-usage`, or add `shm_size` to `DockerLimits`.
  - `--memory 4g` is enough for a Karma run of a mid-size app with one Chrome **(check on the fixture)**.
  - `RunContainerRunner` (one long-lived container per run) works the same; Chrome starts per `ng test` call.

### What this means for the Migrator

- `NODE_IMAGES` → an image table keyed by (Node, browser), plus a `Dockerfile` and a pin per entry.
- Add Node 18 (Angular 15's supported Node). Node 16 also works for Angular 15 and is already pinned.
- Container env: add `CHROME_BIN`, `NG_CLI_ANALYTICS=false`, `PUPPETEER_SKIP_DOWNLOAD=1`. `CI=1` is already set.
- The Docker image is the same for before and after, which a visual check needs anyway.

## 5. Template scanning

### Options

| Option | What it is | Status |
|---|---|---|
| `tree-sitter-html` 0.23.2 (PyPI, Nov 2024) | The official HTML grammar | Mature. Parses Angular attributes (`[x]`, `(y)`, `*ngIf`, `#ref`) as plain attribute names, which is enough to find elements and attribute directives. It breaks on a bare `<` inside text or `{{ }}` (`{{ a < b }}`): tried today, `x < y` in text gave a syntax error and a fake `<y>` element. |
| `tree-sitter-angular` (`dlvandenberg/tree-sitter-angular`, v0.9.2, May 2026, MIT, 67 stars) | Extends tree-sitter-html with bindings, interpolation, pipes, structural directives and control flow | **Not on PyPI.** The repo has a `pyproject.toml` and `setup.py`, so it can be pinned as a git dependency and built (needs a C compiler). Parsed `[disabled]="a < b"` and `{{ x < y ? 1 : 2 }}` with no errors today (through the language pack). |
| `tree-sitter-language-pack` 1.25.0 (PyPI, Nov 2026) | 371 grammars, Angular included | It **downloads the grammar libraries at first use** (a 26 MB bundle into `~/Library/Caches/tree-sitter-language-pack/`). A network fetch at run time, outside the lockfile. Avoid. |
| `@angular/compiler` `parseTemplate` from Node | The parser the schematic and the type-checker use | Exact, including spans and every Angular syntax. Needs a Node process and `@angular/compiler` (pinned in the tools workspace, or the repo's own). Element nodes give `name`, `attributes`, `inputs`, `outputs`, `references`, `templateAttrs` and source spans. |

- Inline templates: `@Component({template: \`...\`})` is a string or template literal in TS. The existing TS tree-sitter parse finds the decorator's `template` property. Parse its text with the template parser and add the literal's start offset to every position. Templates with `${}` interpolation can't be parsed statically; skip and report them. The schematic handles inline templates the same way.

### Recommendation

- **Use tree-sitter-angular for Scan**, pinned as a git dependency at `v0.9.2` (commit SHA) and checked for a clean build on macOS arm64 and Linux. It keeps Scan in Python with no Node process, like the TSX scan, and it handles the syntax tree-sitter-html gets wrong.
- Usages to count in templates: elements named `mat-*` (`<mat-form-field>`, `<mat-chip-list>`), attribute directives (`mat-button`, `mat-raised-button`, `matInput`, `matTooltip`, `matSuffix`), legacy-only attributes (`appearance="legacy"`), and typography classes. Map each to a guide section ("Form Field", "Chips", "Button", …).
- Keep `@angular/compiler` as a fallback for files where tree-sitter reports errors. Don't build two parsers on day one.
- SCSS usages (`@include mat.legacy-*`, `.mat-*` selectors) can be found with `tree-sitter-scss` 1.0.0 (PyPI, Apr 2024, one release) or with a regex over the file. The regex is probably enough for counting.

### What this means for the Migrator

- `scan/parser.py` parses only TS/TSX (`tree_sitter_typescript`); `UsageKind` is `import | jsx | call`. It needs `element`, `attribute` and `scss-include` / `selector` kinds, and a parser chosen by file extension.
- `source_globs` for this spec must include `**/*.html` and `**/*.scss`.
- An **affected file** for Angular is often a template or stylesheet that has no import at all. Scan must link each component's `.ts` to its `templateUrl` and `styleUrls`, so a failing `.html` is repaired with its component.

## 6. A visual check

### The practical shape

- **Build once, serve statically, screenshot with Playwright, all inside the same Docker image.**
  - Angular: `ng build` (production config, or development config for speed), then serve `dist/<app>` with a static server that falls back to `index.html` for client routes. `ng serve` also works but is slower to start and watches files.
  - CRA (kubeflow's frontend): `react-scripts build`, then serve `build/` the same way.
  - Vite (bcgov/wps): `vite build`, then `vite preview` or the same static server.
  - OpossumUI is an Electron app. Its renderer would need a Vite build of the renderer alone and stubs for the IPC bridge, so it is the hardest of the three.
- **Playwright from Python** (`playwright` on PyPI) fits the Migrator: one process drives Chromium, `page.screenshot(full_page=True, animations="disabled", caret="hide")`. The Node test runner's `toHaveScreenshot` adds retries until two screenshots agree and a built-in diff, but means a second test harness. Python's `page.screenshot` plus our own diff is enough.
- Playwright needs its own Chromium build of the matching version, or `channel`/`executable_path` set to the image's Chromium. The Playwright Docker image (topic 4) has it all, at about 2 GB.

### Comparing

- **Pixel diff:** `pixelmatch` 8.0.0 (Node; ports exist for Python) or `odiff-bin` 4.5.0 (a fast native binary; also reports the share of changed pixels and can ignore regions). Both give a changed-pixel count and a diff image. Cheap and exact, but they flag anti-aliasing and 1 px shifts.
- **Perceptual:** SSIM (for example scikit-image) scores structure, not exact pixels. It is less noisy, but still can't say whether a change is right.
- **The real problem for this migration:** MDC changes sizes, spacing and colours on every component. A before/after diff will be large on almost every page. So the diff says *where* things moved, not *whether they are wrong*.
- So use it in two ways:
  - **In evals: compare the run's screenshots with the reference PR's.** Build the merged PR's commit as a third state. "Closer to the reference than the Baseline is" is a real score, and it catches missing compensation styling, the thing silent misses are made of (the owner's rule from M6).
  - **In real runs: show, don't judge.** Put before/after pairs and diff images in the report and PR body, ranked by changed share, so a reviewer looks at the worst pages first. An LLM vision judge ("does the after page lose anything the before page had?") could score them later, at the balanced level.
- Layout checks are a cheaper middle ground: record the bounding boxes of elements by a stable selector (`data-testid`, `id`) before and after, and report big moves. They are less noisy than pixels.

### Choosing pages

- Read the router config: `RouterModule.forRoot(routes)` / `provideRouter` (Angular), `<Route path>` (React Router). Keep the static paths; skip paths with parameters unless the RepoConfig gives example values.
- Prefer pages that render affected components (Scan knows which components each page module declares or imports).
- Let the RepoConfig list routes by hand (`[visual] routes = ["/", "/settings"]`) and override the automatic list. For real repos that will often be needed.

### Auth and backends

- Most real apps call an API at start-up, and many need a login. In the sandbox there is no network, which is good for repeatability, but the pages then show error states.
- Options, simplest first:
  1. **Mock with HAR files.** Playwright's `route_from_har` answers requests from a recorded file. Record once, ideally against a dev backend the owner runs, and replay the same HAR for before, after and reference.
  2. **Use the repo's own mocks.** Kubeflow's frontend has a mock API server for development **(check)**. Some apps have an environment flag for mock data.
  3. **Auth:** set the token in `localStorage` or a cookie before navigation (`context.add_init_script`), or use the app's dev bypass if it has one. bcgov/wps signs in through Keycloak, so it needs one of these **(check)**.
  4. **Storybook**, where the repo has one: stories render components with no backend and no auth. It's the cleanest target, but few Angular 14/15 apps of this kind have one.
- If a page can't be made to render without a backend, leave it out and say so in the report. Don't fake data in app code.

### Flakiness risks

- Animations and ripples: `animations="disabled"` and a stylesheet that sets `transition: none` and `animation: none`. Angular's `BrowserAnimationsModule` still runs its own timers, so wait for the network to go idle plus a short settle time.
- Fonts: Roboto and Material Icons usually come from Google Fonts. Offline, both states fall back the same way, which is fine for a comparison, but icon names then render as text ("delete"). Bake the fonts into the image and route the font URLs to local files.
- Time and random data: Playwright's `page.clock` fixes the date. Random or live data must come from the HAR.
- Lazy-loaded content, scroll position, the blinking caret and spinners: wait for the network to be idle, hide the caret, mask known-dynamic regions.
- Run before, after and reference in the same image with the same viewport and device scale, so rendering differences are only the code's.

### Effort

- A first version (static build, routes from the RepoConfig, Playwright from Python in the Docker image, odiff, before/after/diff images in the report, the reference comparison in evals): **about 4–6 days**.
- HAR recording and replay, automatic route discovery, layout-box checks: **3–5 days more**.
- A vision-judge score with the owner's ratings to check it against: **2–3 days**, plus the owner's rating time.
- Flakiness is the main risk. Budget for two screenshots per state, with a "noisy" flag when they differ.
- Recommended order: build it first for MUI on kubeflow (a CRA build with a mock API), as part of finishing M6. Then reuse it for Angular, where the styling share is even bigger.

### What this means for the Migrator

- A new optional stage after the final Verify: `Visual`. It never decides a file's outcome, it adds evidence (like the *not covered* label).
- `Trap.expected_layer` already has `"visual-only"`: a trap that only a visual check can catch. The visual stage is what would make those measurable.
- It needs a second network-free container job (build + serve + Playwright) and a place for images in the run folder and the PR body.

## 7. Code seams in the current Migrator

### MUI-, React- or TSX-specific today

- **Scan** (`scan/parser.py`): tree-sitter with `tree_sitter_typescript` only. `UsageKind = import | jsx | call`. `dialect_for` knows only TS and TSX. No HTML or SCSS parsing, no link between a component and its `templateUrl`/`styleUrls`.
- **Scan → guide** (`scan/__init__.py`, `migrations/guide.py`): `changes_for_symbol` matches a section whose title equals the imported symbol (`Button`), or a change heading containing it. Angular symbols (`MatLegacyButtonModule`) and template tags (`mat-form-field`) won't match "Button" or "Form Field". It needs a per-spec map from module path, tag or directive to section, such as `legacy-button` → "Button".
- **Guide splitter** (`migrations/guide.py`): `section_level` and `change_level` are already per spec. But Angular's component sections are `###` under one `##` ("Comprehensive List of Changes"), and their changes are bullet points, not `####` headings. A `### 1. Update to Angular Material v15` under "How to Migrate" would also be read as a section. Needed: a `parent_section` filter, and "bullet" as the change unit (or the whole section). No codemod marker (`codemod_marker = None` already works).
- **Rule steps** (`migrations/__init__.py`, `rules.py`): the kinds are `install`, `dependencies`, `codemod`, `format`, `script`. `codemod` runs `node <tools cache>/<bin>`, expands `{files}` and parses jscodeshift output. `ToolsConfig` is required. A `schematic` kind is needed (topic 1). `script` could run `ng generate` today, but it can't read its result and it isn't marked run-once.
- **Format step**: Prettier, else `eslint --fix`, on changed source files only. Fine for Angular if `source_globs` cover `.html` and `.scss`. Prettier formats both.
- **Codemod TODOs** (`rules.find_codemod_todos`): comments from the TS/TSX parser, so `.html` and `.scss` comments are never seen.
- **Codemod false positives** (`false_positives.py`): JSX elements only, and the stray-parentheses fix is MUI's `StyledEngineProvider`. The Angular schematic matches template tags by name too. A repo's own `<mat-card>`-named wrapper is unlikely, but `.mat-*` selectors in the repo's own CSS that aren't Material's could be renamed. This check would need a template version; probably not needed for M7.
- **Verify** (`verify/__init__.py`, `verify/parsers.py`): `parse_tsc` reads only `file(l,c): error TSnnnn`. Lint adds `-f json -o` when the script body contains `eslint`; `ng lint` needs `--format json --output-file`. Test readers exist for `jest` and `vitest` only (`Runner = Literal["jest", "vitest"]` in `config.py`). `related_to` uses `--findRelatedTests`. Coverage reads Jest/Vitest `json-summary`. Snapshots are Jest/Vitest. `SOURCE_EXTENSIONS` is `.tsx .ts .jsx .js`.
- **Test-file detection** (`checks/__init__.py`): reads Jest and Vitest configs (`testMatch`, `setupFiles`, `setupFilesAfterEnv`, `include`) and `__mocks__` / `__snapshots__`. Karma's are elsewhere: `angular.json` `test.options` (`main: src/test.ts`, `include`, `karmaConfig`), and the default `**/*.spec.ts`. `src/test.ts` is the setup file. Jasmine's `xit`/`fit`/`xdescribe`/`fdescribe` are already in the skip-or-focus check.
- **Guardrails** (`repair/guardrails.py`): the config list has no `angular.json`, `karma.conf.js`, `src/test.ts`, `proxy.conf.json` or `.browserslistrc`. The scope rule allows "this file or a local file it imports", found through TS import statements. A component's `templateUrl` and `styleUrls` aren't imports, so the agent fixing `x.component.ts` couldn't touch its `.html` or `.scss`.
- **Escape hatches** (`checks/__init__.py`): `@ts-ignore`, `eslint-disable`, `any`, `as unknown as`. Angular has its own: `CUSTOM_ELEMENTS_SCHEMA` and `NO_ERRORS_SCHEMA` (they silence NG8001/NG8002 in a module or a TestBed), `$any(...)` in templates, `<!-- eslint-disable -->` in templates, and `::ng-deep` / `!important` as styling hacks (warnings, not failures).
- **Repair context** (`repair/context.py`, `repair/shared.py`, `repair/prompt.py`): imports and importers via TS import statements, the JSX element around a failing line, the JSX props around the failing lines for `keyword-context` retrieval, and the parse check in prompt v2 (TS/TSX only). The tool text's example path is `src/App.tsx` (`prompts/*/tools.toml`).
- **The reviewer and the judge**: `repair/reviewer.py` and `evals/reference.py` have MUI v4 → v5 written into their system prompts (`v5_required`, `v5-styling`, `makeStyles`). The scoring items are files whose imports match `@(material-ui|mui)/` (`evals/reference.py`, `CODE_EXTENSIONS = .ts .tsx .js .jsx`). Both need their library text from the spec, as the repair prompt already does, and the scoring items need `.html` and `.scss`.
- **`migrator init`** (`init.py`): detects `vitest`, `jest` or `react-scripts`, a `tsc` script or `tsconfig.json`, eslint scripts, and source files with `.ts/.tsx/.js/.jsx` under `src/`. It needs an Angular path that reads `angular.json` (topic 3).
- **Sandbox** (`execs.py`): images keyed by Node major only (topic 4). Network only for `npm ci`, `npm install`, `yarn install`, `pnpm install`; `ng update` would need its own exception.
- **Spec fields**: `detection` is packages plus major only (topic 2); `preconditions` is `min_major` only; `import_prefixes()` comes from the dependency map, which this spec doesn't have.

### Where models, prices and provider features are set today

| What | Where | How |
|---|---|---|
| Repair models | `configuration.RepairSettings.attempt_models` (TOML in `evals/configs/*.toml`) | Bare Claude ids, one per attempt, e.g. `claude-opus-5-5` |
| Effort | `RepairSettings.effort` / `attempt_efforts`; `Effort = Literal["low","medium","high","xhigh","max"]` | Passed as `reasoning_effort` to `init_chat_model` in `repair/model.anthropic_model` |
| Provider | `repair/model.anthropic_model` and `repair/reviewer.default_model` | `init_chat_model(model, model_provider="anthropic", ...)`, hard-coded |
| Prompt caching | `repair/model.CACHE_CONTROL = {"type": "ephemeral"}` | On the system message and through `.bind(cache_control=...)`, always on |
| Strict tools | `repair/model.py`: `convert_to_openai_tool(t, strict=True)` and `bind_tools(..., strict=True)` | Always on |
| Max tokens | `repair/model.MAX_TOKENS = 16_000`; the advisor's in `AdvisorSettings.max_tokens`; the judge's `JUDGE_MAX_TOKENS = 4000` | Constants |
| Advisor tool | `configuration.AdvisorSettings` (model id) and `repair/model.py` (`advisor_20260301`, an Anthropic server tool) | Anthropic-only |
| Reviewer model | `RepairSettings.reviewer_model` (M6 option D; Sonnet 5.5 on wps) | Bare id, Anthropic provider in `reviewer.default_model` |
| Eval judge | `evals/reference.py`: `JUDGE_MODEL = "claude-opus-5-5"`, `JUDGE_EFFORT = "low"`, a raw `anthropic.Anthropic()` client, `messages.create(..., output_config={"effort": ..., "format": {"type": "json_schema", ...}})` | Hard-coded, and not through LangChain |
| Prices | `cost.PRICES` (Opus, Sonnet, Haiku 5.5; Haiku with a long-prompt card), `PRICES_CHECKED`; cache writes derived as 1.25× and 2× input | `price_for` raises for an unknown model, so a model with no price already can't be costed |
| Cost priors | `cost.py`: `PRIOR_OPUS_ATTEMPT_USD`, the fallback `"claude-opus-5-5"` when a plan has no model, `ADVISOR_PRIOR_*`; scaling by the output-price ratio to Opus | Hard-coded to Opus |
| Usage fields | `cost.py` reads langchain-anthropic's cache-token fields and the advisor's `usage.iterations` | Anthropic's shape |
| CLI text | `cli.py` ("on claude-opus-5-5 at low effort") | A string |

### What this means for the Migrator (three model levels)

- One **model table** (TOML) replaces the scattered ids: per level (`strong`, `balanced`, `fast`) a `provider:model` id, its price card, and its declared features (`effort` levels, `prompt_caching`, `strict_tools`, `advisor`, `structured_output`). `cost.PRICES` becomes this table's price column, keyed by the full `provider:model` id.
- Configurations name levels (`attempt_levels = ["strong", "strong", "strong"]`, `reviewer = "balanced"`), never ids. The table checks that `balanced` ≠ `strong`.
- `anthropic_model` and `reviewer.default_model` become one factory that reads the provider from the id and passes only the features the table declares. Effort, `cache_control` and `strict=True` become conditional, each with a "turned off: not supported by <model>" line in the report.
- The judge moves off the raw Anthropic client onto the same factory at the `balanced` level, with structured output declared as a feature (or a JSON-in-text fallback).
- The cost priors scale from the `strong` level's price instead of Opus by name. The usage reader needs a per-provider mapping for cache tokens.
- The advisor stays an Anthropic-only feature, declared like the others.
- Refuse to start when any level's model has no price card (today the refusal only comes at the first `price_for` call).
