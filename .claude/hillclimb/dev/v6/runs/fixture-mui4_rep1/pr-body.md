Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-003813-fe2`, configuration `cascade-haiku-opus`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: yes.** **9 of 12 affected files migrated without a human (75%)**: 2 by rules, 7 by the repair agent, 0 by a human at Review. 3 handed off, 0 unmigrated.

| | This run |
|---|---|
| Clean run | yes |
| Migrated without a human | 9 / 12 (75%) |
| Hand-offs | 3 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 20 expected · 0 other layer · 2 missed · 1 not scored |
| Cost / time | $0.10 · 7 min 15 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/Faq.tsx`: the repair agent handed off: The Faq.tsx migration to Accordion/AccordionSummary/AccordionDetails is correct for v5, but the failing test is a snapshot test. The committed snapshot in src/screens/__tests__/__snapshots__/Faq.test.tsx.snap still has v4 markup (MuiExpansionPanelSummary-* classes, MuiI…
  - test Faq › renders a question header with its expand icon: Error: expect(received).toMatchSnapshot()
- [ ] `src/screens/Notifications.tsx`: tool-call budget used: 15 calls in attempt 1 without passing run_verify
  - typecheck line 39: No overload matches this call. Overload 1 of 2, '(props: { component: "span"; } & TypographyOwnProps & CommonProps & Omit<Omit<DetailedHTMLProps<HTMLAttributes…
- [ ] `src/screens/Search.tsx`: tool-call budget used: 15 calls in attempt 1 without passing run_verify
  - typecheck line 42: Property 'label' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'.
  - typecheck line 43: Property 'country' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'.
  - test Search › suggests matching cities with their country: TestingLibraryElementError: Unable to find an accessible element with the role "option"
  - test Search › selects Amsterdam: TestingLibraryElementError: Unable to find an accessible element with the role "option" and name `/Amsterdam/`

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.10 = $0.03 output + $0.00 input + $0.07 cache (reads $0.01, writes $0.06), claude-haiku-5-5 $0.03 (51 calls); claude-opus-5-5 $0.07 (3 calls), 54 calls. Cache reads covered 80% of input tokens. Run cap $1.07; month cap $20.00, this month $2.53 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
