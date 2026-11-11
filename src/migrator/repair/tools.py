"""The repair agent's tools: read_file, search_guide, apply_edit, run_verify, hand_off.

They are LangChain ``@tool``-style ``StructuredTool``s with strict schemas, defined once
per run in a fixed order (the tool list is part of the cached prefix). There is no
shell. The guardrails live here, inside the tools, not only in the prompt.

A ``RepairSession`` is one failing file's repair: the graph's tools node rebuilds it
from the run state, points the tools at it, runs the model's tool calls in order and
writes the session back. Calls run one at a time: ``apply_edit`` and ``run_verify``
change the workspace and the session, so running them concurrently (as LangGraph's
``ToolNode`` does with a message's calls) could interleave edits.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, create_model

from migrator.execs import RunTimeoutError
from migrator.repair.context import PatchSize, is_code, numbered
from migrator.repair.guardrails import (
    Blocked,
    added_escape_hatches,
    check_target,
    over_size_limit,
    workspace_path,
)
from migrator.repair.prompt import PromptTemplates, attempt_result, describe_failure
from migrator.repair.records import AttemptRecord, FileRepair
from migrator.repair.retriever import GuideRetriever, render_section
from migrator.scan.parser import parse_tree
from migrator.verify import Failure
from migrator.verify.checker import Checker

TOOL_ORDER = ("read_file", "search_guide", "apply_edit", "run_verify", "hand_off")
MAX_READ_LINES = 2000
Ended = Literal["passed", "handed_off", "cost_cap", "error"]


def first_parse_error(path: str, text: str) -> int | None:
    """The 1-based line of the first syntax error tree-sitter finds, or None."""
    tree = parse_tree(text.encode("utf-8"), path)
    if not tree.root_node.has_error:
        return None
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_missing:
            return int(node.start_point[0]) + 1
        if node.has_error:
            stack.extend(reversed(node.children))
    return int(tree.root_node.start_point[0]) + 1


def new_parse_error(path: str, before: str, after: str) -> int | None:
    """The line of a syntax error the edit introduced (None if the file parsed before
    the edit too badly to tell, or parses after it). Code files only."""
    if not is_code(path):
        return None
    if first_parse_error(path, before) is not None:
        return None
    return first_parse_error(path, after)


def failure_key(f: Failure) -> str:
    return "|".join(str(x) for x in f.key())


class SessionState(BaseModel):
    """One failing file's repair, as the graph state keeps it (JSON-friendly)."""

    path: str
    attempt: int = 1
    max_attempts: int = 3
    tool_calls: int = 0  # in this attempt
    ended: Ended | None = None
    allowed_imports: list[str] = []
    baseline_keys: list[str] = []  # failures known when the file's repair started
    originals: dict[str, str] = {}  # touched file -> its text when this repair started
    record: FileRepair
    # A shared-cause task (M6): the callers' (file, code) failures this task also owns.
    target_keys: list[tuple[str, str]] = []


class RunVerifyOutcome(BaseModel):
    result: Literal["passed", "failed", "handed_off"]
    left: list[Failure]
    elsewhere: list[Failure]


def update_known(
    known: list[Failure], result_failures: list[Failure], ran: list[str] | None
) -> list[Failure]:
    """Known failures after a narrow verify: type-check and lint are whole-project, so
    they are replaced; test failures are replaced for the test files that ran."""
    keep = [f for f in known if f.source == "test"]
    keep = [] if ran is None else [f for f in keep if f.test_file not in set(ran)]
    return [*keep, *result_failures]


class RepairSession:
    """Everything the tools need for one failing file (rebuilt each tools-node step)."""

    def __init__(
        self,
        state: SessionState,
        *,
        workspace: Path,
        after_rules: Mapping[str, str],
        test_files: Mapping[str, str],
        known_failures: list[Failure],
        checker: Checker,
        templates: PromptTemplates,
        retriever: GuideRetriever,
        link_base: str | None,
    ):
        self.state = state
        self.workspace = workspace
        self.after_rules = after_rules
        self.test_files = test_files
        self.known_failures = known_failures
        self.checker = checker
        self.templates = templates
        self.retriever = retriever
        self.link_base = link_base

    # ------------------------------------------------------------------ helpers

    @property
    def record(self) -> FileRepair:
        return self.state.record

    @property
    def current_attempt(self) -> AttemptRecord:
        return self.record.attempts[-1]

    def reject(self, blocked: Blocked) -> str:
        counts = self.record.edits_rejected
        counts[blocked.guardrail] = counts.get(blocked.guardrail, 0) + 1
        return f"Rejected: {blocked.reason}."

    def hand_off(self, reason: str) -> None:
        self.state.ended = "handed_off"
        self.record.outcome = "Handed off"
        self.record.reason = reason
        if self.current_attempt.result is None:
            self.current_attempt.result = "handed_off"

    def patches(self) -> dict[str, PatchSize]:
        out: dict[str, PatchSize] = {}
        for rel in self.record.touched:
            current = (self.workspace / rel).read_text("utf-8")
            out[rel] = PatchSize(self.after_rules.get(rel, ""), current)
        return out

    def workspace_files(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for rel in {*self.after_rules, *self.record.touched}:
            path = self.workspace / rel
            if path.is_file():
                out[rel] = path.read_text("utf-8", errors="replace")
        return out

    # ------------------------------------------------------------------ tools

    def read_file(self, path: str) -> str:
        where = workspace_path(self.workspace, path)
        if isinstance(where, Blocked):
            return f"Error: {where.reason}."
        rel, full = where
        if not full.is_file():
            return f"Error: no file {rel} in the workspace."
        text = full.read_text("utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > MAX_READ_LINES:
            return f"{rel} (first {MAX_READ_LINES} of {len(lines)} lines)\n" + numbered(
                text, 1, MAX_READ_LINES
            )
        return f"{rel} ({len(lines)} lines)\n" + numbered(text)

    def search_guide(self, query: str) -> str:
        docs = self.retriever.rank(query, k=3)
        if not docs:
            return "No section matched. Try a component, prop or API name."
        return "\n\n---\n\n".join(render_section(d, self.link_base) for d in docs)

    def apply_edit(self, path: str, old_text: str, new_text: str) -> str:
        where = workspace_path(self.workspace, path)
        if isinstance(where, Blocked):
            return self.reject(where)
        rel, full = where
        blocked = check_target(rel, self.state.path, self.state.allowed_imports, self.test_files)
        if blocked is not None:
            return self.reject(blocked)
        if not full.is_file():
            return f"Error: no file {rel} in the workspace."
        if not old_text:
            return "Error: old_text is empty; give the exact text to replace."
        if old_text == new_text:
            return "Error: old_text and new_text are the same."
        current = full.read_text("utf-8")
        count = current.count(old_text)
        if count == 0:
            return (
                f"Error: old_text was not found in {rel}. It must match the file exactly, "
                "including indentation; `read_file` shows the current text."
            )
        if count > 1:
            return f"Error: old_text appears {count} times in {rel}; include more context."
        updated = current.replace(old_text, new_text, 1)
        hatches = added_escape_hatches(rel, current, updated)
        if hatches:
            self.record.escape_hatches_rejected[rel] = (
                self.record.escape_hatches_rejected.get(rel, 0) + 1
            )
            self.record.edits_rejected["escape-hatch"] = (
                self.record.edits_rejected.get("escape-hatch", 0) + 1
            )
            return (
                f"Rejected: the edit adds {', '.join(hatches)} to {rel}, which silences a "
                "check instead of satisfying it. Fix the cause, or hand off."
            )
        size = PatchSize(self.after_rules.get(rel, current), updated)
        if over_size_limit(size):
            self.record.edits_rejected["size-limit"] = (
                self.record.edits_rejected.get("size-limit", 0) + 1
            )
            self.hand_off(
                f"patch over the size limit: {rel} would change {size.changed} lines "
                f"({round(size.share * 100)}% of the file)"
            )
            return (
                f"Rejected: with this edit the patch to {rel} would be {size.describe()}, past "
                "the size limit. The file goes to a human; the attempt is over."
            )
        if rel not in self.state.originals:
            self.state.originals[rel] = current
        if rel not in self.record.touched:
            self.record.touched.append(rel)
        full.write_text(updated, "utf-8")
        self.record.edits_applied += 1
        self.record.patch_lines[rel] = size.changed
        result = f"Applied. Patch to {rel} so far: {size.describe()}."
        if self.templates.options.get("apply_edit_parse_warning"):
            line = new_parse_error(rel, current, updated)
            if line is not None:
                self.record.parse_warnings += 1
                result += (
                    f" Warning: {rel} no longer parses (syntax error at line {line}). The "
                    "edit is kept; fix the syntax before `run_verify`."
                )
        return result

    def narrow_verify(self, label: str) -> tuple[list[Failure], list[Failure], list[str] | None]:
        """(failures in the failing file, new failures elsewhere, test files that ran)."""
        targets = set(self.state.target_keys)
        related = sorted({self.state.path, *self.record.touched, *(f for f, _ in targets)})
        result = self.checker.narrow(label, related)
        ran = result.test_files_run
        self.known_failures[:] = update_known(self.known_failures, result.failures, ran)
        baseline = set(self.state.baseline_keys)
        left = [
            f for f in result.failures if f.file == self.state.path or (f.file, f.code) in targets
        ]
        elsewhere = [
            f
            for f in result.failures
            if f.file != self.state.path
            and (f.file, f.code) not in targets
            and failure_key(f) not in baseline
        ]
        return left, elsewhere, ran

    def run_verify(self, note: str) -> str:
        attempt = self.current_attempt
        attempt.note = note.strip().splitlines()[0] if note.strip() else ""
        slug = re.sub(r"[^A-Za-z0-9]+", "-", self.state.path).strip("-")
        left, elsewhere, _ran = self.narrow_verify(f"repair-{slug}-a{attempt.number}")
        attempt.failures_left = len(left)
        attempt.new_failures_elsewhere = [
            f"{f.file or '(none)'}: {describe_failure(f, self.state.path)}" for f in elsewhere
        ]
        if not left and not elsewhere:
            attempt.result = "passed"
            self.state.ended = "passed"
            self.record.outcome = "Migrated by agent"
            patch = "; ".join(f"`{p}` {s.describe()}" for p, s in self.patches().items())
            return (
                f"Attempt {attempt.number} passed: no failures left in {self.state.path} and "
                f"nothing new elsewhere. Patch: {patch or 'no edits'}. This file is done."
            )
        attempt.result = "failed"
        text = attempt_result(
            self.templates,
            attempt=attempt.number,
            max_attempts=self.state.max_attempts,
            note=attempt.note,
            left=left,
            elsewhere=elsewhere,
            path=self.state.path,
            files=self.workspace_files(),
            patches=self.patches(),
        )
        if attempt.number >= self.state.max_attempts:
            self.hand_off(f"{self.state.max_attempts} attempts used; {len(left)} failures left")
            attempt.result = "failed"
        else:
            self.state.attempt += 1
            self.state.tool_calls = 0
        return text

    def hand_off_tool(self, reason: str, suggested_test_change: str = "") -> str:
        self.current_attempt.note = reason.strip().splitlines()[0] if reason.strip() else ""
        self.hand_off(f"the repair agent handed off: {self.current_attempt.note}")
        if suggested_test_change.strip():
            # Shown to the human in the hand-off checklist; never applied (M6).
            self.record.suggested_test_change = suggested_test_change.strip()
        return "Handed off. A human will see this file and your reason; its repair ends here."


# --------------------------------------------------------------------------- tool objects


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _schema(name: str, fields: dict[str, str]) -> type[BaseModel]:
    defs: dict[str, Any] = {key: (str, Field(description=text)) for key, text in fields.items()}
    model: type[BaseModel] = create_model(f"{name}_args", __base__=_Strict, **defs)
    return model


class RepairTools:
    """The five tools, built once per run; ``session`` points them at the current file."""

    def __init__(self, text: Mapping[str, Mapping[str, str]]):
        self.session: RepairSession | None = None
        self.tools: list[BaseTool] = []
        handlers: dict[str, Callable[..., str]] = {
            "read_file": lambda path: self._s().read_file(path),
            "search_guide": lambda query: self._s().search_guide(query),
            "apply_edit": lambda path, old_text, new_text: self._s().apply_edit(
                path, old_text, new_text
            ),
            "run_verify": lambda note: self._s().run_verify(note),
            "hand_off": lambda reason, suggested_test_change="": self._s().hand_off_tool(
                reason, suggested_test_change
            ),
        }
        for name in TOOL_ORDER:
            entries = dict(text[name])
            description = entries.pop("description")
            self.tools.append(
                StructuredTool.from_function(
                    func=handlers[name],
                    name=name,
                    description=description,
                    args_schema=_schema(name, entries),
                )
            )
        self.by_name = {t.name: t for t in self.tools}

    def _s(self) -> RepairSession:
        if self.session is None:
            raise RuntimeError("no repair session: the tools run only inside the graph")
        return self.session

    def invoke(self, call: ToolCall) -> ToolMessage:
        tool = self.by_name.get(call["name"])
        if tool is None:
            return ToolMessage(
                content=f"Error: there is no tool {call['name']!r}.",
                tool_call_id=call["id"] or "",
                name=call["name"],
                status="error",
            )
        try:
            result = tool.invoke(call)
        except RunTimeoutError:
            raise  # the run's wall-clock ceiling ends the run, not just the tool call
        except Exception as exc:  # a bad argument must not kill the run
            return ToolMessage(
                content=f"Error: {type(exc).__name__}: {exc}",
                tool_call_id=call["id"] or "",
                name=call["name"],
                status="error",
            )
        assert isinstance(result, ToolMessage)
        return result
