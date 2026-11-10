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

FailureSource = Literal["typecheck", "lint", "test"]
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


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


def subject_file(test_file: str, exists: Callable[[str], bool]) -> str:
    """The file a test's failures are charged to; the test file itself if none is found."""
    return next((c for c in subject_candidates(test_file) if exists(c)), test_file)


def jest_suite_files(text: str, workspace: str | None) -> list[str]:
    """The test files a Jest ``--json`` report ran."""
    data = json.loads(text)
    return sorted(_relative(s["name"], workspace) for s in data.get("testResults", []))


def parse_jest_json(
    text: str, workspace: str | None, exists: Callable[[str], bool]
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
            name = " › ".join([*test.get("ancestorTitles", []), test.get("title", "")])
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
                    test_name="(suite)",
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
