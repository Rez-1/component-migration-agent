Migration `mui@4->mui@5` by the Migrator, run `2026-11-09-233502-567`, configuration `opus-low`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: yes.** **12 of 12 affected files migrated without a human (100%)**: 2 by rules, 10 by the repair agent, 0 by a human at Review. 0 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 12 / 12 (100%) |
| Hand-offs | 0 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 15 expected · 0 other layer · 0 missed · 0 not scored |
| Cost / time | $0.11 · 3 min 50 s |

## Hand-offs: for a human to finish

None: no file was handed off.

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.11 = $0.07 output + $0.00 input + $0.03 cache (reads $0.01, writes $0.02), claude-opus-5-5, 14 calls. Cache reads covered 95% of input tokens. Run cap $0.47; month cap $20.00, this month $1.63 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
