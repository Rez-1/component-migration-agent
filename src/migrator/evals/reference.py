"""Scoring a real-repo run against the repo's merged migration PR (M6).

**Scoring items** are the source files the reference PR changed that import the old or
the new library, leaving out lockfiles and other non-code files, test files (the repair
agent may not edit them; they are listed as expected hand-offs) and changes that are
formatting only. Each item gets one verdict:

- **matches**: the run made the same change or an equivalent one;
- **other valid fix**: a different change that works;
- **wrong**: it type-checks and passes the tests but behaves differently, or leaves out
  part of the migration the reference did;
- **untouched**: the reference changed the file for the migration and the run didn't;
- **out of scope**: every change the reference made to the file goes beyond the
  migration (a ``makeStyles`` -> ``sx`` rewrite, a refactor): ignored, not a miss.

Deterministic first: a run whose file equals the reference after normalising whitespace,
quotes and trailing commas *matches* without a model. Everything else goes to an LLM
judge (Claude Opus 5.5 at low effort), which also says which reference changes are out
of scope. The judge sees the two diffs only, never which configuration made the run.
Its answers are cached on disk by content, so a file that came out the same in several
runs (every Baseline run, and every file the agent didn't touch) is judged once.

A **real-repo Silent miss** is a *wrong* or *untouched* item whose file has no failure
at the final verify and was not handed off: verify can't show it.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from migrator.checks import find_test_files, read_test_rules
from migrator.config import CaseConfig
from migrator.cost import CostGuard, Ledger, LedgerRow, Usage, cost_usd, now_utc
from migrator.evals.upstream import materialize, reference_changes, reference_file
from migrator.report import Scorecard

JUDGE_MODEL = "claude-opus-5-5"
JUDGE_EFFORT = "low"
JUDGE_MAX_TOKENS = 4000
JUDGE_PROMPT_VERSION = "j2"  # j1 (10 Nov): no per-hunk kinds; 41% agreement with the owner
CODE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
_LIBRARY_IMPORT = re.compile(
    r"""from\s+['"]@(material-ui|mui)/|require\(\s*['"]@(material-ui|mui)/"""
)

Verdict = Literal["matches", "other valid fix", "wrong", "untouched", "out of scope"]
VERDICTS: tuple[Verdict, ...] = ("matches", "other valid fix", "wrong", "untouched", "out of scope")


class ItemScore(BaseModel):
    path: str
    verdict: Verdict
    by: Literal["deterministic", "judge", "override"]
    judge_verdict: Verdict | None = None  # what the judge said, when an override replaced it
    reason: str
    out_of_scope_changes: list[str] = []
    reference_hunks: list[dict[str, str]] = []  # the judge's kind for each reference hunk
    outcome: str | None  # the run's Outcome for the file, when it is an affected file
    final_failures: int
    handed_off: bool
    silent_miss: bool
    covered: bool | None  # by a test at the Pre-check; None without coverage
    judge_key: str | None = None


class ReferenceScore(BaseModel):
    case: str
    run_id: str
    configuration: str
    reference_pr: str
    items: list[ItemScore]
    counts: dict[str, int]
    silent_misses: int
    # The judge's own count, before any recorded override (equal without overrides).
    judge_silent_misses: int | None = None
    # Not scoring items, listed so nothing the reference did is silently dropped.
    test_files_changed: list[str]  # expected hand-offs: only a human may edit tests
    formatting_only: list[str]
    other_files_changed: list[str]  # non-code files and code without the library
    judge_calls: int
    judge_cost_usd: float


# --------------------------------------------------------------------------- items


def normalise(text: str) -> str:
    """Code with formatting differences removed: whitespace, quote style, trailing
    commas and statement semicolons."""
    t = text.replace('"', "'")
    t = re.sub(r",(\s*[)\]}>])", r"\1", t)
    t = re.sub(r";(\s*\n)", r"\1", t)
    return re.sub(r"\s+", "", t)


def uses_library(text: str | None) -> bool:
    return bool(text) and bool(_LIBRARY_IMPORT.search(text or ""))


class Items(BaseModel):
    items: list[str]
    test_files: list[str]
    formatting_only: list[str]
    other: list[str]


def select_items(
    changes: dict[str, str],
    base: dict[str, str],
    reference: Callable[[str], str | None],
    test_files: set[str],
) -> Items:
    items, tests, formatting, other = [], [], [], []
    for path in sorted(changes):
        if path in test_files or "__snapshots__" in path:
            tests.append(path)
            continue
        old, new = base.get(path), reference(path)
        if not path.endswith(CODE_EXTENSIONS) or not (uses_library(old) or uses_library(new)):
            other.append(path)
        elif old is not None and new is not None and normalise(old) == normalise(new):
            formatting.append(path)
        else:
            items.append(path)
    return Items(items=items, test_files=tests, formatting_only=formatting, other=other)


def diff(old: str | None, new: str | None, path: str, context: int = 4) -> str:
    return "".join(
        difflib.unified_diff(
            (old or "").splitlines(keepends=True),
            (new or "").splitlines(keepends=True),
            f"a/{path}",
            f"b/{path}",
            n=context,
        )
    )


# --------------------------------------------------------------------------- the judge

JUDGE_SYSTEM = """\
You grade one file of an automated Material UI v4 -> MUI v5 migration against the \
migration a project's own developers made and merged (the reference).

You get two unified diffs of the same file, both against the same original v4 code:
- REFERENCE: what the developers changed, its hunks labelled [R1], [R2], ...;
- CANDIDATE: what the automated run changed (empty if it changed nothing).

Step 1. Classify every reference hunk as exactly one kind:
- "v5-required": what v5 itself requires: package and import paths, renamed or removed \
components, props and theme keys, changed types, class names and CSS selectors that \
target MUI's internal classes;
- "v5-styling": styling the developers added to make up for a v5 change, so the \
screen looks as it did in v4: a different default size, colour, padding, margin, \
border or class (for example `size="small"` where v5's `margin="dense"` no longer \
shrinks an input, or a colour v5's new default would change). This is part of the \
migration: styling is a big part of migrating a component library;
- "unrelated": not caused by v5: rewriting JSS styling (makeStyles/withStyles) to \
styled()/sx, refactors, renames, new features, unrelated fixes, formatting, test-only \
changes. Keeping makeStyles and withStyles on @mui/styles is correct, not a miss.
A hunk that mixes kinds takes the kind of its most important change; say so in `what`.

Step 2. Judge the candidate against the v5-required and v5-styling hunks only:
- "matches": it makes the same changes, or equivalent ones (for example a different \
but equivalent import style);
- "other valid fix": it differs from the reference but is still a correct v5 \
migration that looks and behaves the same for users, styling included;
- "wrong": it behaves or looks different from the reference, or leaves out a \
v5-required or v5-styling change, or adds a change that breaks the file;
- "untouched": the candidate diff is empty but the reference has v5-required or \
v5-styling hunks;
- "out of scope": every reference hunk is unrelated.

Answer with JSON only: {"reference_hunks": [{"id": "R1", "kind": ..., "what": a short \
description}], "verdict": ..., "reason": one or two sentences naming the deciding \
hunk(s)}.\
"""

HUNK_KINDS = ("v5-required", "v5-styling", "unrelated")
JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reference_hunks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": list(HUNK_KINDS)},
                    "what": {"type": "string"},
                },
                "required": ["id", "kind", "what"],
                "additionalProperties": False,
            },
        },
        "verdict": {
            "type": "string",
            "enum": ["matches", "other valid fix", "wrong", "untouched", "out of scope"],
        },
        "reason": {"type": "string"},
    },
    "required": ["reference_hunks", "verdict", "reason"],
    "additionalProperties": False,
}


class ReferenceHunk(BaseModel):
    id: str
    kind: Literal["v5-required", "v5-styling", "unrelated"]
    what: str


class Judgement(BaseModel):
    verdict: Verdict
    reason: str
    reference_hunks: list[ReferenceHunk] = []
    out_of_scope_changes: list[str] = []  # j1 judgements; j2 derives it from the hunks
    model: str = JUDGE_MODEL
    cost_usd: float = 0.0

    def set_aside(self) -> list[str]:
        if self.reference_hunks:
            return [f"{h.id}: {h.what}" for h in self.reference_hunks if h.kind == "unrelated"]
        return self.out_of_scope_changes


def label_hunks(diff_text: str) -> str:
    """The diff with each hunk header prefixed [R1], [R2], ... for the judge to cite."""
    out, n = [], 0
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("@@"):
            n += 1
            line = f"[R{n}] {line}"
        out.append(line)
    return "".join(out)


def judge_prompt(path: str, reference_diff: str, candidate_diff: str) -> str:
    return (
        f"File: {path}\n\nREFERENCE diff:\n```diff\n{label_hunks(reference_diff) or '(empty)'}"
        f"```\n\nCANDIDATE diff:\n```diff\n{candidate_diff or '(empty)'}```\n"
    )


def judge_key(path: str, base: str | None, ref: str | None, final: str | None) -> str:
    h = hashlib.sha256()
    for part in (JUDGE_PROMPT_VERSION, JUDGE_MODEL, JUDGE_EFFORT, path, base, ref, final):
        h.update((part if part is not None else "\0none").encode() + b"\0")
    return h.hexdigest()[:20]


JudgeFn = Callable[[str, str], Judgement]  # (prompt, ledger file label) -> Judgement


class ClaudeJudge:
    """One structured-output Messages call per judgement, priced and capped through the
    ledger like every repair call (run id ``judge:<case>``, no attempt number)."""

    def __init__(self, case: str, guard: CostGuard, ledger: Ledger):
        import anthropic

        self.client = anthropic.Anthropic(max_retries=2)
        self.case, self.guard, self.ledger = case, guard, ledger
        self.spent = 0.0
        self.calls = 0

    def __call__(self, prompt: str, label: str) -> Judgement:
        from migrator.cost import estimate_tokens

        self.guard.check(
            JUDGE_MODEL, estimate_tokens(JUDGE_SYSTEM + prompt), JUDGE_MAX_TOKENS, self.spent
        )
        output_config: Any = {
            "effort": JUDGE_EFFORT,
            "format": {"type": "json_schema", "schema": JUDGE_SCHEMA},
        }
        response = self.client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=JUDGE_MAX_TOKENS,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config=output_config,
        )
        u = response.usage
        usage = Usage(
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_input_tokens=u.cache_read_input_tokens or 0,
            cache_creation_input_tokens=u.cache_creation_input_tokens or 0,
        )
        cost = cost_usd(JUDGE_MODEL, usage)
        self.spent += cost
        self.calls += 1
        self.ledger.append(
            LedgerRow(
                at=now_utc(),
                run_id=f"judge:{self.case}",
                case=self.case,
                file=label,
                model=str(response.model),
                requested_model=JUDGE_MODEL,
                usage=usage,
                cost_usd=cost,
            )
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"the judge refused {label}")
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        return Judgement(**data, cost_usd=cost)


class JudgeCache:
    def __init__(self, folder: Path):
        self.folder = folder

    def get(self, key: str) -> Judgement | None:
        path = self.folder / f"{key}.json"
        if not path.is_file():
            return None
        return Judgement.model_validate_json(json.loads(path.read_text("utf-8"))["judgement"])

    def put(self, key: str, judgement: Judgement, prompt: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / f"{key}.json").write_text(
            json.dumps({"judgement": judgement.model_dump_json(), "prompt": prompt}, indent=2)
            + "\n",
            "utf-8",
        )


# --------------------------------------------------------------------------- one run


def _load(path: Path) -> dict[str, str]:
    return json.loads(path.read_text("utf-8")) if path.is_file() else {}


class RunInputs(BaseModel):
    """What scoring needs from one run folder."""

    card: Scorecard
    base: dict[str, str]
    final: dict[str, str]
    covered: dict[str, bool] | None


def read_run(run_dir: Path) -> RunInputs:
    card = Scorecard.model_validate_json((run_dir / "scorecard.json").read_text("utf-8"))
    base = _load(run_dir / "state" / "untouched.json")
    final = _load(run_dir / "state" / "final.json")
    if not base or not final:
        raise ValueError(f"{run_dir} has no state/untouched.json or state/final.json")
    covered = None
    if card.coverage is not None:
        covered = {p: True for p in card.coverage.covered} | {
            p: False for p in card.coverage.not_covered
        }
    return RunInputs(card=card, base=base, final=final, covered=covered)


def pending_judgements(case: CaseConfig, runs: list[RunInputs], cache: JudgeCache) -> int:
    """How many judge calls scoring these runs would make (not cached, not decided)."""
    keys: set[str] = set()
    changes = reference_changes(case)
    for r in runs:
        tests = set(
            find_test_files(r.base, set(r.base) | set(changes), read_test_rules(materialize(case)))
        )
        sel = select_items(changes, r.base, lambda p: reference_file(case, p), tests)
        for path in sel.items:
            ref = reference_file(case, path)
            final = r.final.get(path)
            if final is not None and ref is not None and normalise(final) == normalise(ref):
                continue
            key = judge_key(path, r.base.get(path), ref, final)
            if cache.get(key) is None:
                keys.add(key)
    return len(keys)


class Override(BaseModel):
    """A recorded scoring decision by a human (M6): where the judge is not trusted, the
    owner sets the verdict for a file whose run output contains a given change. Kept in
    the case's ``overrides.toml``, with who decided, when and why; the judge's own verdict
    stays in the score beside it."""

    path: str
    when_candidate_contains: str
    verdict: Verdict
    decided_by: str
    date: str
    reason: str

    def applies(self, path: str, final: str | None) -> bool:
        return path == self.path and final is not None and self.when_candidate_contains in final


def load_overrides(case: CaseConfig) -> list[Override]:
    path = case.folder / "overrides.toml"
    if not path.is_file():
        return []
    import tomllib

    with path.open("rb") as fh:
        return [Override.model_validate(o) for o in tomllib.load(fh).get("override", [])]


def score_run(
    case: CaseConfig, run: RunInputs, judge: JudgeFn | None, cache: JudgeCache
) -> ReferenceScore:
    assert case.upstream is not None
    card = run.card
    changes = reference_changes(case)
    tests = set(
        find_test_files(run.base, set(run.base) | set(changes), read_test_rules(materialize(case)))
    )
    sel = select_items(changes, run.base, lambda p: reference_file(case, p), tests)
    overrides = load_overrides(case)
    outcomes = {f.path: f.outcome for f in card.files}
    failures = Counter(f.file for f in (card.verify.failures if card.verify else []) if f.file)
    handed = set(card.repair.review_list) if card.repair else set()
    calls, spent = 0, 0.0
    items: list[ItemScore] = []
    for path in sel.items:
        base, ref, final = run.base.get(path), reference_file(case, path), run.final.get(path)
        key: str | None = None
        oos: list[str] = []
        hunks: list[dict[str, str]] = []
        if final is not None and ref is not None and normalise(final) == normalise(ref):
            verdict: Verdict = "matches"
            by: Literal["deterministic", "judge", "override"] = "deterministic"
            reason = "the same as the reference after normalising formatting"
        else:
            key = judge_key(path, base, ref, final)
            found = cache.get(key)
            if found is None:
                if judge is None:
                    raise RuntimeError(f"{path} needs a judge call and judging is off")
                prompt = judge_prompt(path, diff(base, ref, path), diff(base, final, path))
                found = judge(prompt, path)
                cache.put(key, found, prompt)
                calls += 1
                spent += found.cost_usd
            verdict, by, reason, oos = found.verdict, "judge", found.reason, found.set_aside()
            hunks = [h.model_dump() for h in found.reference_hunks]
            if verdict == "untouched" and final != base:
                verdict = "wrong"  # the run did change it: an empty-diff verdict is a slip
        judge_verdict: Verdict | None = None
        rule = next((o for o in overrides if o.applies(path, final)), None)
        if rule is not None and by == "judge" and verdict != rule.verdict:
            judge_verdict, verdict, by = verdict, rule.verdict, "override"
            reason = f"override ({rule.decided_by}, {rule.date}): {rule.reason}"
        fails = failures.get(path, 0)
        items.append(
            ItemScore(
                path=path,
                verdict=verdict,
                by=by,
                reason=reason,
                out_of_scope_changes=oos,
                reference_hunks=hunks,
                outcome=outcomes.get(path),
                final_failures=fails,
                handed_off=path in handed,
                silent_miss=verdict in ("wrong", "untouched") and fails == 0 and path not in handed,
                covered=run.covered.get(path) if run.covered is not None else None,
                judge_key=key,
                judge_verdict=judge_verdict,
            )
        )
    counts = Counter(i.verdict for i in items)
    return ReferenceScore(
        case=case.id,
        run_id=card.meta.run_id,
        configuration=card.configuration,
        reference_pr=case.upstream.reference_pr,
        items=items,
        counts={v: counts[v] for v in VERDICTS},
        silent_misses=sum(i.silent_miss for i in items),
        judge_silent_misses=sum(
            (i.judge_verdict or i.verdict) in ("wrong", "untouched")
            and i.final_failures == 0
            and not i.handed_off
            for i in items
        ),
        test_files_changed=sel.test_files,
        formatting_only=sel.formatting_only,
        other_files_changed=sel.other,
        judge_calls=calls,
        judge_cost_usd=round(spent, 6),
    )


def render_reference_score(s: ReferenceScore) -> str:
    scored = [i for i in s.items if i.verdict != "out of scope"]
    lines = [
        f"# Reference score: {s.case}, run {s.run_id} ({s.configuration})",
        "",
        f"Scored against [{s.reference_pr}]({s.reference_pr}): {len(scored)} items "
        f"({len(s.items) - len(scored)} more out of scope).",
        "",
        "| Verdict | Items |",
        "|---|---|",
        *[f"| {v} | {s.counts.get(v, 0)} |" for v in VERDICTS],
        "",
        f"**Silent misses** (wrong or untouched, and verify passes for the file): "
        f"{s.silent_misses}"
        + (
            f" ({s.judge_silent_misses} by the judge alone, before the recorded overrides)"
            if s.judge_silent_misses is not None and s.judge_silent_misses != s.silent_misses
            else ""
        ),
        "",
        "| File | Verdict | By | Outcome | Final failures | Covered | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for i in s.items:
        cov = "" if i.covered is None else ("yes" if i.covered else "no")
        mark = " **(silent miss)**" if i.silent_miss else ""
        lines.append(
            f"| `{i.path}` | {i.verdict}{mark} | {i.by} | {i.outcome or ''} | "
            f"{i.final_failures} | {cov} | {i.reason.replace('|', '/')} |"
        )
    overridden = [i for i in s.items if i.by == "override"]
    if overridden:
        lines += ["", "## Recorded overrides (the judge's verdict replaced by a human's)", ""]
        lines += [
            f"- `{i.path}`: judge said {i.judge_verdict}, scored {i.verdict}" for i in overridden
        ]
    oos = [(i.path, c) for i in s.items for c in i.out_of_scope_changes]
    if oos:
        lines += ["", "## Reference changes set aside as out of scope", ""]
        lines += [f"- `{p}`: {c}" for p, c in oos]
    for title, paths in (
        ("Test files the reference changed (expected hand-offs)", s.test_files_changed),
        ("Formatting-only changes (not scored)", s.formatting_only),
        ("Other files the reference changed (not scored)", s.other_files_changed),
    ):
        if paths:
            lines += ["", f"## {title}", "", *[f"- `{p}`" for p in paths]]
    lines += ["", f"Judge: {s.judge_calls} new calls, ${s.judge_cost_usd:.2f}."]
    return "\n".join(lines) + "\n"
