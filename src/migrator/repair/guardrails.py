"""Guardrails: the blocks the repair agent's tools enforce (tickets #7, #11, #14).

The prompt explains them; these functions enforce them. ``apply_edit`` may change only
the failing file and the local files it imports, never a Test file (as the cheating
checks define it, on the untouched repo), a config, a lockfile or ``package.json``,
and never in a way that adds an escape hatch or code that detects it runs under test.
A patch past the size limit (60 changed lines or 40% of a file) hands the file off.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from migrator.checks import CODE_EXTENSIONS, ESCAPE_HATCHES, TEST_SNIFFING, profile
from migrator.config import LOCKFILES
from migrator.repair.context import ANGULAR_ASSETS, PatchSize

MAX_PATCH_LINES = 60
MAX_PATCH_SHARE = 0.40

_CONFIG_NAME = re.compile(
    r"""^(
        package\.json
      | tsconfig(\..+)?\.json | jsconfig\.json
      | \.eslintrc(\..+)? | eslint\.config\..+ | \.prettierrc(\..+)? | prettier\.config\..+
      | \.babelrc(\..+)? | babel\.config\..+
      | (jest|vitest|vite|webpack|rollup|next|craco|postcss|tailwind)\.config\..+
      | \.env(\..+)? | \.npmrc | \.nvmrc | \.yarnrc(\.yml)? | migrate\.toml
      | angular\.json | \.angular-cli\.json | karma\.conf\..+ | proxy\.conf\..+
    )$""",
    re.VERBOSE,
)
# Never readable: git data and the Migrator's own run files.
HIDDEN_DIRS = frozenset({".git", ".migrator"})


class Blocked(BaseModel):
    reason: str
    guardrail: str  # a short key for the scorecard: "test-file", "config", ...


def workspace_path(workspace: Path, path: str) -> tuple[str, Path] | Blocked:
    """A repo-relative POSIX path inside the workspace, or why it is refused."""
    cleaned = path.strip().removeprefix("./")
    candidate = (workspace / cleaned).resolve()
    root = workspace.resolve()
    if candidate != root and root not in candidate.parents:
        return Blocked(reason=f"{path} is outside the workspace", guardrail="outside-workspace")
    rel = candidate.relative_to(root).as_posix()
    parts = PurePosixPath(rel).parts
    if parts and parts[0] in HIDDEN_DIRS:
        return Blocked(reason=f"{rel} is not part of the code", guardrail="outside-workspace")
    return rel, candidate


def check_target(
    rel: str,
    failing_file: str,
    allowed_imports: list[str],
    test_files: Mapping[str, str],
) -> Blocked | None:
    """Whether the repair agent may edit ``rel`` while repairing ``failing_file``."""
    name = PurePosixPath(rel).name
    parts = PurePosixPath(rel).parts
    if "node_modules" in parts:
        return Blocked(reason=f"{rel} is an installed package", guardrail="dependency")
    if name == "package.json" or name in LOCKFILES:
        return Blocked(
            reason=f"{rel} is off-limits: the dependencies are set by the migration",
            guardrail="package-files",
        )
    if rel in test_files:
        return Blocked(
            reason=f"{rel} is a Test file ({test_files[rel]}): the tests define the correct "
            "behaviour, so they can't be changed to pass",
            guardrail="test-file",
        )
    if _CONFIG_NAME.match(name) or not name.endswith((*CODE_EXTENSIONS, *ANGULAR_ASSETS)):
        return Blocked(
            reason=f"{rel} is a config or other non-source file, which is off-limits",
            guardrail="config",
        )
    if rel != failing_file and rel not in allowed_imports:
        allowed = ", ".join([failing_file, *allowed_imports])
        return Blocked(
            reason=f"{rel} is not this file or a local file it imports (allowed: {allowed}). "
            "If the fix needs a change there, change approach or hand off",
            guardrail="scope",
        )
    return None


def added_escape_hatches(path: str, before: str, after: str) -> list[str]:
    """Escape hatches and test-sniffing code the change adds, counted per file."""
    old, new = profile(before, path), profile(after, path)
    found = [what for key, what in ESCAPE_HATCHES.items() if new[key] > old[key]]
    found += [what for key, what in TEST_SNIFFING.items() if new[key] > old[key]]
    return found


def over_size_limit(size: PatchSize) -> bool:
    return size.changed > MAX_PATCH_LINES or size.share > MAX_PATCH_SHARE
