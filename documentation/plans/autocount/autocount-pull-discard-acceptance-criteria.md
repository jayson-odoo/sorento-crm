# UAC: discard an AutoCount pull, pull again, back to where the pull started

Plan: `PLAN-autocount-pull-discard.md`

## Backend

- **AC-DS-1 [BE]** `POST /api/v1/autocount/pulls/{id}/discard` on the owner's pull in `review`
  answers 200 with `phase: "discarded"`; the row's `status` is `cancelled` and `completed_at` is set.
  No product or stock row changes.
- **AC-DS-2 [BE]** The same call works from `building` and from `previewing`, and makes no FoundryX
  request (the fake gateway records zero calls during the discard).
- **AC-DS-3 [BE]** After a discard, `GET /pulls/current?entity=...` answers 404 and `POST /pulls`
  builds a NEW snapshot (new job id, one `build` call on the fake gateway).
- **AC-DS-4 [BE]** Discard twice answers 200 both times with the same body; nothing else changes.
- **AC-DS-5 [BE]** Discard on `confirmed`, `failed` or `expired` answers 409 `NOT_DISCARDABLE` and
  changes nothing.
- **AC-DS-6 [BE]** Another user's pull answers 404 (same as every owner-only pull route); a caller
  with no token answers 401.
- **AC-DS-7 [BE]** Confirm on a discarded pull answers 409 and creates no apply job.
- **AC-DS-8 [BE]** A preview task that finishes after the pull was discarded leaves the phase
  `discarded` (never `review`). A pull job whose `status` is `cancelled` while its phase still reads
  `building` is not returned by `find_open_pull`.

## Frontend

- **AC-DS-9 [FE]** The review card shows `Discard` while the phase is `building`, `previewing` or
  `review`, and not in any other phase.
- **AC-DS-10 [FE]** Clicking `Discard` calls the discard endpoint once, with no dialog and no
  countdown, toasts "Pull discarded", and the card then shows the `Discarded` badge. A failure
  toasts the extracted API message (`extractApiError`).
- **AC-DS-11 [FE]** `Pull again` shows on `failed`, `expired` and `discarded`. Clicking it starts a
  pull for the same entity and navigates to the new job's page. A start failure toasts
  `startPullErrorMessage`.
- **AC-DS-12 [FE]** On a pull job page opened WITHOUT a `page` query param the header button reads
  "Back to Products" (products pull) or "Back to Stock" (stock pull) and links to that list.
- **AC-DS-13 [FE]** On a pull job page opened WITH a `page` query param, and on every non-pull job,
  the button still reads "Back to Import Jobs" and keeps `page` + `pageSize`.
- **AC-DS-14 [FE]** Discard and Pull again are reachable and not clipped at 375px and 1280px.

## Browser

- **AC-DS-15 [E2E]** On the lane stack: Products, Pull from AutoCount, wait for review, Discard,
  badge reads Discarded, Back to Products, Pull from AutoCount again starts a NEW pull (different
  job, Building). Screenshots at 375px and 1280px under
  `documentation/plans/autocount/evidence/autocount-pull-discard/`.
