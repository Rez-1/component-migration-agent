"""The repair prompt: versioned templates, filled from the migration spec (ticket #14).

``prompts/<version>/`` holds the system prompt template, the tool descriptions and the
message templates; a configuration names the version, and any wording change is a new
version. No library names live in the templates: ``library_name``, the versions, the
codemod name, the guide title and ``repair_notes`` come from the migration spec, so the
filled-in system prompt is identical for every file and attempt of a run and the cache
breakpoint after it holds.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path

from langchain_core.documents import Document
from pydantic import BaseModel

from migrator.migrations import MigrationSpec
from migrator.migrations.guide import changes_for_symbol, load_guide
from migrator.repair.context import (
    PatchSize,
    file_view,
    imported_names,
    importers,
    local_imports,
    signatures,
    unified_diff,
)
from migrator.repair.retriever import GuideRetriever, heading, render_section, to_document, unique
from migrator.verify import Failure

PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_TOOL_CALLS = 15  # per attempt (ticket #11)
GUIDE_FULL = 3  # guide sections shown in full; the rest as titles
GUIDE_TITLES = 8
SYMBOL_BONUS = 2.0  # a change about one of the file's own symbols


class UnknownPromptVersionError(LookupError):
    pass


class PromptTemplates(BaseModel):
    version: str
    system: str
    first_message: str
    attempt_result: str
    tools: dict[str, dict[str, str]]
    # Behaviour switches from ``options.toml`` (absent in v1): apply_edit_parse_warning.
    options: dict[str, bool] = {}


@cache
def load_templates(version: str) -> PromptTemplates:
    folder = PROMPTS_DIR / version
    if not folder.is_dir():
        known = ", ".join(sorted(p.name for p in PROMPTS_DIR.iterdir() if p.is_dir()))
        raise UnknownPromptVersionError(f"no repair prompt {version!r} (known: {known})")
    with (folder / "tools.toml").open("rb") as fh:
        tools = tomllib.load(fh)
    options: dict[str, bool] = {}
    if (folder / "options.toml").is_file():
        with (folder / "options.toml").open("rb") as fh:
            options = {k: bool(v) for k, v in tomllib.load(fh).items()}
    return PromptTemplates(
        version=version,
        options=options,
        system=(folder / "system.md").read_text("utf-8"),
        first_message=(folder / "first_message.md").read_text("utf-8"),
        attempt_result=(folder / "attempt_result.md").read_text("utf-8"),
        tools={k: {kk: str(vv) for kk, vv in v.items()} for k, v in tools.items()},
    )


def spec_fields(spec: MigrationSpec) -> dict[str, str]:
    """What the templates are filled with: every library-specific word comes from here."""
    return {
        "library_name": spec.library_name,
        "from_version": spec.from_version,
        "to_version": spec.to_version,
        "codemod_name": spec.codemod_name,
        "guide_title": spec.guide_title,
        "repair_notes": "\n".join(f"- {note}" for note in spec.repair_notes),
    }


def system_prompt(
    templates: PromptTemplates,
    spec: MigrationSpec,
    *,
    max_attempts: int,
    max_tool_calls: int = MAX_TOOL_CALLS,
) -> str:
    from migrator.repair.guardrails import MAX_PATCH_LINES, MAX_PATCH_SHARE

    return templates.system.format_map(
        {
            **spec_fields(spec),
            "max_attempts": max_attempts,
            "max_tool_calls": max_tool_calls,
            "max_patch_lines": MAX_PATCH_LINES,
            "max_patch_percent": round(MAX_PATCH_SHARE * 100),
        }
    ).strip()


def tool_text(templates: PromptTemplates, spec: MigrationSpec) -> dict[str, dict[str, str]]:
    fields = spec_fields(spec)
    return {
        name: {key: value.format_map(fields) for key, value in entries.items()}
        for name, entries in templates.tools.items()
    }


# --------------------------------------------------------------------------- failures


def describe_failure(f: Failure, path: str) -> str:
    if f.source == "typecheck":
        where = f", line {f.line}" if f.line else ""
        return f"**Type error** {f.code or ''}{where}: {f.message}".replace("  ", " ")
    if f.source == "lint":
        where = f", line {f.line}" if f.line else ""
        return f"**Lint error** {f.code or ''}{where}: {f.message}".replace("  ", " ")
    if f.source == "migration":  # M7: what is left of the old version
        where = f", line {f.line}" if f.line else ""
        return f"**Not migrated yet**{where}: {f.message}"
    attributed = "" if f.test_file is None or f.file != path else " (This test imports this file.)"
    return f'**Failing test** `{f.test_file}` › "{f.test_title}": {f.message}{attributed}'


def failure_list(failures: Sequence[Failure], path: str) -> str:
    if not failures:
        return "None."
    return "\n".join(f"{i}. {describe_failure(f, path)}" for i, f in enumerate(failures, 1))


def failure_elsewhere(f: Failure, files: Mapping[str, str]) -> str:
    if f.source == "test":
        return f'Failing test `{f.test_file}` › "{f.test_name}": {f.message}'
    kind = {"typecheck": "Type error", "lint": "Lint error", "migration": "Not migrated yet"}[
        f.source
    ]
    where = f"`{f.file}` line {f.line}" if f.line else f"`{f.file}`"
    text = f"{kind} {f.code or ''}, {where}: {f.message}".replace("  ", " ")
    if f.file and f.line and f.file in files:
        lines = files[f.file].splitlines()
        if 0 < f.line <= len(lines):
            text += f" Line {f.line} reads `{lines[f.line - 1].strip()}`."
    return text


# --------------------------------------------------------------------------- guide

_NAME = re.compile(
    r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+|[a-z]+[A-Z][\w$]*|[A-Z][a-z]+[A-Z][\w$]*"
)
_QUOTED = re.compile(r"'([A-Za-z_$][\w$.]*)'|\"([A-Za-z_$][\w$.]*)\"")


def guide_query(
    symbols: Sequence[str], failures: Sequence[Failure], text: str
) -> tuple[str, list[str]]:
    """The keyword query for a file: the code on its failing lines, the names its
    failure messages quote, and its failing tests' names and messages. The symbols of
    the file's usages pick candidate sections (``guide_sections``); they join the query
    only when the failures give nothing to search for, because a symbol that names a
    whole guide section (``Theme``) would otherwise outrank the change that matters."""
    lines = text.splitlines()
    parts: list[str] = []
    for f in failures:
        if f.line and 0 < f.line <= len(lines) and f.source != "test":
            parts.append(lines[f.line - 1].strip())
        for m in _QUOTED.finditer(f.message):
            parts.append(m.group(1) or m.group(2))
        if f.source == "test":
            parts.append(f"{f.test_name or ''} {f.message}")
    if not parts:
        parts = list(dict.fromkeys(symbols))
    names = [n for p in parts for n in _NAME.findall(p)]
    shown = list(dict.fromkeys(names))[:6]
    return " ".join(parts), shown


_IMPORT = re.compile(
    r"import\s+(?:type\s+)?(?P<clause>[^;]*?)\s+from\s+['\"](?P<module>[^'\"]+)['\"]", re.S
)
_PASCAL = re.compile(r"^[A-Z][A-Za-z0-9]*$")
IMPORT_BOOST = 2.0  # keyword-imports: a section about a component the file imports
FOREIGN_FACTOR = 0.25  # ... and the score left to a section about a component it doesn't


def library_imports(text: str, modules: Sequence[str]) -> list[str]:
    """Names a file imports from the library's packages (``modules`` are prefixes such
    as ``@mui/``): ``import { Autocomplete } from '@mui/material'`` and
    ``import Autocomplete from '@mui/material/Autocomplete'`` both give ``Autocomplete``."""
    out: list[str] = []
    for m in _IMPORT.finditer(text):
        module = m.group("module")
        if not any(module == prefix or module.startswith(prefix + "/") for prefix in modules):
            continue
        clause = m.group("clause")
        bare = clause.replace("{", " ").replace("}", " ")
        names = re.findall(r"[A-Za-z_$][\w$]*(?:\s+as\s+[A-Za-z_$][\w$]*)?", bare)
        for name in names:
            original = name.split()[0]
            if original not in ("type", "as", "default") and original not in out:
                out.append(original)
        last = module.rsplit("/", 1)[-1]
        if _PASCAL.match(last) and last not in out:
            out.append(last)
    return out


def enclosing_props(text: str, path: str, lines: Sequence[int]) -> list[str]:
    """The JSX props a failing line sits inside (``renderOption`` for a line in
    ``renderOption={(o) => <span>{o.label}</span>}``), innermost first. The failing
    line's own words often name only the markup, while the prop names the API."""
    from migrator.scan.parser import parse_tree

    if not path.endswith((".tsx", ".jsx", ".ts", ".js")):
        return []
    data = text.encode("utf-8")
    root = parse_tree(data, path).root_node
    out: list[str] = []
    for line in lines:
        row = line - 1
        if row < 0:
            continue
        line_text = data.splitlines()[row] if row < len(data.splitlines()) else b""
        col = len(line_text) - len(line_text.lstrip())
        node = root.descendant_for_point_range((row, col), (row, max(col, len(line_text) - 1)))
        while node is not None:
            if node.type == "jsx_attribute" and node.named_children:
                name = (node.named_children[0].text or b"").decode("utf-8", "replace")
                if name and name not in out:
                    out.append(name)
            node = node.parent
    return out


IMPORT_MODES = ("keyword-imports", "keyword-context")


def section_query(
    spec: MigrationSpec,
    retriever: GuideRetriever,
    *,
    path: str,
    symbols: Sequence[str],
    failures: Sequence[Failure],
    text: str,
) -> tuple[str, list[str], list[str]]:
    """The first message's guide query for a file under the retriever's mode:
    (query, names to show, the file's imports from the new packages). With
    ``keyword-context`` the JSX props around the failing lines join the query."""
    query, shown = guide_query(symbols, failures, text)
    imports = library_imports(text, spec.import_prefixes())
    if retriever.mode == "keyword-context":
        lines = [f.line for f in failures if f.line and f.source != "test"]
        props = enclosing_props(text, path, lines)
        if props:
            query = f"{query} {' '.join(props)}"
            shown = list(dict.fromkeys([*props, *shown]))[:6]
    return query, shown, imports


def rank_sections(
    spec: MigrationSpec,
    retriever: GuideRetriever,
    symbols: Sequence[str],
    query: str,
    imports: Sequence[str] = (),
) -> list[Document]:
    """The guide sections for a file's first message, best first. Candidates: the
    changes about the file's own symbols (which get a small bonus) and a keyword search
    over the whole guide, ranked by the failures' query.

    With ``retrieval = "keyword-imports"`` (M5) the file's own components weigh more: a
    section named after a component the file uses (its old-library symbols and what it
    imports from the new packages) gets ``IMPORT_BOOST``, and a section named after a
    component it does not use keeps ``FOREIGN_FACTOR`` of its score. Failure text such
    as "label" or "span" matches every component's "span and label" change, while only
    the components in the file can be the cause."""
    changes = load_guide(spec.guide_dir(), spec.guide)
    by_symbol = unique(to_document(c) for s in symbols for c in changes_for_symbol(s, changes))
    searched = retriever.rank(query, k=GUIDE_FULL + GUIDE_TITLES)
    candidates = unique([*searched, *by_symbol])
    if not candidates:
        return []
    ids = [str(d.metadata["id"]) for d in retriever.documents]
    scores = dict(zip(ids, retriever.scores(query), strict=True))
    own = {str(d.metadata["id"]) for d in by_symbol}
    by_imports = retriever.mode in IMPORT_MODES
    used = {*symbols, *imports}
    components = {str(d.metadata["section"]) for d in retriever.documents}
    components = {c for c in components if _PASCAL.match(c)}

    def score(d: Document) -> float:
        key = str(d.metadata["id"])
        value = scores.get(key, 0.0) + (SYMBOL_BONUS if key in own else 0.0)
        if by_imports:
            section = str(d.metadata["section"])
            if section in used:
                value += IMPORT_BOOST
            elif section in components:
                value *= FOREIGN_FACTOR
        return value

    ranked = sorted(candidates, key=lambda d: -score(d))
    # The file's own components get the first slot: a failure's code words ("label",
    # "span") match many sections, while the component that owns the failing line is
    # usually the one whose change it is.
    best_own = next(
        (d for d in ranked if str(d.metadata["id"]) in own and score(d) > SYMBOL_BONUS), None
    )
    if best_own is not None:
        ranked.remove(best_own)
        ranked.insert(0, best_own)
    return ranked


def guide_sections(
    spec: MigrationSpec,
    retriever: GuideRetriever,
    symbols: Sequence[str],
    query: str,
    imports: Sequence[str] = (),
) -> str:
    """Top 3 sections in full (codemod-marked ones included and labelled), the rest as
    titles (``rank_sections`` orders them)."""
    ranked = rank_sections(spec, retriever, symbols, query, imports)
    if not ranked:
        return "No section matched; `search_guide` looks up a component or API by name."
    full = [render_section(d, spec.guide.link_base) for d in ranked[:GUIDE_FULL]]
    titles = [f"- {heading(d)}" for d in ranked[GUIDE_FULL : GUIDE_FULL + GUIDE_TITLES]]
    out = "\n\n".join(full)
    if titles:
        out += "\n\nAlso possibly relevant (`search_guide` for the text):\n\n" + "\n".join(titles)
    return out


# --------------------------------------------------------------------------- messages


def _fence(path: str) -> str:
    return {"tsx": "tsx", "ts": "ts", "jsx": "jsx", "js": "js"}.get(path.rsplit(".", 1)[-1], "")


def first_message(
    templates: PromptTemplates,
    spec: MigrationSpec,
    retriever: GuideRetriever,
    *,
    path: str,
    max_attempts: int,
    failures: Sequence[Failure],
    untouched: str | None,
    after_rules: str,
    files: Mapping[str, str],
    test_files: Mapping[str, str],
    symbols: Sequence[str],
) -> str:
    """The first user message of a file's conversation (Migrator-written, no LLM)."""
    diff = unified_diff(path, untouched, after_rules)
    rules_diff = (
        f"```diff\n{diff}```" if diff else "Nothing: the Rules stage left this file as it was."
    )
    heading_text, text = file_view(after_rules, [f.line for f in failures if f.line])
    imports = local_imports(path, files)
    import_lines = [
        f"- `{imp}`: "
        + (", ".join(f"`{s}`" for s in signatures(imp, files[imp])) or "(no exports)")
        for imp in imports
    ]
    used = {k: v for k, v in importers(path, files).items() if k not in test_files}
    used_lines = [f"- `{k}` imports `{imported_names(v)}` from this file." for k, v in used.items()]
    query, shown, imports = section_query(
        spec, retriever, path=path, symbols=symbols, failures=failures, text=after_rules
    )
    guide = guide_sections(spec, retriever, symbols, query, imports)
    return templates.first_message.format_map(
        {
            "path": path,
            "max_attempts": max_attempts,
            "failure_count": len(failures),
            "failures": failure_list(failures, path),
            "rules_diff": rules_diff,
            "file_heading": heading_text,
            "fence": _fence(path),
            "file_text": text,
            "imports": "\n".join(import_lines) or "None.",
            "used_by": "\n".join(used_lines) or "No other source file imports this file.",
            "guide_query": ", ".join(f"`{s}`" for s in shown) or "the failures",
            "guide": guide,
        }
    ).strip()


def attempt_result(
    templates: PromptTemplates,
    *,
    attempt: int,
    max_attempts: int,
    note: str,
    left: Sequence[Failure],
    elsewhere: Sequence[Failure],
    path: str,
    files: Mapping[str, str],
    patches: Mapping[str, PatchSize],
) -> str:
    """What the Migrator appends after an attempt that did not pass (no LLM)."""
    attempts_left = max_attempts - attempt
    left_list = "".join(f"\n  - {describe_failure(f, path)}" for f in left)
    elsewhere_list = "".join(f"\n  - {failure_elsewhere(f, files)}" for f in elsewhere)
    patch = "; ".join(f"`{p}` {s.describe()}" for p, s in patches.items()) or "no edits"
    if attempts_left > 0:
        nxt = f"Attempt {attempt + 1} of {max_attempts}."
        if elsewhere:
            nxt += " Fix the new failures without bringing back the old ones."
    else:
        nxt = "No attempts left: this file goes to a human."
    return templates.attempt_result.format_map(
        {
            "attempt": attempt,
            "note": note,
            "failures_left": len(left),
            "failures_left_list": left_list,
            "new_elsewhere": len(elsewhere),
            "new_elsewhere_list": elsewhere_list,
            "patch": patch,
            "attempts_left": attempts_left,
            "next_step": nxt,
        }
    ).strip()
