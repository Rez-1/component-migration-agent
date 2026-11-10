Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-005034-abb`, configuration `cascade-haiku-opus`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: yes.** **11 of 12 affected files migrated without a human (92%)**: 3 by rules, 8 by the repair agent, 0 by a human at Review. 1 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 11 / 12 (92%) |
| Hand-offs | 1 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 13 expected · 0 other layer · 2 missed · 0 not scored |
| Cost / time | $0.16 · 5 min 57 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/IssueDetail.tsx`: tool-call budget used: 15 calls in attempt 1 without passing run_verify
  - test IssueDetail › adds a label and says so: TestingLibraryElementError: Unable to find an accessible element with the role "alert"
  - test IssueDetail › removes a label with Backspace, and Undo brings it back: TestingLibraryElementError: Unable to find an accessible element with the role "alert"
  - test IssueDetail › puts the cursor in the comment box once the dialog is open: Error: expect(element).toHaveFocus()

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.16 = $0.05 output + $0.00 input + $0.12 cache (reads $0.01, writes $0.10), claude-haiku-5-5 $0.02 (33 calls); claude-opus-5-5 $0.14 (7 calls), 40 calls. Cache reads covered 80% of input tokens. Run cap $0.92; month cap $20.00, this month $2.74 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
