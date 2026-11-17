"""M7: the Migrator's own final snapshot update can rewrite an inline snapshot inside a
test file (``toMatchInlineSnapshot``). That rewrite is not the agent's test edit; an
edit the agent made to the same file is."""

from __future__ import annotations

from migrator.checks import CheckInput, FileSet, run_checks
from migrator.run.stages.verify import without_inline_rewrites

TEST = "src/pages/RunDetails.test.tsx"
CODE = "src/pages/RunDetails.tsx"
OLD_SNAPSHOT = "it('renders', () => expect(x).toMatchInlineSnapshot(`<div class=\"jss1\" />`))\n"
NEW_SNAPSHOT = OLD_SNAPSHOT.replace("jss1", "css-1x2y")
UPDATES = [{"test_file": TEST, "snapshot_file": None, "tests": ["renders"], "stage": "final"}]


def hits(after_rules: FileSet, before_update: FileSet, final: FileSet) -> list[str]:
    checked = without_inline_rewrites(final, before_update, UPDATES)
    report = run_checks(CheckInput(before=after_rules, after_rules=after_rules, final=checked))
    return [f"{h.check}:{h.file}" for h in report.hits]


def test_the_migrators_inline_snapshot_rewrite_is_not_a_test_edit() -> None:
    after_rules = {TEST: OLD_SNAPSHOT, CODE: "export const A = 1\n"}
    before_update = {**after_rules, CODE: "export const A = 2\n"}  # the agent fixed the code
    final = {**before_update, TEST: NEW_SNAPSHOT}  # then the Migrator ran vitest -u
    assert hits(after_rules, before_update, final) == []
    # without the exclusion, the same run fails the check
    report = run_checks(CheckInput(before=after_rules, after_rules=after_rules, final=final))
    assert [h.check for h in report.hits] == ["test-file-changed"]


def test_an_agent_edit_to_the_test_file_still_fails_the_check() -> None:
    after_rules = {TEST: OLD_SNAPSHOT}
    edited = OLD_SNAPSHOT + "it('extra', () => { expect(1).toBe(1) })\n"
    before_update = {TEST: edited}  # the agent edited the test
    final = {TEST: edited.replace("jss1", "css-1x2y")}  # then the snapshot update
    assert hits(after_rules, before_update, final) == [f"test-file-changed:{TEST}"]


def test_without_a_snapshot_update_the_final_files_are_checked_as_they_are() -> None:
    final = {TEST: NEW_SNAPSHOT}
    assert without_inline_rewrites(final, None, UPDATES) is final
    assert without_inline_rewrites(final, {TEST: OLD_SNAPSHOT}, []) == final
