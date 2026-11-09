"""The Scan stage: find every usage of the old (and new) library and write the usage report.

The report's expected split between codemods and repair is a forecast, not a
measurement: an old usage is expected to need repair when the guide lists a breaking
change for its symbol whose heading lacks the "handled by a codemod" marker.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from migrator.migrations import MigrationSpec
from migrator.migrations.guide import GuideChange, changes_for_symbol, load_guide
from migrator.scan.parser import ParsedFile, Usage, parse_file
from migrator.scan.teams import TeamSource, load_teams
from migrator.workspace import list_files

SCHEMA_VERSION = 1


class ScanInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo: Path
    spec: MigrationSpec
    source_globs: list[str]
    exclude: list[str]


class GuideRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    codemod_handled: bool


class FileUsages(BaseModel):
    path: str
    team: str
    old_usages: list[Usage]
    new_usages: list[Usage]
    expected_repair: list[str]  # guide change ids
    has_syntax_errors: bool = False

    @property
    def affected(self) -> bool:
        return bool(self.old_usages)


class SymbolSummary(BaseModel):
    symbol: str
    module: str
    usages: int
    files: int
    guide_changes: list[GuideRef]


class TeamSummary(BaseModel):
    team: str
    source: TeamSource
    affected_files: int
    usages: int
    expected_repair_usages: int
    expected_repair_files: int


class UsageTotals(BaseModel):
    files_scanned: int
    affected_files: int
    old_usages: int
    new_usages: int
    expected_by_codemods: int
    expected_repair: int
    expected_repair_files: int


class ScanMeta(BaseModel):
    """Values that change from one scan to the next; kept apart from the stable part."""

    scanned_at: str
    commit: str | None


class UsageReport(BaseModel):
    schema_version: int = SCHEMA_VERSION
    migration: str
    target_repo: str
    totals: UsageTotals
    by_team: list[TeamSummary]
    by_symbol: list[SymbolSummary]
    files: list[FileUsages]
    meta: ScanMeta

    def affected_files(self) -> list[str]:
        return [f.path for f in self.files if f.affected]

    def file(self, path: str) -> FileUsages | None:
        return next((f for f in self.files if f.path == path), None)


def scan_sources(repo: Path, spec: MigrationSpec, paths: list[str]) -> dict[str, ParsedFile]:
    usage = spec.usage

    def wanted(module: str) -> bool:
        return usage.is_old(module) or usage.is_new(module)

    return {p: parse_file((repo / p).read_bytes(), p, wanted) for p in paths}


def repo_name(repo: Path) -> str:
    """The package.json name, else the folder name."""
    package = repo / "package.json"
    if package.is_file():
        try:
            name = json.loads(package.read_text("utf-8")).get("name")
        except (ValueError, AttributeError):
            name = None
        if isinstance(name, str) and name:
            return name
    return repo.resolve().name


def _git_commit(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except OSError:
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def scan(inp: ScanInput) -> UsageReport:
    spec = inp.spec
    teams = load_teams(inp.repo)
    guide = load_guide(spec.guide_dir(), spec.guide)
    paths = list_files(inp.repo, inp.source_globs, inp.exclude)
    parsed = scan_sources(inp.repo, spec, paths)

    guide_by_symbol: dict[str, list[GuideChange]] = {}

    def changes(symbol: str) -> list[GuideChange]:
        if symbol not in guide_by_symbol:
            base = symbol.split(".")[0]
            guide_by_symbol[symbol] = [] if base == "*" else changes_for_symbol(base, guide)
        return guide_by_symbol[symbol]

    files: list[FileUsages] = []
    for path in paths:
        result = parsed[path]
        old = [u for u in result.usages if spec.usage.is_old(u.module)]
        new = [u for u in result.usages if spec.usage.is_new(u.module)]
        if not old and not new:
            continue
        repair_ids = sorted(
            {
                c.id
                for u in old
                if u.kind != "import"
                for c in changes(u.symbol)
                if not c.codemod_handled
            }
        )
        files.append(
            FileUsages(
                path=path,
                team=teams.team_for(path),
                old_usages=old,
                new_usages=new,
                expected_repair=repair_ids,
                has_syntax_errors=result.has_syntax_errors,
            )
        )

    def needs_repair(u: Usage) -> bool:
        # Import statements themselves are rewritten by the codemods (the guide's ✅
        # import changes); the breaking changes live where the symbol is used.
        return u.kind != "import" and any(not c.codemod_handled for c in changes(u.symbol))

    old_all = [(f, u) for f in files for u in f.old_usages]
    repair_usages = [(f, u) for f, u in old_all if needs_repair(u)]

    by_symbol: dict[tuple[str, str], list[tuple[FileUsages, Usage]]] = defaultdict(list)
    for f, u in old_all:
        by_symbol[(u.symbol, u.module)].append((f, u))
    symbols = [
        SymbolSummary(
            symbol=symbol,
            module=module,
            usages=len(items),
            files=len({f.path for f, _ in items}),
            guide_changes=[
                GuideRef(
                    id=c.id, title=f"{c.section}: {c.title}", codemod_handled=c.codemod_handled
                )
                for c in changes(symbol)
            ],
        )
        for (symbol, module), items in by_symbol.items()
    ]
    symbols.sort(key=lambda s: (-s.usages, s.symbol, s.module))

    team_names = sorted({f.team for f in files if f.affected})
    by_team = []
    for team in team_names:
        team_files = [f for f in files if f.affected and f.team == team]
        team_repair = [(f, u) for f, u in repair_usages if f.team == team]
        by_team.append(
            TeamSummary(
                team=team,
                source=teams.source,
                affected_files=len(team_files),
                usages=sum(len(f.old_usages) for f in team_files),
                expected_repair_usages=len(team_repair),
                expected_repair_files=len({f.path for f, _ in team_repair}),
            )
        )
    by_team.sort(key=lambda t: (-t.usages, t.team))

    totals = UsageTotals(
        files_scanned=len(paths),
        affected_files=sum(1 for f in files if f.affected),
        old_usages=len(old_all),
        new_usages=sum(len(f.new_usages) for f in files),
        expected_by_codemods=len(old_all) - len(repair_usages),
        expected_repair=len(repair_usages),
        expected_repair_files=len({f.path for f, _ in repair_usages}),
    )
    return UsageReport(
        migration=spec.id,
        target_repo=repo_name(inp.repo),
        totals=totals,
        by_team=by_team,
        by_symbol=symbols,
        files=files,
        meta=ScanMeta(
            scanned_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            commit=_git_commit(inp.repo),
        ),
    )
