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
from collections.abc import Iterable, Mapping
from pathlib import Path

from migrator.config import LeftoverCheck
from migrator.verify.parsers import Failure
from migrator.workspace import list_files

_SPECIFIER = re.compile(r"""(?:\bfrom\s+|\bimport\s*\(?\s*|\brequire\(\s*)(['"])([^'"\n]+)\1""")
_STYLE_EXTENSIONS = (".scss", ".sass", ".css", ".less")
# A class of the old components' internal structure: `.mat-form-field-wrapper`, not the
# MDC components' `.mat-mdc-*` (M7, Angular; the schematic's notes are about these).
_INTERNAL_CLASS = re.compile(r"\.mat-(?!mdc-)[a-z][\w-]*")
_CODE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def rules_under_todos(files: Mapping[str, str], markers: Iterable[str]) -> list[tuple[str, str]]:
    """(stylesheet, the line right under each TODO comment): the rule the comment is
    about, as the Rules stage left it. If that exact line is still in the file after
    repair, the rule wasn't restyled, whatever happened to the comment."""
    wanted = [m for m in markers if m]
    found: list[tuple[str, str]] = []
    for rel, text in sorted(files.items()):
        if not rel.endswith(_STYLE_EXTENSIONS) or not any(m in text for m in wanted):
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not any(m in line for m in wanted):
                continue
            for after in lines[i + 1 :]:
                bare = after.strip()
                if bare and not bare.startswith(("/*", "//", "*")):
                    # Only a rule that names an internal class can go stale: one on the
                    # component's element (`mat-radio-button { ... }`) still applies,
                    # and removing the note resolves it.
                    if _INTERNAL_CLASS.search(bare):
                        found.append((rel, bare))
                    break
    return found


def find_leftovers(
    workspace: Path,
    check: LeftoverCheck,
    only: Iterable[str] | None = None,
    stale_rules: Iterable[tuple[str, str]] = (),
) -> list[Failure]:
    """Leftovers in the workspace's source files (or only in ``only``). ``stale_rules``:
    lines under the Rules stage's TODO comments (``rules_under_todos``) that must not
    survive unchanged."""
    stale: dict[str, set[str]] = {}
    for rel, line in stale_rules:
        stale.setdefault(rel, set()).add(line)
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
        code_lines = _without_comments(text) if is_style else text.splitlines()
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
                bare = code_lines[number - 1]  # a mixin named in a comment doesn't count
                for pattern in styles:
                    if hit := pattern.search(bare):
                        found.append(
                            Failure(
                                source="migration",
                                file=rel,
                                line=number,
                                code="leftover-style",
                                message=f"still uses {_token(bare, hit.start())}",
                            )
                        )
                        break
            if line.strip() in stale.get(rel, ()):
                found.append(
                    Failure(
                        source="migration",
                        file=rel,
                        line=number,
                        code="stale-rule",
                        message="this rule still targets the old version's internal classes "
                        f"(a Codemod TODO marked it): {line.strip()[:160]}",
                    )
                )
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


def _without_comments(text: str) -> list[str]:
    """A stylesheet's lines with ``//`` and ``/* */`` comments blanked, line for line."""
    out: list[str] = []
    in_block = False
    for line in text.splitlines():
        kept: list[str] = []
        i = 0
        while i < len(line):
            if in_block:
                end = line.find("*/", i)
                if end < 0:
                    i = len(line)
                else:
                    in_block, i = False, end + 2
            elif line.startswith("/*", i):
                in_block, i = True, i + 2
            elif line.startswith("//", i) and not line[max(0, i - 5) : i].endswith(":"):
                break  # a line comment (not the // of a url(http://...))
            else:
                kept.append(line[i])
                i += 1
        out.append("".join(kept))
    return out


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
