# UAC: flyer read as a background job

Plan: `documentation/plans/dealer-kit/PLAN-flyer-read-background-job.md`
Status: draft, contract for the branch `fm/flyer-read-background-job`.
Supersedes the "read inside the request" half of
`flyer-read-hardening-acceptance-criteria.md` (AC-J1 to AC-J3 there); everything
about the library picker (AC-A*) stands unchanged.

## Journey

**Actor.** A designer (or the captain) with `dealer_kit.page.edit`, arriving from
the sidebar: Dealer Kit -> Flyers. They hold a printed flyer as a PDF, either on
their laptop or already filed in Resource Management.

**What the first screen shows.** The Flyers list: every flyer already read,
newest first, each with its status. Nothing on it is asked twice.

**Steps and the single decision at each.**

1. **Read a flyer.** Opens the same dialog as today: "Upload a file" or "Choose
   from Files". The one decision is which file.
2. **Read the flyer.** The dialog closes AT ONCE. A toast says
   "Reading the flyer in the background - it will appear in your uploads". The
   designer is back on the list, free to leave the page, and the flyer is
   already listed at the top with a **Processing** pill. Nothing else is asked;
   the name, size and type come off the file.
3. **Wait, or do not.** The list refreshes itself while any row is Processing.
   The row flips to **Done** (page and code counts filled in) or **Failed**
   with the reason beside it, in the same words the request used to say
   ("not a PDF", "password protected", "over the 50 MB limit", "could not be
   fetched from storage").
4. **Open the report.** Clicking a Done row lands on the review screen exactly as
   today. Clicking a Processing row shows the review screen in its waiting
   state and it fills in on its own; a Failed row shows the reason with a
   "Read another flyer" way out.

**What they hold at the end.** A reading with its report, reachable from the
list, and a list that tells the truth about every read that was ever started
- including the ones that failed, and why.

**What everyone else is told.** Nothing new. The read is the designer's own
working material; there is no stakeholder to notify.

**What the system already knows and never asks.** The file name, size and type
(from the upload or the attachment row); who asked (the session); which company
(the scope); whether the same file is ALREADY being read (the row it would
duplicate).

## Acceptance criteria

Tags: `[BE]` backend, `[FE]` frontend, `[T]` test, `[E2E]` real-browser evidence
run. Every AC traces to a journey step (J1..J4) or to the diagnosis (D).

### D. Diagnosis (recorded, not built)

- **AC-D1** `[T]` The plan records, measured on this machine against the real
  36-page flyer held in `attachments`: storage download time, `extract_flyer`
  time, and the gateway timeout the production path is subject to (or the best
  evidence available when the host nginx config is not in the repo). The
  conclusion "any in-request design 504s" rests on those numbers.

### J2. The request returns at once

- **AC-J2.1** `[BE]` `POST /api/v1/dealer-kit/flyer-readings/from-attachment`
  answers **202** with a `FlyerReadingSummary` whose `status` is `processing`,
  before any byte of the PDF is fetched. Its pre-checks are unchanged and still
  run in-request on metadata only: out-of-scope or trashed -> 404, non-PDF mime
  -> 400 `FLYER_NOT_A_PDF`, recorded size over the ceiling -> 413
  `FLYER_TOO_LARGE`, no stored key -> 422 `FLYER_SOURCE_MISSING`.
- **AC-J2.2** `[BE]` `POST /api/v1/dealer-kit/flyer-readings` (multipart) answers
  **202** with a `FlyerReadingSummary` whose `status` is `processing`. The
  ceiling is still enforced as the bytes arrive (413 with the limit named).
  The bytes are staged in object storage under a non-attachment prefix, in a
  threadpool, never on the event loop; nothing extracts in the request.
- **AC-J2.3** `[BE]` Both routes enqueue ONE RQ job on the `flyer_read` queue,
  carrying the reading id (and, for an upload, the staged object's provider and
  key). The worker's default queue list includes `flyer_read`.
- **AC-J2.4** `[BE]` Idempotent re-click: while a reading for the SAME source is
  `processing` in the caller's company - same `source_attachment_id` for the
  library path, same `sha256` for the upload path - a second POST returns
  **202** with the EXISTING reading and enqueues nothing. A `done` or `failed`
  reading for the same source does not block a new read.
- **AC-J2.5** `[BE]` If enqueueing fails (Redis unreachable), the reading is
  marked `failed` with a message naming the queue problem, the response is
  still 202 carrying that row, and no staged object is left behind.
- **AC-J2.6** `[BE]` Both routes still require `dealer_kit.page.edit`; a caller
  without it gets the same 403 as before.
- **AC-J2.7** `[T]` pytest covers: 202 + enqueued for both routes; the
  idempotent second click; enqueue failure -> failed row; the pre-check
  refusals still answering in-request; permission denial.

### J3. The job does the work and records the truth

- **AC-J3.1** `[BE]` The job (`app/tasks/flyer_read_tasks.py::read_flyer`)
  loads the reading, re-establishes the reading's company scope, fetches the
  bytes (staged object or attachment), re-asserts the ceiling on the real byte
  length, extracts with artwork, stores the page banners, and writes
  `reading_json`, `byte_size`, `sha256`, `status = done`, `finished_at` in ONE
  commit. A reading made this way is indistinguishable from one the old
  synchronous route made (same banners, same report).
- **AC-J3.2** `[BE]` A refusal the extractor raises (not a PDF, password
  protected, over the ceiling on real bytes, storage fetch failure) marks the
  row `failed` with `error_message` set to the SAME words the synchronous route
  used for that case; any other exception marks it `failed` with a generic
  message plus the exception text. The job never re-raises: the row is the
  record, and a poisoned queue helps nobody.
- **AC-J3.3** `[BE]` The staged upload object is deleted after the job, on
  success AND on failure.
- **AC-J3.4** `[BE]` If the reading was deleted while the job ran, the job
  discards its result, stores no banners, and exits cleanly.
- **AC-J3.5** `[BE]` `GET /flyer-readings` and `GET /flyer-readings/{id}` carry
  `status`, `errorMessage`, `finishedAt` on every row (existing rows read
  `done`); a `processing` or `failed` reading's detail returns an empty report
  rather than an error.
- **AC-J3.6** `[T]` pytest covers the job body end to end against the fixture
  flyer with the in-process fake storage: done transition with the report
  reproducible through GET, failed transition with the exact message for a
  non-PDF, staged object cleanup, and the vanished-row case.
- **AC-J3.7** `[BE]` The existing synchronous read suites keep passing by
  running the job inline after the 202 (a test helper), not by keeping a
  synchronous route alive.

### J2/J3 in the browser

- **AC-FE.1** `[FE]` On "Read the flyer" (either tab), the dialog closes
  immediately on the 202 and a toast reads
  "Reading the flyer in the background - it will appear in your uploads". The
  "can take up to a minute" description is gone; no waiting copy remains.
- **AC-FE.2** `[FE]` The Flyers list gains a **Status** column with a pill:
  Processing / Done / Failed, using the shared `lib/status-pill.ts` palette. A
  Failed pill shows the reason beside it (truncated with the full text on
  `title`).
- **AC-FE.3** `[FE]` The list query polls (every 3 s) while any row is
  Processing and stops when none is; the create hooks invalidate the list so
  the new row appears without a reload.
- **AC-FE.4** `[FE]` A Done row navigates to the review screen exactly as
  today. The review screen, when its reading is Processing, shows a waiting
  state and refetches every 3 s until it is Done; when Failed it shows the
  reason and a link back to the list. The seed panel and dimension review are
  not offered until Done.
- **AC-FE.5** `[FE]` Delete works on any row regardless of status, with the
  same confirmation as today.
- **AC-FE.6** `[T]` vitest covers: the list rendering each of the three pills
  (and the failure reason), the dialog closing on 202 with the toast, and the
  review screen's processing and failed states.
- **AC-FE.7** `[E2E]` Recorded agent-browser evidence run on the local stack
  with the worker up: sidebar clicks to Flyers, Read a flyer, Choose from Files,
  pick the real 36-page flyer, Read the flyer -> dialog closes within a second,
  toast shown, row appears as Processing, flips to Done, click opens the report
  with codes matched. Network log shows the POST at 202 in well under a second
  and no request over a few hundred milliseconds apart from the polling GETs.

### Kept from PR #164

- **AC-K1** `[BE]` Nothing that still runs in-request runs on the event loop:
  the multipart route stays `async def` for the chunked ceiling read and hands
  hashing + staging to `run_in_threadpool`; the from-attachment route stays a
  plain `def`.
