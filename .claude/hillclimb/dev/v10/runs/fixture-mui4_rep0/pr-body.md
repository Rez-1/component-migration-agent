Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-013653-c8e`, configuration `haiku-advisor-opus`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

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
| Cost / time | $0.24 · 8 min 30 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/Faq.tsx`: the repair agent handed off: The failing assertion is a snapshot of v4 DOM (class names MuiExpansionPanelSummary-root/-content/-expandIcon, MuiIconButton-label inside the expand icon). The v5 AccordionSummary renders different classes and structure (MuiAccordionSummary-*, expandIconWrapper div, no …
  - test Faq › renders a question header with its expand icon: Error: expect(received).toMatchSnapshot()
- [ ] `src/screens/Search.tsx`: tool-call budget used: 15 calls in attempt 1 without passing run_verify
  - typecheck line 42: Property 'label' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'.
  - typecheck line 43: Property 'country' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'.
  - test Search › suggests matching cities with their country: TestingLibraryElementError: Unable to find an accessible element with the role "option"
  - test Search › selects Amsterdam: TestingLibraryElementError: Unable to find an accessible element with the role "option" and name `/Amsterdam/`

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.24 = $0.07 output + $0.00 input + $0.16 cache (reads $0.00, writes $0.16), claude-haiku-5-5 $0.03 (57 calls); claude-opus-5-5 $0.21 (2 calls), 57 calls. Cache reads covered 80% of input tokens. Run cap $3.40; month cap $20.00, this month $4.67 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
