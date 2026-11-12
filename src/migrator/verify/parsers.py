"""Turn type-check, lint and test-runner output into Failures.

- tsc: its plain-text diagnostics (``file(line,col): error TSnnnn: message``).
- ESLint: its JSON formatter, with the default "stylish" text as a fallback.
- Jest: its ``--json`` report, which also carries the totals the cheating checks
  compare with the Pre-check (tests run, skipped, snapshots).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# "migration": what is left of the old version after the Rules stage (M7, leftovers).
FailureSource = Literal["typecheck", "lint", "test", "migration"]
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# How a failing test is named, as stored in every result and scorecard. Only this
# module spells them; everyone else asks a Failure (``ran_no_spec`` and the rest).
TEST_NAME_JOINER = " › "  # between a test's describe blocks and its title
NO_SPEC_RAN = "(build)"  # the test bundle didn't compile, so no spec ran (Karma)
WHOLE_SUITE = "(suite)"  # a test file that failed outside any test


def split_test_check(check: str) -> tuple[str, str]:
    """A Trap's test check (the test file and the test name, joined as in a failing
    test's name) as (test file, test name). Trap checks are hand-written in this format;
    this is the one place that reads it."""
    test_file, _, name = check.partition(TEST_NAME_JOINER)
    return test_file.strip(), name.strip()


class Failure(BaseModel):
    """One problem reported by verification, with its file, line and message.

    For a failing test, ``file`` is the file under test (``__tests__/Search.test.tsx``
    is charged to ``Search.tsx``) and ``test_file``/``test_name`` say which test failed.
    """

    model_config = ConfigDict(frozen=True)

    source: FailureSource
    file: str | None
    line: int | None = None
    column: int | None = None
    code: str | None = None  # TS2322, an ESLint rule id
    message: str
    test_file: str | None = None
    test_name: str | None = None

    def key(self) -> tuple[str | None, ...]:
        """Identity across runs, ignoring line numbers (the codemods move code)."""
        if self.source == "test":
            return (self.source, self.test_file, self.test_name, None)
        return (self.source, self.file, self.code, self.message)

    @property
    def ran_no_spec(self) -> bool:
        """The test bundle didn't compile, so no test ran at all (Karma, M7)."""
        return self.source == "test" and self.test_name == NO_SPEC_RAN

    @property
    def whole_suite_failed(self) -> bool:
        """A test file failed outside any test (a compile error, a crash on import)."""
        return self.source == "test" and self.test_name == WHOLE_SUITE

    @property
    def test_title(self) -> str:
        """The failing test's name to show; a failure with none reads as its suite."""
        return self.test_name or WHOLE_SUITE

    def matches_test_check(self, check: str) -> bool:
        """This failure is the test a Trap's check names (``split_test_check``): that
        test, by its full name or its title, or its whole suite failing."""
        test_file, name = split_test_check(check)
        return (
            self.source == "test"
            and self.test_file == test_file
            and self.test_name is not None
            and (
                self.test_name == name
                or self.whole_suite_failed
                or self.test_name.endswith(f"{TEST_NAME_JOINER}{name}")
            )
        )


class TestTotals(BaseModel):
    """The test runner's own counts, for comparing a run with its Pre-check."""

    model_config = ConfigDict(frozen=True)

    suites_total: int
    suites_failed: int
    tests_total: int
    tests_passed: int
    tests_failed: int
    tests_skipped: int  # pending + todo
    snapshots_total: int
    snapshots_unmatched: int
    snapshots_updated: int
    snapshots_added: int
    snapshots_obsolete: int  # "unchecked" in Jest's report
    snapshot_files_removed: int


def clean(text: str, workspace: str | None = None) -> str:
    """Strip colour codes and the workspace's absolute path; the folder around the
    workspace (a run's own temporary folder) becomes ``..``, so a test that names a path
    next to the workspace has the same name in every run (M6: kubeflow's
    ``should be in sync with …/backend/…`` test; with a different temp folder per run its
    failure never matched the Pre-check's, once the Pre-check came from a cache)."""
    text = _ANSI.sub("", text)
    if workspace:
        root = workspace.rstrip("/") + "/"
        parent = root.rstrip("/").rsplit("/", 1)[0] + "/"
        for prefix in (root, root.removeprefix("/private") if root.startswith("/private/") else ""):
            if prefix:
                text = text.replace(prefix, "")
        for prefix in (
            parent,
            parent.removeprefix("/private") if parent.startswith("/private/") else "",
        ):
            if prefix and prefix != "/":
                text = text.replace(prefix, "../")
    return text


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


SUITE_MESSAGE_CHARS = 700
_REPO_FRAME = re.compile(r"^at .*?\(((?!node_modules/)[^()\s]+:\d+:\d+)\)$")
_SUITE_BOILERPLATE = (
    "Test suite failed to run",
    "Jest encountered an unexpected token",
    "This usually means",
    "By default, if Jest sees",
    "Here's what you can do",
    "You'll find more details",
    "•",
)


def suite_message(text: str) -> str:
    """A suite that failed outside any test (it could not load): its real error, not
    Jest's first line. Jest puts that first line ("Test suite failed to run") and a
    block of generic advice before the error, so keep the lines after "Details:" when
    there are any, else the first lines that aren't boilerplate; joined with " | " and
    bounded (M6: on a real repo the agent saw only the first line and could not act)."""
    lines = [line.strip() for line in text.splitlines()]
    if "Details:" in lines:
        lines = lines[lines.index("Details:") + 1 :]
    kept = [
        line
        for line in lines
        if line and not line.startswith("●") and not line.startswith(_SUITE_BOILERPLATE)
    ][:8]
    body = " | ".join(kept)
    if len(body) > SUITE_MESSAGE_CHARS:
        body = body[: SUITE_MESSAGE_CHARS - 1] + "…"
    # Which of the repo's files was loading when it broke: the first stack frame that
    # is not in node_modules (the code frame above shows the line, not the file).
    frame = next(
        (m.group(1) for line in lines if (m := _REPO_FRAME.search(line))),
        None,
    )
    if frame:
        body = f"{body} | at {frame}"
    return f"Test suite failed to run: {body}" if body else "Test suite failed to run"


def _relative(path: str, workspace: str | None) -> str:
    cleaned = clean(path, workspace)
    return cleaned.removeprefix("./")


# --------------------------------------------------------------------------- tsc

_TSC_LINE = re.compile(
    r"^(?P<file>[^\s(][^(]*?)\((?P<line>\d+),(?P<col>\d+)\): error (?P<code>TS\d+): (?P<msg>.*)$"
)
_TSC_GLOBAL = re.compile(r"^error (?P<code>TS\d+): (?P<msg>.*)$")


def parse_tsc(output: str, workspace: str | None = None) -> list[Failure]:
    """One Failure per diagnostic; continuation lines are folded into the message."""
    failures: list[Failure] = []
    current: dict[str, Any] | None = None
    extra: list[str] = []

    def flush() -> None:
        if current is not None:
            message = " ".join([current.pop("msg"), *extra]).strip()
            failures.append(Failure(source="typecheck", message=message, **current))

    for raw in clean(output, workspace).splitlines():
        if m := _TSC_LINE.match(raw):
            flush()
            current = {
                "file": _relative(m["file"], workspace),
                "line": int(m["line"]),
                "column": int(m["col"]),
                "code": m["code"],
                "msg": m["msg"],
            }
            extra = []
        elif m := _TSC_GLOBAL.match(raw):
            flush()
            current = {"file": None, "code": m["code"], "msg": m["msg"]}
            extra = []
        elif current is not None and raw.startswith("  ") and raw.strip():
            # Keep the first continuation line: it usually names the mismatch.
            if not extra:
                extra.append(raw.strip())
        else:
            flush()
            current = None
            extra = []
    flush()
    return failures


# --------------------------------------------------------------------------- ng build

# `ng build` (and ngc) report TypeScript and Angular template errors as
# `src/app/a.component.html:12:5 - error NG8001: 'mat-chip-list' is not a known element:`,
# sometimes after an `Error: ` prefix; esbuild-based builds prefix `✘ [ERROR] `.
_NG_LINE = re.compile(
    r"^(?:Error: |✘ \[ERROR\] )?(?P<file>[^\s:][^:]*?):(?P<line>\d+):(?P<col>\d+) - error "
    r"(?P<code>(?:NG|TS)\d+): (?P<msg>.*)$"
)
# Sass: `SassError: Undefined mixin.` then, a few lines later, `  src/a.scss 12:3  root`.
_SASS_ERROR = re.compile(r"^(?:Error: |✘ \[ERROR\] )?(?:SassError: |Sass error: )?(?P<msg>.+)$")
_SASS_WHERE = re.compile(r"^\s+(?P<file>\S+\.s?[ac]ss) (?P<line>\d+):(?P<col>\d+)\s")


def parse_ng_build(output: str, workspace: str | None = None) -> list[Failure]:
    """One Failure per TypeScript, template or Sass error in an Angular build's output.
    A template error is charged to the template file, where the fix usually goes."""
    failures: list[Failure] = []
    lines = clean(output, workspace).splitlines()
    current: dict[str, Any] | None = None

    def flush() -> None:
        if current is not None:
            failures.append(Failure(source="typecheck", message=current.pop("msg"), **current))

    i = 0
    while i < len(lines):
        raw = lines[i]
        if m := _NG_LINE.match(raw):
            flush()
            current = {
                "file": _relative(m["file"], workspace),
                "line": int(m["line"]),
                "column": int(m["col"]),
                "code": m["code"],
                "msg": m["msg"].rstrip(":").strip(),
            }
        elif "SassError" in raw or raw.lstrip().startswith("Sass error"):
            flush()
            current = None
            message = _SASS_ERROR.match(raw.strip())
            for follow in lines[i + 1 : i + 12]:
                if w := _SASS_WHERE.match(follow):
                    failures.append(
                        Failure(
                            source="typecheck",
                            file=_relative(w["file"], workspace),
                            line=int(w["line"]),
                            column=int(w["col"]),
                            code="sass",
                            message=(message["msg"] if message else raw).strip(),
                        )
                    )
                    break
        elif not raw.strip():
            flush()
            current = None
        i += 1
    flush()
    seen: set[tuple[str | None, int | None, str | None, str]] = set()
    out = []
    for f in failures:  # Angular repeats some errors (once per build target)
        key = (f.file, f.line, f.code, f.message)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


# --------------------------------------------------------------------------- eslint


def parse_eslint_json(
    text: str, workspace: str | None = None, include_warnings: bool = False
) -> list[Failure]:
    data = json.loads(text)
    failures: list[Failure] = []
    for result in data:
        path = _relative(result["filePath"], workspace)
        for msg in result.get("messages", []):
            severity = msg.get("severity", 2)
            if severity < 2 and not include_warnings:
                continue
            failures.append(
                Failure(
                    source="lint",
                    file=path,
                    line=msg.get("line"),
                    column=msg.get("column"),
                    code=msg.get("ruleId"),
                    message=("" if severity >= 2 else "warning: ") + str(msg.get("message", "")),
                )
            )
    return failures


_STYLISH_LOC = re.compile(
    r"^\s+(?P<line>\d+):(?P<col>\d+)\s+(?P<sev>error|warning)\s+(?P<msg>.+?)(?:\s{2,}(?P<rule>[\w@/-]+))?\s*$"
)


def parse_eslint_stylish(
    output: str, workspace: str | None = None, include_warnings: bool = False
) -> list[Failure]:
    failures: list[Failure] = []
    current_file: str | None = None
    for raw in clean(output, workspace).splitlines():
        if m := _STYLISH_LOC.match(raw):
            if current_file is None or (m["sev"] == "warning" and not include_warnings):
                continue
            failures.append(
                Failure(
                    source="lint",
                    file=current_file,
                    line=int(m["line"]),
                    column=int(m["col"]),
                    code=m["rule"],
                    message=("warning: " if m["sev"] == "warning" else "") + m["msg"],
                )
            )
        elif raw and not raw.startswith(" ") and not raw.startswith((">", "✖")):
            looks_like_path = "/" in raw or raw.endswith((".ts", ".tsx", ".js", ".jsx"))
            current_file = _relative(raw.strip(), workspace) if looks_like_path else None
    return failures


# --------------------------------------------------------------------------- jest

TEST_DIRS = ("__tests__",)
TEST_SUFFIXES = (".test", ".spec")
SOURCE_EXTENSIONS = (".tsx", ".ts", ".jsx", ".js")


def subject_candidates(test_file: str) -> list[str]:
    """Where the file under test would be: ``a/__tests__/B.test.tsx`` -> ``a/B.tsx``."""
    path = PurePosixPath(test_file)
    stem = path.name
    for ext in SOURCE_EXTENSIONS:
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break
    for suffix in TEST_SUFFIXES:
        stem = stem.removesuffix(suffix)
    folder = path.parent
    folders = [folder.parent, folder] if folder.name in TEST_DIRS else [folder]
    return [(f / f"{stem}{ext}").as_posix() for f in folders for ext in SOURCE_EXTENSIONS]


def subject_file(test_file: str, exists: Callable[[str], bool | str | None]) -> str:
    """The file a test's failures are charged to; the test file itself if none is found.
    ``exists`` may return the file's real path (its exact case) instead of True."""
    for candidate in subject_candidates(test_file):
        found = exists(candidate)
        if found:
            return found if isinstance(found, str) else candidate
    return test_file


def jest_suite_files(text: str, workspace: str | None) -> list[str]:
    """The test files a Jest ``--json`` report ran."""
    data = json.loads(text)
    return sorted(_relative(s["name"], workspace) for s in data.get("testResults", []))


def parse_jest_json(
    text: str, workspace: str | None, exists: Callable[[str], bool | str | None]
) -> tuple[list[Failure], TestTotals]:
    data = json.loads(text)
    failures: list[Failure] = []
    for suite in data.get("testResults", []):
        test_file = _relative(suite["name"], workspace)
        subject = subject_file(test_file, exists)
        assertions = suite.get("assertionResults", [])
        for test in assertions:
            if test.get("status") != "failed":
                continue
            # Cleaned too: a test can name a path (kubeflow: "should be in sync with
            # <path>"), and the name is part of the failure's key across verifies.
            name = clean(
                TEST_NAME_JOINER.join([*test.get("ancestorTitles", []), test.get("title", "")]),
                workspace,
            )
            message = first_line(clean("\n".join(test.get("failureMessages", [])), workspace))
            location = test.get("location") or {}
            failures.append(
                Failure(
                    source="test",
                    file=subject,
                    message=message or "test failed",
                    test_file=test_file,
                    test_name=name,
                    line=location.get("line"),
                    column=location.get("column"),
                )
            )
        if suite.get("status") == "failed" and not any(
            t.get("status") == "failed" for t in assertions
        ):
            # The suite failed outside any test: a compile error, a crash on import.
            message = suite_message(clean(suite.get("message", ""), workspace))
            failures.append(
                Failure(
                    source="test",
                    file=subject,
                    message=message or "test suite failed to run",
                    test_file=test_file,
                    test_name=WHOLE_SUITE,
                )
            )
    snap = data.get("snapshot", {})
    totals = TestTotals(
        suites_total=data.get("numTotalTestSuites", 0),
        suites_failed=data.get("numFailedTestSuites", 0),
        tests_total=data.get("numTotalTests", 0),
        tests_passed=data.get("numPassedTests", 0),
        tests_failed=data.get("numFailedTests", 0),
        tests_skipped=data.get("numPendingTests", 0) + data.get("numTodoTests", 0),
        snapshots_total=snap.get("total", 0),
        snapshots_unmatched=snap.get("unmatched", 0),
        snapshots_updated=snap.get("updated", 0),
        snapshots_added=snap.get("added", 0),
        snapshots_obsolete=snap.get("unchecked", 0),
        snapshot_files_removed=snap.get("filesRemoved", 0),
    )
    return failures, totals
