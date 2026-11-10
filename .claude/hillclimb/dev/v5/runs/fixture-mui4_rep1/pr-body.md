Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-001516-e95`, configuration `sonnet-medium`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

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
| Cost / time | $0.14 · 5 min 26 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/Faq.tsx`: the repair agent handed off: The snapshot still holds v4 markup (MuiExpansionPanelSummary classes, IconButton expand icon). The v5 AccordionSummary renders different DOM and class names, so the snapshot needs regenerating by a human. The component code is already correctly migrated, and I can't edi…
  - test Faq › renders a question header with its expand icon: Error: expect(received).toMatchSnapshot()

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.14 = $0.06 output + $0.00 input + $0.08 cache (reads $0.01, writes $0.07), claude-sonnet-5-5, 16 calls. Cache reads covered 61% of input tokens. Run cap $0.84; month cap $20.00, this month $2.04 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
