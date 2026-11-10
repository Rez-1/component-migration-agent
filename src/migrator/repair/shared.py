"""Shared causes (M6): one error, many callers, one definition to fix.

On OpossumUI the codemod added ``size="large"`` to every use of the repo's own
``IconButton`` wrapper, so five files failed the type-check with the same error, and the
repair agent fixed each caller separately, where the developers fixed the wrapper once.

Before Repair starts, failures are grouped: a group is one error code on one name the
failing line uses, imported from one local file. When 3 or more files fail that way,
the local file becomes one repair task, queued first, with every caller's failure in
it; after it, only the callers that still fail are repaired.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from migrator.checks import resolve_import
from migrator.verify import Failure

MIN_CALLERS = 3

_IMPORT = re.compile(
    r"""import\s+(?:type\s+)?(?P<clause>[^;]*?)\s+from\s+['"](?P<spec>\.[^'"]+)['"]""",
    re.DOTALL,
)
_NAME = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


class SharedCause(BaseModel):
    """One group: ``code`` on ``symbol`` from ``source``, in ``callers``."""

    source: str  # the local file that defines the symbol
    symbol: str
    code: str
    callers: list[str]
    failures: list[Failure]  # the callers' failures in this group

    def failure_keys(self) -> set[tuple[str | None, str | None]]:
        return {(f.file, f.code) for f in self.failures}


def local_names(path: str, text: str, files: Mapping[str, str]) -> dict[str, str]:
    """Names ``path`` imports from local files: local name -> the file it comes from."""
    out: dict[str, str] = {}
    for m in _IMPORT.finditer(text):
        target = resolve_import(path, m.group("spec"), files)
        if target is None:
            continue
        clause = m.group("clause")
        default, _, rest = clause.partition("{")
        names = [default.strip(" ,")] if default.strip(" ,") else []
        for part in rest.rstrip("}").split(","):
            name = part.split(" as ")[-1].strip()
            if name and not name.startswith("type "):
                names.append(name)
        for name in names:
            if _NAME.fullmatch(name):
                out[name] = target
    return out


def enclosing_element(path: str, text: str, line: int, column: int) -> str | None:
    """The JSX element whose tag contains (line, column): tsc reports a bad prop at the
    attribute's line (``size="large"``), not at ``<IconButton``."""
    from migrator.scan.parser import node_text, parse_tree

    root = parse_tree(text.encode("utf-8"), path).root_node
    node = root.descendant_for_point_range((line - 1, column - 1), (line - 1, column - 1))
    while node is not None:
        if node.type in ("jsx_opening_element", "jsx_self_closing_element"):
            name = node.child_by_field_name("name")
            return node_text(name).split(".")[0] if name is not None else None
        node = node.parent
    return None


def find_shared_causes(
    failures: Sequence[Failure],
    files: Mapping[str, str],
    test_files: Mapping[str, str],
    min_callers: int = MIN_CALLERS,
) -> list[SharedCause]:
    """Groups of the same coded failure on the same imported name, in 3+ files."""
    groups: dict[tuple[str, str, str], list[Failure]] = {}
    imports: dict[str, dict[str, str]] = {}
    for f in failures:
        if not (f.code and f.line and f.file) or f.file in test_files or f.file not in files:
            continue
        if f.file not in imports:
            imports[f.file] = local_names(f.file, files[f.file], files)
        lines = files[f.file].splitlines()
        if not 0 < f.line <= len(lines):
            continue
        line = lines[f.line - 1][max(0, (f.column or 1) - 1) :] or lines[f.line - 1]
        element = enclosing_element(f.file, files[f.file], f.line, f.column or 1)
        for name in [*([element] if element else []), *_NAME.findall(line)]:
            source = imports[f.file].get(name)
            if source is not None and source not in test_files:
                groups.setdefault((f.code, source, name), []).append(f)
                break
    out: list[SharedCause] = []
    for (code, source, symbol), fs in sorted(groups.items()):
        callers = sorted({f.file for f in fs if f.file})
        if len(callers) >= min_callers:
            out.append(
                SharedCause(source=source, symbol=symbol, code=code, callers=callers, failures=fs)
            )
    return out


def shared_cause_section(cause: SharedCause, path: str) -> str:
    """The first-message section for a shared cause (the source file's or a caller's)."""
    others = [c for c in cause.callers if c != path]
    rows = "\n".join(f"- `{f.file}` line {f.line}: {f.code} {f.message}" for f in cause.failures)
    if path == cause.source:
        head = (
            f"The same error ({cause.code}) appears in {len(cause.callers)} files, all on "
            f"`{cause.symbol}` from this file. Their failures are part of this task: it "
            "passes when they are gone too. Fix the shared definition here when it is the "
            "cause, rather than each caller."
        )
    else:
        head = (
            f"This same error ({cause.code}) appears in {len(others)} other files, all on "
            f"`{cause.symbol}` from `{cause.source}`. If the cause is in that shared "
            "definition, fix it there (it is a local import of this file) instead of here."
        )
    return f"{head}\n\n{rows}"
