# Node tooling in practice: pinned `@mui/codemod` and tree-sitter for TSX

Research for [Rez-1/component-migration-agent#5](https://github.com/Rez-1/component-migration-agent/issues/5). Checked 2026-11-09 against the npm registry (`npm view`, `npm pack` tarballs of `@mui/codemod` 5.15.14, 9.4.0, 9.5.0 and `jscodeshift` 17.4.0), `mui/material-ui` `master` (`packages/mui-codemod`, through `gh api`), the PyPI JSON API, and the `tree-sitter/py-tree-sitter` and `tree-sitter/tree-sitter-typescript` repos. The codemod and parser claims marked **(verified)** were run against a two-file synthetic fixture in `/private/tmp/claude-501/cmrun`. No real project was touched.

## Recommendation

Pin **`@mui/codemod@9.4.0`**. Install it into the agent's own Node workspace from a lockfile and call `node <workspace>/node_modules/@mui/codemod/codemod.js` directly, not `npx @mui/codemod@latest`. Do **not** use 9.5.0, the current `latest`: its CLI crashes on start. Its `v5.0.0/*` transform files are byte-identical to 9.4.0's, so 9.4.0 loses nothing. Run each transform with `-- --verbose=2 --fail-on-error`. Treat the codemod's own exit code as meaningless and work out what changed by hashing or diffing the clean copy ourselves. Parse the ` OKK `/` ERR ` lines only as a cross-check. For the scanner, use **`tree-sitter==0.26.0` + `tree-sitter-typescript==0.23.2`** on **Python ≥ 3.10**. Use `language_tsx()` for `.tsx`/`.jsx`/`.js` and `language_typescript()` for `.ts`.

## 1. Which `@mui/codemod` version

| Version | Published | Status for us |
|---|---|---|
| 5.15.14 (last 5.x) | 2024-03-19 | Works, but ships jscodeshift `^0.13.1` and transforms under `node/v5.0.0/`. Outdated. |
| 9.3.0 | 2026-08-05 | **Broken**: tarball left out transforms (`Transform '…' not found`). [mui/material-ui#48928](https://github.com/mui/material-ui/issues/48928), fixed in 9.3.1. |
| **9.4.0** | 2026-08-27 | **Works (verified).** yargs `^17.7.3`, jscodeshift `^17.4.0`, engines `node >=14`. |
| 9.5.0 (`latest`) | 2026-10-09 | **Broken (verified)**: `TypeError: yargs.command is not a function` on any invocation, `--help` included. |
| 10.0.0-alpha.0 (`next`) | — | Pre-release. Not for pinning. |

- **Why 9.5.0 breaks.** It bumped to `yargs@^18` (ESM-only, `"type": "module"`), but the published `codemod.js` still calls `yargs.command(...)` on the `require('yargs')` result (`npm view @mui/codemod@9.5.0 dependencies`). On `master`, `packages/mui-codemod/src/codemod.js` already uses `yargs(hideBin(process.argv))`. The fix exists in source but has not been released. Other dist-tags: `latest-v7: 7.3.10`, `latest-v6: 6.5.0`. There is no `latest-v5` tag.
- **The v5 transforms are unchanged.** `diff -r` of `v5.0.0/` and `util/` between 9.4.0 and 9.5.0 is empty. From 5.15.14 to 9.x, every one of the four transforms and `theme-breakpoints` differs only by transpiler output (optional chaining, `interopRequireDefault().default`). The one real logic fix is in `top-level-imports` (a `== null` bug), which is not part of `preset-safe`. 9.x adds `v5.0.0/path-imports.js`.
- **The npm `latest` changes under you.** In the last three months, two of the four releases (9.3.0, 9.5.0) were broken. Never call `@latest`.

### Command lines

The wrapper always passes these flags to jscodeshift (source: `codemod.js` in the 9.4.0 tarball): `--extensions js,ts,jsx,tsx,json --parser tsx --ignore-pattern **/node_modules/** --ignore-pattern **/*.css --packageName=@mui/material`. **`--parser` defaults to `tsx`**, so TS/TSX needs no extra flag. Paths can be directories or individual files. There is no built-in glob expansion; quoted globs are passed through to jscodeshift as-is.

```bash
CM="node $WS/node_modules/@mui/codemod/codemod.js"   # WS = agent's pinned Node workspace (npm ci)
$CM v5.0.0/preset-safe          "$COPY/src" -- --verbose=2 --fail-on-error
$CM v5.0.0/variant-prop         "$COPY/src" -- --verbose=2 --fail-on-error
$CM v5.0.0/link-underline-hover "$COPY/src" -- --verbose=2 --fail-on-error
$CM v5.0.0/box-sx-prop          "$COPY/src" -- --verbose=2 --fail-on-error
```

- **Run order matters.** `preset-safe` includes `mui-replace`, which rewrites `@material-ui/core` → `@mui/material`. `variant-prop` matches `^(@material-ui\/core|@mui\/material)(\/TextField|\/Select|\/FormControl)?$` and `box-sx-prop` matches `@mui/material|@material-ui/core`, so both still find their targets afterwards. None of the three extra transforms is in `preset-safe`'s list.
- **Passing jscodeshift options.** Use the `--` passthrough. Anything after `--` goes into yargs' `argv._` and is spliced in before the fixed flags **(verified)**. The README's `--jscodeshift="--run-in-band --verbose=2"` form **does not work with more than one option**. The wrapper pushes that string as a *single* argv entry, and jscodeshift's `argsParser.js` splits on the first `=`. The result is one unknown option named `--run-in-band --verbose` **(verified: verbose output did not appear)**. One option per `--jscodeshift` is fine. Because the fixed flags come *after* the `--` passthrough, overriding `--extensions` or `--parser` needs `--parser=…` (a real wrapper option) or `--jscodeshift="--extensions=ts,tsx"`.
- **`--dry` and `--print`** are wrapper options that map to jscodeshift's.

### How it reports changes

- jscodeshift prints one line per file with `--verbose=2`: ` OKK <path>` (modified), ` NOC <path>` (unchanged), ` SKIP `, ` ERR <path> Transformation error (…)`. It ends with a `Results: N errors / N unmodified / N skipped / N ok` summary (`jscodeshift/src/Runner.js`, `Worker.js`) **(verified)**.
- **The exit code is always 0.** `codemod.js` calls `childProcess.spawnSync('node', args, {stdio: 'inherit'})` and never checks `.status`, so even `--fail-on-error` with a parse error exits 0 **(verified)**. Output also goes to the inherited stdout, mixed with an `Executing command: …` line.
- **Conclusion:** we must diff ourselves. Snapshot the content hash of every file before each transform and compare after. Use the `OKK`/`ERR` lines as a secondary signal, and treat any `ERR` as "file not transformed at all": a throw in any sub-transform of `preset-safe` aborts the whole file.

### Network at run time

- The transforms are pure local AST rewrites. Nothing in them fetches anything. `npx --offline @mui/codemod@9.4.0 --version` works from the npx cache **(verified)**. A plain `npx` may still contact the registry to resolve the spec, so install into a lockfiled workspace instead.
- **There is a dependency on the target project's `node_modules`.** `optimal-imports` (part of `preset-safe`) handles deep imports like `@material-ui/core/Button/Button` by calling `require.resolve('@material-ui/core/modern/<subpath>' | '.../es/<subpath>', {paths: [dirname(file)]})`. Without the v4 package installed in the clean copy, that file fails: `ERR … Cannot find module '@material-ui/core/es/Button'` **(verified)**. One-level imports (`@material-ui/core/Button`) don't hit this path. Either install the project's v4 deps in the copy first (that is the network step) or pre-flatten deep imports.

## 2. Known issues on TypeScript

- **Type annotations survive.** With the `tsx` parser (babel + typescript plugin through recast), interface declarations, generics, `as`, `!`, and typed params all came through unchanged in the fixture **(verified)**. Other parsers (`babel`, `flow`) were not tested; keep the `tsx` default.
- **Formatting churn is real.** recast reprints every node it touches. In the fixture, `box-sx-prop` turned `<Box p={2} border="1px solid" className=…>` into a multi-line element with `sx={{ p: 2, border: "1px solid" }}` (double quotes, despite its `quote: 'single'` printOptions). `material-ui-styles` added a blank line after the new import. Open upstream issue: [mui/material-ui#46464](https://github.com/mui/material-ui/issues/46464), where the codemod adds semicolons to unrelated lines in TS files. Plan to run the project's Prettier/ESLint `--fix` on changed files only, after the codemods, and exclude formatting from the diff we show reviewers. `printOptions` can be passed with `--jscodeshift="--printOptions={\"quote\":\"single\"}"`.
- **`theme-breakpoints` is not idempotent, and it runs inside `preset-safe`.** The README says: "⚠️ This mod is not idempotent, it should be run only once". The same warning applies to `preset-safe`. A second `preset-safe` run turned `down('md')` into `down('lg')` and reported `1 ok` **(verified)**. Our "exactly once on a clean copy" rule is required. Record a per-copy marker, and never re-run on a dirty or partially migrated tree. `variant-prop` has its own caveat: don't run it if the theme already sets a default `variant`.
- **`.json` files are included.** The hard-coded `--extensions` list includes `json`, so any `.json` under the path is parsed with the tsx parser and reported as `ERR … Missing semicolon` **(verified)**. That is harmless but noisy. Either pass file lists rather than directories or filter `.json` `ERR` lines out.
- **`.ts` files with angle-bracket casts** (`<Foo>x`) are ambiguous under the `tsx` parser and will `ERR`. This is an inference from the grammar, not tested. Run a second pass over just those files with `--parser=ts` if any show up.
- **Node version.** 9.4.0 says `node >=14`, but jscodeshift 17 needs a modern Node. Tested on Node 24.14.0.

## 3. Python tree-sitter for TS/TSX

| Package | Latest | Python | Notes |
|---|---|---|---|
| [`tree-sitter`](https://pypi.org/project/tree-sitter/) (py-tree-sitter) | **0.26.0** (2026-06-30) | **≥ 3.10** (0.23.2 was the last on 3.9) | Wheels cp310+ for macOS, manylinux, musllinux, Windows. Supports language ABI 13–15. |
| [`tree-sitter-typescript`](https://pypi.org/project/tree-sitter-typescript/) | **0.23.2** (2024-11-11, still the latest GitHub release) | ≥ 3.9 | `cp39-abi3` wheels. Exposes `language_typescript()` and `language_tsx()` (ABI 14), plus `HIGHLIGHTS_QUERY`/`TAGS_QUERY`. |
| [`tree-sitter-language-pack`](https://pypi.org/project/tree-sitter-language-pack/) | 1.25.0 | ≥ 3.11 | Alternative bundle of 100+ grammars. Not needed. |

The system `/usr/bin/python3` is 3.9, so the project must require ≥ 3.10 (we tested 3.12 via `uv`). **API change:** since 0.25, use `Query(language, src)` + `QueryCursor(query).matches/captures(node)`. In 0.26, `Language.query()` and `Language.version` were **removed** ([v0.25.0](https://github.com/tree-sitter/py-tree-sitter/releases/tag/v0.25.0), [v0.26.0](https://github.com/tree-sitter/py-tree-sitter/releases/tag/v0.26.0) release notes). Older tutorials using `lang.query(...).captures()` returning tuples are stale.

Sketch **(verified on 0.26.0 + 0.23.2)**:

```python
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Query, QueryCursor

TSX = Language(tsts.language_tsx())      # use tsts.language_typescript() for .ts
parser = Parser(TSX)

IMPORTS = Query(TSX, r'''
(import_statement
  (import_clause
    [ (identifier) @default
      (named_imports (import_specifier name: (identifier) @imported alias: (identifier)? @alias))
      (namespace_import (identifier) @namespace) ])
  source: (string (string_fragment) @source)
  (#match? @source "^@material-ui/"))
''')
USES = Query(TSX, r'''
(jsx_opening_element      name: [(identifier) (member_expression)] @jsx)
(jsx_self_closing_element name: [(identifier) (member_expression)] @jsx)
(call_expression      function: [(identifier) (member_expression)] @call)
''')

tree = parser.parse(src_bytes)                     # check tree.root_node.has_error
local = {}                                         # local name -> (module, kind)
for _, caps in QueryCursor(IMPORTS).matches(tree.root_node):   # one match per specifier
    mod = caps["source"][0].text.decode()
    for kind in ("default", "namespace", "alias", "imported"):
        if kind == "imported" and "alias" in caps:
            continue
        for n in caps.get(kind, []):
            local[n.text.decode()] = (mod, kind)
for cap, nodes in QueryCursor(USES).captures(tree.root_node).items():   # dict[str, list[Node]]
    for n in nodes:
        if n.text.decode().split(".")[0] in local:
            print(cap, n.text.decode(), n.start_point.row + 1)
```

On a sample with default, named, aliased (`Link as MuiLink`), namespace (`* as Icons`) and `import type` imports, this found `makeStyles(...)` calls and `<Button>`, `<TextField>`, `<MuiLink>` and `<Icons.Add>` JSX.

The sketch does not yet handle these cases:
- `import type { X }` and inline `type` specifiers: the `type` keyword is a child token of `import_statement`/`import_specifier`. Flag them as type-only.
- `export { X } from '@material-ui/core'` re-exports (`export_statement` with `source:`).
- `require(...)` and dynamic `import(...)`.
- JSX closing tags: the closing element is skipped on purpose, to avoid double-counting.
- Names used as values (`styled(Button)`, `component={Link}`). Add an `(identifier) @ref` capture filtered by `local` if we want every reference.
