# UAC: AutoCount pull advances on the server

Plan: `PLAN-autocount-pull-server-advance.md`. Principle: `PRINCIPLES.md` D27.

## Server-side advance (SA)

- AC-SA-1 A pull whose FoundryX snapshot is `ready` has its preview enqueued within 30 s of
  readiness with NO browser open on the pull page, and exactly once. Test: T1, T4.
- AC-SA-2 A pull still `building` is left `building`; FoundryX `progress`, when sent, is stored
  on the row so the next viewer sees it. Test: T2.
- AC-SA-3 With no `building` pull in the database the tick makes no outbound call and constructs
  no FoundryX client. Test: T3.
- AC-SA-4 One pull's FoundryX error never stops the other pulls in the same tick and never
  escapes the tick; the failing pull is retried on the next tick unchanged. Test: T5.
- AC-SA-5 A `building` pull past `BUILD_EXPIRY` (60 min) is marked `expired` by the tick, with
  no FoundryX call, the same outcome the browser poll already produced. Test: T6.
- AC-SA-6 Pulls in any phase other than `building` (`previewing`, `review`, `confirmed`,
  `discarded`, `failed`, `expired`) are never touched by the tick. Test: T7.
- AC-SA-7 The tick is registered as APScheduler job `autocount_pull_advance` at a 30 s interval in
  `start_scheduler`, so it runs wherever `ENABLE_SCHEDULER=true` (prod: the worker container).
  Test: T8.
- AC-SA-8 A browser poll and the tick racing on the same ready pull enqueue ONE preview
  (existing conditional update `status == pending`). Test: T4 covers the sequential form; the
  concurrent form is the same UPDATE (`tests/test_autocount_pull_sr1.py` already covers it).

## Browser viewer (BV)

- AC-BV-1 `usePull` polls while its tab is hidden (`refetchIntervalInBackground: true`), so the
  progress shown when the user returns is at most 10 s old. Test: F1.
- AC-BV-2 Poll cadence and stop rules are unchanged: 10 s while `building`/`previewing`, while
  `confirmed` until the apply job ends, off otherwise. Test: existing `useAutocountPull.test.tsx`.

## Principle (PR)

- AC-PR-1 `PRINCIPLES.md` Design mandates carries D27 (server-driven job stages; browser is a
  viewer; hidden tabs keep polling), citing this lane as the precedent.

## Regression

- AC-RG-1 `tests/test_autocount_pull_sr1.py`, `test_autocount_pull_fixes.py`,
  `test_autocount_pull_discard.py`, `tests/test_scheduled_task_*.py` stay green.
- AC-RG-2 No migration, no new env var, single alembic head at the pre-PR gate.

## Prod check (after deploy, owner)

- AC-PD-1 Next SRT products pull run with the owner AWAY from the tab: `started_at - created_at`
  is about FoundryX build time (about 4 min at N=4), not the owner's return time.
