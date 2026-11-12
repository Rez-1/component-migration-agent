"""The repair agent's parts: guardrails, prompt, retriever, model setup and cost accounting."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from migrator.cost import (
    Budget,
    CallRecord,
    CostCapError,
    CostGuard,
    Ledger,
    LedgerPreflight,
    LedgerRow,
    PlannedExperiment,
    RunCaps,
    Usage,
    cost_usd,
    now_utc,
    run_cost,
    usage_from_langchain,
    worst_case_usd,
)
from migrator.migrations import MigrationSpec
from migrator.pipeline import RunResult
from migrator.repair.context import PatchSize, file_view, signatures
from migrator.repair.guardrails import added_escape_hatches, check_target, workspace_path
from migrator.repair.model import GuardedModel, provider_model
from migrator.repair.prompt import (
    PROMPTS_DIR,
    first_message,
    load_templates,
    spec_fields,
    system_prompt,
    tool_text,
)
from migrator.repair.retriever import GuideRetriever, heading, render_section
from migrator.repair.tools import TOOL_ORDER, RepairTools
from tests.conftest import FIXTURE
from tests.fakes import ScriptedChatModel, ai, call
from tests.test_graph import CARD, DASH, GOOD, THEME, USERS, fix_dashboard, record_of, run

# --------------------------------------------------------------------------- guardrails


def test_every_guardrail_against_an_adversarial_agent(tmp_path: Path, spec: MigrationSpec) -> None:
    attacks = ai(
        # a Test file (imported only by tests: test-utils)
        call(
            "apply_edit",
            path="src/test-utils.tsx",
            old_text="render(ui)",
            new_text="render(ui, {})",
        ),
        # escape hatches
        call(
            "apply_edit",
            path=DASH,
            old_text="  marginTop: theme.spacing(1) * 3,",
            new_text="  // @ts-ignore\n  marginTop: theme.spacing(1) * 3,",
        ),
        call(
            "apply_edit",
            path=DASH,
            old_text="theme.spacing(4) + 24",
            new_text="(theme.spacing(4) as any) + 24",
        ),
        call(
            "apply_edit",
            path=DASH,
            old_text="theme.spacing(1) * 3",
            new_text="(process.env.NODE_ENV === 'test' ? 24 : theme.spacing(1) * 3)",
        ),
        # package files and configs
        call("apply_edit", path="package.json", old_text='"jest"', new_text='"vitest"'),
        call("apply_edit", path="package-lock.json", old_text="{}", new_text="{ }"),
        call("apply_edit", path="tsconfig.json", old_text="strict", new_text="loose"),
        # a file this one does not import (UsersTable imports Dashboard, not the reverse)
        call("apply_edit", path=USERS, old_text="48 * rows", new_text="String(48 * rows)"),
        # outside the workspace, and into git data
        call("apply_edit", path="../../outside.ts", old_text="a", new_text="b"),
        call("read_file", path="../../outside.ts"),
    )
    result, _, _, _ = run(
        tmp_path, spec, {**GOOD, DASH: [attacks, *fix_dashboard()]}, keep_workspace=True
    )
    assert isinstance(result, RunResult) and result.workspace is not None
    card = result.scorecard
    record = record_of(card, DASH)
    assert record.edits_rejected == {
        "test-file": 1,
        "escape-hatch": 3,
        "package-files": 2,
        "config": 1,
        "scope": 1,
        "outside-workspace": 1,
    }
    assert record.outcome == "Migrated by agent"  # the legitimate fix still lands
    assert card.cheating is not None and card.cheating.hits == []
    ws = result.workspace
    assert "render(ui)" in (ws / "src/test-utils.tsx").read_text()
    assert "@ts-ignore" not in (ws / DASH).read_text() and "as any" not in (ws / DASH).read_text()
    assert '"jest"' in (ws / "package.json").read_text()
    assert "String(" not in (ws / USERS).read_text()
    # Every refusal says why, so the agent can change course within the attempt.
    assert record.conversation is not None
    messages = json.loads((result.run_dir / record.conversation).read_text())
    texts = [m["data"]["content"] for m in messages if m["type"] == "tool"][:10]
    assert "Test file" in texts[0]
    assert "`@ts-ignore`" in texts[1] and "the `any` type" in texts[2]
    assert "NODE_ENV" in texts[3]
    assert "dependencies are set by the migration" in texts[4]
    assert "config" in texts[6]
    assert "not this file or a local file it imports" in texts[7]
    assert "outside the workspace" in texts[8] and "outside the workspace" in texts[9]


def test_a_patch_over_the_size_limit_is_refused_and_handed_off(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    big = "\n".join(f"export const x{i} = {i};" for i in range(30))
    rewrite = ai(
        call(
            "apply_edit",
            path=DASH,
            old_text="export function Dashboard",
            new_text=big + "\nexport function Dashboard",
        )
    )
    result, _, _, _ = run(tmp_path, spec, {**GOOD, DASH: [rewrite]}, keep_workspace=True)
    assert isinstance(result, RunResult) and result.workspace is not None
    record = record_of(result.scorecard, DASH)
    assert record.outcome == "Handed off" and "size limit" in (record.reason or "")
    assert "export const x0" not in (result.workspace / DASH).read_text()


def test_check_target_rules() -> None:
    tests = {"src/test-utils.tsx": "imported only by tests", "src/a.test.tsx": "test glob"}
    ok = check_target("src/b.tsx", "src/a.tsx", ["src/b.tsx"], tests)
    assert ok is None
    assert check_target("src/a.tsx", "src/a.tsx", [], tests) is None
    blocked = check_target("src/test-utils.tsx", "src/a.tsx", ["src/test-utils.tsx"], tests)
    assert getattr(blocked, "guardrail", None) == "test-file"
    assert (
        getattr(check_target("tsconfig.json", "src/a.tsx", [], tests), "guardrail", None)
        == "config"
    )
    assert (
        getattr(check_target("yarn.lock", "src/a.tsx", [], tests), "guardrail", None)
        == "package-files"
    )
    assert (
        getattr(check_target("node_modules/x/index.js", "src/a.tsx", [], tests), "guardrail", None)
        == "dependency"
    )
    assert (
        getattr(check_target("src/c.tsx", "src/a.tsx", ["src/b.tsx"], tests), "guardrail", None)
        == "scope"
    )


def test_escape_hatches_are_counted_per_file() -> None:
    before = "// @ts-ignore\nconst a: number = f();\nconst b = 1;\n"
    moved = "const b = 1;\n// @ts-ignore\nconst a: number = f();\n"
    assert added_escape_hatches("x.ts", before, moved) == []  # moving one is not adding one
    assert added_escape_hatches("x.ts", before, before + "// eslint-disable-next-line\n") == [
        "an `eslint-disable` comment"
    ]
    assert added_escape_hatches("x.ts", before, before + "const c = d as unknown as E;\n")
    assert added_escape_hatches("x.ts", before, before + "if (typeof jest !== 'undefined') {}\n")
    # In a string or a comment's text, "any" is not the any type.
    assert added_escape_hatches("x.ts", before, before + "const s = 'as any';\n") == []


def test_reads_stay_inside_the_workspace(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert not isinstance(workspace_path(tmp_path, "src/a.ts"), type(None))
    assert getattr(workspace_path(tmp_path, "../x"), "guardrail", None) == "outside-workspace"
    assert (
        getattr(workspace_path(tmp_path, ".git/config"), "guardrail", None) == "outside-workspace"
    )
    assert workspace_path(tmp_path, "./src/a.ts") == ("src/a.ts", (tmp_path / "src/a.ts").resolve())


def test_patch_size() -> None:
    size = PatchSize("a\nb\nc\nd\n", "a\nB\nc\nd\nE\n")
    assert (size.changed, size.added, size.removed) == (2, 2, 1)
    assert size.share == 0.5


# --------------------------------------------------------------------------- prompt

LIBRARY_WORDS = re.compile(r"material|\bmui\b|@mui|material-ui|codemod\b(?!s)", re.IGNORECASE)


def test_the_templates_name_no_library(spec: MigrationSpec) -> None:
    folder = PROMPTS_DIR / "v1"
    for name in ("system.md", "first_message.md", "attempt_result.md", "tools.toml"):
        text = (folder / name).read_text()
        for word in (spec.library_name, spec.codemod_name, spec.from_, spec.to, "MUI", "Material"):
            assert word not in text, f"{word!r} is hardcoded in {name}"
        assert not re.search(r"@mui|material-ui|makeStyles|adaptV4Theme", text), name


def test_the_system_prompt_is_filled_from_the_spec(spec: MigrationSpec) -> None:
    templates = load_templates("v1")
    text = system_prompt(templates, spec, max_attempts=3)
    fields = spec_fields(spec)
    for key in ("library_name", "from_version", "to_version", "codemod_name", "guide_title"):
        assert fields[key] in text
    for note in spec.repair_notes:
        assert f"- {note}" in text
    assert "up to 3 attempts" in text and "up to 15 tool calls" in text
    assert "{" not in text  # nothing left unfilled
    # Same spec, same prompt: it is identical for every file, so it can be cached.
    assert system_prompt(templates, spec, max_attempts=3) == text


def test_the_tools_are_strict_and_in_a_fixed_order(spec: MigrationSpec) -> None:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    tools = RepairTools(tool_text(load_templates("v1"), spec)).tools
    assert [t.name for t in tools] == list(TOOL_ORDER)
    for tool in tools:
        schema = convert_to_openai_tool(tool, strict=True)["function"]
        assert schema["strict"] is True
        assert schema["parameters"]["additionalProperties"] is False
        assert not LIBRARY_WORDS.search(tool.description)
    with (PROMPTS_DIR / "v1" / "tools.toml").open("rb") as fh:
        assert list(tomllib.load(fh)) == list(TOOL_ORDER)
    assert spec.guide_title in tools[1].description  # filled from the spec


def test_the_first_message_has_every_section(spec: MigrationSpec) -> None:
    from migrator.verify import Failure

    after = (
        (FIXTURE / "src/screens/Search.tsx")
        .read_text()
        .replace("@material-ui/lab", "@mui/material")
    )
    files = {
        "src/screens/Search.tsx": after,
        "src/data/cities.ts": (FIXTURE / "src/data/cities.ts").read_text(),
        "src/App.tsx": "import { Search } from './screens/Search';\n",
    }
    failures = [
        Failure(
            source="typecheck",
            file="src/screens/Search.tsx",
            line=41,
            code="TS2339",
            message="Property 'label' does not exist on type 'HTMLAttributes<HTMLLIElement>'.",
        ),
        Failure(
            source="test",
            file="src/screens/Search.tsx",
            message="Unable to find role option",
            test_file="src/screens/__tests__/Search.test.tsx",
            test_name="Search › selects Amsterdam",
        ),
    ]
    text = first_message(
        load_templates("v1"),
        spec,
        GuideRetriever.from_spec(spec),
        path="src/screens/Search.tsx",
        max_attempts=3,
        failures=failures,
        untouched=(FIXTURE / "src/screens/Search.tsx").read_text(),
        after_rules=after,
        files=files,
        test_files={},
        symbols=["Autocomplete", "TextField", "Typography", "makeStyles"],
    )
    assert text.startswith("## Failing file: `src/screens/Search.tsx`\n\nAttempt 1 of 3.")
    assert "**Type error** TS2339, line 41" in text
    assert (
        '**Failing test** `src/screens/__tests__/Search.test.tsx` › "Search › selects Amsterdam"'
        in text
    )
    assert "(This test imports this file.)" in text
    assert "-import { Autocomplete } from '@material-ui/lab';" in text  # the Rules diff
    assert " 1  import { useState } from 'react';" in text  # numbered, whole file
    assert "`src/data/cities.ts`: `export interface City" in text
    assert "`src/App.tsx` imports `Search` from this file." in text
    assert "**Autocomplete › Update renderOption**" in text


def test_a_long_file_is_shown_around_its_failures() -> None:
    text = "\n".join(f"line {i}" for i in range(1, 501))
    heading_text, shown = file_view(text, [250])
    assert heading_text.startswith("lines 235–265 of 500")
    assert "line 250" in shown and "line 100" not in shown


def test_signatures_cut_bodies() -> None:
    source = (
        "export const t = (x: number): string => `${x}`;\n"
        "export function f(a: string): void { console.log(a); }\n"
        "export interface I { a: string }\n"
        "export const theme = createTheme({ a: 1 });\n"
    )
    assert signatures("a.ts", source) == [
        "export const t = (x: number): string =>",
        "export function f(a: string): void",
        "export interface I { a: string }",
        "export const theme = createTheme(…)",
    ]


# --------------------------------------------------------------------------- retriever


def test_keyword_retrieval_finds_the_change_and_labels_codemod_sections(
    spec: MigrationSpec,
) -> None:
    retriever = GuideRetriever.from_spec(spec)
    docs = retriever.invoke("Autocomplete renderOption")  # the LangChain retriever interface
    assert heading(docs[0]) == "Autocomplete › Update renderOption"
    assert any(heading(d).endswith("(codemod)") for d in docs)  # labelled, not dropped
    srs = retriever.rank("Typography srOnly", k=1)[0]
    assert heading(srs) == "Typography › Remove srOnly variant"
    rendered = render_section(srs, spec.guide.link_base)
    assert "](/" not in rendered  # relative links point at the v5 docs site


# --------------------------------------------------------------------------- the model


def test_the_anthropic_model_gets_effort_and_never_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_init(model: str, **kwargs: Any) -> Any:
        seen.update({"model": model, **kwargs})
        return ScriptedChatModel(script={})

    import langchain.chat_models

    monkeypatch.setattr(langchain.chat_models, "init_chat_model", fake_init)
    provider_model("claude-opus-5-5", "low", 16_000)
    assert seen["model"] == "claude-opus-5-5" and seen["model_provider"] == "anthropic"
    assert seen["reasoning_effort"] == "low" and seen["max_tokens"] == 16_000
    assert "temperature" not in seen and "tool_choice" not in seen


def test_the_guarded_model_binds_strict_tools_and_the_cache_breakpoints(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    model = ScriptedChatModel(script={"x": [ai(call("run_verify", note="n"))]})
    tools = RepairTools(tool_text(load_templates("v1"), spec)).tools
    guarded = GuardedModel(
        lambda *_: model,
        tools,
        effort="low",
        run_id="r",
        case=None,
    )
    _message, record = guarded.call(
        "claude-opus-5-5",
        "system",
        [HumanMessage(content="## Failing file: `x`")],
        budget=Budget("r", RunCaps(run_usd=5, month_usd=20), Ledger(tmp_path / "l.jsonl")),
        file="x",
        attempt=1,
    )
    assert model.bind_kwargs == {"strict": True}
    request = model.requests[0]
    assert request["kwargs"]["cache_control"] == {"type": "ephemeral"}  # automatic caching
    assert request["messages"][0].content[0]["cache_control"] == {"type": "ephemeral"}
    assert record.model == "claude-opus-5-5" and record.cost_usd > 0


def test_the_guard_refuses_before_sending(tmp_path: Path) -> None:
    guard = CostGuard(1.0, 20.0, Ledger(tmp_path / "l.jsonl"))
    worst = worst_case_usd("claude-opus-5-5", 10_000, 16_000)
    assert worst == pytest.approx((10_000 * 5.0 + 16_000 * 20.0) / 1e6)
    assert guard.check("claude-opus-5-5", 10_000, 16_000, run_spent_usd=0.5) == worst
    with pytest.raises(CostCapError, match=r"run past its \$1\.00 cap"):
        guard.check("claude-opus-5-5", 10_000, 16_000, run_spent_usd=0.7)
    with pytest.raises(ValueError, match="no unlimited"):
        CostGuard(float("inf"), 20, Ledger(tmp_path / "l.jsonl"))


# --------------------------------------------------------------------------- cost accounting


def test_cache_tokens_come_from_the_breakdown_fields() -> None:
    # langchain-anthropic folds cache tokens into input_tokens and, with the TTL
    # breakdown, sets cache_creation to 0.
    with_ttl = {
        "input_tokens": 1000 + 5000 + 2000,
        "output_tokens": 300,
        "input_token_details": {
            "cache_read": 5000,
            "cache_creation": 0,
            "ephemeral_5m_input_tokens": 2000,
            "ephemeral_1h_input_tokens": 0,
        },
    }
    usage = usage_from_langchain(with_ttl)
    assert usage == Usage(
        input_tokens=1000,
        output_tokens=300,
        cache_read_input_tokens=5000,
        cache_creation_input_tokens=2000,
    )
    without_ttl = {
        "input_tokens": 1500,
        "output_tokens": 10,
        "input_token_details": {"cache_read": 0, "cache_creation": 500},
    }
    assert usage_from_langchain(without_ttl).cache_creation_input_tokens == 500
    assert usage_from_langchain(without_ttl).input_tokens == 1000
    # Opus 5.5: 1000 x $4 + 5000 x $0.20 + 2000 x $5 + 300 x $20, per million
    assert cost_usd("claude-opus-5-5", usage) == pytest.approx((4000 + 1000 + 10000 + 6000) / 1e6)


def test_cache_reads_through_a_run(tmp_path: Path, spec: MigrationSpec) -> None:
    cached = {
        THEME: [
            ai(
                call("apply_edit", path=THEME, old_text="label: {", new_text="root: {"),
                call("run_verify", note="root"),
                input_tokens=200,
                cache_write=3000,
            )
        ],
        DASH: [
            ai(call("read_file", path=DASH), input_tokens=300, cache_read=3000),
            *[
                m.model_copy(
                    update={
                        "usage_metadata": {
                            **(m.usage_metadata or {}),
                            "input_tokens": 3400,
                            "input_token_details": {"cache_read": 3000, "cache_creation": 0},
                        }
                    }
                )
                for m in fix_dashboard()
            ],
        ],
        CARD: [ai(call("hand_off", reason="test-utils"), input_tokens=100, cache_read=3000)],
    }
    result, _, _, _ = run(tmp_path, spec, cached)
    cost = result.scorecard.cost  # type: ignore[union-attr]
    assert cost.usage.cache_read_input_tokens == 9000
    assert cost.usage.cache_creation_input_tokens == 3000
    assert cost.cache_read_share is not None and cost.cache_read_share > 0.5
    assert cost.warnings == []


def test_a_run_whose_cache_reads_stay_zero_is_warned() -> None:
    calls = [
        CallRecord(
            model="claude-opus-5-5",
            requested_model="claude-opus-5-5",
            usage=Usage(input_tokens=5000, output_tokens=100),
            cost_usd=0.022,
        )
        for _ in range(3)
    ]
    cost = run_cost(calls, 5, 20)
    assert any("cache reads stayed at 0" in w for w in cost.warnings)
    assert run_cost(calls[:2], 5, 20).warnings == []
    swapped = [c.model_copy(update={"model": "claude-opus-5"}) for c in calls[:1]]
    assert any("served model differs" in w for w in run_cost(swapped, 5, 20).warnings)


def test_preflight_estimates_from_the_ledger_or_the_prior(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    pre = LedgerPreflight(ledger)
    plan = PlannedExperiment(
        configuration="opus-low",
        uses_llm=True,
        runs=2,
        max_cost_usd=10,
        attempt_models=["claude-opus-5-5"] * 3,
        month_cap_usd=20,
    )
    ok = pre.check(plan)
    assert ok.ok and ok.estimated_usd == pytest.approx(2 * 14 * 0.20)  # the prior
    assert not pre.check(plan.model_copy(update={"max_cost_usd": 3})).ok
    assert "--max-cost" in pre.check(plan.model_copy(update={"max_cost_usd": None})).reason
    haiku = pre.check(plan.model_copy(update={"attempt_models": ["claude-haiku-5-5"] * 3}))
    assert haiku.estimated_usd == pytest.approx(2 * 14 * 0.005)
    for i in range(6):  # once the ledger has attempts, it is the basis
        ledger.append(
            LedgerRow(
                at=now_utc(),
                run_id="r1",
                file=f"f{i}",
                attempt=1,
                model="claude-opus-5-5",
                requested_model="claude-opus-5-5",
                usage=Usage(),
                cost_usd=0.10,
            )
        )
    assert pre.check(plan).estimated_usd == pytest.approx(2 * 6 * 0.10)
    ledger.append(
        LedgerRow(
            at=now_utc(),
            run_id="big",
            model="claude-opus-5-5",
            requested_model="claude-opus-5-5",
            usage=Usage(),
            cost_usd=19.0,
        )
    )
    refused = pre.check(plan.model_copy(update={"max_cost_usd": 100}))
    assert not refused.ok and "left of this month" in refused.reason


# --------------------------------------------------------------------------- the fixture


TRAP_WORDS = re.compile(
    r"\btraps?\b|hand.?off|benchmark|traps\.yaml|repair agent|on purpose|expected layer",
    re.IGNORECASE,
)
GLOSSARY_WORDS = re.compile(r"Test file|Migrator|Hand-off")


def test_nothing_in_the_fixture_describes_the_traps() -> None:
    """Everything in the fixture is copied into the workspace, where read_file can
    reach it (M2 audit, finding #3): no file may describe the traps."""
    leaks = []
    built = {"node_modules", "dist", ".angular"}  # installed or built, not the fixture
    for fixture in sorted(p for p in FIXTURE.parent.iterdir() if p.is_dir()):
        for path in sorted(fixture.rglob("*")):
            if built & set(path.parts) or not path.is_file() or path.name == "package-lock.json":
                continue
            if path.suffix in (".ico", ".png"):
                continue
            for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if TRAP_WORDS.search(line) or GLOSSARY_WORDS.search(line):
                    leaks.append(f"{path.relative_to(FIXTURE.parent)}:{i}: {line.strip()}")
        # traps.yaml and the case README live outside the fixture, so outside the workspace.
        assert not (fixture / "traps.yaml").exists()
    assert leaks == []


def test_offline_retrieval_hit_rate_on_the_dev_fixture(spec: MigrationSpec) -> None:
    """The measured miss: Search's renderOption section is not in keyword's top 3."""
    from migrator.config import load_traps
    from migrator.evals.retrieval import measure, render
    from tests.conftest import REPO_ROOT

    flow = REPO_ROOT / ".claude" / "hillclimb" / "dev" / "baseline" / "runs"
    traps = load_traps(REPO_ROOT / "evals" / "cases" / "fixture-mui4" / "traps.yaml")
    report = measure(flow / "fixture-mui4_rep0", traps, spec, "keyword")
    assert len(report.traps) == 9 and report.hits == 5
    search = next(t for t in report.traps if t.trap == "autocomplete-render-option")
    assert not search.hit and search.rank == 14
    assert "**5 of 9**" in render([report])
