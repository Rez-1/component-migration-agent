Migration `mui@4->mui@5` by the Migrator, run `2026-11-09-231518-ed8`, configuration `baseline`, commands sandboxed in docker. Every number below comes from the run's `scorecard.json`.

**Clean run: no. The final verify found 16 failures in 10 files.** **2 of 12 affected files migrated without a human (17%)**: 2 by rules, 0 by the repair agent, 0 by a human at Review. 0 handed off, 10 unmigrated.

| | This run |
|---|---|
| Clean run | no |
| Migrated without a human | 2 / 12 (17%) |
| Hand-offs | 0 |
| Regressions | 0 |
| Cheating-check hits | 0 (0 warnings); 1 Rules-layer notes |
| Codemod TODOs left | 0 |
| Traps (fixture) | 12 expected · 0 other layer · 10 missed · 1 not scored |
| Cost / time | $0 · 1 min 5 s |

## Hand-offs: for a human to finish

None: no file was handed off.

Unmigrated (no layer finished them):

- [ ] `src/screens/AccountDialog.tsx`: 1 test
- [ ] `src/screens/Dashboard.tsx`: 2 typecheck
- [ ] `src/screens/Faq.tsx`: 1 test
- [ ] `src/screens/Notifications.tsx`: 1 typecheck
- [ ] `src/screens/ProfileCard.tsx`: 1 test
- [ ] `src/screens/ProfileForm.tsx`: 1 typecheck
- [ ] `src/screens/ResponsiveNav.tsx`: 1 test
- [ ] `src/screens/Search.tsx`: 2 test, 2 typecheck
- [ ] `src/screens/Settings.tsx`: 2 test, 1 typecheck
- [ ] `src/theme.ts`: 1 typecheck

## Codemod TODOs

None: the codemods left no FIXME or TODO comments.

## Cost

$0: this run made no model calls. Run cap $5.00; month cap $20.00.

<sub>Node 20.20.2, npm 10.8.2, migrator 0.1.0. Verify ran the repo's type-check, lint and tests in a Docker container with no network.</sub>
