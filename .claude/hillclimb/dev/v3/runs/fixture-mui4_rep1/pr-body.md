Migration `mui@4->mui@5` by the Migrator, run `2026-11-09-232513-1cd`, configuration `opus-low`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: yes.** **11 of 12 affected files migrated without a human (92%)**: 2 by rules, 9 by the repair agent, 0 by a human at Review. 1 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 11 / 12 (92%) |
| Hand-offs | 1 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 22 expected · 0 other layer · 0 missed · 1 not scored |
| Cost / time | $0.24 · 5 min 28 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/Faq.tsx`: the repair agent handed off: Snapshot records v4 AccordionSummary DOM (IconButton expandIcon/class names) that v5 changes by design; code is correctly migrated, snapshot needs a human review and update (-u).
  - test Faq › renders a question header with its expand icon: Error: expect(received).toMatchSnapshot()

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.24 = $0.10 output + $0.00 input + $0.14 cache (reads $0.01, writes $0.13), claude-opus-5-5, 15 calls. Cache reads covered 59% of input tokens. Run cap $0.93; month cap $20.00, this month $1.30 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
