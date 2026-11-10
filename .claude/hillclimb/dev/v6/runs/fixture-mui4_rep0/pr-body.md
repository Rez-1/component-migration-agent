Migration `mui@4->mui@5` by the Migrator, run `2026-11-10-003043-4b7`, configuration `cascade-haiku-opus`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

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
| Cost / time | $0.13 · 7 min 25 s |

## Hand-offs: for a human to finish

- [ ] `src/screens/Faq.tsx`: the repair agent handed off: The failing assertion is a snapshot of the v4 markup (MuiExpansionPanelSummary classes, v4 IconButton expand wrapper). The v5 AccordionSummary renders different classes and structure, so the code is migrated correctly and the only way to pass is to update the snapshot, …
  - test Faq › renders a question header with its expand icon: Error: expect(received).toMatchSnapshot()
- [ ] `src/screens/Search.tsx`: tool-call budget used: 15 calls in attempt 1 without passing run_verify
  - typecheck line 42: Property 'label' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'.
  - typecheck line 43: Property 'country' does not exist on type 'HTMLAttributes<HTMLLIElement> & { key: any; }'.
  - test Search › suggests matching cities with their country: TestingLibraryElementError: Unable to find an accessible element with the role "option"
  - test Search › selects Amsterdam: TestingLibraryElementError: Unable to find an accessible element with the role "option" and name `/Amsterdam/`

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0.13 = $0.03 output + $0.00 input + $0.10 cache (reads $0.01, writes $0.09), claude-haiku-5-5 $0.03 (43 calls); claude-opus-5-5 $0.10 (6 calls), 49 calls. Cache reads covered 77% of input tokens. Run cap $1.20; month cap $20.00, this month $2.43 of $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
