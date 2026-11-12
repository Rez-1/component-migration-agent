"""Review aids the Migrator gathers for its evidence (M6): lines repeated across files
and possible test-fitting edits. Hints for a human, never failures; Scoring only copies
them onto the Scorecard."""

from __future__ import annotations

import re

from migrator.checks import Layer
from migrator.scoring import RepeatedEdit, TestFittingFlag


def repeated_edits(
    after_rules: dict[str, str], final: dict[str, str], layers: dict[str, Layer], min_files: int = 3
) -> list[RepeatedEdit]:
    """Lines the later layers added to ``min_files`` or more files (see RepeatedEdit)."""
    import difflib

    by_line: dict[str, set[str]] = {}
    for path, layer in layers.items():
        if layer == "rules" or path not in final:
            continue
        old = after_rules.get(path, "").splitlines()
        for line in difflib.ndiff(old, final[path].splitlines()):
            text = line[2:].strip()
            if line[:2] in ("+ ", "- ") and len(text) >= 6 and any(c.isalnum() for c in text):
                by_line.setdefault(f"{line[0]} {text}", set()).add(path)
    return [
        RepeatedEdit(line=line, files=sorted(paths))
        for line, paths in sorted(by_line.items())
        if len(paths) >= min_files
    ]


_A11Y_PROP = re.compile(
    r"\baria-[a-z]+|\baria[A-Z]\w*|\brole\s*=|\btabIndex\b|\btitle\s*=|\bdescribeChild\b"
    r"|\bcomponent\s*=|\baria-label|\bdisableInteractive\b"
)
_JSX_TAG = re.compile(r"<([A-Za-z][\w.]*)")


def test_fitting_flags(
    after_rules: dict[str, str],
    final: dict[str, str],
    repaired: list[tuple[str, list[str]]],
    test_failing: set[str],
) -> list[TestFittingFlag]:
    """Possible test-fitting edits (see TestFittingFlag). ``repaired`` is each repaired
    file with the files its patch touched; ``test_failing`` the files that failed a test
    before Repair."""
    import difflib

    flags: list[TestFittingFlag] = []
    for path, touched in repaired:
        if path not in test_failing:
            continue
        for rel in touched:
            old, new = after_rules.get(rel, ""), final.get(rel)
            if new is None or old == new:
                continue
            changed = [
                line
                for line in difflib.ndiff(old.splitlines(), new.splitlines())
                if line[:2] in ("+ ", "- ")
            ]
            hits = [line[0] + " " + line[2:].strip() for line in changed if _A11Y_PROP.search(line)]
            added = {t for line in changed if line[0] == "+" for t in _JSX_TAG.findall(line)}
            removed = {t for line in changed if line[0] == "-" for t in _JSX_TAG.findall(line)}
            if added != removed:
                hits += [
                    line[0] + " " + line[2:].strip() for line in changed if _JSX_TAG.search(line)
                ]
            if hits:
                flags.append(
                    TestFittingFlag(file=rel, repaired_for=path, lines=list(dict.fromkeys(hits)))
                )
    return flags
