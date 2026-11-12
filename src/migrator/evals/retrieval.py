"""Offline retrieval metric: does the first message show the right guide section?

For each repair trap of a fixture case whose file fails after the Rules stage, this
rebuilds the guide ranking the repair agent's first message for that file would show
(``prompt.rank_sections``, the same code path) and checks whether the trap's guide
section (``breaking_change`` in ``traps.yaml``) is among the top 3, which the message
shows in full. No model is called: it needs only a finished run's folder (the files
after Rules, the verify failures and the usage report), so it is free and offline.

The trap labels are used only to score the ranking, never by the retriever; climbing on
this metric is climbing on the dev split, so a gain must be confirmed on held-out cases.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from migrator.config import Trap, TrapList
from migrator.migrations import MigrationSpec
from migrator.migrations.guide import load_guide, slug
from migrator.repair.prompt import GUIDE_FULL, guide_query, rank_sections
from migrator.repair.retriever import GuideRetriever
from migrator.scan import UsageReport
from migrator.verify import Failure


class RetrievalError(ValueError):
    pass


class TrapRetrieval(BaseModel):
    trap: str
    file: str
    expected: str  # guide change id
    rank: int | None  # 1-based position in the first message's ranking; None if absent
    top: list[str]  # the ids shown in full

    @property
    def hit(self) -> bool:
        return self.rank is not None and self.rank <= GUIDE_FULL


class RetrievalReport(BaseModel):
    mode: str
    run: str
    traps: list[TrapRetrieval]
    skipped: list[str]  # repair traps whose file had no failure after Rules

    @property
    def hits(self) -> int:
        return sum(t.hit for t in self.traps)


def _section_key(text: str) -> str:
    return slug(text.replace("✅", "").replace("›", " ").strip())


def expected_change(trap: Trap, spec: MigrationSpec) -> str:
    """The guide change id for a trap's ``breaking_change`` (file + "section > title")."""
    extra = trap.model_extra or {}
    change = extra.get("breaking_change") or {}
    file, heading = change.get("file"), change.get("section")
    if not file or not heading:
        raise RetrievalError(f"trap {trap.id} names no breaking_change file and section")
    section, _, title = (part.strip() for part in str(heading).partition("›"))
    for c in load_guide(spec.guide_dir(), spec.guide):
        if c.file != file:
            continue
        if _section_key(c.section) == _section_key(section) and _section_key(
            c.title
        ) == _section_key(title or section):
            return c.id
    raise RetrievalError(f"trap {trap.id}: no guide change {file} › {heading!r}")


def measure(
    run_dir: Path,
    traps: TrapList,
    spec: MigrationSpec,
    mode: str = "keyword",
    layers: Sequence[str] = ("agent",),
) -> RetrievalReport:
    """Score the first-message ranking of every repair trap's file in one run folder."""
    state = run_dir / "state" / "after-rules.json"
    card_path = run_dir / "scorecard.json"
    usage_path = run_dir / "usage-report.json"
    for path in (state, card_path, usage_path):
        if not path.is_file():
            raise RetrievalError(f"{run_dir} is not a finished run folder (no {path.name})")
    after: dict[str, str] = json.loads(state.read_text("utf-8"))
    card = json.loads(card_path.read_text("utf-8"))
    verify = card.get("verify") or {}
    failures = [Failure.model_validate(f) for f in verify.get("failures") or []]
    usage = UsageReport.model_validate_json(usage_path.read_text("utf-8"))
    retriever = GuideRetriever.from_spec(spec)
    rows: list[TrapRetrieval] = []
    skipped: list[str] = []
    for trap in traps.traps:
        if trap.expected_layer not in layers:
            continue
        target = trap.location.file
        mine = [f for f in failures if f.file == target]
        if not mine or target not in after:
            skipped.append(trap.id)
            continue
        file_usages = usage.file(target)
        symbols = (
            list(
                dict.fromkeys(
                    u.symbol.split(".")[0] for u in file_usages.old_usages if u.symbol != "*"
                )
            )
            if file_usages
            else []
        )
        query, _shown = guide_query(symbols, mine, after[target])
        ranked = [str(d.metadata["id"]) for d in rank_sections(spec, retriever, symbols, query)]
        expected = expected_change(trap, spec)
        rank = ranked.index(expected) + 1 if expected in ranked else None
        rows.append(
            TrapRetrieval(
                trap=trap.id, file=target, expected=expected, rank=rank, top=ranked[:GUIDE_FULL]
            )
        )
    return RetrievalReport(mode=mode, run=str(run_dir), traps=rows, skipped=skipped)


def render(reports: Sequence[RetrievalReport]) -> str:
    """A markdown table: one row per trap, one column per retrieval mode."""
    if not reports:
        return ""
    head = "| Trap | File | " + " | ".join(r.mode for r in reports) + " |"
    lines = [head, "|---|---|" + "---|" * len(reports)]

    def cell(t: TrapRetrieval) -> str:
        if t.rank is None:
            return "not ranked"
        return f"{'**hit**' if t.hit else 'miss'} (#{t.rank})"

    for i, t in enumerate(reports[0].traps):
        cells = [cell(r.traps[i]) for r in reports]
        lines.append(f"| `{t.trap}` | `{t.file}` | " + " | ".join(cells) + " |")
    totals = " | ".join(f"**{r.hits} of {len(r.traps)}**" for r in reports)
    lines.append(f"| Top-{GUIDE_FULL} hit rate | | {totals} |")
    return "\n".join(lines)
