"""What is left of the old version after the Rules stage (M7).

For most migrations the old code stops compiling once the old packages go, so verify
finds it. Angular Material's legacy components still compile in 15 and 16, so a file
the schematic didn't migrate passes every check; without this check it would never be
repaired and would count as migrated. Each leftover is a Failure with the source
``migration``: an import of an old module, a stylesheet line in the old style (a
``mat.legacy-*`` mixin) and, when the spec says so, a Codemod TODO the schematic left.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from migrator.config import LeftoverCheck
from migrator.verify.parsers import Failure
from migrator.workspace import list_files

_SPECIFIER = re.compile(r"""(?:\bfrom\s+|\bimport\s*\(?\s*|\brequire\(\s*)(['"])([^'"\n]+)\1""")
_STYLE_EXTENSIONS = (".scss", ".sass", ".css", ".less")
_CODE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def find_leftovers(
    workspace: Path, check: LeftoverCheck, only: Iterable[str] | None = None
) -> list[Failure]:
    """Leftovers in the workspace's source files (or only in ``only``)."""
    modules = [re.compile(p) for p in check.old_modules]
    styles = [re.compile(p) for p in check.old_styles]
    todo = (
        re.compile("|".join(re.escape(m) for m in check.todo_markers))
        if check.todo_markers
        else None
    )
    paths = list_files(workspace, check.source_globs, check.exclude)
    if only is not None:
        wanted = set(only)
        paths = [p for p in paths if p in wanted]
    found: list[Failure] = []
    for rel in paths:
        try:
            text = (workspace / rel).read_text("utf-8", errors="replace")
        except OSError:
            continue
        is_code = rel.endswith(_CODE_EXTENSIONS)
        is_style = rel.endswith(_STYLE_EXTENSIONS)
        for number, line in enumerate(text.splitlines(), start=1):
            if is_code:
                for m in _SPECIFIER.finditer(line):
                    if any(p.search(m.group(2)) for p in modules):
                        found.append(
                            Failure(
                                source="migration",
                                file=rel,
                                line=number,
                                code="leftover-import",
                                message=f"still imports {m.group(2)}",
                            )
                        )
            if is_style:
                for pattern in styles:
                    if hit := pattern.search(line):
                        found.append(
                            Failure(
                                source="migration",
                                file=rel,
                                line=number,
                                code="leftover-style",
                                message=f"still uses {_token(line, hit.start())}",
                            )
                        )
                        break
            if todo is not None and todo.search(line):
                found.append(
                    Failure(
                        source="migration",
                        file=rel,
                        line=number,
                        code="codemod-todo",
                        message="Codemod TODO: " + _comment(line),
                    )
                )
    return found


def _token(line: str, start: int) -> str:
    m = re.match(r"[\w.$@-]+", line[start:])
    return m.group(0) if m else line.strip()[:80]


def _comment(line: str) -> str:
    text = line.strip()
    for opener, closer in (("/*", "*/"), ("<!--", "-->"), ("//", "")):
        if text.startswith(opener):
            text = text[len(opener) :]
            if closer and text.endswith(closer):
                text = text[: -len(closer)]
            break
    return " ".join(text.split())[:200]
