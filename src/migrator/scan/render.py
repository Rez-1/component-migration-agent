"""Markdown for the usage report, always rendered from the JSON model."""

from __future__ import annotations

from migrator.scan import UsageReport


def _pct(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%" if whole else "—"


def render_usage_report(report: UsageReport, top_symbols: int = 10) -> str:
    t = report.totals
    affected = [f for f in report.files if f.affected]
    old_modules = sorted({u.module.split("/")[0] + "/*" for f in affected for u in f.old_usages})
    lines = [
        f"# Usage report: {report.target_repo}",
        "",
        f"`{report.migration}` · {t.files_scanned} files scanned",
        "",
        f"**{t.affected_files} affected files, {t.old_usages} usages of "
        f"{', '.join(f'`{m}`' for m in old_modules) or 'the old library'}, "
        f"{t.new_usages} of the new library.** "
        f"The official codemods are expected to handle {t.expected_by_codemods} of the "
        f"{t.old_usages} usages ({_pct(t.expected_by_codemods, t.old_usages)}). "
        f"{t.expected_repair} usages in {t.expected_repair_files} files touch breaking changes "
        "the guide doesn't mark as codemod-handled, so expect repair work there.",
        "",
        "> The split is a forecast from the guide's ✅ markers: a JSX element or call is "
        "counted for repair when its symbol has any unmarked breaking change, whether or "
        "not the file uses the changed prop. Import statements count as codemod-handled.",
        "",
        "## By team",
        "",
        "| Team | Affected files | Usages | Expected repair |",
        "|---|---|---|---|",
    ]
    for team in report.by_team:
        repair = (
            f"{team.expected_repair_usages} usages in {team.expected_repair_files} "
            f"file{'s' if team.expected_repair_files != 1 else ''}"
            if team.expected_repair_usages
            else "—"
        )
        lines.append(f"| {team.team} | {team.affected_files} | {team.usages} | {repair} |")
    source = report.by_team[0].source if report.by_team else "CODEOWNERS"
    if source == "folder":
        lines += ["", "No CODEOWNERS file, so teams are top-level folders."]

    lines += [
        "",
        "## Most-used symbols",
        "",
        "| Symbol | Module | Usages | Files | Guide says |",
        "|---|---|---|---|---|",
    ]
    for sym in report.by_symbol[:top_symbols]:
        notes = "; ".join(
            ("✅ " if g.codemod_handled else "") + g.title.split(": ", 1)[-1]
            for g in sym.guide_changes
        )
        lines.append(
            f"| {sym.symbol} | {sym.module} | {sym.usages} | {sym.files} | {notes or '—'} |"
        )
    if len(report.by_symbol) > top_symbols:
        lines += [
            "",
            f"(top {top_symbols} of {len(report.by_symbol)} symbols; full list in "
            "`usage-report.json`)",
        ]

    lines += [
        "",
        "## Files",
        "",
        "| File | Team | Usages | Expected repair |",
        "|---|---|---|---|",
    ]
    for f in sorted(affected, key=lambda f: (-len(f.expected_repair), f.path)):
        repair = ", ".join(i.split("#", 1)[1] for i in f.expected_repair[:3])
        more = len(f.expected_repair) - 3
        if more > 0:
            repair += f" (+{more})"
        warn = " (syntax errors)" if f.has_syntax_errors else ""
        lines.append(f"| {f.path}{warn} | {f.team} | {len(f.old_usages)} | {repair or '—'} |")
    return "\n".join(lines) + "\n"
