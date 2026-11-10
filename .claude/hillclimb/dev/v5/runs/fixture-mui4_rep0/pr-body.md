Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-000903-634`, configuration `sonnet-medium`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

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
| Cost / time | $0.16 · 6 min 9 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/Faq.tsx`: the repair agent handed off: The snapshot was recorded with v4 markup (MuiExpansionPanelSummary classes, IconButton expand icon). v5 AccordionSummary legitimately renders different markup, so the snapshot needs regenerating. Snapshots are off-limits for me, and the source is already migrated correc…
  - test Faq › renders a question header with its expand icon: Error: expect(received).toMatchSnapshot()
- [ ] `src/screens/Notifications.tsx`: 3 attempts used; 2 failures left
  - typecheck line 39: No overload matches this call. Overload 1 of 2, '(props: { component: "span"; } & TypographyOwnProps & CommonProps & Omit<Omit<DetailedHTMLProps<HTMLAttributes…

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.16 = $0.06 output + $0.00 input + $0.09 cache (reads $0.01, writes $0.08), claude-sonnet-5-5, 20 calls. Cache reads covered 66% of input tokens. Run cap $1.00; month cap $20.00, this month $1.91 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
