---
name: add-migration
description: Add a new migration (one component-library version jump, such as mui@4 -> mui@5) to the Migrator. Use when someone wants the Migrator to support a library or version it doesn't yet, or asks to write, research or fix a migration.toml. Guides the research and fills the spec; `migrator spec check` holds the rules.
---

# Add a migration

A **migration** is one version jump of one component library, described as data in `src/migrator/migrations/<name>/migration.toml`, with the vendored guide in `guide/` and the pinned codemod tools in `tools/`. Read `CONTEXT.md` for the words used here (Rules, Rule step, Codemod TODO, Baseline, ...) and `src/migrator/migrations/mui-4-to-5/` for a finished example.

**The rules live in the CLI, not in this skill.** `uv run migrator spec check <name>` decides whether a spec is valid. This skill only says what to research and in what order. When the two disagree, the check wins: fix the spec, or propose a change to `src/migrator/spec_tools.py` with a test.

**Find facts yourself; ask the human for decisions.** Versions, tags, commits, heading levels and which codemods exist are facts you can look up. Repair policies (what the agent must not rewrite), which version to target, and whether to include an optional codemod are decisions for the human.

## 1. Scope

- One jump, from one major to the next: `lib@N -> lib@N+1`. Skipping a major takes two specs.
- Check it doesn't exist yet: `ls src/migrator/migrations/`.
- Folder name: lower-case words joined by `-`, such as `mui-4-to-5` or `angular-material-legacy-to-mdc`.

```bash
uv run migrator spec new <name> --from <lib>@<N> --to <lib>@<M> --library "<Library name>"
```

This writes a commented `migration.toml` (every `TODO` must be replaced), `guide/SOURCE.md` to fill in, and `tools/package.json`.

## 2. The guide: source, pin, licence

1. Find the official migration guide **in the library's own repository**, not a blog post or the rendered site. The rendered pages are usually thin wrappers around Markdown files in the repo.
2. **Pin a tag, never a branch.** Prefer the last release of the target major, where the guide is final and nothing newer has crept in. Branches drift: later majors rewrite install commands and component names, and some guides disappear from `main` entirely (Angular's MDC guide did). Get the tag's commit:
   ```bash
   gh api repos/<owner>/<repo>/commits/<tag> --jq .sha
   ```
3. Check the licence allows vendoring (MIT and Apache-2.0 do, with the notice kept). Copy `LICENSE` next to the files.
4. Copy the files **unchanged** from `https://raw.githubusercontent.com/<owner>/<repo>/<tag>/<path>`. Fill in `guide/SOURCE.md`: the repository, tag, commit, path, files, date, and `git hash-object` of the largest file.
5. Read the heading structure and set `[guide]`:
   - `section_level`: the heading level of one component or area (MUI: `##`, Angular MDC: `###`);
   - `change_level`: one change inside it, deeper than the section;
   - `drop_sections`: headings with no changes (a link list repeated in every file, an intro);
   - `codemod_marker`: a prefix on headings the codemods already handle, if the guide has one (MUI: `✅`);
   - `link_base`: where site-relative links should point.
6. Run `spec check` and read the `guide split` line. Then open a few sections with `load_guide` and confirm that one section is one component.

Write what you found, and why you picked that tag, in `docs/research/<name>-guide-source.md`. `docs/research/migration-guide-source.md` is the example.

## 3. The deterministic layer: codemods

1. List the **official** codemods or schematics for this jump, from the guide and the library's codemod package. For each one, note:
   - its order;
   - whether it is idempotent (most aren't, so every codemod runs exactly once and the spec enforces it);
   - whether it needs the old packages installed (MUI's `preset-safe` resolves imports against `node_modules`);
   - what it leaves behind where it gives up: a TODO or FIXME marker, which goes in `codemod_todo_markers`.
2. Pin the codemod package **exactly** in `tools/package.json` and lock it without running install scripts:
   ```bash
   cd src/migrator/migrations/<name>/tools && npm install --package-lock-only --ignore-scripts
   ```
3. Name each binary in `[tools.bins]` (`node_modules/<package>/<bin>.js`), and add one `codemod` rule step per transform, with `{files}` in its args.
4. If the deterministic layer runs from the **target repo's own** tooling, such as an Angular schematic through `ng generate`, it is not a pinned codemod. Use that rule-step kind once the Migrator has it (planned in M7, `docs/m7-plan.md`), and don't fake it with a script step.

## 4. Dependencies, detection, usage

- `[[dependency_map]]`: each old package and its new packages, at **exact** versions matching the guide's tag. Confirm each one exists: `npm view <pkg>@<version> version`. Leave it empty when the jump doesn't change packages.
- Rule-step order: an install before codemods that need the old packages, then `dependencies`, then an install of the new packages. `spec check` flags orders that can't work.
- `[detection]`: the packages and the major version that identify a repo on the old version.
- `[usage]`: module-specifier regexes for old and new imports, used by the scanner and the "no old imports" check.
- `source_globs` and `exclude`: where the library is used. Angular templates (`.html`) and styles count too.

## 5. Repair notes and prompt fields

`library_name`, `from_version`, `to_version`, `codemod_name` and `guide_title` fill the repair prompt; no library names live in prompt text. `repair_notes` are policies, one sentence each, such as "Keep makeStyles on @mui/styles". **Ask the human for these.** They decide what counts as a correct migration, and the evals score against them.

## 6. Check until it passes

```bash
uv run migrator spec check <name> --network
```

`--network` also confirms on GitHub that the guide's commit exists, and on npm that every pin exists. Fix every `fail`, and read every `warn`: a warning is either fixed or explained in the research note.

## 7. A Baseline on a sample repo

A Baseline runs the codemods and the dependency map with no model calls, so it is free. Run one on a small repo still on the old version, as a throwaway copy:

```bash
uv run migrator init <repo>
uv run migrator migrate <repo> --from <lib>@<N> --to <lib>@<M> --dry-run
```

Read `usage-report.md` and the scorecard:
- Did the codemods run?
- Which files still fail?
- Which Codemod TODOs did they leave?

Codemod false positives (changes to the repo's own components that share a library name) belong in the Rules layer, not in repair notes.

## Done means

- `spec check --network` reports 0 failed, and every warning is fixed or explained.
- `guide/` holds the unchanged files, `LICENSE` and a complete `SOURCE.md`.
- `docs/research/<name>-guide-source.md` records the source, the tag choice and the codemod facts.
- A Baseline ran on a sample repo and its result is noted.
- The repair notes came from the human.
