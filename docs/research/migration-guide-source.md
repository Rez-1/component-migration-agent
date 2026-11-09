# Migration guide source: where the repair loop's guide text comes from

Research for [Rez-1/component-migration-agent#2](https://github.com/Rez-1/component-migration-agent/issues/2). Checked 2026-11-09 against the GitHub API and raw files.

## Recommendation

Vendor the five Markdown files in `docs/data/material/migration/migration-v4/` from **mui/material-ui tag `v5.18.0`** (commit `b8e2c1ccf37f595c5b46684f8a6393680606d78c`, the last v5 release). Don't track `master`. Split the files on headings: in the component file each `##` is one component (63 sections) and each `###` is one change (126). The repo is MIT, so we can vendor the files if we copy MUI's copyright and licence notice next to them.

## Source files

Path: [`docs/data/material/migration/migration-v4/`](https://github.com/mui/material-ui/tree/v5.18.0/docs/data/material/migration/migration-v4). The rendered pages are just wrappers: `docs/pages/material-ui/migration/*.js` loads these files.

| File | Lines @ v5.18.0 | `##` / `###` | Content |
|---|---|---|---|
| [`migration-v4.md`](https://github.com/mui/material-ui/blob/v5.18.0/docs/data/material/migration/migration-v4/migration-v4.md) | 376 | 10 / 12 | Getting started: package renames, import mapping, codemods (`preset-safe`, `variant-prop`, `link-underline-hover`) |
| [`v5-style-changes.md`](https://github.com/mui/material-ui/blob/v5.18.0/docs/data/material/migration/migration-v4/v5-style-changes.md) | 696 | 12 / 36 | Theme and styles. Each `##` is a package or area (`@mui/material/styles`, Theme structure, System…) |
| [`v5-component-changes.md`](https://github.com/mui/material-ui/blob/v5.18.0/docs/data/material/migration/migration-v4/v5-component-changes.md) | 2044 | 63 / 126 | **Per-component**: `## AccordionSummary`, `## AppBar`, … `## Typography`, `## Theme`, `## @mui/types` |
| [`migrating-from-jss.md`](https://github.com/mui/material-ui/blob/v5.18.0/docs/data/material/migration/migration-v4/migrating-from-jss.md) | 472 | 3 / 2 | makeStyles/withStyles → styled/sx/tss-react |
| [`troubleshooting.md`](https://github.com/mui/material-ui/blob/v5.18.0/docs/data/material/migration/migration-v4/troubleshooting.md) | 293 | 9 / 2 | Symptom-titled sections, e.g. `## TypeError: Cannot read properties of undefined (reading 'pxToRem')` |

There are no translated copies (`-zh.md` and so on) in this folder.

### Structure and how to split it

- Every file starts with the same `## Material UI v5 migration` list of links. Drop that section when splitting.
- `v5-component-changes.md` has 61 component `##` sections in alphabetical order, from AccordionSummary to Typography, plus `## Theme` and `## @mui/types`. Most components get one or more `### <change>` subsections. The `##` names match the component import names (`Button`, `TextField`, `ExpansionPanel`, `GridList`, `Hidden`, `RootRef`…), so a keyword lookup on component names from errors and imports can go straight to them. A component index is easy to build from the `##` headings. The repo doesn't ship one: the docs site generates the table of contents from the headings.
- **A ✅ prefix on a `###` heading means a codemod already handles that change** (48 headings in the component file, 22 in the style file). The file says so in its intro `:::warning`. The repair loop can rank these lower or skip them.
- Admonitions are `:::warning` / `:::success` / `:::info` blocks. Internal links are site-relative (`/material-ui/...`), and anchors point at other files (`#preset-safe`).
- Proposed chunk key: `(file, ## heading, ### heading)`, with the `##` text as the component keyword.

## Which ref to pin

- `master` still has the v4 guide ([folder on master](https://github.com/mui/material-ui/tree/master/docs/data/material/migration/migration-v4)). The latest tag on master is `v10.0.0-alpha.0`, and there is a `v5.x` branch.
- **`v5.18.0` (2025-07-08) and the `v5.x` branch are byte-identical** for all five files.
- Since then, master has made [about 10 commits](https://github.com/mui/material-ui/commits/master/docs/data/material/migration/migration-v4) to the folder. Most fix links or typos. The real differences between master and v5.18.0:
  - `v5-style-changes.md`: master adds a section on JSS array-syntax values ("Refactor alternative syntax for space- and comma-separated values") and a "Refactor local rule references" heading. It also moves two subsections down to `####`. That is about 110 changed lines and the only real content gain.
  - `migration-v4.md`: **the install commands lose their version pins** (`npm install @mui/material` instead of `@mui/material@^5.0.0`). Read literally, that installs v7 or later, which is wrong for our target. `@material-ui/docs -> @mui/internal-core-docs`.
  - `v5-component-changes.md`: the Grid section changes `Unstable_Grid2` to `Grid2` (v6+ naming, so wrong for v5), and links move to `v5.mui.com` or absolute paths.
  - Master also adds a `<!-- #target-branch-reference -->` infra comment.
- The `AccordionSummary` section ([#45947](https://github.com/mui/material-ui/pull/45947), Apr 2025) is already in v5.18.0. An older v5 tag such as `v5.15.20` doesn't have it, which is another reason to use 5.18.0.
- Optionally, cherry-pick the master JSS array-syntax section into our copy and mark it as backported. Otherwise stay on v5.18.0.

Pinned blob SHA for change detection: `v5-component-changes.md` @ v5.18.0 = `185614b0bfe8a7ffee98621cfca63e7d9a6ca329`.

## Licence

- The [`LICENSE`](https://github.com/mui/material-ui/blob/v5.18.0/LICENSE) file in mui/material-ui is MIT ("Copyright (c) 2014 Call-Em-All"). GitHub reports `MIT` for the repo, and `docs/` has no separate docs licence.
- MIT lets us vendor these files into an MIT repo. The one requirement is to include the copyright and permission notice with the copied files. Suggested layout: `vendor/mui-migration-v4/` with the files, a copy of `LICENSE`, and a `SOURCE.md` that records the repo, tag, commit, path and the date we copied them.
- Not legal advice. This is the plain reading of MIT.

## M7 seam: Angular Material legacy → MDC

- Source: [`guides/v15-mdc-migration.md`](https://github.com/angular/components/blob/15.2.9/guides/v15-mdc-migration.md) in angular/components (MIT). Pin to tag **`15.2.9`**, the last 15.x release (commit `d593195dcff51a482425c0ad898fb63baaa7435e`). It is one 683-line file.
- The file is still on the 16.x tags (checked `16.2.14`) but **no longer on `main`**, where it returns 404, so we must pin a tag.
- The structure is different from MUI's. The per-component sections are **`###`** headings (Autocomplete, Button, Card, Checkbox, Chips, Dialog, Form Field, Input, List, Menu, …, Tooltip: 26 components), nested under `## Comprehensive List of Changes`. There are no ✅ codemod markers. So the splitter's heading level and "component section parent" need to be per-migration config, not hard-coded.

## Risks

- Following master would quietly bring in v6+/v7 guidance (unpinned installs, Grid2 naming). Always pin a tag.
- Links in the files are site-relative and will be broken in our copy. If we show sources, rewrite them to `https://v5.mui.com`.
- Some keywords sit in style-file sections, not component ones (`makeStyles`, `withStyles`, `createMuiTheme`, `fade`). So the lookup index should cover `###` headings in all five files, not only the component file.
