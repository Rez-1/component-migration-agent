"""M6: real-repo cases, the worst-case reservation, coverage, snapshots, reference scoring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrator.config import CaseConfig, load_case
from migrator.configuration import find_configuration
from migrator.evals.reference import (
    ItemScore,
    JudgeCache,
    Judgement,
    ReferenceScore,
    judge_key,
    load_overrides,
    normalise,
    render_reference_score,
    select_items,
)
from migrator.graph import snapshot_belongs
from migrator.rules import apply_extra_dependencies
from migrator.verify import (
    Failure,
    VerifyResult,
    is_snapshot_failure,
    read_coverage,
    snapshot_only_test_files,
)
from tests.conftest import REPO_ROOT

CONFIGS = REPO_ROOT / "evals" / "configs"


def test_older_configuration_digests_are_unchanged() -> None:
    # The M6 cost field is left out of the digest while unset (M2-M5 results stay attached).
    assert (
        find_configuration("opus-low", CONFIGS).digest() == "d81d48a907d0"
    )  # as recorded in .claude/hillclimb/dev/v3
    m6 = find_configuration("m6-opus-low", CONFIGS)
    assert (m6.cost.max_run_usd, m6.cost.max_month_usd, m6.cost.reserve_attempt_usd) == (
        8.0,
        50.0,
        0.15,
    )
    assert m6.repair == find_configuration("opus-low", CONFIGS).repair


def test_real_repo_cases_load_with_an_upstream() -> None:
    case = load_case(REPO_ROOT / "evals" / "m6-cases" / "opossum-ui" / "case.toml")
    assert case.upstream is not None and case.source == ""
    assert case.repo.node == "16" and case.repo.coverage and case.repo.update_snapshots
    with pytest.raises(ValueError, match="either a fixture"):
        CaseConfig.model_validate(
            {"id": "x", "migration": "m", "split": "dev", "runner": "jest", "reference": "none"}
        )


def test_extra_dependencies_set_and_remove() -> None:
    package: dict[str, object] = {
        "dependencies": {"@devexpress/dx-react-grid": "^2.7.0", "@material-ui/pickers": "3"},
        "devDependencies": {"jest": "27"},
    }
    notes = apply_extra_dependencies(
        package, {"@devexpress/dx-react-grid": "3.0.0", "@material-ui/pickers": "", "x": "1"}
    )
    assert package["dependencies"] == {"@devexpress/dx-react-grid": "3.0.0", "x": "1"}
    assert len(notes) == 3


def test_coverage_labels(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    summary = {
        "total": {},
        str(ws / "src/A.tsx"): {"functions": {"total": 2, "covered": 1}, "lines": {}},
        str(ws / "src/B.tsx"): {"functions": {"total": 3, "covered": 0}, "lines": {"covered": 4}},
        str(ws / "src/c.ts"): {"functions": {"total": 0}, "lines": {"covered": 2}},
    }
    (tmp_path / "cov").mkdir()
    (tmp_path / "cov" / "coverage-summary.json").write_text(json.dumps(summary))
    assert read_coverage(tmp_path / "cov", ws) == {
        "src/A.tsx": True,
        "src/B.tsx": False,
        "src/c.ts": True,
    }


def _test_failure(test_file: str, message: str) -> Failure:
    return Failure(source="test", file="src/X.tsx", message=message, test_file=test_file)


def test_snapshot_only_test_files() -> None:
    snap = "expect(received).toMatchSnapshot()"
    result = VerifyResult(
        commands=[],
        failures=[
            _test_failure("src/a.test.tsx", snap),
            _test_failure("src/b.test.tsx", snap),
            _test_failure("src/b.test.tsx", "expect(element).toBeVisible()"),
            _test_failure("src/c.test.tsx", "Snapshot `C > renders 1` mismatched"),
            _test_failure("src/d.test.tsx", "expect(x).toMatchInlineSnapshot()"),
        ],
    )
    assert snapshot_only_test_files(result) == ["src/a.test.tsx", "src/c.test.tsx"]
    assert not is_snapshot_failure(Failure(source="lint", file="a", message=snap))
    assert snapshot_belongs("src/__snapshots__/a.test.tsx.snap", "src/a.test.tsx")
    assert not snapshot_belongs("src/x/__snapshots__/a.test.tsx.snap", "src/a.test.tsx")


def test_reference_items_and_normalising() -> None:
    assert normalise('import { a, } from "x";\n') == normalise("import { a } from 'x'\n")
    base = {
        "src/A.tsx": "import B from '@material-ui/core/Button';\n",
        "src/fmt.tsx": "import B from '@material-ui/core/Button';\n",
        "src/util.ts": "export const x = 1;\n",
        "src/A.test.tsx": "import A from './A';\n",
    }
    ref = {
        "src/A.tsx": "import B from '@mui/material/Button';\n",
        "src/fmt.tsx": 'import B from "@material-ui/core/Button"\n',
        "src/util.ts": "export const x = 2;\n",
        "src/A.test.tsx": "import A from './A'; // v5\n",
        "yarn.lock": "",
    }
    changes = dict.fromkeys(ref, "M")
    sel = select_items(changes, base, ref.get, {"src/A.test.tsx"})
    assert sel.items == ["src/A.tsx"]
    assert sel.formatting_only == ["src/fmt.tsx"]
    assert sel.test_files == ["src/A.test.tsx"]
    assert sel.other == ["src/util.ts", "yarn.lock"]


def test_judge_cache_round_trip(tmp_path: Path) -> None:
    cache = JudgeCache(tmp_path)
    key = judge_key("a.tsx", "old", "ref", "new")
    assert key != judge_key("a.tsx", "old", "ref", "other") and cache.get(key) is None
    cache.put(key, Judgement(verdict="wrong", reason="r", out_of_scope_changes=[]), "prompt")
    got = cache.get(key)
    assert got is not None and got.verdict == "wrong"


def test_a_suite_that_cannot_load_keeps_its_real_error() -> None:
    from migrator.verify.parsers import suite_message

    text = (
        "  ● Test suite failed to run\n\n    Jest encountered an unexpected token\n\n"
        "    This usually means that you are trying to import a file which Jest cannot parse\n\n"
        "    Details:\n\n    node_modules/@mui/material/Typography/Typography.js:3\n"
        "    import _x from '@babel/runtime/helpers/esm/x';\n    ^^^^^^\n\n"
        "    SyntaxError: Cannot use import statement outside a module\n\n"
        "      at Runtime.createScriptFromCode (node_modules/jest-runtime/build/index.js:1:2)\n"
        "      at Object.<anonymous> (src/List.tsx:7:1)\n"
    )
    message = suite_message(text)
    assert message.startswith("Test suite failed to run: node_modules/@mui/material/Typography")
    assert "SyntaxError: Cannot use import statement" in message
    assert message.endswith("at src/List.tsx:7:1")
    assert suite_message("● Test suite failed to run") == "Test suite failed to run"


def _totals(tests: int) -> object:
    from migrator.verify.parsers import TestTotals

    return TestTotals(
        suites_total=10, suites_failed=0, tests_total=tests, tests_passed=tests,
        tests_failed=0, tests_skipped=0, snapshots_total=0, snapshots_unmatched=0,
        snapshots_updated=0, snapshots_added=0, snapshots_obsolete=0,
        snapshot_files_removed=0,
    )  # fmt: skip


def test_tests_lost_after_rules_are_not_charged_to_the_agent() -> None:
    from migrator.checks import _totals_findings

    pre, after_rules = _totals(587), _totals(506)
    same = _totals_findings(pre, _totals(506), "agent", after_rules)  # type: ignore[arg-type]
    assert [(f.layer, f.detail) for f in same] == [
        ("rules", "tests run: 587 at the Pre-check -> 506 (already 506 after Rules)")
    ]
    worse = _totals_findings(pre, _totals(480), "agent", after_rules)  # type: ignore[arg-type]
    assert [f.layer for f in worse] == ["agent"]
    no_rules = _totals_findings(pre, _totals(506), "agent")  # type: ignore[arg-type]
    assert [f.layer for f in no_rules] == ["agent"]


def test_a_vitest_coverage_include_is_not_a_test_glob(tmp_path: Path) -> None:
    from migrator.checks import read_test_rules

    (tmp_path / "vitest.config.mts").write_text(
        "export default defineConfig({ test: { setupFiles: ['src/vitest.setup.ts'],\n"
        "  include: ['src/**/*.{test,spec}.{ts,tsx}'],\n"
        "  coverage: { provider: 'v8', include: ['src/**/*.{ts,tsx,js,jsx}'],\n"
        "    exclude: ['src/apis/**'] } } });\n"
    )
    rules = read_test_rules(tmp_path)
    assert rules.test_globs == ["src/**/*.{test,spec}.{ts,tsx}"]
    assert "src/vitest.setup.ts" in rules.setup_files


def test_coverage_from_a_vitest_report_without_a_summary(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    report = tmp_path / "precheck-vitest.json"
    report.write_text(
        json.dumps(
            {
                "coverageMap": {
                    str(ws / "src/A.tsx"): {"path": str(ws / "src/A.tsx"), "f": {"0": 2}, "s": {}},
                    str(ws / "src/B.tsx"): {
                        "path": str(ws / "src/B.tsx"),
                        "f": {"0": 0},
                        "s": {"0": 1},
                    },
                    str(ws / "src/c.ts"): {"path": str(ws / "src/c.ts"), "f": {}, "s": {"0": 1}},
                }
            }
        )
    )
    assert read_coverage(tmp_path / "missing", ws, report) == {
        "src/A.tsx": True,
        "src/B.tsx": False,
        "src/c.ts": True,
    }


def test_a_shared_cause_groups_one_error_on_one_wrapper() -> None:
    from migrator.repair.shared import find_shared_causes, shared_cause_section

    wrapper = "export function IconButton(props: { title: string }) { return null; }\n"
    caller = (
        "import { IconButton } from '../IconButton/IconButton';\n"
        "export const X = () => (\n  <IconButton\n    title='a'\n    size=\"large\"\n  />\n);\n"
    )
    files = {"src/IconButton/IconButton.tsx": wrapper}
    failures = []
    for name in ("A", "B", "C"):
        files[f"src/{name}/{name}.tsx"] = caller
        failures.append(
            Failure(source="typecheck", file=f"src/{name}/{name}.tsx", line=5, column=5,
                    code="TS2322", message="Type '{ size: string; }' is not assignable")
        )  # fmt: skip
    causes = find_shared_causes(failures, files, {})
    assert [(c.source, c.symbol, len(c.callers)) for c in causes] == [
        ("src/IconButton/IconButton.tsx", "IconButton", 3)
    ]
    assert find_shared_causes(failures[:2], files, {}) == []  # two callers are not enough
    assert "appears in 3 files" in shared_cause_section(causes[0], "src/IconButton/IconButton.tsx")
    assert "2 other files" in shared_cause_section(causes[0], "src/A/A.tsx")


def test_repeated_edits_flag_a_line_added_to_three_files() -> None:
    from migrator.report import repeated_edits

    after = {f"src/{n}.tsx": "<IconButton\n/>\n" for n in "ABCD"}
    final = {p: '<IconButton\n  size="medium"\n/>\n' for p in after}
    flags = repeated_edits(
        after, final, dict.fromkeys(["src/A.tsx", "src/B.tsx", "src/C.tsx"], "agent")
    )
    assert [(f.line, len(f.files)) for f in flags] == [('+ size="medium"', 3)]
    assert repeated_edits(after, final, {"src/A.tsx": "agent", "src/B.tsx": "rules"}) == []


def test_m6_v2_configuration_turns_both_changes_on() -> None:
    v2 = find_configuration("m6-opus-low-v2", CONFIGS)
    assert v2.repair.shared_causes and v2.repair.prompt_version == "v3"
    assert v2.digest() != find_configuration("m6-opus-low", CONFIGS).digest()


ICON_BUTTON_AFTER_RULES = """      <MuiTooltip
        classes={{ tooltip: classes.tooltip }}
        title={props.tooltipTitle}
        placement={props.placement}
      >
"""
# OpossumUI run v3 rep0: Opus added describeChild so a v4 `title` test would pass.
ICON_BUTTON_FINAL = ICON_BUTTON_AFTER_RULES.replace(
    "        placement=", "        describeChild\n        placement="
)


def test_the_opossum_describe_child_edit_is_flagged_as_possible_test_fitting() -> None:
    from migrator.report import test_fitting_flags

    path = "src/Frontend/Components/IconButton/IconButton.tsx"
    flags = test_fitting_flags(
        {path: ICON_BUTTON_AFTER_RULES}, {path: ICON_BUTTON_FINAL}, [(path, [path])], {path}
    )
    assert [(f.file, f.lines) for f in flags] == [(path, ["+ describeChild"])]
    # The same edit for a file whose failures were not tests is not flagged.
    assert (
        test_fitting_flags(
            {path: ICON_BUTTON_AFTER_RULES}, {path: ICON_BUTTON_FINAL}, [(path, [path])], set()
        )
        == []
    )


def test_test_fitting_flags_aria_props_and_a_changed_element_but_not_other_edits() -> None:
    from migrator.report import test_fitting_flags

    old = "<Button onClick={go}>\n  Go\n</Button>\n"
    flags = test_fitting_flags(
        {"a.tsx": old, "b.tsx": old, "c.tsx": old},
        {
            "a.tsx": old.replace("onClick={go}", 'onClick={go} aria-disabled="false"'),
            "b.tsx": old.replace("<Button", "<MenuItem").replace("</Button>", "</MenuItem>"),
            "c.tsx": old.replace("onClick={go}", "onClick={run}"),
        },
        [("a.tsx", ["a.tsx"]), ("b.tsx", ["b.tsx"]), ("c.tsx", ["c.tsx"])],
        {"a.tsx", "b.tsx", "c.tsx"},
    )
    assert [f.file for f in flags] == ["a.tsx", "b.tsx"]


FP_BEFORE = """import MuiIconButton from '@material-ui/core/IconButton';
import { IconButton } from '../IconButton/IconButton';
import OpenIcon from '@material-ui/icons/OpenInNew';

export const Row = () => (
  <div>
    <MuiIconButton onClick={go}>
      <OpenIcon />
    </MuiIconButton>
    <IconButton tooltipTitle="open" icon={<OpenIcon className="x" />} />
  </div>
);
"""
# What preset-safe writes: size="large" on every element named like an IconButton.
FP_AFTER = (
    FP_BEFORE.replace("@material-ui/core/IconButton", "@mui/material/IconButton")
    .replace("@material-ui/icons/OpenInNew", "@mui/icons-material/OpenInNew")
    .replace("<MuiIconButton onClick={go}>", '<MuiIconButton onClick={go} size="large">')
    .replace(
        'icon={<OpenIcon className="x" />} />', 'icon={<OpenIcon className="x" />} size="large" />'
    )
)


def test_only_the_repos_own_wrapper_has_the_codemod_change_undone() -> None:
    from migrator.false_positives import revert_false_positives
    from migrator.migrations import find_spec

    usage = find_spec("mui@4", "mui@5").usage
    text, found = revert_false_positives(
        "src/Row.tsx", FP_BEFORE, FP_AFTER, lambda m: usage.is_old(m) or usage.is_new(m), []
    )
    assert [(f.element, f.imported_from) for f in found] == [
        ("IconButton", "../IconButton/IconButton")
    ]
    assert '<MuiIconButton onClick={go} size="large">' in text  # MUI's own keeps the change
    assert '<IconButton tooltipTitle="open" icon={<OpenIcon className="x" />} />' in text
    assert "@mui/material/IconButton" in text  # import rewrites are untouched


def test_an_installed_package_and_an_unchanged_file_are_left_alone() -> None:
    from migrator.false_positives import revert_false_positives

    before = (
        "import { Grid } from '@devexpress/dx-react-grid-material-ui';\n"
        "const g = <Grid rows={r} />;\n"
    )
    after = before.replace("rows={r}", 'rows={r} size="large"')
    lib = lambda m: m.startswith(("@material-ui/", "@mui/"))  # noqa: E731
    assert (
        revert_false_positives(
            "a.tsx", before, after, lib, ["@devexpress/dx-react-grid-material-ui"]
        )[1]
        == []
    )
    assert revert_false_positives("a.tsx", before, before, lib, [])[1] == []


TOPBAR_AFTER_RULES = """      <IconButton
        tooltipTitle="open file"
        icon={
          <FolderOpenIcon
            className={classes.openFileIcon}
            aria-label={'open file'}
          />
        }
      />
"""
# OpossumUI run v10 rep1: the agent dropped the icon's aria-label so a test that found
# two elements labelled "open file" (v5's Tooltip labels the button too) would pass.
TOPBAR_FINAL = """      <IconButton
        tooltipTitle="open file"
        icon={<FolderOpenIcon className={classes.openFileIcon} />}
      />
"""


def _test_failure_in(path: str) -> Failure:
    return Failure(source="test", file=path, message="TestingLibraryElementError", test_file="t")


def test_a_flagged_passing_patch_becomes_a_test_fitting_hand_off() -> None:
    from migrator.graph import test_fitting_reason

    icon = "src/Frontend/Components/IconButton/IconButton.tsx"
    why = test_fitting_reason(
        icon, [icon], {icon: ICON_BUTTON_AFTER_RULES}, {icon: ICON_BUTTON_FINAL},
        [_test_failure_in(icon)],
    )  # fmt: skip
    assert why == f"possible test-fitting: {icon}: + describeChild"
    top = "src/Frontend/Components/TopBar/TopBar.tsx"
    why = test_fitting_reason(
        top, [top], {top: TOPBAR_AFTER_RULES}, {top: TOPBAR_FINAL}, [_test_failure_in(top)]
    )
    assert why is not None and "- aria-label={'open file'}" in why
    # A file whose failures were type errors only: the same edit is not test-fitting.
    type_error = Failure(source="typecheck", file=top, message="TS2322", code="TS2322")
    assert (
        test_fitting_reason(
            top, [top], {top: TOPBAR_AFTER_RULES}, {top: TOPBAR_FINAL}, [type_error]
        )
        is None
    )


def test_m6_v3_configuration_adds_test_fitting_hand_offs() -> None:
    v3 = find_configuration("m6-opus-low-v3", CONFIGS)
    v2 = find_configuration("m6-opus-low-v2", CONFIGS)
    assert v3.repair.test_fitting_hand_off and not v2.repair.test_fitting_hand_off
    assert v3.repair.model_copy(update={"test_fitting_hand_off": False}) == v2.repair


def test_a_base_url_import_makes_a_component_a_source_file_not_a_test_file() -> None:
    from migrator.checks import TestFileRules, find_test_files, resolve_import

    files = {
        "src/components/SidePanel.tsx": "export default () => null;\n",
        "src/components/SidePanel.test.tsx": "import SidePanel from './SidePanel';\n",
        "src/pages/RunDetails.tsx": "import SidePanel from 'src/components/SidePanel';\n",
    }
    assert resolve_import("src/pages/RunDetails.tsx", "src/components/SidePanel", files) == (
        "src/components/SidePanel.tsx"
    )
    assert resolve_import("src/a.tsx", "react", files) is None
    assert resolve_import("src/a.tsx", "@mui/material/Button", files) is None
    assert resolve_import("src/a.tsx", "components/SidePanel", files) == (
        "src/components/SidePanel.tsx"  # CRA's baseUrl "src"
    )
    tests = find_test_files(files, set(files), TestFileRules())
    assert "src/components/SidePanel.tsx" not in tests  # kubeflow: was "imported only by tests"
    assert "src/components/SidePanel.test.tsx" in tests


class _FakeStructured:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.seen: list[object] = []

    def with_structured_output(self, schema: type, **kw: object) -> _FakeStructured:
        assert kw.get("method") == "json_schema" and kw.get("include_raw") is True
        self.schema = schema
        return self

    def invoke(self, messages: object, config: object = None) -> dict[str, object]:
        from langchain_core.messages import AIMessage

        self.seen.append(messages)
        raw = AIMessage(
            content="{}",
            usage_metadata={"input_tokens": 3000, "output_tokens": 100, "total_tokens": 3100},
            response_metadata={"model_name": "claude-sonnet-5-5"},
        )
        return {
            "raw": raw,
            "parsed": self.schema(verdict=self.verdict, reason="r"),
            "parsing_error": None,
        }


def test_the_reviewer_is_one_capped_ledgered_call_on_another_model(tmp_path: Path) -> None:
    from migrator.cost import CostCapError, CostGuard, Ledger
    from migrator.repair.reviewer import review_patch

    ledger = Ledger(tmp_path / "ledger.jsonl")
    fake = _FakeStructured("fits_old_test")
    review = review_patch(
        "prompt", model="claude-sonnet-5-5", guard=CostGuard(2.0, 50.0, ledger), ledger=ledger,
        run_id="r1", case="c", path="src/A.tsx", run_spent_usd=0.0,
        factory=lambda m, e, t: fake,  # type: ignore[arg-type,return-value]
    )  # fmt: skip
    assert (review.verdict, review.model) == ("fits_old_test", "claude-sonnet-5-5")
    rows = ledger.rows()
    assert len(rows) == 1 and rows[0].file == "review src/A.tsx" and rows[0].cost_usd > 0
    assert review.call.cost_usd == rows[0].cost_usd
    with pytest.raises(CostCapError):  # the guard runs before the call, as for repair
        review_patch(
            "prompt", model="claude-sonnet-5-5", guard=CostGuard(2.0, 50.0, ledger),
            ledger=ledger, run_id="r1", case="c", path="src/A.tsx", run_spent_usd=1.999,
            factory=lambda m, e, t: fake,  # type: ignore[arg-type,return-value]
        )  # fmt: skip


def test_m6_v4_adds_a_sonnet_reviewer_and_a_two_dollar_stop() -> None:
    v4 = find_configuration("m6-opus-low-v4", CONFIGS)
    v3 = find_configuration("m6-opus-low-v3", CONFIGS)
    assert v4.repair.reviewer_model == "claude-sonnet-5-5"
    assert v4.repair.reviewer_model not in v4.repair.attempt_models
    assert v4.cost.stop_run_usd == 2.0 and v4.cost.max_run_usd == 8.0
    assert v4.repair.model_copy(update={"reviewer_model": None}) == v3.repair


def test_a_path_next_to_the_workspace_reads_the_same_in_every_run() -> None:
    from migrator.verify.parsers import clean

    def name(run: str) -> str:
        ws = f"/private/var/folders/mw/x/T/migrator-{run}/workspace"
        return clean(f"in sync with /private/var/folders/mw/x/T/migrator-{run}/backend/c.json", ws)

    assert (
        name("2026-11-10-1-aaa-x1")
        == name("2026-11-10-2-bbb-y2")
        == "in sync with ../backend/c.json"
    )


def test_a_test_is_charged_to_its_component_as_spelled_on_disk(tmp_path: Path) -> None:
    from migrator.verify import real_path
    from migrator.verify.parsers import subject_file

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Month.tsx").write_text("x")
    (tmp_path / "src" / "month.test.tsx").write_text("x")
    assert real_path(tmp_path, "src/month.tsx") == "src/Month.tsx"
    assert real_path(tmp_path, "src/Month.tsx") == "src/Month.tsx"
    assert real_path(tmp_path, "src/Week.tsx") is None
    # wps: month.test.tsx's failures belong to Month.tsx, the path every file list has.
    assert subject_file("src/month.test.tsx", lambda p: real_path(tmp_path, p)) == "src/Month.tsx"


def test_the_wps_override_is_recorded_and_applies_only_to_its_fix() -> None:
    case = load_case(REPO_ROOT / "evals" / "m6-cases" / "bcgov-wps" / "case.toml")
    (rule,) = load_overrides(case)
    assert rule.verdict == "other valid fix" and rule.decided_by and rule.date and rule.reason
    fixed = "makeStyles(styles, { defaultTheme: createTheme() })"
    assert rule.applies(rule.path, fixed)
    assert not rule.applies(rule.path, "makeStyles(styles)")
    assert not rule.applies("src/other.tsx", fixed)
    assert not rule.applies(rule.path, None)


def test_a_rendered_score_shows_overrides_and_the_judges_own_count() -> None:
    item = ItemScore(
        path="src/Day.tsx",
        verdict="other valid fix",
        by="override",
        judge_verdict="wrong",
        reason="override (the owner, 2026-11-11): same fix as elsewhere",
        outcome="migrated",
        final_failures=0,
        handed_off=False,
        silent_miss=False,
        covered=None,
    )
    score = ReferenceScore(
        case="c",
        run_id="r",
        configuration="cfg",
        reference_pr="https://example.test/pr/1",
        items=[item],
        counts={"other valid fix": 1},
        silent_misses=0,
        judge_silent_misses=1,
        test_files_changed=[],
        formatting_only=[],
        other_files_changed=[],
        judge_calls=0,
        judge_cost_usd=0.0,
    )
    text = render_reference_score(score)
    assert "(1 by the judge alone, before the recorded overrides)" in text
    assert "`src/Day.tsx`: judge said wrong, scored other valid fix" in text
