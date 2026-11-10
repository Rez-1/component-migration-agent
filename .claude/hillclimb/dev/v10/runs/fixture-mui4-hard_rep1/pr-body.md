Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-020103-b23`, configuration `haiku-advisor-opus`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: yes.** **10 of 12 affected files migrated without a human (83%)**: 4 by rules, 6 by the repair agent, 0 by a human at Review. 2 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 10 / 12 (83%) |
| Hand-offs | 2 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 11 expected · 0 other layer · 4 missed · 0 not scored |
| Cost / time | $0.02 · 5 min 21 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/IssueDetail.tsx`: tool-call budget used: 15 calls in attempt 1 without passing run_verify
  - test IssueDetail › adds a label and says so: TestingLibraryElementError: Unable to find an accessible element with the role "alert"
  - test IssueDetail › removes a label with Backspace, and Undo brings it back: TestingLibraryElementError: Unable to find an accessible element with the role "alert"
  - test IssueDetail › puts the cursor in the comment box once the dialog is open: Error: expect(element).toHaveFocus()
- [ ] `src/screens/NewIssueDialog.tsx`: patch over the size limit: src/components/DurationInput.tsx would change 16 lines (48% of the file)
  - test NewIssueDialog › assigns new issues to the signed-in user, marked in the list: Error: expect(element).toHaveAttribute("aria-selected", "true") // element.getAttribute("aria-selected") === "true"
  - test NewIssueDialog › creates the issue with a tidied estimate: Error: expect(jest.fn()).toHaveBeenCalledWith(...expected)

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.02 = $0.01 output + $0.00 input + $0.01 cache (reads $0.00, writes $0.01), claude-haiku-5-5, 35 calls. Cache reads covered 79% of input tokens. Run cap $2.74; month cap $20.00, this month $5.11 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
