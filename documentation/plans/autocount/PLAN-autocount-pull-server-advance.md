# PLAN: AutoCount pull advances on the server, not on an open browser tab

Status: review passed (opus, 23 Sep), PR pending
Branch: `fix/autocount-pull-server-advance` (worktree `sorento_crm-pull-advance`, off `7c2c8e342`)
UAC: `autocount-pull-server-advance-acceptance-criteria.md`
Principle: `PRINCIPLES.md` Design mandates, D27 (added in this lane)

## Problem (measured, prod, 23 Sep 2026)

SRT products pull `4e9589c5`: created 07:40, FoundryX snapshot ready 07:43 (their run log:
3 min 35 s), Sorento preview `started_at` 08:17, `completed_at` 08:21. Real work was 3.5 min
theirs + 4 min ours; the other 34 minutes nothing ran.

Cause: the preview task is enqueued ONLY inside `refresh_pull_status`
(`app/services/autocount_pull_service.py:266-284`), which only runs when a browser calls
`GET /api/v1/autocount/pulls/{id}`. That call comes from `usePull`'s 10 s `refetchInterval`
(`autocount-pull/hooks/useAutocountPull.ts:80-89`). React Query skips interval refetches while
the tab is hidden (`refetchIntervalInBackground` defaults to false) and the app-wide default is
`refetchOnWindowFocus: false` (`providers/query-provider.tsx:41`), so the owner switching to
another tab stopped the poll; the snapshot sat `ready` until he came back and the next tick
enqueued it. The same pause is why the progress bar looked stuck at 08:2x: the last polled
value stayed on screen until a manual reload.

No server-side ticker exists for `building` pulls. The original plan chose "no RQ worker held
while FoundryX builds" (right) but left the build -> preview transition to the browser (wrong).

## Fix (two seams, both tiny)

### BE: scheduler tick `autocount_pull_advance`, every 30 s

`app/services/autocount_pull_service.py`:

```python
def advance_building_pulls(db: Session) -> int:
    """Server-side driver for the build -> preview transition (D27). Returns the number
    of pulls whose status was refreshed. Zero `building` pulls = zero FoundryX calls."""
```

- Select `ImportJob` rows where `job_type IN JOB_TYPES.values()`, `status == pending`,
  `job_metadata->'autocount_pull'->>'phase' == 'building'`. Session is `scheduler_session()`
  (all companies, same as every other tick).
- For each: `refresh_pull_status(db, job)` inside its own `try/except`; one pull's FoundryX
  error (or `FoundryxPullError(NOT_CONFIGURED)` on a dev box) is logged at warning and the loop
  continues. The next tick retries. Nothing new is marked failed here: `refresh_pull_status`
  already owns expiry (`BUILD_EXPIRY`) and FoundryX `failed`.
- `_claim_and_enqueue_preview`'s conditional UPDATE (`status == pending`) is the exactly-once
  guard, unchanged. A browser poll and the tick racing each other enqueue one preview.
- `refresh_pull_status` is reused unchanged, so a client is constructed per building pull per
  tick (one integrations SELECT + one decrypt; nothing at this scale). With zero building pulls
  no client is constructed.

`app/scheduler/task_scheduler.py`: `_autocount_pull_advance_tick()` next to
`_chatbot_delegated_sweep_tick` (same shape: own session, never raises), registered in
`start_scheduler` with `IntervalTrigger(seconds=30)`, `id="autocount_pull_advance"`. 30 s
because FoundryX builds take minutes; the browser fast path stays at 10 s.

Prod: the scheduler runs in the `worker` container (`ENABLE_SCHEDULER=true` there only), which
is also where the enqueued preview runs. No new env, no migration.

### FE: `usePull` keeps polling while the tab is hidden

`useAutocountPull.ts` `usePull`: add `refetchIntervalInBackground: true`. One GET every 10 s
for the life of a running pull, from one tab. That is the whole cost.

## Not doing

- No RQ job that sleeps on FoundryX status (holds a worker slot for up to 60 min; the plan's
  original reason still stands).
- No `refetchOnWindowFocus` change to the global default.
- No change to the apply path: `confirm_pull` enqueues the apply inside the request already.
- No generalised "job stage advancer" registry. One tick for one job type; the principle names
  the rule, the next job type pays for its own tick.

## Tests (one coder writes red then green, small fix track)

pytest `tests/test_autocount_pull_server_advance.py` (Postgres, `tests/_pg_fixture.py`,
patch `app.services.autocount_pull_service.enqueue_job` and `FoundryxAutocountClient` the same
way `tests/test_autocount_pull_sr1.py` does):

- T1 one `building` pull, FoundryX `ready`: after `advance_building_pulls`, phase `previewing`,
  status `queued`, `enqueue_job` called once with `preview_autocount_pull` and the job's id.
- T2 FoundryX still `building` with `progress`: no enqueue, progress stored on the row.
- T3 no `building` pulls: returns 0, `FoundryxAutocountClient` never constructed.
- T4 T1 then a second `advance_building_pulls` (FoundryX still says `ready`): `enqueue_job`
  called once in total (conditional update holds).
- T5 two `building` pulls, the first one's `client.status` raises: the second still advances,
  the first is untouched (still `building`, status `pending`), no exception escapes.
- T6 `building` pull older than `BUILD_EXPIRY`: phase `expired`, status `failed`, no FoundryX
  call for it.
- T7 pulls in `previewing`, `review`, `confirmed`, `discarded` are not selected (no FoundryX
  call, rows unchanged).
- T8 `start_scheduler` registers a job with `id="autocount_pull_advance"` and a 30 s interval
  (patch `BackgroundScheduler` and inspect `add_job` calls; the scheduler must not actually
  start).

vitest `autocount-pull/hooks/useAutocountPull.test.tsx` (extend the existing file):

- F1 `usePull` passes `refetchIntervalInBackground: true` to `useQuery` (spy on
  `@tanstack/react-query`'s `useQuery` the way other hook specs in this repo do, or assert via
  `queryClient.getQueryCache().find(...)?.observers[0].options`).

## Verification

- pytest: the new file + `tests/test_autocount_pull_sr1.py`, `tests/test_autocount_pull_fixes.py`,
  `tests/test_autocount_pull_discard.py`, `tests/test_scheduled_task_*.py`, against
  `sorento_buc_ci` (lane `.env` already points there).
- vitest: `autocount-pull/hooks/`.
- Browser pass: n/a, no screen changes (small fix track rule). Prod check after deploy: next SRT
  pull's `started_at - created_at` is FoundryX build time (about 4 min), owner away from the tab.

## Rollout

Pre-PR gate (fetch main, merge, single alembic head - no migration in this lane), push, PR,
reviewer (opus) once. Never merge without go.
