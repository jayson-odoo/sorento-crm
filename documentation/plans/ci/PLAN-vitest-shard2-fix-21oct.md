# PLAN: release vitest shard 2 finishes inside the job time limit

Status: in review, PR #1813 (small fix track: CI + test-only diff, no migration, no auth change)

## Problem

Release run 39522177768 (main = prod 44e2561989 + #1808 + #1810) lost job
`Validate frontend (vitest) (2)` to the 20 min job timeout twice, while shards
1/3/4 finished in 15:00 / 19:02 / 18:34. Suspects were #1808's new tests (real
timers, 15 s timeouts, a never-resolving promise) and #1810's gearRemark.test.tsx.

## Measured cause

- No hang. The cancelled job (118975513821) was still passing files 0.1 s before
  "The operation was canceled".
- `CI=1 taskset -c 0,1 npx vitest run --shard=2/4` on main 9559607d: 438 files,
  4695 tests, all green, 12m49s wall. Per-file overhead is most of it:
  environment 392 s, import 258 s, setup 133 s, vs 649 s of test bodies.
- The files #1808 / #1810 added each run in under 2 s.
- Real sleeps in the whole shard total ~32 s: the 3 s `refetchInterval` tests in
  `useFlyerReadings.test.tsx` (14.4 s) and `useFlyerSpecProposals.test.tsx`
  (19.4 s).
- vitest's `--shard` splits by file COUNT (1751 files / 4), not by weight, and
  every shard sits near the cap, so fixing single files cannot buy the margin.

## Fix (owner ruling 21 Oct: both)

1. (a) The six polling tests run on fake timers (`vi.advanceTimersByTimeAsync`
   inside `act`) and also pin that no GET fires before 3 s. Test-only.
2. (b) `deploy.yml` validate-frontend runs 5 shards (`--shard=N/5`), not 4. Same
   tests, one more runner install. `timeout-minutes` stays 20.

No product code changes.

## Acceptance

- Both polling test files green, kill-tested against changed / always / never
  poll intervals.
- Each of the 5 shards runs locally on 2 pinned CPUs well inside the cap
  (numbers in the PR body).
- The next release's 5 vitest shards each finish well under 20 min.
- Same tests, same assertions: nothing skipped or deleted.
