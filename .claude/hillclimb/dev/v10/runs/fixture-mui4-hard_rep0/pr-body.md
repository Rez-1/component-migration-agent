Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-015409-1e7`, configuration `haiku-advisor-opus`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: yes.** **11 of 12 affected files migrated without a human (92%)**: 3 by rules, 8 by the repair agent, 0 by a human at Review. 1 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 11 / 12 (92%) |
| Hand-offs | 1 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 12 expected · 0 other layer · 3 missed · 0 not scored |
| Cost / time | $0.15 · 6 min 50 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/NewIssueDialog.tsx`: tool-call budget used: 15 calls in attempt 1 without passing run_verify
  - test NewIssueDialog › assigns new issues to the signed-in user, marked in the list: Error: expect(element).toHaveAttribute("aria-selected", "true") // element.getAttribute("aria-selected") === "true"
  - test NewIssueDialog › creates the issue with a tidied estimate: Error: expect(jest.fn()).toHaveBeenCalledWith(...expected)

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.15 = $0.06 output + $0.00 input + $0.09 cache (reads $0.00, writes $0.09), claude-haiku-5-5 $0.03 (41 calls); claude-opus-5-5 $0.12 (1 call), 41 calls. Cache reads covered 81% of input tokens. Run cap $2.90; month cap $20.00, this month $5.09 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
