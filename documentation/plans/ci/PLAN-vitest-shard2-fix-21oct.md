# PLAN: release vitest shard 2 finishes inside the job time limit

Status: in progress (small fix track: test-only diff, no migration, no auth change)

## Problem

Release run 39522177768 (main = prod 44e2561989 + #1808 + #1810) lost job
`Validate frontend (vitest) (2)` to the 20 min job timeout twice, while shards
1/3/4 finished in 15-19 min. Suspects: #1808's new tests (real timers, 15 s
timeouts, a never-resolving promise) and #1810's gearRemark.test.tsx.

## Approach

1. Reproduce `npx vitest run --shard=2/4` with `CI=1` (same command as
   `.github/workflows/deploy.yml` validate-frontend), verbose reporter, per-file
   durations.
2. Find the slow or hanging files; fix them with fake timers / bounded waits.
   Test-only. Product code only if a real hang is found (called out in the PR).
3. Record before/after shard-2 wall time in the PR body.

Not the fix: raising `timeout-minutes`.

## Acceptance

- Shard 2 wall time locally drops back in line with the other shards; the
  files #1808/#1810 added each run in seconds, not tens of seconds.
- Same tests, same assertions: nothing skipped or deleted.
