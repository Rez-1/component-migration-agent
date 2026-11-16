Migrate this repository from {library_name} {from_version} to {to_version}.

What you have:

- The repository is your working directory, a git repository with one commit. Its packages are installed (still {from_version}).
- The official migration guide, "{guide_title}" ({guide_tag}), is in `{guide_dir}`.
- {codemod_name}, pinned to the guide's version, is installed as `{codemod_bin}`. Usage: `{codemod_bin} <codemod> <paths>`, for example `{codemod_example}`.
- The package manager is {package_manager}. The package registry is reachable; the rest of the internet is not.
- The repository's own checks, which decide whether the migration worked:
  - type-check: `{typecheck}`
  - lint: `{lint}`
  - tests: `{test}`

Migrate every file that uses {library_name} {from_version} to {to_version}, update the dependencies, and make the type-check, lint and tests pass. Nobody can answer questions during this task: decide for yourself and keep going until you are done.

Rules. Your work is checked against them after you finish:

- Don't edit test files or snapshot files, and don't delete, skip or weaken tests.
- Don't edit configuration: tsconfig, ESLint, Jest, Babel, or the scripts in package.json.
- Change dependencies only with {package_manager} (it updates package.json and the lockfile). Don't edit the lockfile by hand.
- No escape hatches: no `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`, `as any` or `eslint-disable` comments.
- If you can't migrate a file properly within these rules, leave it as it is and list it. When you are done, write `{unfinished_file}` as a JSON array with one entry per file you didn't finish, for example `[{{"path": "src/Foo.tsx", "reason": "why"}}]`, paths relative to the repository root. Write `[]` if you finished every file.
