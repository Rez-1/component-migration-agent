# Scorecard: mui4-fixture-app · run 2026-11-09-1415-a3f

> PROTOTYPE. Mock numbers for the fixture, to react to. Not real output.

`mui@4 → mui@5` · configuration `opus-low` · fixture case, dev split · 6 min 12 s · **$2.97** of $5.00 cap

**Clean run: no.** Final verify found 1 failure outside handed-off files (a regression in `ResponsiveNav.tsx`). **9 of 12 affected files migrated without a human (75%)**: 3 by rules, 6 by the repair agent. 2 handed off, 1 unmigrated. 0 cheating-check hits.

| | This run | Baseline (rules only) |
|---|---|---|
| Clean run | no (1 failure) | no (14 failures in 8 files) |
| Migrated without a human | 9 / 12 (75%) | 4 / 12 (33%) |
| Hand-offs | 2 | — |
| Regressions | 1 | 0 |
| Cheating-check hits | 0 (1 warning) | — |
| Codemod TODOs left | 2 | 2 |
| Traps | 20 expected · 0 other layer · 1 missed · 1 not scored | 12 expected · 9 missed · 1 not scored |
| Cost / time | $2.97 · 6 min 12 s | $0 · 1 min 48 s |

## Files

| File | Outcome | Attempts | Patch | Failures before → after | Cost | Note |
|---|---|---|---|---|---|---|
| src/theme.ts | Migrated by agent | 3 | +11 −4 | 2 → 0 | $0.91 | |
| src/screens/Search.tsx | Migrated by agent | 2 | +14 −9 | 3 → 0 | $0.63 | |
| src/screens/AccountDialog.tsx | Migrated by agent | 2 | +8 −1 | 1 → 0 | $0.54 | |
| src/screens/Dashboard.tsx | Migrated by agent | 1 | +2 −2 | 2 → 0 | $0.25 | |
| src/screens/Settings.tsx | Migrated by agent | 1 | +3 −3 | 1 → 0 | $0.20 | warning: non-null `!` added (line 22) |
| src/screens/ProfileForm.tsx | Migrated by agent | 1 | +4 −4 | 2 → 0 | $0.22 | |
| src/screens/Notifications.tsx | Handed off | 3 | reverted | 1 → 1 | $0.22 | 3 attempts used |
| src/screens/ProfileCard.tsx | Handed off | 1 | reverted | 1 → 1 | $0.00 | agent: "fix needs src/test-utils.tsx (a test file)" |
| src/screens/ResponsiveNav.tsx | Unmigrated | 0 | — | 0 → 1 | $0 | **regression**, caused by `src/theme.ts` attempt 3 |
| 3 files | Migrated by rules | | | | | UsersTable, Faq, App |

Not affected but changed by the agent: none.

## Traps (fixture)

| Result | Traps |
|---|---|
| Expected | 12 base · 7 repair · 1 human (ProfileCard handed off) |
| Missed | Typography `srOnly` (Notifications.tsx handed off after 3 attempts) |
| Not scored | Switch default colour (visual only) |

## Cost

$2.97 = $1.96 output + $0.71 input + $0.30 cache (reads $0.13, writes $0.17), all Opus 5.5. Cache reads covered 75% of input tokens. Run cap $5.00; this month $11.40 of $20.00.
