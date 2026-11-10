Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-014527-934`, configuration `haiku-advisor-opus`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

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
| Cost / time | $0.27 · 8 min 38 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/Faq.tsx`: the repair agent handed off: The failing test is a snapshot test, and its .snap file still holds the v4 output (MuiExpansionPanelSummary-* classes, expandIcon IconButton markup). Migrated v5 AccordionSummary renders different classes and structure, so no code change in Faq.tsx can match it without …
  - test Faq › renders a question header with its expand icon: Error: expect(received).toMatchSnapshot()

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.27 = $0.10 output + $0.00 input + $0.16 cache (reads $0.00, writes $0.16), claude-haiku-5-5 $0.03 (54 calls); claude-opus-5-5 $0.24 (2 calls), 54 calls. Cache reads covered 79% of input tokens. Run cap $3.16; month cap $20.00, this month $4.93 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
