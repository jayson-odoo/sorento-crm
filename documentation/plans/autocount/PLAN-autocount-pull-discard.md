# PLAN: discard an AutoCount pull, pull again, back to where the pull started

Status: tests being written (light lane: tester reds, one coder, one reviewer, browser pass on the lane stack; no migration, no auth change)

UAC: `autocount-pull-discard-acceptance-criteria.md`

## Journey

Owner, prod, 21 Sep 2026: pulled SRT products, the review showed every list price as 0 (a join was
not configured on the FoundryX side). He wanted to throw the pull away and pull again. He could
not: the only action on a pull in review is Confirm, and Pull on the Products page reopens the same
pull. Separately, the job page of a pull only offers "Back to Import Jobs", although he got there
from Products.

## Measured facts (origin/main cc6c09f19)

- `autocount_pull_service._OPEN_PHASES = ("building", "previewing", "review")`; `start_pull` returns
  `find_open_pull(...)` when one exists, so an open pull is reused for ever.
- Only `building` expires (`BUILD_EXPIRY`, 60 min). `review` never does.
- Routes in `app/api/v1/integrations/autocount_pull.py`: start, current, get, rows, download,
  compare, confirm. No discard.
- `find_open_pull` skips a job whose `status` is `failed` but not one whose status is `cancelled`.
  The generic Cancel button on the job page (`canCancel` = pending / queued / started) can set
  `cancelled` on a pull job while its stored phase still says `building`.
- FE: `AutocountPullReview.tsx` renders Confirm only in `review`; phases `failed` and `expired`
  show no next step. `import-jobs/[id]/page.tsx` hardcodes "Back to Import Jobs" (4 places; the
  main one keeps `?page=&pageSize=` when the user came from the list).

## Design

One new phase, `discarded`. No new table, no new column, no migration: the phase lives in
`import_jobs.metadata.autocount_pull.phase` like the others.

Backend
- `pull_service.discard_pull(db, job)`: allowed from `building`, `previewing`, `review`. Sets phase
  `discarded`, `job.status = cancelled`, `completed_at = now`. Already `discarded` answers the same
  body again (idempotent). Any other phase (`confirmed`, `failed`, `expired`) raises
  `PullNotDiscardable`, route answers 409 `NOT_DISCARDABLE`.
- `POST /api/v1/autocount/pulls/{job_id}/discard`, resolved through `_resolve_pull` (owner only,
  same as confirm). No FoundryX call: the snapshot expires on its own.
- The preview task must not resurrect a discarded pull: its final write to `review` happens only
  when the stored phase is still `previewing` (re-read the row first).
- `find_open_pull` also skips a job whose status is `cancelled`.
- Confirm on a discarded pull is already a 409 (phase is not `review`); pinned by a test.

Frontend
- Type `AutocountPullPhase` gains `discarded`; label "Discarded", neutral badge.
- Review card: `Discard` (outline) beside Confirm while `building`, `previewing` or `review`.
  Immediate, no dialog, no countdown (owner ruling 21 Sep: nothing of the user's is lost, the row
  stays as history, pulling again is free). Toast "Pull discarded".
- `Pull again` on `failed`, `expired` and `discarded`: calls the existing `startPull(entity)` and
  navigates to the new job.
- Back button on a pull job: no `page` query param (the user did not come from the Import Jobs
  list) reads "Back to Products" / "Back to Stock" and links to that list. With a `page` param it
  stays "Back to Import Jobs". Non-pull jobs unchanged.

## Out of scope

- Blocking Confirm when every pulled price is 0 (owner: the cause was his FoundryX join, fixed).
- Auto-expiry of `review`. Trigger to build it: stale reviews start blocking users who cannot
  discard them (not possible once Discard ships, the pull is owner-only).

## Tests

Backend, new file `tests/test_autocount_pull_discard.py` (Postgres, `tests/_pg_fixture.py`, fake
FoundryX from `tests/support/fake_foundryx.py`): see UAC AC-DS-1 to AC-DS-8.
Frontend vitest: `AutocountPullReview.discard.test.tsx`, service test additions, a page-level test
for the Back link: see UAC AC-DS-9 to AC-DS-14.
Browser (agent-browser, lane stack :3083/:8083 on the clone): AC-DS-15.
