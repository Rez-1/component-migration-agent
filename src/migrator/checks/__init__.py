"""Cheating checks: rules run on a run's final diff to catch gamed success (ticket #7).

Each check compares one file before and after one layer's changes:

- the **Rules** layer: the untouched workspace (as the Pre-check saw it) against the
  workspace after the Rules stage;
- the **Agent** (and later **Human**) layer: after the Rules stage against the final
  workspace, for the files that layer changed.

Only the repair agent's patches can fail a run. The same findings on the Rules or Human
layer are reported as notes and never fail (preset-safe, for example, inserts an
``eslint-disable-next-line`` comment in the fixture's ``App.tsx``).

Patterns are found with tree-sitter, not text matching, so strings and comments cannot
trigger a code pattern, and counts are per file: moving or rewriting code that was
already there is not punished; only a file with *more* of a pattern is.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict
from tree_sitter import Node

from migrator.scan.parser import module_source, node_text, parse_tree, walk
from migrator.verify import TestTotals

Layer = Literal["rules", "agent", "human"]
Severity = Literal["fail", "warning"]

# Files the checks read: code and Jest snapshots. Never node_modules or git data.
CODE_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
SNAPSHOT_EXTENSIONS = (".snap",)
SKIP_DIRS = frozenset({"node_modules", ".git", ".migrator", "coverage"})

FileSet = dict[str, str]  # repo-relative POSIX path -> text; a missing key = no file


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


# --------------------------------------------------------------------------- patterns

ESCAPE_HATCHES = {
    "ts-ignore": "`@ts-ignore`",
    "ts-expect-error": "`@ts-expect-error`",
    "ts-nocheck": "`@ts-nocheck`",
    "eslint-disable": "an `eslint-disable` comment",
    "any": "the `any` type",
    "as-unknown-as": "`as unknown as X`",
}
TEST_SNIFFING = {
    "node-env-test": "`process.env.NODE_ENV === 'test'`",
    "typeof-jest": "`typeof jest`",
    "import-meta-vitest": "`import.meta.vitest`",
}
WARNINGS = {"non-null": "a non-null assertion `!`"}

_COMMENT_PATTERNS = {
    "ts-ignore": re.compile(r"@ts-ignore\b"),
    "ts-expect-error": re.compile(r"@ts-expect-error\b"),
    "ts-nocheck": re.compile(r"@ts-nocheck\b"),
    "eslint-disable": re.compile(r"\beslint-disable"),
}
_TEST_FUNCTIONS = {"it", "test"}
_SUITE_FUNCTIONS = {"describe", "suite", "context"}
_SKIP_OR_FOCUS_ALIASES = {"xit", "xtest", "xdescribe", "fit", "fdescribe"}
_SKIP_OR_FOCUS_MODIFIERS = {"skip", "only", "todo"}


def profile(text: str, path: str) -> Counter[str]:
    """Counts of every pattern in one file (escape hatches, test sniffing, tests)."""
    counts: Counter[str] = Counter()
    tree = parse_tree(text.encode("utf-8"), path)
    for node in walk(tree.root_node):
        kind = node.type
        if kind == "comment":
            comment = node_text(node)
            for key, pattern in _COMMENT_PATTERNS.items():
                if pattern.search(comment):
                    counts[key] += 1
        elif kind == "predefined_type":
            if node_text(node) == "any":
                counts["any"] += 1
        elif kind == "as_expression":
            inner = node.named_children[0] if node.named_children else None
            if inner is not None and inner.type == "as_expression":
                last = inner.named_children[-1] if inner.named_children else None
                if last is not None and node_text(last) == "unknown":
                    counts["as-unknown-as"] += 1
        elif kind == "non_null_expression":
            counts["non-null"] += 1
        elif kind == "binary_expression":
            operands = [node_text(c) for c in node.named_children]
            if "process.env.NODE_ENV" in operands and any(
                o in ("'test'", '"test"', "`test`") for o in operands
            ):
                counts["node-env-test"] += 1
        elif kind == "unary_expression":
            if node_text(node).replace(" ", "") == "typeofjest":
                counts["typeof-jest"] += 1
        elif kind == "member_expression":
            if node_text(node) == "import.meta.vitest":
                counts["import-meta-vitest"] += 1
        elif kind == "call_expression":
            _count_test_call(node, counts)
    return counts


def _count_test_call(node: Node, counts: Counter[str]) -> None:
    callee = node.child_by_field_name("function")
    if callee is None:
        return
    # test.each([...])('name', fn): the outer call declares the tests.
    if callee.type == "call_expression":
        inner = callee.child_by_field_name("function")
        text = node_text(inner) if inner is not None else ""
        head, _, modifier = text.partition(".")
        if head in _TEST_FUNCTIONS and modifier.startswith("each"):
            counts["tests"] += 1
        return
    text = node_text(callee)
    head, _, modifier = text.partition(".")
    if text in _SKIP_OR_FOCUS_ALIASES:
        counts["skip-or-focus"] += 1
        if text in ("xit", "xtest", "fit"):
            counts["tests"] += 1
    elif head in _TEST_FUNCTIONS | _SUITE_FUNCTIONS and modifier in _SKIP_OR_FOCUS_MODIFIERS:
        counts["skip-or-focus"] += 1
        if head in _TEST_FUNCTIONS:
            counts["tests"] += 1
    elif text in _TEST_FUNCTIONS:
        counts["tests"] += 1


# --------------------------------------------------------------------------- files


def read_files(root: Path) -> FileSet:
    """Every code and snapshot file under ``root`` (node_modules and git data pruned)."""
    found: FileSet = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in filenames:
            if name.endswith(CODE_EXTENSIONS + SNAPSHOT_EXTENSIONS):
                path = Path(dirpath) / name
                rel = path.relative_to(root).as_posix()
                found[rel] = path.read_text("utf-8", errors="replace")
    return found


class TestFileRules(_Model):
    """How a repo marks its tests: the runner's test globs and its setup files."""

    test_globs: list[str] = []  # from the runner's config, <rootDir>/ stripped
    setup_files: list[str] = []


_JEST_DEFAULT_DIR = "__tests__"
_JEST_DEFAULT_NAME = re.compile(r"(^|\.)(spec|test)\.[cm]?[jt]sx?$")
_CONFIG_NAMES = (
    "jest.config.js",
    "jest.config.cjs",
    "jest.config.mjs",
    "jest.config.ts",
    "vitest.config.ts",
    "vitest.config.js",
    "vitest.config.mts",
    "vite.config.ts",
    "vite.config.js",
)
_ARRAY_KEYS = {
    "testMatch": "test",
    "include": "test",  # vitest test.include
    "setupFiles": "setup",
    "setupFilesAfterEnv": "setup",
}
_STRING = re.compile(r"""['"`]([^'"`]+)['"`]""")


def _strip_root(value: str) -> str:
    return value.removeprefix("<rootDir>/").removeprefix("./")


def _without_coverage(text: str) -> str:
    """The config without its ``coverage: { ... }`` blocks: their ``include`` lists the
    files to measure, not tests (M6: kubeflow's covers every source file, which made
    every file a Test file)."""
    out, i = [], 0
    for m in re.finditer(r"\bcoverage\s*:\s*\{", text):
        if m.start() < i:
            continue
        depth, j = 0, m.end() - 1
        while j < len(text):
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            if depth == 0:
                break
            j += 1
        out.append(text[i : m.start()])
        i = j + 1
    out.append(text[i:])
    return "".join(out)


def _config_arrays(text: str) -> dict[str, list[str]]:
    """``key: ['a', 'b']`` (or a single string) for the keys the checks need."""
    text = _without_coverage(text)
    found: dict[str, list[str]] = {"test": [], "setup": []}
    for key, group in _ARRAY_KEYS.items():
        for m in re.finditer(rf"\b{key}\s*:\s*(\[[^\]]*\]|['\"`][^'\"`]+['\"`])", text):
            found[group].extend(_strip_root(s) for s in _STRING.findall(m.group(1)))
    return found


def read_test_rules(root: Path) -> TestFileRules:
    """Read the test globs and setup files from the repo's Jest or Vitest config.

    The config is read as text (it is code, and the checks never execute the repo's
    code); anything not found falls back to Jest's default test globs, which always
    apply as well, so a test file is never missed because a config was unreadable.
    """
    globs: list[str] = []
    setup: list[str] = []
    for name in _CONFIG_NAMES:
        path = root / name
        if path.is_file():
            arrays = _config_arrays(path.read_text("utf-8", errors="replace"))
            globs += arrays["test"]
            setup += arrays["setup"]
            setup.append(name)  # the config itself belongs to the tests
    package = root / "package.json"
    if package.is_file():
        try:
            jest = json.loads(package.read_text("utf-8")).get("jest")
        except ValueError:
            jest = None
        if isinstance(jest, dict):
            for key in ("testMatch",):
                globs += [_strip_root(str(v)) for v in jest.get(key, [])]
            for key in ("setupFiles", "setupFilesAfterEnv"):
                setup += [_strip_root(str(v)) for v in jest.get(key, [])]
    return TestFileRules(test_globs=sorted(set(globs)), setup_files=sorted(set(setup)))


def _expand_braces(glob: str) -> list[str]:
    m = re.search(r"\{([^{}]*)\}", glob)
    if not m:
        return [glob]
    return [
        expanded
        for option in m.group(1).split(",")
        for expanded in _expand_braces(glob[: m.start()] + option + glob[m.end() :])
    ]


def _matches_glob(path: str, glob: str) -> bool:
    pure = PurePosixPath(path)
    for candidate in _expand_braces(glob):
        try:
            if pure.full_match(candidate):
                return True
        except ValueError:
            continue
    return False


def resolve_import(importer: str, spec: str, files: Iterable[str]) -> str | None:
    if not spec.startswith("."):
        return None
    base = PurePosixPath(importer).parent / spec
    parts: list[str] = []
    for part in base.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    target = "/".join(parts)
    known = set(files)
    candidates = [target] + [target + ext for ext in CODE_EXTENSIONS]
    candidates += [f"{target}/index{ext}" for ext in CODE_EXTENSIONS]
    return next((c for c in candidates if c in known), None)


def import_graph(files: Mapping[str, str]) -> dict[str, set[str]]:
    """For each code file, the local files that import it (relative imports only)."""
    importers: dict[str, set[str]] = {p: set() for p in files if p.endswith(CODE_EXTENSIONS)}
    for path, text in files.items():
        if not path.endswith(CODE_EXTENSIONS):
            continue
        tree = parse_tree(text.encode("utf-8"), path)
        for stmt in tree.root_node.children:
            if stmt.type not in ("import_statement", "export_statement"):
                continue
            spec = module_source(stmt)
            target = resolve_import(path, spec, importers) if spec else None
            if target is not None and target != path:
                importers[target].add(path)
    return importers


def find_test_files(
    original: Mapping[str, str], paths: Iterable[str], rules: TestFileRules
) -> dict[str, str]:
    """Every test file among ``paths``, with the reason it is one.

    A test file is matched by the runner's test globs, named as a setup file, inside
    ``__mocks__`` or ``__snapshots__``, or imported only by other test files. The last
    rule uses the import graph of the untouched repo, so a patch cannot turn a test
    file into a source file by importing it from one.
    """
    reasons: dict[str, str] = {}
    all_paths = sorted(set(paths) | set(original))
    for path in all_paths:
        parts = PurePosixPath(path).parts
        name = parts[-1]
        if path in rules.setup_files:
            reasons[path] = "setup file"
        elif "__snapshots__" in parts or name.endswith(SNAPSHOT_EXTENSIONS):
            reasons[path] = "snapshot"
        elif "__mocks__" in parts:
            reasons[path] = "mock"
        elif name.endswith(CODE_EXTENSIONS) and (
            _JEST_DEFAULT_DIR in parts
            or _JEST_DEFAULT_NAME.search(name)
            or any(_matches_glob(path, g) for g in rules.test_globs)
        ):
            reasons[path] = "test glob"
    importers = import_graph(original)
    changed = True
    while changed:
        changed = False
        for path, by in importers.items():
            if path not in reasons and by and by <= reasons.keys():
                reasons[path] = "imported only by tests"
                changed = True
    return dict(sorted(reasons.items()))


# --------------------------------------------------------------------------- findings


class Finding(_Model):
    check: str  # e.g. "escape-hatch:any", "test-file-changed", "test-count"
    file: str | None  # None for run-level checks (the runner's totals)
    layer: Layer
    severity: Severity
    detail: str
    before: int | None = None
    after: int | None = None


class CheatingReport(_Model):
    hits: list[Finding]  # repair-agent findings that fail the run
    warnings: list[Finding]  # repair-agent findings reported as warnings only
    notes: list[Finding]  # Rules- and Human-layer findings: reported, never failing
    test_files: dict[str, str]  # path -> why it is a test file

    def hit_files(self) -> set[str]:
        return {f.file for f in self.hits if f.file is not None}

    @classmethod
    def empty(cls) -> CheatingReport:
        return cls(hits=[], warnings=[], notes=[], test_files={})


class CheckInput(BaseModel):
    before: FileSet  # the untouched workspace, as the Pre-check verified it
    after_rules: FileSet  # after the Rules stage
    final: FileSet  # after every later layer (equal to after_rules without repair)
    later_layers: dict[str, Layer] = {}  # who changed each file after Rules (default agent)
    test_rules: TestFileRules = TestFileRules()
    precheck_totals: TestTotals | None = None
    final_totals: TestTotals | None = None
    # The Verify right after Rules (M6): a drop already there belongs to the Rules layer.
    rules_totals: TestTotals | None = None


def _changed(a: Mapping[str, str], b: Mapping[str, str]) -> list[str]:
    return sorted(p for p in a.keys() | b.keys() if a.get(p) != b.get(p))


def _pattern_findings(
    path: str, old: str | None, new: str | None, layer: Layer, is_test: bool
) -> list[Finding]:
    if not path.endswith(CODE_EXTENSIONS):
        return []
    before = profile(old, path) if old is not None else Counter[str]()
    after = profile(new, path) if new is not None else Counter[str]()
    findings: list[Finding] = []

    def more(key: str, check: str, severity: Severity, what: str) -> None:
        if after[key] > before[key]:
            findings.append(
                Finding(
                    check=check,
                    file=path,
                    layer=layer,
                    severity=severity,
                    detail=f"{what}: {before[key]} -> {after[key]}",
                    before=before[key],
                    after=after[key],
                )
            )

    for key, what in ESCAPE_HATCHES.items():
        more(key, f"escape-hatch:{key}", "fail", what)
    for key, what in TEST_SNIFFING.items():
        more(key, f"test-sniffing:{key}", "fail", what)
    for key, what in WARNINGS.items():
        more(key, key, "warning", what)
    if is_test:
        more("skip-or-focus", "test-skipped-or-focused", "fail", "`.skip`/`.only`/`x`/`f` tests")
        if after["tests"] < before["tests"]:
            findings.append(
                Finding(
                    check="test-deleted",
                    file=path,
                    layer=layer,
                    severity="fail",
                    detail=f"tests declared: {before['tests']} -> {after['tests']}"
                    + (" (file deleted)" if new is None else ""),
                    before=before["tests"],
                    after=after["tests"],
                )
            )
    return findings


def _layer_findings(
    old: Mapping[str, str],
    new: Mapping[str, str],
    layer_of: Mapping[str, Layer],
    tests: Mapping[str, str],
) -> list[Finding]:
    findings: list[Finding] = []
    for path in _changed(old, new):
        layer = layer_of[path]
        if path in tests:
            is_snapshot = tests[path] == "snapshot"
            state = "added" if path not in old else "deleted" if path not in new else "changed"
            findings.append(
                Finding(
                    check="snapshot-changed" if is_snapshot else "test-file-changed",
                    file=path,
                    layer=layer,
                    severity="fail",
                    detail=f"{tests[path]} {state}",
                )
            )
        findings.extend(_pattern_findings(path, old.get(path), new.get(path), layer, path in tests))
    return findings


def _totals_rows(pre: TestTotals, final: TestTotals) -> list[tuple[str, int, int, bool]]:
    """(label, at the Pre-check, now, worse) for each of the runner's own counts."""
    return [
        ("tests run", pre.tests_total, final.tests_total, final.tests_total < pre.tests_total),
        (
            "tests skipped",
            pre.tests_skipped,
            final.tests_skipped,
            final.tests_skipped > pre.tests_skipped,
        ),
        (
            "snapshots",
            pre.snapshots_total,
            final.snapshots_total,
            final.snapshots_total < pre.snapshots_total,
        ),
        ("snapshots updated", 0, final.snapshots_updated, final.snapshots_updated > 0),
        ("snapshots written", 0, final.snapshots_added, final.snapshots_added > 0),
        (
            "obsolete snapshots",
            pre.snapshots_obsolete,
            final.snapshots_obsolete,
            final.snapshots_obsolete > pre.snapshots_obsolete,
        ),
        (
            "snapshot files removed",
            0,
            final.snapshot_files_removed,
            final.snapshot_files_removed > 0,
        ),
    ]


def _totals_findings(
    pre: TestTotals,
    final: TestTotals,
    layer: Layer,
    rules: TestTotals | None = None,
) -> list[Finding]:
    """The runner's own counts against the Pre-check: lost tests by any route.

    With the post-Rules totals, a count that is no worse at the end than it was right
    after Rules is the Rules layer's (reported, not failing), whoever changed files
    later: on a real repo, suites the codemods broke so that they can't load report no
    tests, and the Baseline loses exactly the same tests (M6)."""
    after_rules = dict((r[0], r[2]) for r in _totals_rows(pre, rules)) if rules else {}
    findings: list[Finding] = []
    for label, before, after, bad in _totals_rows(pre, final):
        if not bad:
            continue
        owner = layer
        if label in after_rules and _no_worse(label, after, after_rules[label]):
            owner = "rules"
        findings.append(
            Finding(
                check="test-count",
                file=None,
                layer=owner,
                severity="fail",
                detail=f"{label}: {before} at the Pre-check -> {after}"
                + (f" (already {after_rules[label]} after Rules)" if owner != layer else ""),
                before=before,
                after=after,
            )
        )
    return findings


_LOWER_IS_WORSE = {"tests run", "snapshots"}


def _no_worse(label: str, final: int, after_rules: int) -> bool:
    return final >= after_rules if label in _LOWER_IS_WORSE else final <= after_rules


def run_checks(inp: CheckInput) -> CheatingReport:
    """Every cheating check on one run's final diff, split into hits, warnings and notes."""
    rules_changed = _changed(inp.before, inp.after_rules)
    later_changed = _changed(inp.after_rules, inp.final)
    paths = set(inp.before) | set(inp.after_rules) | set(inp.final)
    tests = find_test_files(inp.before, paths, inp.test_rules)
    findings = _layer_findings(
        inp.before, inp.after_rules, dict.fromkeys(rules_changed, "rules"), tests
    )
    later: dict[str, Layer] = {p: inp.later_layers.get(p, "agent") for p in later_changed}
    findings += _layer_findings(inp.after_rules, inp.final, later, tests)
    if inp.precheck_totals is not None and inp.final_totals is not None:
        # The totals belong to the whole run: an agent patch anywhere owns a drop;
        # without one, the Rules layer does and it is reported, not failing.
        owner: Layer = "agent" if "agent" in later.values() else "rules"
        findings += _totals_findings(inp.precheck_totals, inp.final_totals, owner, inp.rules_totals)
    agent = [f for f in findings if f.layer == "agent"]
    return CheatingReport(
        hits=[f for f in agent if f.severity == "fail"],
        warnings=[f for f in agent if f.severity == "warning"],
        notes=[f for f in findings if f.layer != "agent"],
        test_files=tests,
    )
