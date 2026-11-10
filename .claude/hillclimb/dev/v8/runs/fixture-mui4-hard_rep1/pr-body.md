Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-013210-754`, configuration `opus-low-tools-v2`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: no. The final verify found 2 failures in 1 files.** **11 of 12 affected files migrated without a human (92%)**: 3 by rules, 8 by the repair agent, 0 by a human at Review. 0 handed off, 1 unmigrated.

| | This run |
|---|---|
| Clean run | no |
| Migrated without a human | 11 / 12 (92%) |
| Hand-offs | 0 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 13 expected · 0 other layer · 2 missed · 0 not scored |
| Cost / time | $0.12 · 4 min 5 s |

## Hand-offs: for a human to finish

None: no file was handed off.

Unmigrated (no layer finished them):

- [ ] `src/screens/NewIssueDialog.tsx`: cost cap: the next call (claude-opus-5-5, worst case $0.37) could take this run past its $0.47 cap (spent $0.12)

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.12 = $0.08 output + $0.00 input + $0.04 cache (reads $0.01, writes $0.02), claude-opus-5-5, 15 calls. Cache reads covered 95% of input tokens. Run cap $0.47; month cap $20.00, this month $4.43 of $20.00. Repair stopped at the cost cap.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
