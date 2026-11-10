# M6 candidate repos: real v4 → v5 migrations

Researched 2026-11-10. Every number is measured at the **base commit of the reference PR**, using shallow clones and file reads only. Nothing was installed or run.

## Method and heuristics

- **MUI files** are non-test `.js/.jsx/.ts/.tsx` files that import `@material-ui/*`. Lines are the raw line count of those files.
- **Test coverage** (heuristic): a MUI source file counts as tested if some test file imports a path with the same basename, or the test file shares its stem. For `index.tsx` the folder name is used. This overstates real coverage, because an import doesn't mean the test checks styling.
- **Reference PR** counts come from `gh api …/pulls/N/files`. The "tests" column includes `.snap` files and test helpers.
- **Keeps JSS?** asks whether the reference PR leaves `makeStyles`/`withStyles` on `@mui/styles`, as our Q15 policy does, or rewrites it to `styled`/`sx`. When it rewrites, the Q17 closeness diff compares our output against a different target.
- **Contamination:** our model's knowledge cutoff is June 2026. PRs merged before then may be in its training data.

## Summary table

| Repo / PR | Stack | MUI files / lines | JSS (makeStyles / withStyles) | Tests (unit / e2e) | MUI files with a test | Ref PR: files, +/-, commits | Keeps JSS? | Runnability | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| [kubeflow/pipelines#12925](https://github.com/kubeflow/pipelines/pull/12925) `frontend/` | TS 4.9, React 17, Vite 7, **Vitest 4**, npm (lock v3), Node 22 (`.nvmrc`) | 69 / **21,133** | 0 / 1 (styling is **typestyle**, in 49 of 69 files) | 102 unit in `src` (+10 server), **62 snapshot tests** | 54/69 (78%) | 129 files (60 src, 17 tests, 39 `.snap`), +19.3k/−31.4k (31k of that is lockfile + snapshots), 5 commits | n/a (no JSS) | Low | **Good (dev)** |
| [opossum-tool/OpossumUI#218](https://github.com/opossum-tool/OpossumUI/pull/218) | TS 4.5, React 17, CRA 4.0.3 (Jest 26), Electron 13, yarn v1 | 52 / 5,949 | 44 / 1 | 125 unit+integration (RTL), 1 Playwright | 41/52 (79%) | 64 files (53 src, 9 tests), +526/−294, 4 commits | **Yes** | Medium | **Good (dev)** |
| [bcgov/wps#1933](https://github.com/bcgov/wps/pull/1933) `web/` | TS 4.4, React 17, CRA 5 (Jest 27), yarn v1, `engines: node ~14` | 123 / 12,866 | 86 / 1 | 38 unit, 12 Cypress | 29/123 (24%) | 150 files (127 src, 21 tests), +1,103/−919, 37 commits (many merges from main) | **Yes** (adds `adaptV4Theme`) | Medium | **Good (held-out)**, with caveats |
| [cypress-io/cypress-realworld-app#1522](https://github.com/cypress-io/cypress-realworld-app/pull/1522) | TS 4.9.5, React 18, Vite 4, Vitest 0.33 + Cypress 13 (component + e2e), yarn 1.22 via `yarnPath`, Node 20.12 | 49 / 4,488 | 31 / 1 | 9 Vitest (backend data only), 5 Cypress component, 28 Cypress e2e | 4/49 (8%, Cypress component tests only) | 61 files (49 src, 5 tests), +1,340/−1,010, 51 commits | **No** (ran `jss-to-styled` on every folder) | Medium | Usable with caveats |
| [etn-ccis/blui-react-design-patterns#219](https://github.com/etn-ccis/blui-react-design-patterns/pull/219) | TS 4.6, React 17, CRA 5 (Jest 27, **Enzyme** + RTL), Cypress 9, yarn v1, no Node hint | 52 / 10,392 | 48 / 0 | 37 unit, 34 Cypress | 31/52 (60%) | 101 files (55 src, 43 tests), +1,914/−1,268, 20 commits | Yes | **High** | Usable with caveats (lean skip) |
| [backstage/community-plugins#9533](https://github.com/backstage/community-plugins/pull/9533) `workspaces/tekton` | TS 5.8, React 17/18 peer, backstage-cli (Jest 30), **yarn 4 (berry)** monorepo, Node 22/24 | 33 / 3,924 | 20 / 0 | 29 unit, Playwright e2e | 7/33 (21%) | 54 files (40 src, 5 tests), +1,252/−691, 3 commits, merged **2026-06-30** | **No** (→ `sx`) | Medium-high | Usable with caveats (alternative held-out) |
| [backstage/community-plugins#9708](https://github.com/backstage/community-plugins/pull/9708) `workspaces/argocd` | as tekton | 33 / 3,661 | 9 / 0 | 60 unit, Playwright e2e | 25/33 (76%) | 47 files (38 src, 5 tests), +348/−479, 6 commits, merged **2026-07-09** | **No** (→ `styled`/`sx`) | Medium-high | Usable with caveats |
| [newjersey/navigator.business.nj.gov#538](https://github.com/newjersey/navigator.business.nj.gov/pull/538) `web/` | TS 4.4, React 17, Next 11, Jest 27, npm | 21 / 2,212 | 3 / 0 | 21 unit, 9 Cypress | 7/21 (33%) | 28 files, +685/−247, 1 commit | Yes | Low | Skip (fixture-sized) |

## Per-repo notes

### kubeflow/pipelines frontend (#12925): good dev case

- **Custom code:** the theme lives in `src/Css.tsx` (`createTheme` with v4 `overrides`) next to a typestyle `commonCss`/`classes()` system that most MUI files use. The `src/atoms/` wrappers sit on top of MUI: `Input.tsx` spreads `OutlinedTextFieldProps` into `TextField`, which will hit the v5 `variant` typing change; there are also `MD2Tabs.tsx` (147-line custom tabs), `CardTooltip.tsx` (`withStyles` on Tooltip), `BusyButton` and `IconWithTooltip`. Deep imports: `@material-ui/core/colors/grey` ×3. Files are large, about 300 lines on average (`RunDetails.tsx` is 1,359).
- **Tests:** coverage is genuinely good. Many tests pin MUI DOM: 22 `Mui*` class references in tests (`.MuiTableSortLabel-root`, `MuiButton-label`, which v5 removes), and 62 snapshot tests.
- **Reference PR:** one scoped PR. React stays at 17, the codemod runs first, and theme overrides move to `components.styleOverrides`. It updated 39 `.snap` files and 17 test files. Signs that it was AI-assisted: "address copilot review notes" and "remove accidental task notes". It merged 2026-03 (contamination risk).
- **Runnability:** modern and self-contained, with npm, Vitest, `tsc --noEmit` and `eslint --max-warnings=0`. `pretest` runs `npx tailwindcss build`. Generated API clients are checked in.
- **Caveat:** after migration, snapshots and class-name assertions *must* fail, and Q4 blocks test edits. The harness needs a policy for this, such as excluding `.snap` mismatches and scoring them separately, or allowing `vitest -u` for snapshots only. Otherwise every snapshot file becomes a hand-off.

### OpossumUI (#218): good dev case

- **Custom code:** 44 `makeStyles` calls, with shared styles in `src/Frontend/shared-styles.ts`. MUI private class names in *source* styles, such as `'& div.MuiAccordionSummary-expandIcon'` (that class is gone in v5) in `AggregatedAttributionsPanel.tsx` and `LicenseSubPanel.tsx`, and `MuiButtonGroup-grouped*` in `HamburgerMenu.tsx`. These are classic silent misses: they type-check and lint cleanly but stop styling. Three deep imports `@material-ui/core/Typography/Typography`, and `@material-ui/styles` ×2.
- **Tests:** RTL tests plus integration tests driven through `test-helpers/`, which rely on DOM structure (`getByRole('presentation').firstChild`). The reference PR edited `context-menu-test-helpers.ts`, so some post-migration failures can only be fixed in test code.
- **Reference PR:** small and clean (4 commits). It follows the official guide, keeps JSS on `@mui/styles` (matching Q15), and its only extras are styling and test fixes. Merged 2021-11.
- **Runnability:** CRA 4.0.3 and Electron 13. `playwright@1.16` downloads browsers and `electron` downloads its binary at install, so set `ELECTRON_SKIP_BINARY_DOWNLOAD=1` and `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`. `postinstall` runs husky and `update-commit-hash`, which needs a git repo. Use Node 16. Unit tests need no backend.

### bcgov/wps web (#1933): held-out, with caveats

- **Custom code:** the largest JSS surface (86 `makeStyles`) and the most realistic layering. `src/app/theme.ts` has two themes with `overrides`. `components/Grid.tsx` wraps `Grid` (`GridContainer`/`GridItem`). A custom `DatePicker` sits on `@material-ui/pickers` with `date-io/luxon`. `@devexpress/dx-react-grid-material-ui` is a third-party MUI wrapper. Private classes appear in source (`.MuiToggleButton-label`, `.MuiAlert-icon`) and in Cypress specs. `withStyles` deep imports ×3.
- **Tests:** about 24% of MUI files have a test, which is the honest low-coverage profile M6 wants.
- **Reference PR:** mixed. It bumps **devexpress v2→v3** (v3 requires MUI v5), replaces the pickers with a new `WPSDatePicker` and deletes its test, adds `adaptV4Theme`, and skips one slider test with `xit`. It also has many CSS fixes and 37 commits with merges from main. It stays on `makeStyles`, which is good for Q17.
- **Runnability:** `engines: node ~14.x, npm ~8.1` but ships a yarn v1 lockfile. CRA 5 / Jest 27 should run on Node 16. Unit tests need no backend; the Keycloak and API env vars matter only at runtime. The harness must do the devexpress and pickers swap in its dependency step (a case config), because the LLM can't edit `package.json`.

### cypress-realworld-app (#1522): usable with caveats

- **Custom code:** 31 `makeStyles` and few wrappers. Formik forms wrap `TextField`; `@material-ui/lab` appears ×4. A `patch-package` patch on `@material-ui/core` `ButtonBase` (`patches/@material-ui+core+4.12.4.patch`) goes stale after migration, and the reference deletes it. Three auth variants (Auth0, Okta, Google) each have their own entry and container files.
- **Tests:** Vitest unit tests cover only backend data and utils, not UI. MUI coverage is 5 Cypress component tests, plus 28 e2e specs that need the local Express/lowdb backend. That leaves `tsc` and `eslint` as the realistic verify signal, so this is a good silent-miss stress test.
- **Reference PR:** 51 commits. It ran the codemods step by step, then **`jss-to-styled` on every folder**, removed `@mui/styles`, and fixed layout and test issues. Because it converted every `makeStyles` to `styled` and we keep JSS (Q15), the Q17 diff will be noisy. Either score closeness only on non-style hunks, or treat this repo as a "verify-only" case.
- **Runnability:** yarn 1.22 via `yarnPath`, Node 20.12, and a husky + patch-package `postinstall`. Cypress component tests need the Cypress binary download.

### blui-react-design-patterns (#219): usable with caveats, lean skip

- It's a design-pattern *showcase* (one page per pattern), so most of the custom-looking code is the external **Brightlayer UI** wrapper library. The reference bumps `@brightlayer-ui/react-components` 5→6 and `react-themes` 6→7 (their MUI v5 builds), and the harness would have to do that too. 30 deep `@material-ui/core/styles/*` imports. The 67 `.Mui*` references are mostly in Cypress specs.
- **Tests:** Enzyme with the unofficial React 17 adapter, and `mount(...).find(Checkbox)` against the MUI component type. 43 test files changed in the reference PR, so many failures are fixable only in tests.
- **Runnability risk is high.** `node-sass@7.0.1` is a dependency but nothing uses it (no `.scss`). It has no prebuilt binary for Node ≥18, so install falls back to node-gyp. Use Node 16 or `--ignore-scripts`. No Node version hint, and the reference also downgraded Cypress.

### Backstage community-plugins: tekton (#9533) and argocd (#9708)

- **Realistic layering:** plugins sit on `@backstage/core-components` and `@backstage/theme`, which stay MUI v4, and mix in **PatternFly 6** (39 files). The argocd base already has some `@mui/material` imports, so it starts half-migrated. Tekton's reference adds a `TektonStylesProvider` with a class-name seed.
- Both PRs merged after June 2026, so **contamination risk is the lowest of all candidates**. But both rewrite `makeStyles` to `sx`/`styled`, and both carry "address copilot comments" commits.
- **Runnability:** yarn 4.14 monorepo. Each workspace's `postinstall` runs `cd ../../ && yarn install`, which installs the whole community-plugins root. That is heavy but doable with `nodeLinker: node-modules`. Uses `backstage-cli repo lint --since origin/main`, so call `lint:all` instead. Needs Node 22.

### Others found, not deep-dived

- [CartoDB/carto-react#501](https://github.com/CartoDB/carto-react/pull/501): a JS library, not an app.
- [visualize-admin/visualization-tool#453](https://github.com/visualize-admin/visualization-tool/pull/453): 100 commits, heavily mixed.
- [mikhael28/paretOS#138](https://github.com/mikhael28/paretOS/pull/138): JS.
- [npocccties/chibichilo#525](https://github.com/npocccties/chibichilo/pull/525): 111 files, TS, a possible spare.
- [jichu4n/qbjc#7](https://github.com/jichu4n/qbjc/pull/7) and [cofacts/community-builder#15](https://github.com/cofacts/community-builder/pull/15): mixed with CRA, React and TS upgrades.
- [MetaMask/metamask-extension#41955](https://github.com/MetaMask/metamask-extension/pull/41955): huge repo, unsuitable.
- Other Backstage plugin PRs: rbac #9230 (+3.2k/−9.9k), topology #1525, azure-devops #1805 (later reverted in #2095), acr #9627, servicenow #9523.

## Recommendation

- **Dev:** kubeflow frontend and OpossumUI. Both run on a modern or easy toolchain, have honest test coverage (about 78%), and carry real custom code: the typestyle theme and atoms in kubeflow, private class-name selectors and DOM-coupled test helpers in Opossum. Opossum's reference keeps JSS, so Q17 closeness is meaningful there.
- **Held-out:** bcgov/wps. It's the largest and most layered (devexpress grid, custom pickers, two themes), has only about 24% coverage, keeps JSS, and its reference PR is messy in the way real migrations are.
- **Alternative held-out:** backstage tekton #9533, if contamination matters more than closeness scoring.
- **Harness work these cases need:**
  - A per-case dependency-bump list (devexpress, BLUI).
  - A snapshot and test-only failure policy (kubeflow, Opossum).
  - Install env flags (`ELECTRON_SKIP_BINARY_DOWNLOAD`, `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD`, `--ignore-scripts` for node-sass).
  - Pinning Node 16 for the CRA repos.
