Migration `mui@4->mui@5` by the Migrator, run `2026-11-09-234828-9f7`, configuration `haiku-high`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: yes.** **10 of 12 affected files migrated without a human (83%)**: 2 by rules, 8 by the repair agent, 0 by a human at Review. 2 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 10 / 12 (83%) |
| Hand-offs | 2 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 21 expected · 0 other layer · 1 missed · 1 not scored |
| Cost / time | $0.04 · 9 min 2 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/Faq.tsx`: the repair agent handed off: The failing snapshot in src/screens/__tests__/__snapshots__/Faq.test.tsx.snap records v4 markup (MuiExpansionPanelSummary classes, IconButton-based expand icon). A correct v5 AccordionSummary renders different classes and structure, so the code can't match it without re…
  - test Faq › renders a question header with its expand icon: Error: expect(received).toMatchSnapshot()
- [ ] `src/screens/Notifications.tsx`: tool-call budget used: 15 calls in attempt 1 without passing run_verify
  - typecheck line 39: No overload matches this call. Overload 1 of 2, '(props: { component: "span"; } & TypographyOwnProps & CommonProps & Omit<Omit<DetailedHTMLProps<HTMLAttributes…

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.04 = $0.02 output + $0.00 input + $0.02 cache (reads $0.00, writes $0.01), claude-haiku-5-5, 62 calls. Cache reads covered 83% of input tokens. Run cap $0.37; month cap $20.00, this month $1.70 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
