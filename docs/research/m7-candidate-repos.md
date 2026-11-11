# M7 candidate repos: real Angular Material legacy → MDC migrations

Researched 2026-11-11. Every number is measured at the **base commit of the reference PR**, using shallow (sparse where the repo is large) clones and file reads only. Nothing was installed or run.

## Method and heuristics

- **Search.** `gh search prs` and the search API on titles (`mdc`, `mdc migration`, `legacy material`, `material 15`, `MatLegacy`), split into date windows from 2022-11 to 2026-11 so results weren't capped at 100. Also `gh search commits` for `mdc-migration`, `migrate to mdc`, `legacy material components` and `MDC-based`, mapping each commit to its PR with `repos/…/commits/SHA/pulls`. Each hit was then checked for one focused merged PR.
- **What counts as the migration.** The PR must *remove* `@angular/material/legacy-*` / `MatLegacy*` imports (`-` lines in the diff). PRs that only *add* them, such as the `ng update @angular/material@15` rewrite to legacy entry points, are rejected.
- **Material files.** "TS" means non-spec `.ts` files that import `@angular/material`. "HTML" means templates with a `<mat-…>` element or a `mat…` / `mat-…-button` attribute. Lines are the raw line count of those files.
- **Custom SCSS.** Files that mention `.mat-*`, `.mdc-*`, `@angular/material` or `mat.*` mixins. "Internal selectors" counts selectors on legacy-only DOM classes that MDC removes or renames (`.mat-form-field-wrapper/-infix/-underline`, `.mat-button-wrapper`, `.mat-checkbox-layout`, `.mat-tab-label`, `.mat-list-item-content` and similar). These are the classic silent misses: they still compile and lint, but stop styling anything.
- **Test coverage** (heuristic): a Material component counts as tested if a `.spec.ts` with the same stem sits next to it. "Trivial" specs have at most one `it()`, which is usually the generated "should create". Like M6, this overstates real coverage.
- **Reference PR** counts come from `gh api …/pulls/N/files`. "tests" includes Cypress/e2e files. "Ran the schematic?" is judged from commit messages, the PR body, and `TODO(mdc-migration)` comments in the diff (the schematic writes these).
- **Contamination:** our model's knowledge cutoff is June 2026. PRs merged before then may be in its training data.

## Summary table

| Repo / PR | Stack | Material files: TS / HTML (lines) | Custom SCSS (theme files / internal selectors) | Tests (unit / e2e) | Material comps with a spec | Ref PR: files, +/-, commits | Ran schematic? | Runnability | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| [kubermatic/dashboard#6629](https://github.com/kubermatic/dashboard/pull/6629) `modules/web/` | Angular 16.2, Material 16.2 (half migrated: 92 legacy / 325 MDC import lines), TS 5.1, **Jest** (jest-preset-angular), Cypress 11, npm (lock v3), `engines: node >=18`, `FROM node:18` | 173 / 303 (28.6k / 30.8k) | 106 files (3 theme) / **225** | 107 Jest (36 trivial), 31 Cypress | 55/476 (12%) | 245 files (65 ts, 68 html, 102 scss, 6 tests), +1,438/−892, 4 commits, merged 2024-03 | **Yes**, and left 286 `TODO(mdc-migration)` comments in | Medium | **Good (dev)** |
| [MaibornWolff/codecharta#3226](https://github.com/MaibornWolff/codecharta/pull/3226) `visualization/` | Angular 15.1, Material 15.1 (all legacy), TS 4.9, **Jest** + Puppeteer e2e, npm (lock v2), `engines: node >=16`, CI Node 16 | 25 / 48 (1.0k / 1.3k) | 27 files (2 theme) / 20 | 269 Jest (42 trivial), 9 Puppeteer e2e | 44/57 (77%) | 130 files (32 ts, 24 html, 41 scss, 31 tests), +733/−797, 46 commits, merged 2023-03 | **Yes** (first commit) | Low | **Good (dev)** |
| [valitydev/dashboard#127](https://github.com/valitydev/dashboard/pull/127) | Angular 15.2, Material 15.2, TS 4.9, Karma/Jasmine, no e2e, npm (lock v2, CI uses `npm ci --force`), no Node hint | 224 / 88 (11.0k / 2.6k) | 58 files (**39** per-component `_*-theme.scss`) / 0 | 128 Karma (34 trivial) | 33/161 (20%) | 327 files (190 ts, 68 html, 29 scss, 32 tests), +647/−790, 19 commits, merged 2023-06 | No (by hand, no TODOs) | Medium | **Good (held-out)**, with caveats |
| [Health-Education-England/tis-revalidation-v2#1255](https://github.com/Health-Education-England/tis-revalidation-v2/pull/1255) | Angular 16.1, Material 16.1, TS 5.1, Karma/Jasmine, Cypress 12, npm (lock v2), CI Node 18.12 | 20 / 43 (1.8k / 2.7k) | 28 files (2 theme) / 17, `::ng-deep .mat-` ×3 | 92 Karma (33 trivial), 6 Cypress | 44/47 (94%) | 66 files (9 ts, 18 html, 23 scss, 15 tests), +390/−367, 26 commits, merged 2024-02 | Mostly by hand, one component at a time | Medium | Good (alternative held-out) |
| [google/peoplemath#259](https://github.com/google/peoplemath/pull/259) | Angular 16.2, Material 16.2, TS 4.9, Karma/Jasmine, Protractor stub, npm (lock v3), CI Node 16 + 18 | 20 / 25 (3.5k / 0.8k) | 6 `.css` files, prebuilt legacy theme only / 11 | 45 Karma (25 trivial) | 25/26 (96%) | 54 files (20 ts, 12 html, 11 css, 10 tests), +239/−330, 8 commits, merged 2023-11 | Yes ("part 1") | **Low** | Usable with caveats (fallback dev) |
| [zitadel/zitadel#6482](https://github.com/zitadel/zitadel/pull/6482) `console/` | Angular 16.2, Material 16.2, TS 4.9, Karma (no `test` script), Cypress e2e at repo root, yarn v1 | 233 / 155 (28.7k / 13.9k) | 70 files (**57** with theme mixins) / 17 | 170 Karma (169 trivial), 13 Cypress | 155/168 (specs are empty) | 412 files (227 ts, 57 html, 98 scss, 15 tests), +2,708/−2,695, 39 commits (merges from main), merged 2023-10 | Unclear; heavy hand restyling, drops dynamic theming | **High** | Usable with caveats (verify-only stress test) |
| [mxtommy/Kip#308](https://github.com/mxtommy/Kip/pull/308) | **Angular 17.2 core with Material 16.2** (pinned to keep legacy), TS 5.3, Karma, Protractor, npm (lock v2), no Node hint | 12 / 29 (2.5k / 2.4k) | 22 files (17 theme) / 1 | 67 Karma (66 trivial) | 21/30 (specs are empty) | 46 files (15 ts, 17 html, 14 scss, 0 tests), +457/−417, 9 commits, merged 2024-02 | No | Medium-high | Skip (no test signal, broken lint) |
| [SiLeBAT/fcl-client@7ec9591](https://github.com/SiLeBAT/fcl-client/commit/7ec959129372c1168df45ce777d03cd2fbb338ea) (commit on `develop`, no PR) | Angular 16.2, Material 16.2, TS 4.9.5, Jest, npm (lock v2), CI Node 16 | 36 / 68 (5.7k / 3.7k) | 24 files (8 theme) / 54 | 32 Jest (6 trivial) | 9/81 (11%) | 84 files (34 ts, 24 html, 26 scss, 0 tests), +527/−242, 1 commit, pushed **2026-11-05** (authored 2026-06-22) | Yes, plus "some manual changes" | Low-medium | Skip (reference is incomplete by its own message) |

## Per-repo notes

### kubermatic/dashboard web (#6629): good dev case

- **Custom code:** a large Angular app with 51 shared components in `src/app/shared/components` (`autocomplete`, `button`, `chip-autocomplete`, `combobox`, `select`, `search-field`, `pagination-page-size`, `number-stepper` and more), all built on Material. The theme lives in `src/assets/css/{material,global,theme}/` plus `src/assets/themes/{light,dark}.scss`. It includes both `mat.all-legacy-component-themes` and `mat.all-component-themes`, because the base is already partly migrated. It has 252 SCSS files and **225 selectors on legacy-only internal classes**, the biggest silent-miss surface of any candidate.
- **Tests:** 107 Jest specs (71 with real assertions) and 31 Cypress specs. Coverage of Material components is low (about 12% by stem), and no spec queries `.mat-` classes, so most styling breakage will be invisible to tests. Verification will rest on `tsc`, lint and a build.
- **Reference PR:** the cleanest "schematic first" reference. It has 4 commits ("Migrate to MDC based angular components", then 3 × "Refactored code"). It removes all 105 legacy import lines and **leaves 286 `TODO(mdc-migration)` comments in the SCSS**, mostly "targets internal classes of button / form-field / select". So the merged result is close to raw schematic output plus fixes. That suits Q17 closeness scoring, and the TODOs mark exactly where a silent-miss checker should look. The only extras are `@angular/flex-layout` 14-beta → 15-beta and `gts` 5.0 → 5.2. Angular stays at 16. Merged 2024-03 (contamination risk).
- **Runnability:** Node 18. `postinstall` runs `node version.js`, which calls `git-describe` and needs a git repo with tags, so a shallow clone without tags may fail. Stub it or fetch tags. `prepare` runs `cd ../../ && husky install`, which needs the monorepo root. Set `CYPRESS_INSTALL_BINARY=0`. `npm run build` runs `ng b -c=production-ee` (edition env var). Jest needs no backend.

### MaibornWolff/codecharta visualization (#3226): good dev case

- **Custom code:** a central `app/material/material.module.ts` re-exports every legacy module, which is a single choke point the schematic must rewrite. Theming is in `app/material/_theme.scss`, with per-component overrides in `matDialog.scss`, `matMenu.scss` and `matSelect.scss`, and it uses per-component `mat.legacy-*-theme` mixins rather than `all-legacy-component-themes`. Base is pure Angular 15.1 with all-legacy imports (52 legacy vs 5 MDC import lines), which is exactly the M7 target state.
- **Tests:** the strongest suite. 269 Jest specs, only 42 trivial, and 77% of Material components have a spec. There are 9 Puppeteer e2e specs. The PR body says specs reached into internal CSS classes and broke. The PR fixed 31 test files and switched 2 suites to component harnesses, so some failures can only be fixed in test code (a Q4 policy question, as in M6).
- **Reference PR:** the first commit is "execute the ng migrate command for material ui", and the next 45 commits are hand fixes to styling and tests, with two merges from main. **Scope creep:** it also changes the primary colour to match the logo and adds the logo to the UI. Exclude those hunks from closeness scoring. Merged 2023-03 (contamination risk).
- **Runnability:** Node 16 (CI and `engines`). `puppeteer@17` downloads Chromium at install, so set `PUPPETEER_SKIP_DOWNLOAD=1` unless e2e is wanted. No postinstall. Unit tests need no backend.

### valitydev/dashboard (#127): held-out, with caveats

- **Custom code:** the most layered theming of all candidates. There are **39 per-component `_*-theme.scss` files**, each a mixin taking the Material theme, plus a local wrapper layer in `src/components/` (buttons, form-controls, popups, nested-table, filters) and `src/app/shared/components/`. It uses the team's own `@vality/ng-core` library (7 imports) and `ngx-mat-select-search`. It is Angular 15.2 with all-legacy imports (301 legacy import lines).
- **Tests:** 128 Karma specs (94 with real assertions), but only about 20% of Material components have one. That is the honest low-coverage profile we want for held-out. No e2e.
- **Reference PR:** done by hand ("new dialog", "new buttons", "repl all lagacy mat", then a run of "fix tabs", "fix dialog padding", "fix icon button"). There are no schematic TODOs. **Dependency bumps the harness must replay:** `@vality/ng-core` 0.7.1-… → 15.0.0 (their MDC build) and `ngx-mat-select-search` 6 → 7. It also bumps Prettier 2.5 → 2.8 and edits `tsconfig`. Merged 2023-06.
- **Runnability:** all `@vality/*` packages are on public npm. CI installs with `npm ci --force` because of peer conflicts. `postinstall` runs `ngcc`, which is fine on Angular 15. Lint is `eslint --max-warnings 1075`, so compare warning counts, not zero. Karma needs headless Chrome. No backend needed for unit tests.

### Health-Education-England/tis-revalidation-v2 (#1255): alternative held-out

- **Custom code:** `src/scss/material/` (`_index`, `_palette`, `_variables`) holds an NHS palette over `mat.all-legacy-component-themes`. Shared form-control wrappers (`material-autocomplete`, `material-selection-list`) and `confirm-dialog` / `info-dialog` sit in `src/app/shared/`. It has 17 internal-class selectors and 3 `::ng-deep .mat-*`.
- **Tests:** 92 Karma specs (59 real), and 3 spec files query `.mat-` classes. The PR edited 9 unit specs and 6 Cypress files ("update E2E targetting new MDC elements"). Cypress needs the real backend.
- **Reference PR:** one component per commit ("update material card / checkbox / chip … to MDC"), each fixing styles. It replaced `mat-list` in the trainee details panel with plain HTML, because restoring the old look needed too much `ng-deep`. That makes it a good "the agent should hand off here" case. Angular stays at 16. Merged 2024-02.
- **Runnability:** Node 18.12 in CI. `npm run test:ci` uses ChromeHeadless. Husky v8. It is small (20 TS files), which makes it a cheap held-out run.

### google/peoplemath (#259): fallback dev, small

- A planning tool with a Go backend in `backend/` that the frontend unit tests don't need. Styling is the prebuilt `legacy-deeppurple-amber.css` theme plus 6 small `.css` files with 11 internal selectors, so there is little custom theming.
- 45 Karma specs (20 real), and almost every component has one. The PR ran the migration ("part 1"), then fixed buttons, dialogs and padding by hand over 8 commits. Merged 2023-11.
- The easiest toolchain of all (CI matrix Node 16 and 18, no postinstall). But it is close to fixture-sized, so it's useful only for smoke-testing the M7 pipeline.

### zitadel console (#6482): usable with caveats

- **Custom code:** the largest real surface. 566 legacy import lines, 57 SCSS files with per-component theme mixins, `component-themes.scss`, and a runtime "dynamic theming" layer that the PR deletes.
- **Tests:** 170 specs, but 169 are the generated "should create". There is no `test` script, so CI never runs them. The 13 Cypress e2e specs need a running ZITADEL instance.
- **Reference PR:** 39 commits with several merges from main. It is mostly hand restyling, drops dynamic theming, and bumps Angular 16.2.0 → 16.2.5 (patch only). Expect noisy closeness.
- **Runnability is high:** `build` and `lint` both need TypeScript generated from `../proto` by `buf generate`, which needs the `buf` CLI and remote plugins (network). Treat it as a verify-only stress test for type-check and build at scale, not as a scored case.

### mxtommy/Kip (#308): skip

- It pins Material 16 under Angular 17 to keep the legacy components, so install needs peer-dep overrides. `ng lint` uses the removed `tslint` builder and won't run. 66 of 67 specs are empty. The PR has no test changes and is pure template and SCSS restyling. That leaves `ng build` as the only signal.

### SiLeBAT/fcl-client (commit 7ec9591): skip, but worth watching

- It is the only real-app migration committed after the cutoff (pushed 2026-11-05, though authored 2026-06-22). It is a pushed commit on `develop`, not a PR. The commit message says it "applied ng migration and some manual changes", that the code "does not pass testing or linting", and that the layout is "only partially restored". The fixes were folded into the later Angular 20 → 21 upgrade commit (154 files, +22.7k/−15.7k).
- So there is no clean reference to score against. It has 54 internal-class selectors and 32 Jest specs (26 real), which makes it a decent extra verify-only case.

### Rejected: switched to `legacy-*` only (not the migration)

These PRs *add* `legacy-` imports and remove none. They are the `ng update` step, not the MDC migration:

- [NationalBankBelgium/stark#3774](https://github.com/NationalBankBelgium/stark/pull/3774) (+206 legacy lines)
- [kendraio/kendraio-app#358](https://github.com/kendraio/kendraio-app/pull/358) (+96, mixed with the Angular 15 bump)
- [hmcts/ccd-case-ui-toolkit#1590](https://github.com/hmcts/ccd-case-ui-toolkit/pull/1590) (+35, library)
- [tonysamperi/ngx-mat-timepicker#47](https://github.com/tonysamperi/ngx-mat-timepicker/pull/47) (+32, library)
- Commits such as "ng update @angular/material@15: everything rewritten to legacy entry points" and "Update to Angular 15 using legacy Material components" in small personal repos.

### Others found, not deep-dived

- **Second half only:** [kendraio/kendraio-app#454](https://github.com/kendraio/kendraio-app/pull/454). Its base already has 0 legacy imports, so the TS rewrite happened earlier and this PR only fixes templates and styles. It also has 8 specs for 119 Material components.
- **Done piecemeal across many PRs** (no single reference): OpenSlides client, tensorboard, google/ground-platform, ghostfolio, truenas/webui, CarnegieLearningWeb/UpGrade, dasch-swiss/dsp-app, sillsdev/web-xforge, gravitee console, Xyna-Factory, City-of-Helsinki/allu, ita-social-projects/OoS-Frontend, spica-engine.
- **Mixed with a large Angular or UI upgrade:** usnistgov/WIPP-frontend#238 (+147k), geneontology/noctua-visual-pathway-editor#262 (714 files), yamcs#778 ("Misc", 1,206 files), Sphere/eagle-fusion#684 (a release PR), devsecopsmaturitymodel#557 / #562 (Angular 14→15→17, 2026-05), m9sweeper#336, TheLegion/juke#36.
- **Possible spares:** [valitydev/control-center#206](https://github.com/valitydev/control-center/pull/206) (98 files, mostly TS imports), [CESNET/perun-web-apps#1246](https://github.com/CESNET/perun-web-apps/pull/1246) (85 files, mostly templates, multi-app monorepo), [damingerdai/hoteler-web#709](https://github.com/damingerdai/hoteler-web/pull/709) (62 files), [Klaster1/timer-5#23](https://github.com/Klaster1/timer-5/pull/23) (29 files).
- **Libraries, not apps:** IHK-GfI/lux-components, Ecodev/natural, hamzahamidi/ajsf#367 (merged 2026-08, but also bumps Angular 14 → 15), porscheinformatik/material-addons, udos86/ng-dynamic-forms.
- **Post-cutoff, but no PR or a toy repo:** SharebookBR/sharebook-frontend@d462382 (2026-09, 40 files, a pushed commit at the end of an automated 14→17 hop sequence). There are many 2026 demo repos (banking demos, "angular-upgrade-14-to-22" style) that look generated, and they are not real codebases.

## Recommendation

- **Dev:** kubermatic web and codecharta.
  - kubermatic is large and half-migrated, and its reference is close to raw schematic output. The 286 TODOs it left in point straight at 225 internal-class selectors, so Q17 closeness and silent-miss detection are both meaningful there.
  - codecharta is pure Angular 15.1 with all-legacy imports, has the best real test suite (Jest, 77% of components), and runs on Node 16 with no postinstall. Its reference ran the schematic first, then fixed tests and styling by hand. Strip the logo and colour hunks before scoring.
- **Held-out:** valitydev/dashboard. It is the M7 counterpart to bcgov/wps: large (327 files), heavily layered (39 component theme mixins, a local wrapper layer, the team's own `ng-core` library), and only about 20% covered. Its reference is a messy hand migration with dependency bumps.
- **Alternative held-out:** tis-revalidation-v2. It is smaller and better tested, with Cypress edits and a "replace the component" decision.
- **Fallback dev:** peoplemath. It has the easiest toolchain but is near fixture-sized.
- **Contamination:** every recommended reference merged between 2023-03 and 2024-03, so all are pre-cutoff. No real app did the migration in one clean PR after June 2026; by then most projects had already moved to Angular 17+. The only post-cutoff real case (fcl-client) has an admittedly incomplete reference. If contamination matters, run fcl-client as a verify-only case, not as a scored one.
- **Harness work these cases need:**
  - A per-case dependency-bump list (`@vality/ng-core` → 15.0.0, `ngx-mat-select-search` 7, `@angular/flex-layout` 15-beta for kubermatic).
  - A policy for test-only fixes (codecharta, HEE), as in M6.
  - Install env flags: `PUPPETEER_SKIP_DOWNLOAD=1`, `CYPRESS_INSTALL_BINARY=0`, `npm ci --force` for vality, and a stub for kubermatic's `git-describe` postinstall.
  - Headless Chrome for the Karma repos (vality, HEE, peoplemath).
  - A silent-miss check on legacy internal class selectors (`.mat-form-field-wrapper` and friends) in SCSS and specs, since the schematic only leaves TODOs and doesn't fix them.
