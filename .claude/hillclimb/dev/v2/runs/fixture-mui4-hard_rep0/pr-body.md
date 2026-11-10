Migration `mui@4->mui@5` by the Migrator, run `2026-11-09-231732-148`, configuration `baseline`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: no. The final verify found 13 failures in 7 files.** **5 of 12 affected files migrated without a human (42%)**: 5 by rules, 0 by the repair agent, 0 by a human at Review. 0 handed off, 7 unmigrated.

| | This run |
|---|---|
| Clean run | no |
| Migrated without a human | 5 / 12 (42%) |
| Hand-offs | 0 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 6 expected · 0 other layer · 9 missed · 0 not scored |
| Cost / time | $0 · 56 s |

## Hand-offs: for a human to finish

None: no file was handed off.

Unmigrated (no layer finished them):

- [ ] `src/components/RangeSlider.tsx`: 1 typecheck
- [ ] `src/components/StatusChip.tsx`: 1 typecheck
- [ ] `src/screens/Activity.tsx`: 1 lint, 1 test, 1 typecheck
- [ ] `src/screens/Board.tsx`: 1 test
- [ ] `src/screens/IssueDetail.tsx`: 3 test
- [ ] `src/screens/IssueList.tsx`: 1 test, 1 typecheck
- [ ] `src/screens/NewIssueDialog.tsx`: 2 test

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0: this run made no model calls. Run cap $5.00; month cap $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
