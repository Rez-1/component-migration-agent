"""The run graph on a fake toolchain and a scripted model (no Node, no LLM).

Covers the wiring (stage order, Rules exactly once, one interrupt per hand-off, resume
from a SQLite checkpoint), the attempt and tool-call limits as edges, Regressions and
the agent being told which file it broke, and the cost cap ending Repair.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from migrator.configuration import Configuration
from migrator.cost import Ledger
from migrator.graph import repair_order
from migrator.migrations import MigrationSpec
from migrator.pipeline import PausedRun, RunOptions, RunResult, resume_run, start_run
from migrator.repair.records import ReviewAnswer
from migrator.report import FileRepairSummary
from migrator.review import ReviewPayload
from tests.conftest import FakeRunner
from tests.fakes import (
    FakeToolchain,
    ScriptedChatModel,
    ai,
    call,
    factory_for,
    make_mini_repo,
)

THEME = "src/theme.ts"
DASH = "src/screens/Dashboard.tsx"
CARD = "src/screens/ProfileCard.tsx"
USERS = "src/screens/UsersTable.tsx"


def configuration(models: list[str] | None = None, **cost: float) -> Configuration:
    models = models or ["claude-opus-5-5"] * 3
    return Configuration.model_validate(
        {
            "name": "opus-low",
            "repair": {
                "enabled": True,
                "attempt_models": models,
                "effort": "low",
                "prompt_version": "v1",
                "retrieval": "keyword",
                "max_attempts": len(models),
            },
            "cost": cost,
        }
    )


def fix_theme() -> list[AIMessage]:
    return [
        ai(
            call("apply_edit", path=THEME, old_text="label: {", new_text="root: {"),
            call("run_verify", note="the label slot is gone; style the root"),
        )
    ]


def fix_dashboard() -> list[AIMessage]:
    return [
        ai(
            call(
                "apply_edit",
                path=DASH,
                old_text="theme.spacing(1) * 3",
                new_text="theme.spacing(3)",
            ),
            call(
                "apply_edit",
                path=DASH,
                old_text="): number => theme.spacing(4) + 24",
                new_text="): number => parseFloat(theme.spacing(4)) + 24",
            ),
            call("run_verify", note="spacing returns px strings"),
        )
    ]


def hand_off_card() -> list[AIMessage]:
    return [ai(call("hand_off", reason="the theme must come from test-utils, a Test file"))]


GOOD: dict[str, list[AIMessage]] = {
    THEME: fix_theme(),
    DASH: fix_dashboard(),
    CARD: hand_off_card(),
}


class Recorder:
    """A Reviewer that answers from a list and records every payload it is shown."""

    def __init__(self, answers: list[str | None]):
        self.answers = list(answers)
        self.seen: list[ReviewPayload] = []

    def review(self, payload: ReviewPayload) -> ReviewAnswer | None:
        self.seen.append(payload)
        choice = self.answers.pop(0) if self.answers else "revert"
        return None if choice is None else ReviewAnswer.model_validate({"choice": choice})


def run(
    tmp_path: Path,
    spec: MigrationSpec,
    script: dict[str, list[AIMessage]],
    *,
    config: Configuration | None = None,
    reviewer: Any = None,
    mode: str = "eval",
    toolchain: FakeToolchain | None = None,
    max_run_usd: float | None = None,
    keep_workspace: bool = False,
    **options: Any,
) -> tuple[RunResult | PausedRun, ScriptedChatModel, FakeToolchain, FakeRunner]:
    repo = tmp_path / "repo"
    if not repo.exists():
        make_mini_repo(repo)
    toolchain = toolchain or FakeToolchain()
    runner = FakeRunner(toolchain)
    model = ScriptedChatModel(script=script)
    result = start_run(
        RunOptions.model_validate(
            {
                "repo": repo,
                "spec": spec,
                "run_dir": tmp_path / "run",
                "configuration": config or configuration(),
                "tools_cache": tmp_path / "cache",
                "run_id": "r1",
                "max_run_usd": max_run_usd,
                "mode": mode,
                "keep_workspace": keep_workspace,
                **options,
            }
        ),
        runner,
        model_factory=factory_for(model),
        reviewer=reviewer,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    return result, model, toolchain, runner


def card_of(result: RunResult | PausedRun) -> Any:
    assert isinstance(result, RunResult)
    return result.scorecard


def outcomes(card: Any) -> dict[str, str]:
    return {f.path: f.outcome for f in card.files}


def record_of(card: Any, path: str) -> FileRepairSummary:
    assert card.repair is not None
    record: FileRepairSummary = next(f for f in card.repair.files if f.path == path)
    return record


def conversation(result: RunResult, path: str) -> list[dict[str, Any]]:
    record = record_of(result.scorecard, path)
    assert record.conversation is not None
    messages: list[dict[str, Any]] = json.loads((result.run_dir / record.conversation).read_text())
    return messages


# --------------------------------------------------------------------------- wiring


def test_the_whole_run_repairs_hands_off_and_scores(tmp_path: Path, spec: MigrationSpec) -> None:
    result, model, toolchain, _ = run(tmp_path, spec, GOOD)
    card = card_of(result)
    assert card.status == "completed"
    assert outcomes(card) == {
        "src/App.tsx": "Migrated by rules",
        CARD: "Handed off",
        DASH: "Migrated by agent",
        USERS: "Migrated by rules",
        THEME: "Migrated by agent",
    }
    # Clean run: the only failure left is in the handed-off file.
    assert card.headline.clean_run
    assert [f.file for f in card.verify.failures] == [CARD]
    assert card.headline.hand_offs == 1 and card.repair.review_list == [CARD]
    assert card.headline.regressions == 0
    # Rules ran exactly once: each codemod once.
    assert toolchain.codemods == [
        "preset-safe",
        "variant-prop",
        "link-underline-hover",
        "box-sx-prop",
    ]
    # Files are repaired one at a time, shared modules (.ts) first.
    assert [r["file"] for r in model.requests] == [THEME, DASH, CARD]
    assert card.repair.attempts == 3 and card.repair.tool_calls == 6
    # The eval auto-answer is Revert, and the scorecard carries cost and the model.
    assert card.repair.files[2].review == "revert"
    assert card.cost.model_calls == 3 and card.cost.models == ["claude-opus-5-5"]


def test_narrow_verify_runs_only_the_related_tests(tmp_path: Path, spec: MigrationSpec) -> None:
    _, _, toolchain, _ = run(tmp_path, spec, GOOD)
    assert toolchain.related == [[THEME], [DASH]]


def test_one_conversation_per_file_and_it_is_append_only(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    script = {**GOOD, DASH: [ai(call("read_file", path=DASH)), *fix_dashboard()]}
    result, model, _, _ = run(tmp_path, spec, script)
    dash = [r["messages"] for r in model.requests if r["file"] == DASH]
    assert len(dash) == 2
    # The second request starts with exactly the first request's messages.
    first, second = dash
    assert [m.content for m in second[: len(first)]] == [m.content for m in first]
    # A new file starts a fresh conversation (system prompt + its own first message).
    card_requests = [r["messages"] for r in model.requests if r["file"] == CARD]
    assert isinstance(card_requests[0][1], HumanMessage) and len(card_requests[0]) == 2
    assert isinstance(result, RunResult)
    assert conversation(result, DASH)[0]["type"] == "human"


def test_the_system_prompt_is_identical_for_every_file(tmp_path: Path, spec: MigrationSpec) -> None:
    _, model, _, _ = run(tmp_path, spec, GOOD)
    systems = {json.dumps(r["messages"][0].content) for r in model.requests}
    assert len(systems) == 1
    block = model.requests[0]["messages"][0].content[0]
    assert block["cache_control"] == {"type": "ephemeral"}  # the explicit breakpoint


def test_repair_order_puts_imported_and_shared_modules_first() -> None:
    files = {
        "src/a.tsx": "import { b } from './b';\n",
        "src/b.tsx": "export const b = 1;\n",
        "src/theme.ts": "export const t = 1;\n",
    }
    assert repair_order(["src/a.tsx", "src/b.tsx", "src/theme.ts"], files) == [
        "src/theme.ts",
        "src/b.tsx",
        "src/a.tsx",
    ]


# --------------------------------------------------------------------------- review, resume


def test_pause_at_a_hand_off_and_resume_without_rerunning_rules(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    pauser = Recorder([None])
    paused, _, toolchain, runner = run(tmp_path, spec, GOOD, reviewer=pauser, mode="cli")
    assert isinstance(paused, PausedRun)
    assert paused.payload.path == CARD
    assert (tmp_path / "run" / "checkpoints.sqlite").is_file()
    record = json.loads((tmp_path / "run" / "run.json").read_text())
    assert record["status"] == "paused"
    commands_before = len(runner.commands)

    # A new process: rebuild everything from run.json and the SQLite checkpoint.
    done = resume_run(
        tmp_path / "run",
        reviewer=Recorder(["revert"]),
        runner=runner,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    card = card_of(done)
    assert outcomes(card)[CARD] == "Handed off"
    assert toolchain.codemods == [
        "preset-safe",
        "variant-prop",
        "link-underline-hover",
        "box-sx-prop",
    ]
    after = runner.commands[commands_before:]
    assert not any("v5.0.0/" in c for c in after)  # no codemod ran on resume
    assert not any(c.startswith("npm ci") for c in after)  # nor the Pre-check
    assert json.loads((tmp_path / "run" / "run.json").read_text())["status"] == "done"


def test_resume_runs_with_the_options_the_run_started_with(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    """Resume rebuilds RunOptions from run.json, so no option is lost on the way."""
    paused, _, _, runner = run(
        tmp_path, spec, GOOD, reviewer=Recorder([None]), mode="cli", incremental_typecheck=True
    )
    assert isinstance(paused, PausedRun)
    commands_before = len(runner.commands)
    resume_run(
        tmp_path / "run",
        reviewer=Recorder(["revert"]),
        runner=runner,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    typechecks = [c for c in runner.commands[commands_before:] if "typecheck" in c]
    assert typechecks and all("--incremental" in c for c in typechecks)


def test_every_run_option_survives_run_json(spec: MigrationSpec, tmp_path: Path) -> None:
    from migrator.pipeline import RunRecord, options_from_record, record_options

    opts = RunOptions(
        repo=tmp_path / "repo",
        spec=spec,
        run_dir=tmp_path / "run",
        traps=tmp_path / "traps.toml",
        keep_workspace=True,
        tools_cache=tmp_path / "cache",
        configuration=configuration(),
        ceiling_s=900.0,
        run_id="r1",
        max_run_usd=3.0,
        mode="cli",
        sandbox="docker",
        branch="migrate/x",
        precheck_cache=True,
        run_container=True,
        node_modules_volume=True,
        incremental_typecheck=True,
    )
    record = RunRecord(
        run_id="r1",
        thread_id="r1",
        repo=str(opts.repo),
        migration_from=spec.from_,
        migration_to=spec.to,
        case=None,
        traps=str(opts.traps),
        configuration=opts.configuration.model_dump(mode="json"),
        keep_workspace=True,
        tools_cache=str(opts.tools_cache),
        max_run_usd=3.0,
        mode="cli",
        options=record_options(opts),
    )
    back = RunRecord.model_validate_json(record.model_dump_json())
    assert options_from_record(back, opts.run_dir) == opts


def test_resume_refuses_a_workspace_changed_while_paused(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    paused, _, _, runner = run(tmp_path, spec, GOOD, reviewer=Recorder([None]), mode="cli")
    assert isinstance(paused, PausedRun)
    (Path(paused.payload.workspace) / CARD).write_text("// changed by hand\n")
    from migrator.pipeline import ChangedWorkspaceError

    with pytest.raises(ChangedWorkspaceError, match="ProfileCard"):
        resume_run(tmp_path / "run", reviewer=Recorder(["revert"]), runner=runner)
    done = resume_run(
        tmp_path / "run",
        reviewer=Recorder(["keep"]),
        runner=runner,
        accept_changes=True,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
    )
    card = card_of(done)
    assert CARD in card.repair.human_changed


def test_edit_at_review_makes_the_file_migrated_by_a_human(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    class Editor(Recorder):
        def review(self, payload: ReviewPayload) -> ReviewAnswer | None:
            utils = Path(payload.workspace) / "src/test-utils.tsx"
            utils.write_text(
                "import { ThemeProvider } from '@mui/material/styles';\n" + utils.read_text()
            )
            return ReviewAnswer(choice="edit")

    result, _, _, _ = run(tmp_path, spec, GOOD, reviewer=Editor([]), mode="cli")
    card = card_of(result)
    assert outcomes(card)[CARD] == "Migrated by human"
    assert card.headline.clean_run and card.verify.failures == []
    # The human's change to a Test file is reported as a note, never a hit.
    assert card.cheating.hits == []
    assert any(n.file == "src/test-utils.tsx" and n.layer == "human" for n in card.cheating.notes)


def test_a_failed_edit_asks_again(tmp_path: Path, spec: MigrationSpec) -> None:
    reviewer = Recorder(["edit", "revert"])  # the "edit" changes nothing, so it still fails
    result, _, _, _ = run(tmp_path, spec, GOOD, reviewer=reviewer, mode="cli")
    assert [p.path for p in reviewer.seen] == [CARD, CARD]
    assert outcomes(card_of(result))[CARD] == "Handed off"


# --------------------------------------------------------------------------- limits


def test_three_failed_attempts_hand_the_file_off(tmp_path: Path, spec: MigrationSpec) -> None:
    noop = [ai(call("run_verify", note=f"try {i}")) for i in range(1, 4)]
    result, model, _, _ = run(tmp_path, spec, {**GOOD, DASH: noop})
    card = card_of(result)
    record = next(f for f in card.repair.files if f.path == DASH)
    assert record.outcome == "Handed off" and "3 attempts used" in (record.reason or "")
    assert [a.result for a in record.attempts] == ["failed", "failed", "failed"]
    assert len([r for r in model.requests if r["file"] == DASH]) == 3


def test_the_model_is_chosen_per_attempt(tmp_path: Path, spec: MigrationSpec) -> None:
    noop = [ai(call("run_verify", note=f"try {i}")) for i in range(1, 4)]
    models = ["claude-haiku-5-5", "claude-haiku-5-5", "claude-opus-5-5"]
    result, _, _, _ = run(tmp_path, spec, {**GOOD, DASH: noop}, config=configuration(models))
    record = next(f for f in card_of(result).repair.files if f.path == DASH)
    assert [a.model for a in record.attempts] == models


def test_the_tool_call_budget_hands_the_file_off(tmp_path: Path, spec: MigrationSpec) -> None:
    reads = [ai(call("read_file", path=DASH)) for _ in range(20)]
    result, model, _, _ = run(tmp_path, spec, {**GOOD, DASH: reads})
    record = next(f for f in card_of(result).repair.files if f.path == DASH)
    assert record.outcome == "Handed off" and "tool-call budget" in (record.reason or "")
    assert record.attempts[0].tool_calls == 15
    assert len([r for r in model.requests if r["file"] == DASH]) == 15


def test_a_reply_without_a_tool_call_is_nudged_and_counted(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    script = {**GOOD, DASH: [ai(text="I think it's the spacing."), *fix_dashboard()]}
    result, model, _, _ = run(tmp_path, spec, script)
    dash = [r for r in model.requests if r["file"] == DASH]
    assert "run_verify" in dash[1]["messages"][-1].content  # the nudge
    record = next(f for f in card_of(result).repair.files if f.path == DASH)
    assert record.outcome == "Migrated by agent" and record.attempts[0].tool_calls == 4


def test_calls_after_the_attempt_ends_are_not_run(tmp_path: Path, spec: MigrationSpec) -> None:
    late = ai(
        call("hand_off", reason="giving up"),
        call("apply_edit", path=DASH, old_text="theme.spacing(1) * 3", new_text="x"),
    )
    result, _, _, _ = run(tmp_path, spec, {**GOOD, DASH: [late]})
    messages = conversation(result, DASH)  # type: ignore[arg-type]
    assert "Not run" in messages[-1]["data"]["content"]


def test_a_refusal_hands_the_file_off(tmp_path: Path, spec: MigrationSpec) -> None:
    refusal = ai(text="", stop_reason="refusal")
    result, _, _, _ = run(tmp_path, spec, {**GOOD, DASH: [refusal]})
    record = next(f for f in card_of(result).repair.files if f.path == DASH)
    assert record.outcome == "Handed off" and "refusal" in (record.reason or "")


# --------------------------------------------------------------------------- regressions


def _breaks_users_table() -> AIMessage:
    return ai(
        call("apply_edit", path=DASH, old_text="theme.spacing(1) * 3", new_text="theme.spacing(3)"),
        call(
            "apply_edit",
            path=DASH,
            old_text="): number => theme.spacing(4) + 24",
            new_text="): string => `calc(${theme.spacing(4)} + 24px)`",
        ),
        call("run_verify", note="spacing returns strings now"),
    )


def test_an_attempt_that_breaks_another_file_fails_and_says_which(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    second = ai(
        call(
            "apply_edit",
            path=DASH,
            old_text="): string => `calc(${theme.spacing(4)} + 24px)`",
            new_text="): number => parseFloat(theme.spacing(4)) + 24",
        ),
        call("run_verify", note="keep it a number"),
    )
    result, _, _, _ = run(tmp_path, spec, {**GOOD, DASH: [_breaks_users_table(), second]})
    assert isinstance(result, RunResult)
    messages = conversation(result, DASH)
    verdict = next(
        m["data"]["content"] for m in messages if "Result of attempt 1" in str(m["data"]["content"])
    )
    assert "Failures left in this file: **0**" in verdict
    assert "New failures in other files: **1**" in verdict
    assert f"`{USERS}` line 5" in verdict and "TS2322" in verdict
    assert "Attempt 2 of 3" in verdict
    record = record_of(result.scorecard, DASH)
    assert [a.result for a in record.attempts] == ["failed", "passed"]
    assert record.attempts[0].new_failures_elsewhere == 1
    assert result.scorecard.headline.regressions == 0


def test_a_kept_patch_that_breaks_a_clean_file_is_a_regression(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    script = {**GOOD, DASH: [_breaks_users_table()] * 3}
    result, _, _, _ = run(tmp_path, spec, script, reviewer=Recorder(["keep", "keep"]), mode="cli")
    card = card_of(result)
    assert card.regressions == [USERS]
    assert card.headline.regressions == 1
    users = next(f for f in card.files if f.path == USERS)
    assert users.outcome == "Unmigrated" and users.note.startswith("regression")
    assert not card.headline.clean_run


def test_revert_at_review_undoes_the_patch(tmp_path: Path, spec: MigrationSpec) -> None:
    script = {**GOOD, DASH: [_breaks_users_table()] * 3}
    result, _, _, _ = run(tmp_path, spec, script, keep_workspace=True)
    assert isinstance(result, RunResult) and result.workspace is not None
    assert "theme.spacing(1) * 3" in (result.workspace / DASH).read_text()  # Rules version
    assert result.scorecard.regressions == []


# --------------------------------------------------------------------------- cost cap


def test_a_cap_too_small_for_one_call_leaves_every_file_unmigrated(
    tmp_path: Path, spec: MigrationSpec
) -> None:
    result, model, _, _ = run(tmp_path, spec, GOOD, max_run_usd=0.05)
    card = card_of(result)
    assert model.requests == []  # nothing was sent
    assert card.cost.stopped_by_cap and card.cost.model_calls == 0
    assert card.repair.stopped_by_cost_cap
    for path in (THEME, DASH, CARD):
        assert outcomes(card)[path] == "Unmigrated"
    reasons = {f.path: f.reason for f in card.repair.files}
    assert reasons[THEME].startswith("cost cap:")
    assert reasons[DASH] == reasons[CARD] == "cost cap: not attempted"
    assert (tmp_path / "run" / "scorecard.md").is_file()  # there is always a scorecard


def test_the_cap_stops_repair_part_way(tmp_path: Path, spec: MigrationSpec) -> None:
    # Haiku: worst case per call ~ $0.008 + input. Make the first call expensive.
    pricey = [
        ai(
            call("apply_edit", path=THEME, old_text="label: {", new_text="root: {"),
            call("run_verify", note="root"),
            model="claude-haiku-5-5",
            input_tokens=90_000,
            output_tokens=40_000,
        )
    ]
    config = configuration(["claude-haiku-5-5"] * 3)
    result, model, _, _ = run(
        tmp_path, spec, {**GOOD, THEME: pricey}, config=config, max_run_usd=0.035
    )
    card = card_of(result)
    assert [r["file"] for r in model.requests] == [THEME]
    assert outcomes(card)[THEME] == "Migrated by agent"
    assert outcomes(card)[DASH] == "Unmigrated" and outcomes(card)[CARD] == "Unmigrated"
    assert card.cost.total_usd <= 0.035 and card.cost.stopped_by_cap


def test_the_month_cap_counts_the_ledger(tmp_path: Path, spec: MigrationSpec) -> None:
    from migrator.cost import LedgerRow, Usage, now_utc

    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append(
        LedgerRow(
            at=now_utc(),
            run_id="earlier",
            model="claude-opus-5-5",
            requested_model="claude-opus-5-5",
            usage=Usage(),
            cost_usd=19.9,
        )
    )
    result, model, _, _ = run(tmp_path, spec, GOOD)
    card = card_of(result)
    assert model.requests == []
    assert "month" in (card.repair.cost_cap_reason or "")


def test_every_call_is_in_the_ledger(tmp_path: Path, spec: MigrationSpec) -> None:
    result, _, _, _ = run(tmp_path, spec, GOOD)
    rows = Ledger(tmp_path / "ledger.jsonl").rows()
    card = card_of(result)
    assert len(rows) == card.cost.model_calls == 3
    assert {(r.file, r.attempt) for r in rows} == {(THEME, 1), (DASH, 1), (CARD, 1)}
    assert round(sum(r.cost_usd for r in rows), 6) == card.cost.total_usd
    assert card.cost.month_spent_usd == round(sum(r.cost_usd for r in rows), 6)


def test_tool_results_are_returned_for_every_call(tmp_path: Path, spec: MigrationSpec) -> None:
    _, model, _, _ = run(tmp_path, spec, GOOD)
    for request in model.requests:
        messages = request["messages"]
        for i, m in enumerate(messages):
            if isinstance(m, AIMessage) and m.tool_calls:
                answered = {t.tool_call_id for t in messages[i + 1 :] if isinstance(t, ToolMessage)}
                assert {c["id"] for c in m.tool_calls} <= answered


# --------------------------------------------------------------------------- hand-off isolation

BROKEN = "export function Dashboard() {\n  return <Paper>;\n}"  # unclosed JSX


def _shell_toolchain() -> FakeToolchain:
    """ProfileCard's suite loads Dashboard through the app shell (test-utils -> App), so a
    syntax error in Dashboard makes it fail to load, as Search broke Settings in the
    first Haiku run. ProfileCard's own fix is a typed makeStyles callback."""
    from tests.fakes import TEST_RULES, TestRule

    def card_failing(ws: Path) -> bool:
        dash_broken = "<Paper>;" in (ws / DASH).read_text()
        text = (ws / CARD).read_text()
        untyped = "makeStyles((theme) =>" in text
        return "@mui/" in text and (dash_broken or untyped)  # passes on v4 (Pre-check)

    card = TestRule(
        "src/screens/__tests__/ProfileCard.test.tsx",
        "shows the card",
        CARD,
        card_failing,
        "SyntaxError: Unexpected token (suite failed to load)",
        deps=["src/test-utils.tsx", "src/App.tsx", DASH],
    )
    return FakeToolchain(test_rules=[card, *TEST_RULES[1:]])


def _break_and_hand_off() -> list[AIMessage]:
    return [
        ai(
            call(
                "apply_edit",
                path=DASH,
                old_text="export function Dashboard() {\n  return <Paper />;\n}",
                new_text=BROKEN,
            ),
            call("hand_off", reason="not sure how spacing works now"),
        )
    ]


def _fix_card() -> list[AIMessage]:
    return [
        ai(
            call(
                "apply_edit",
                path=CARD,
                old_text="makeStyles((theme) =>",
                new_text="makeStyles((theme: Theme) =>",
            ),
            call("run_verify", note="type the theme"),
        )
    ]


def test_a_handed_off_patch_is_set_aside_until_review(tmp_path: Path, spec: MigrationSpec) -> None:
    script = {THEME: fix_theme(), DASH: _break_and_hand_off(), CARD: _fix_card()}
    result, model, _, _ = run(
        tmp_path, spec, script, toolchain=_shell_toolchain(), keep_workspace=True
    )
    card = card_of(result)
    # ProfileCard was repaired in a workspace without Dashboard's broken patch.
    assert outcomes(card)[CARD] == "Migrated by agent"
    assert record_of(card, CARD).attempts[0].result == "passed"
    assert [r["file"] for r in model.requests].count(CARD) == 1
    assert outcomes(card)[DASH] == "Handed off"
    assert isinstance(result, RunResult) and result.workspace is not None
    assert BROKEN not in (result.workspace / DASH).read_text()  # the eval reverted it


def test_keep_at_review_puts_the_set_aside_patch_back(tmp_path: Path, spec: MigrationSpec) -> None:
    script = {THEME: fix_theme(), DASH: _break_and_hand_off(), CARD: _fix_card()}
    reviewer = Recorder(["keep"])
    result, _, _, _ = run(
        tmp_path,
        spec,
        script,
        toolchain=_shell_toolchain(),
        reviewer=reviewer,
        mode="cli",
        keep_workspace=True,
    )
    assert "<Paper>;" in reviewer.seen[0].diff  # the human sees the agent's patch
    assert isinstance(result, RunResult) and result.workspace is not None
    assert BROKEN in (result.workspace / DASH).read_text()
    card = result.scorecard
    # Kept, the broken patch fails ProfileCard's suite again at the final verify. It is
    # not a Regression (ProfileCard failed after Rules too), but it is not migrated.
    users = next(f for f in card.files if f.path == CARD)
    assert users.outcome == "Unmigrated" and "final verify" in users.note
