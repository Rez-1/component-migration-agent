"""The Report stage's rendering: the scorecard as markdown, and the pull-request body,
both rendered from the Scorecard JSON alone (ticket #10). Scoring itself, and the
Scorecard schema, live in ``migrator.scoring``.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from migrator.checks import Finding
from migrator.cost import RunCost
from migrator.scoring import Scorecard, TrapCounts
from migrator.visual.compare import VisualReport


def write_json(model: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", "utf-8"
    )


def _visual_lines(visual: VisualReport, *, task: bool) -> list[str]:
    """The visual check, for the scorecard and the PR body: never a verdict."""
    box = "- [ ] " if task else "- "
    if visual.skipped:
        return [f"- Not compared: {visual.skipped}"]
    lines = [
        f"{box}`{e.name}` breaks in the {e.capture} capture: {_md_cell('; '.join(e.errors), 200)}"
        for e in visual.new_page_errors
    ]
    for c in visual.comparisons:
        flagged = c.flagged
        lines.append(
            f"- {c.b} against {c.a}: {len(flagged)} of {len(c.pages)} pages differ by "
            f"{c.threshold:.1%} of their pixels or more"
            + (f"; no screenshot for {', '.join(m.name for m in c.missing)}" if c.missing else "")
        )
        lines += [
            f"  {box}`{p.name}`: {p.share:.2%} of pixels differ"
            + (f" (`{p.diff_png}`)" if p.diff_png else "")
            + (f"; files: {', '.join(f'`{f}`' for f in p.files)}" if p.files else "")
            for p in flagged
        ]
    return lines


# --------------------------------------------------------------------------- markdown


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _pct(share: float) -> str:
    return f"{round(share * 100)}%"


def _duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} min {secs} s" if minutes else f"{secs} s"


def traps_line(t: TrapCounts | None) -> str:
    if t is None:
        return "—"
    return (
        f"{t.expected} expected · {t.other_layer} other layer · {t.missed} missed"
        f"{f' ({t.silent} silent)' if t.silent else ''} · {t.not_scored} not scored"
    )


def usd(value: float | None) -> str:
    """Dollars for a report: "—" when there is no value (never a silent $0)."""
    if value is None:
        return "—"
    return "$0" if value == 0 else f"${value:.2f}"


def _cost_head(cost: RunCost) -> str:
    if cost.model_calls == 0:
        return f"$0 (no LLM) of {usd(cost.run_cap_usd)} cap"
    return f"**{usd(cost.total_usd)}** of {usd(cost.run_cap_usd)} cap"


def _models_part(cost: RunCost) -> str:
    """The models with their share when there is more than one (a cascade, a reviewer)."""
    if len(cost.by_model) < 2:
        return ", ".join(cost.models)
    return "; ".join(
        f"{m.model} {usd(m.cost_usd)} ({m.calls} {'call' if m.calls == 1 else 'calls'})"
        for m in cost.by_model
    )


def _cost_line(cost: RunCost) -> str:
    caps = f"Run cap {usd(cost.run_cap_usd)}; month cap {usd(cost.month_cap_usd)}"
    month = (
        f", this month {usd(cost.month_spent_usd)} of {usd(cost.month_cap_usd)}"
        if cost.month_spent_usd is not None
        else ""
    )
    warnings = "".join(f" **Warning:** {w}." for w in cost.warnings)
    stopped = " Repair stopped at the cost cap." if cost.stopped_by_cap else ""
    if cost.model_calls == 0:
        return f"$0: this run made no model calls. {caps}{month}.{stopped}"
    share = (
        f" Cache reads covered {round(cost.cache_read_share * 100)}% of input tokens."
        if cost.cache_read_share is not None
        else ""
    )
    return (
        f"{usd(cost.total_usd)} = {usd(cost.output_usd)} output + {usd(cost.input_usd)} input"
        f" + {usd(cost.cache_read_usd + cost.cache_write_usd)} cache (reads "
        f"{usd(cost.cache_read_usd)}, writes {usd(cost.cache_write_usd)}), "
        f"{_models_part(cost)}, {cost.model_calls} calls.{share} {caps}{month}."
        f"{stopped}{warnings}"
    )


def _cheating_cell(card: Scorecard) -> str:
    if card.cheating is None:
        return "— (not checked: the run stopped before Verify)"
    h = card.headline
    rules_notes = len(card.cheating.notes)
    cell = f"{h.cheating_check_hits} ({h.cheating_check_warnings} warnings)"
    return cell + (f"; {rules_notes} Rules-layer notes" if rules_notes else "")


def _finding_row(f: Finding) -> str:
    return f"| {f.file or '(run)'} | {f.layer} | {f.check} | {f.detail} |"


def _cheating_section(card: Scorecard) -> list[str]:
    report = card.cheating
    if report is None:
        return []
    lines = ["", "## Cheating checks", ""]
    if not report.hits and not report.warnings:
        lines.append("No hits and no warnings on repair-agent patches.")
    for title, findings in (("Hits (fail the run)", report.hits), ("Warnings", report.warnings)):
        if findings:
            lines += [f"**{title}**", "", "| File | Layer | Check | Detail |", "|---|---|---|---|"]
            lines += [_finding_row(f) for f in findings] + [""]
    if report.notes:
        lines += [
            "",
            "Reported, not failing (only repair-agent patches can fail a run):",
            "",
            "| File | Layer | Check | Detail |",
            "|---|---|---|---|",
        ]
        lines += [_finding_row(f) for f in report.notes]
    lines += ["", f"{len(report.test_files)} test files checked."]
    return lines


def _repair_section(card: Scorecard) -> list[str]:
    r = card.repair
    if r is None:
        return []
    lines = [
        "",
        "## Repair",
        "",
        f"{len(r.files)} failing files, {r.attempts} attempts, {r.tool_calls} tool calls."
        + (f" **Stopped by the cost cap:** {r.cost_cap_reason}." if r.stopped_by_cost_cap else ""),
    ]
    if r.edits_rejected:
        lines.append(
            "Edits refused by the guardrails: "
            + ", ".join(f"{k} {v}" for k, v in r.edits_rejected.items())
            + "."
        )
    if r.files:
        lines += [
            "",
            "| File | Outcome | Attempts | Tool calls | Patch | Why |",
            "|---|---|---|---|---|---|",
        ]
        for f in r.files:
            patch = ", ".join(f"{Path(p).name} {n}" for p, n in f.patch_lines.items()) or "—"
            why = (f.reason or "").replace("|", "\\|")
            if f.review:
                why += f" (Review: {f.review})"
            lines.append(
                f"| {f.path} | {f.outcome} | {len(f.attempts)} | {f.tool_calls} | {patch} | {why} |"
            )
    if r.review_list:
        lines += ["", "Review list: " + ", ".join(f"`{p}`" for p in r.review_list) + "."]
    if card.regressions:
        lines += ["", "Regressions: " + ", ".join(f"`{p}`" for p in card.regressions) + "."]
    return lines


def render_scorecard(card: Scorecard) -> str:
    h = card.headline
    m = card.meta
    share = h.migrated_without_human
    lines = [
        f"# Scorecard: {card.target_repo} · run {m.run_id}",
        "",
        f"`{card.migration}` · configuration `{card.configuration}`"
        + (f" · case `{card.case}`" if card.case else "")
        + f" · {_duration(m.duration_s)} · {_cost_head(card.cost)}",
        "",
    ]
    if card.status == "rejected":
        lines += [f"**Rejected at the Pre-check:** {card.reason}.", ""]
    elif card.status == "rules_failure":
        lines += [f"**Rules failure:** {card.reason}. Every affected file ends Unmigrated.", ""]
    by = h.outcomes
    clean = (
        "Clean run: yes."
        if h.clean_run
        else f"Clean run: no. Final verify found {h.failures} failures in {h.failing_files} files."
    )
    lines += [
        f"**{clean}** **{share.count} of {share.total} affected files migrated without a human "
        f"({_pct(share.share)})**: {by['Migrated by rules']} by rules, "
        f"{by['Migrated by agent']} by the repair agent. {by['Handed off']} handed off, "
        f"{by['Unmigrated']} unmigrated.",
        "",
        "| | This run |",
        "|---|---|",
        f"| Clean run | {_yes_no(h.clean_run)}"
        + ("" if h.clean_run else f" ({h.failures} failures in {h.failing_files} files)")
        + " |",
        f"| Migrated without a human | {share.count} / {share.total} ({_pct(share.share)}) |",
        f"| Hand-offs | {h.hand_offs} |",
        f"| Regressions | {h.regressions} |",
        f"| Cheating-check hits | {_cheating_cell(card)} |",
        f"| Codemod TODOs left | {h.codemod_todos} |",
        f"| Traps | {traps_line(h.traps)} |",
        f"| Cost / time | {usd(card.cost.total_usd)} · {_duration(m.duration_s)} |",
        "",
        "## Files",
        "",
        "| File | Outcome | Failures | Note |",
        "|---|---|---|---|",
    ]
    finished = [f for f in card.files if f.outcome == "Migrated by rules"]
    for f in card.files:
        if f.outcome != "Migrated by rules":
            lines.append(f"| {f.path} | {f.outcome} | {f.failures} | {f.note} |")
    if finished:
        names = ", ".join(Path(f.path).stem for f in finished)
        lines.append(f"| {len(finished)} files | Migrated by rules | 0 | {names} |")
    lines += [
        "",
        "Changed but not affected: "
        + (", ".join(f"`{p}`" for p in card.changed_not_affected) or "none")
        + ".",
    ]

    if card.verify and card.verify.failures:
        lines += ["", "## Failures", "", "| File | Check | Where | Message |", "|---|---|---|---|"]
        ordered = sorted(card.verify.failures, key=lambda x: (x.file or "", x.source, x.line or 0))
        for fail in ordered:
            where = (
                fail.test_name
                if fail.source == "test"
                else (f"line {fail.line}" if fail.line else "")
            )
            check = fail.source + (f" {fail.code}" if fail.code else "")
            message = fail.message.replace("|", "\\|")
            if len(message) > 140:
                message = message[:137] + "…"
            lines.append(f"| {fail.file or '(none)'} | {check} | {where} | {message} |")
        if card.verify.pre_existing_excluded:
            lines += ["", f"{card.verify.pre_existing_excluded} Pre-existing failures excluded."]

    if card.traps is not None:
        lines += [
            "",
            "## Traps (fixture)",
            "",
            "| Result | Expected layer | Traps |",
            "|---|---|---|",
        ]
        groups: dict[tuple[str, str], list[str]] = {}
        for t in card.traps:
            groups.setdefault((t.result, t.expected_layer), []).append(t.id)
        order = {"Expected": 0, "Other layer": 1, "Missed": 2, "Not scored": 3}
        layer_order = {"rules": 0, "agent": 1, "human": 2, "visual-only": 3}
        for (result, layer), ids in sorted(
            groups.items(), key=lambda kv: (order[kv[0][0]], layer_order.get(kv[0][1], 9))
        ):
            lines.append(f"| {result} | {layer} | {len(ids)}: {', '.join(ids)} |")
        quiet = [
            t
            for t in card.traps
            if t.expected_layer in ("agent", "human") and not any(c.fired for c in t.checks)
        ]
        fixed = [t.id for t in quiet if t.result in ("Expected", "Other layer")]
        uncaught = [t.id for t in quiet if t.silent_miss]
        if not quiet:
            lines += ["", "Every agent and human trap's check still fails at the final verify."]
        if fixed:
            lines += [
                "",
                f"Fixed (their checks now pass at the final verify): {', '.join(fixed)}.",
            ]
        if uncaught:
            lines += [
                "",
                f"Silent misses (no check fails, so verify can't show them; the fix "
                f"is missing or was made in another file, so a human should look): "
                f"{', '.join(uncaught)}.",
            ]

    lines += _repair_section(card)
    lines += _cheating_section(card)

    if card.rules:
        lines += [
            "",
            "## Rule steps",
            "",
            "| # | Step | Status | Changed | Detail |",
            "|---|---|---|---|---|",
        ]
        for i, s in enumerate(card.rules.steps, start=1):
            label = s.kind if s.name == s.kind else f"{s.kind} {s.name}"
            lines.append(f"| {i} | {label} | {s.status} | {len(s.changed_files)} | {s.detail} |")
    pre = card.precheck
    totals = card.verify.test_totals if card.verify else None
    lines += [
        "",
        "## Pre-check and tests",
        "",
        f"Pre-check: {pre.status}"
        + (f" ({pre.reason})" if pre.reason else "")
        + f", {len(pre.pre_existing_failures)} Pre-existing failures.",
    ]
    if pre.test_totals and totals:
        lines += [
            "",
            "| | Pre-check | Final verify |",
            "|---|---|---|",
            f"| Tests run | {pre.test_totals.tests_total} | {totals.tests_total} |",
            f"| Tests failing | {pre.test_totals.tests_failed} | {totals.tests_failed} |",
            f"| Tests skipped | {pre.test_totals.tests_skipped} | {totals.tests_skipped} |",
            f"| Suites failing | {pre.test_totals.suites_failed} of {pre.test_totals.suites_total} "
            f"| {totals.suites_failed} of {totals.suites_total} |",
            f"| Snapshots | {pre.test_totals.snapshots_total} | {totals.snapshots_total} |",
        ]
    lines += _m6_review_section(card)
    lines += ["", "## Cost", "", _cost_line(card.cost)]
    lines += [
        "",
        f"Node {m.node_version or '?'}, npm {m.npm_version or '?'}, migrator {m.migrator_version}.",
    ]
    return "\n".join(lines) + "\n"


def _m6_review_section(card: Scorecard) -> list[str]:
    """M6 review flags and lists: nothing on runs that don't produce them."""
    out: list[str] = []
    if card.coverage is not None:
        c = card.coverage
        out += [
            "",
            "## Test coverage of the files migrated without a human",
            "",
            f"{len(c.covered)} covered by a test, {len(c.not_covered)} not covered"
            + (": " + ", ".join(f"`{p}`" for p in c.not_covered) if c.not_covered else "."),
        ]
    if card.snapshots_to_review:
        out += ["", "## Snapshots to review (updated by the Migrator, not the agent)", ""]
        out += [
            f"- `{s.snapshot_file or s.test_file}` ({s.stage}): {len(s.tests)} tests"
            for s in card.snapshots_to_review
        ]
    if card.test_fitting:
        out += ["", "## Possible test-fitting, check this", ""]
        out += [
            f"- `{t.file}` (repairing `{t.repaired_for}`): "
            + "; ".join(f"`{_md_cell(x, 100)}`" for x in t.lines[:4])
            for t in card.test_fitting
        ]
    if card.visual is not None:
        out += ["", "## Visual changes to review", "", *_visual_lines(card.visual, task=False)]
    if card.codemod_false_positives:
        out += ["", "## Codemod false positives (undone by Rules)", ""]
        out += [
            f"- `{f.file}` line {f.line}: `<{f.element}>` had stray `(` and `)` text "
            f"around its child; removed them from `{_md_cell(f.reverted, 160)}`"
            if f.kind == "stray_parens"
            else f"- `{f.file}` line {f.line}: `<{f.element}>` is the repo's own (from "
            f"`{f.imported_from}`); undid `{_md_cell(f.reverted, 160)}`"
            for f in card.codemod_false_positives
        ]
    if card.repeated_edits:
        out += ["", "## Hint: the same change repeated in several files", ""]
        out += [
            f"- `{_md_cell(r.line, 120)}` in {len(r.files)} files: check whether it belongs "
            "in one shared place"
            for r in card.repeated_edits
        ]
    reviewed = [f for f in (card.repair.files if card.repair else []) if f.reviewed_by]
    if reviewed:
        out += ["", "## Flagged patches reviewed by a second model", ""]
        out += [
            f"- `{f.path}`: {f.review_verdict} ({f.reviewed_by}): "
            + _md_cell(f.review_reason or "", 300)
            + (" Stays migrated; check it." if f.review_verdict == "v5_required" else "")
            for f in reviewed
        ]
    suggested = [f for f in (card.repair.files if card.repair else []) if f.suggested_test_change]
    if suggested:
        out += ["", "## Suggested test changes (not applied)", ""]
        out += [f"- `{f.path}`: {_md_cell(f.suggested_test_change or '', 400)}" for f in suggested]
    return out


# --------------------------------------------------------------------------- PR body

STAGE_LABELS = {"rules": "Rules", "agent": "Repair agent", "review": "Review (human)"}


def _md_cell(text: str, limit: int = 160) -> str:
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def pr_title(card: Scorecard) -> str:
    share = card.headline.migrated_without_human
    return (
        f"Migrate {card.migration.replace('->', ' to ')}: {share.count} of {share.total} files "
        f"migrated without a human"
    )


def render_pr_body(card: Scorecard) -> str:
    """The PR body: the scorecard's summary, the hand-off checklist, the codemod TODOs
    and the cost. Rendered from the scorecard alone, so the JSON stays the source."""
    h = card.headline
    m = card.meta
    share = h.migrated_without_human
    by = h.outcomes
    clean = (
        "Clean run: yes."
        if h.clean_run
        else f"Clean run: no. The final verify found {h.failures} failures in "
        f"{h.failing_files} files."
    )
    lines = [
        f"Migration `{card.migration}` by the Migrator, run `{m.run_id}`, configuration "
        f"`{card.configuration}`"
        + (f", commands sandboxed in {m.sandbox}" if m.sandbox else "")
        + ". Every number below comes from the run's `scorecard.json`.",
        "",
        f"**{clean}** **{share.count} of {share.total} affected files migrated without a "
        f"human ({_pct(share.share)})**: {by['Migrated by rules']} by rules, "
        f"{by['Migrated by agent']} by the repair agent, {by['Migrated by human']} by a human "
        f"at Review. {by['Handed off']} handed off, {by['Unmigrated']} unmigrated.",
        "",
        "| | This run |",
        "|---|---|",
        f"| Clean run | {_yes_no(h.clean_run)} |",
        f"| Migrated without a human | {share.count} / {share.total} ({_pct(share.share)}) |",
        f"| Hand-offs | {h.hand_offs} |",
        f"| Regressions | {h.regressions} |",
        f"| Cheating-check hits | {_cheating_cell(card)} |",
        f"| Codemod TODOs left | {h.codemod_todos} |",
    ]
    if h.traps:
        lines.append(f"| Traps (fixture) | {traps_line(h.traps)} |")
    lines += [f"| Cost / time | {usd(card.cost.total_usd)} · {_duration(m.duration_s)} |", ""]

    # The checklist: what a human must finish before merging.
    reasons = {f.path: f.reason for f in card.repair.files} if card.repair else {}
    failures = card.verify.failures if card.verify else []
    handed = [f for f in card.files if f.outcome == "Handed off"]
    suggested = {
        r.path: r.suggested_test_change
        for r in (card.repair.files if card.repair else [])
        if r.suggested_test_change
    }
    lines += ["## Hand-offs: for a human to finish", ""]
    if not handed:
        lines.append("None: no file was handed off.")
    for f in handed:
        lines.append(
            f"- [ ] `{f.path}`: {_md_cell(reasons.get(f.path) or f.note or 'handed off', 300)}"
        )
        for fail in [x for x in failures if x.file == f.path][:5]:
            where = (
                fail.test_name
                if fail.source == "test"
                else (f"line {fail.line}" if fail.line else "")
            )
            lines.append(
                f"  - {fail.source}{f' {where}' if where else ''}: {_md_cell(fail.message)}"
            )
        if f.path in suggested:
            lines.append(
                f"  - Suggested test change (not applied; approve or edit): "
                f"{_md_cell(suggested[f.path], 600)}"
            )
    if card.test_fitting:
        lines += ["", "Possible test-fitting, check this (behaviour a test sees was changed):", ""]
        lines += [
            f"- [ ] `{t.file}` (repairing `{t.repaired_for}`): "
            + "; ".join(f"`{_md_cell(x, 100)}`" for x in t.lines[:4])
            for t in card.test_fitting
        ]
    if card.visual is not None and (card.visual.to_review or card.visual.skipped):
        lines += ["", "Visual changes to review (screenshots in the run folder):", ""]
        lines += _visual_lines(card.visual, task=True)
    if card.codemod_false_positives:
        lines += ["", "Codemod false positives, undone by Rules (check them):", ""]
        lines += [
            f"- [ ] `{f.file}` line {f.line}: the codemod left `(` and `)` as text inside "
            f"`<{f.element}>`; they were removed"
            if f.kind == "stray_parens"
            else f"- [ ] `{f.file}` line {f.line}: `<{f.element}>` from `{f.imported_from}` is "
            "the repo's own; the codemod's change was undone"
            for f in card.codemod_false_positives
        ]
    if card.repeated_edits:
        lines += ["", "Hint: the same change repeated in several files:", ""]
        lines += [
            f"- `{_md_cell(r.line, 120)}`, the same change repeated in {len(r.files)} files: "
            "check whether it belongs in one shared place ("
            + ", ".join(f"`{p}`" for p in r.files)
            + ")"
            for r in card.repeated_edits
        ]
    unmigrated = [f for f in card.files if f.outcome == "Unmigrated"]
    if unmigrated:
        lines += ["", "Unmigrated (no layer finished them):", ""]
        lines += [
            f"- [ ] `{f.path}`: {_md_cell(reasons.get(f.path) or f.note or 'unmigrated', 300)}"
            for f in unmigrated
        ]
    if card.regressions:
        lines += [
            "",
            "Regressions (clean after Rules, failing at the final verify): "
            + ", ".join(f"`{p}`" for p in card.regressions)
            + ".",
        ]
    todos = card.rules.codemod_todos if card.rules else []
    lines += ["", "## Codemod TODOs", ""]
    if not todos:
        lines.append("None: the codemods left no FIXME or TODO comments.")
    lines += [f"- [ ] `{t.file}` line {t.line}: {_md_cell(t.text)}" for t in todos]

    if m.commits:
        lines += ["", "## Commits", "", "| Stage | Commit | Files |", "|---|---|---|"]
        lines += [
            f"| {STAGE_LABELS.get(c.stage, c.stage)} | {c.sha[:8]} {_md_cell(c.title)} | "
            f"{len(c.files)} |"
            for c in m.commits
        ]
    lines += ["", "## Cost", "", _cost_line(card.cost)]
    lines += [
        "",
        f"<sub>Node {m.node_version or '?'}, npm {m.npm_version or '?'}, migrator "
        f"{m.migrator_version}. Verify ran the repo's type-check, lint and tests"
        + (" in a Docker container with no network." if m.sandbox == "docker" else ".")
        + "</sub>",
    ]
    return "\n".join(lines) + "\n"
