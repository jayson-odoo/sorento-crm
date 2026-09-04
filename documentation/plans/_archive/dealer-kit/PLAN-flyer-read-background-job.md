# PLAN: flyer read as a background job

Status: implemented, verified, reviewed. Ready for PR.
Branch `fm/flyer-read-background-job`.
UAC: `documentation/plans/dealer-kit/flyer-read-background-job-acceptance-criteria.md`
Supersedes the in-request half of `PLAN-flyer-read-hardening.md` (PR #164) and
closes backlog row BL-004. The library picker half of that plan is untouched.
Classification: CORE change inside the existing `dealer_kit` module. One
migration (columns on `dealer_kit.flyer_reading`), one new RQ task module, one
new queue name. No new permission, no new table.

---

## 1. Diagnosis

The captain's screenshot (2026-08-15 evening) shows the "Read a flyer" dialog on
the **Choose from Files** tab, file `UPDATED SORENTO A3 FLYER 202...`, button in
its "Reading the flyer" state, and the toast
`Gateway timeout (504). The API took too long to respond.` That string is
`extractApiError`'s branch for `response.status === 504`
(`sorento_crm_frontend/lib/api-client.ts:43-44`), so a proxy in front of the
backend closed the request with a 504 while FastAPI was still working.

### Measured on this machine (2026-08-15, prod-copy DB, quiet)

Script in the session scratchpad; the same document PR #164 measured against,
`_SORENTO A3 FLYER 2025-2026_compressed.pdf`, attachment
`180abf0c-4353-4ce6-8d5a-1ff68e650a7d`, 21.1 MB, 36 A3 pages, 1252 cards.

| Step | Time |
| --- | --- |
| `AttachmentService.get_file_content_for` (R2 download, 21.1 MB) | **0.94 s** |
| `extract_flyer(data, with_artwork_images=True)` | **18.6 s** |

PR #164 measured the same extraction at 17.7 to 18.2 s quiet and the whole
POST at 39 to 62 s on a loaded machine (banner uploads to R2, commit, report
recompute on top). Nothing about the read got faster; the fix in #164 moved it
off the event loop, which stopped it freezing the worker, and did nothing about
its duration - by design, per its own plan.

### The gateway

Production traffic is `host nginx -> sorento_backend upstream`
(`scripts/blue_green_deploy.sh:5-7`, upstreams in
`/etc/nginx/conf.d/sorento_upstreams.conf`). That host nginx config is NOT in
the repository, and neither is the server-side compose (gitignored, hand-edited
at `/opt/sorento-crm2`, per `.github/workflows/deploy.yml:568-573`). The
`sorento_crm_frontend/nginx.conf` in the repo sets `proxy_read_timeout 300s`
for `/api/v1/`, but that file is the frontend CONTAINER's nginx, which the
blue/green path does not route API calls through. With no directive in the
host config, nginx's `proxy_read_timeout` default is **60 s**, and gunicorn is
started with `--timeout 120` (`sorento_crm/docker-compose.yml:88`), which is
above it. A 40 to 60 s read on the loaded production box, plus a real prod
network to R2 for the download and the 18 banner objects, is exactly the
neighbourhood of a 60 s cut-off; the captain's flyer ("UPDATED", so newer and
possibly larger than the 21 MB copy measured here) sits on the wrong side of it.

Whether the exact value is 60 s or something else, the shape of the conclusion
does not move: the read is tens of seconds of work whose duration grows with the
document, and any design that keeps the HTTP request open for it will meet a
proxy timeout somewhere. The request has to return before the work starts.
Raising the timeout is not on the table - it fixes one flyer and re-breaks on
the next bigger one, and it keeps a designer staring at a disabled button for a
minute.

---

## 2. The design

The catalogue PDF export already does the shape we want
(`app/api/v1/dealer_kit/pages.py::request_export` -> 202 -> RQ job on its own
queue -> a row that flips `pending -> processing -> ready | failed`, watched by
My Downloads). The flyer read follows it. Reuse the same helpers
(`enqueue_job`, `SessionLocal`, `set_company_scope`, `storage_router`).

### 2.1 Where the status lives: on the reading row

The Flyers list (`/dealer-kit/flyer-readings`) is the "my uploads" surface the
dialog lives on, and its rows are `dealer_kit.flyer_reading`. So the reading row
is created at enqueue time, in `processing`, with the SAME id it will have when
done. That is what makes "it appears in my uploads" and "Done links to the
report exactly as today" one thing: the row is there from the first second, and
the report link is `/dealer-kit/flyer-readings/{id}` throughout.

Considered and rejected: a separate `ImportJob` row (`import_jobs`,
superadmin-only "Import Jobs" page - not the designer's surface, and it would
mean two rows describing one read); the `downloads` table (it is a file the
user pulls, not a record they review).

**Migration** (next number after the current head `358_...`; check
`alembic heads` before naming, keep one head, id 32 chars or fewer):

| Column | Type | Note |
| --- | --- | --- |
| `status` | `VARCHAR(16) NOT NULL DEFAULT 'done'` | `processing` / `done` / `failed`. Server default `done` backfills every existing row (they were all read synchronously and successfully) - AC-J3.5. Add a CHECK constraint on the three values. |
| `error_message` | `TEXT NULL` | Why it failed, in the words the request used to say. |
| `finished_at` | `TIMESTAMP NULL` | When the job wrote done/failed. |
| `source_attachment_id` | `UUID NULL` | The library file it came from; NULL for an upload. No FK: a reading is derived working material and must not block or cascade an attachment delete (the bytes are not kept either). |
| `job_id` | `VARCHAR(64) NULL` | The RQ job id, for operators. |
| `sha256` | make **nullable** | The library path has no bytes at enqueue. Filled by the job. |

`byte_size` stays NOT NULL: at enqueue it is the real length for an upload and
the attachment's recorded `file_size_bytes` (or 0) for the library path; the
job overwrites it with the real length. `reading_json` at enqueue is the empty
reading `{"version": READING_FORMAT_VERSION, "pages": []}` so `page_count` /
`code_count` / `headings` read 0 / 0 / [] on a pending row without special
cases.

Partial index for the idempotency lookup:
`(company_id, source_attachment_id) WHERE status = 'processing'` and
`(company_id, sha256) WHERE status = 'processing'`.

Model: `FlyerReadingRecord` gains the columns; add small helpers
`is_done(record)` etc. only if the routes need them.

### 2.2 Service (`app/services/dealer_kit/flyer_reading_service.py`)

Keep the module's existing helpers. Add, and rewire, as follows.

```
FLYER_READ_QUEUE = "flyer_read"
FLYER_READ_JOB_TIMEOUT = 900          # 15 min; the real flyer is 20 to 60 s
STAGING_PREFIX = "flyer-readings/pending/"

class ReadingStatus: PROCESSING = "processing"; DONE = "done"; FAILED = "failed"

def enqueue_reading_from_upload(db, *, filename, data, user_id) -> FlyerReadingRecord
def enqueue_reading_from_attachment(db, *, attachment_id, user_id) -> FlyerReadingRecord
def complete_reading(db, record, *, data, filename) -> FlyerReadingRecord     # the job's core
def fail_reading(db, record, *, message) -> FlyerReadingRecord
def create_reading(db, *, filename, data, user_id) -> FlyerReadingRecord     # KEPT: enqueue-shape row + complete_reading, synchronously (tests, scripts)
```

**`enqueue_reading_from_upload`** (called from the route inside
`run_in_threadpool`, AC-K1):

1. `sha256 = hashlib.sha256(data).hexdigest()`.
2. Idempotency: an existing row in scope with `status = processing` and the same
   `sha256` -> return it, stage nothing, enqueue nothing (AC-J2.4).
3. Stage the bytes: `storage_router.get_backend(storage_router.default_provider())`
   `.upload_file(file_content=data, file_path=f"{STAGING_PREFIX}{uuid4().hex}.pdf",
   content_type="application/pdf")`. Call `storage_router.get_backend` /
   `default_provider` **through the module attribute at call time**, not
   imported by name at module load: `tests/_fake_storage.py::patch_storage`
   patches `storage_router.get_backend`, and a name imported at load would hold
   the real backend and PUT to the live bucket (the very thing that file was
   written to stop). Same rule as `asset_service`.
   As built, a bucket that refuses this PUT is a **502 `FLYER_STAGING_FAILED`**
   ("That flyer could not be stored for reading. Try again in a moment."), not
   the bare 500 an unwrapped driver error would produce. This is the one storage
   failure that can be told to a designer while they are still looking at the
   dialog, and nothing has been written when it fires - the row is created
   AFTER the bytes are parked, so a staging failure leaves no reading claiming
   to be in progress.
4. Create the row: `filename`, `byte_size=len(data)`, `sha256`, empty
   `reading_json`, `status=processing`, `created_by`. Commit (company stamp
   happens here, in the request scope).
5. Enqueue (below). Return the row.

**`enqueue_reading_from_attachment`**: steps 1 to 4 of today's
`create_reading_from_attachment` (scope 404, trashed 404, `assert_pdf_mime`,
recorded-size 413, `extract_key` 422) run exactly as they are, in the request,
on metadata only. Then idempotency on `(source_attachment_id, processing)`.
Then create the row with `filename` from `stored_filename or original_filename`,
`byte_size = int(file_size_bytes or 0)`, `sha256 = None`,
`source_attachment_id`, `status=processing`. Commit. Enqueue. Return. **No
storage call in this path.**

**Enqueue**, shared by both:

```
try:
    job = enqueue_job(read_flyer, str(record.id), staged_provider, staged_key,
                      queue_name=FLYER_READ_QUEUE, job_timeout=FLYER_READ_JOB_TIMEOUT)
    record.job_id = job.id; db.commit()
except Exception as exc:                       # Redis down
    fail_reading(db, record, message=f"Could not queue the flyer read: {exc}")
    discard staged object if any (best-effort, warn on failure)
```

Import `enqueue_job` and the task function **inside** the function (the task
module imports `SessionLocal`; a top-level import here would drag the queue and
the DB engine into every module that touches a flyer). Expose ONE seam tests can
patch: `flyer_reading_service._enqueue(record, staged_provider, staged_key)`
(module-level, monkeypatched by name) - AC-J2.7 asserts against it.

**`complete_reading(db, record, *, data, filename)`** is today's
`create_reading` body from `extract_flyer` onwards, writing INTO the given row
instead of building a new one: extract with artwork, `_store_banners`, then set
`reading_json`, `byte_size=len(data)`, `sha256`, `status=done`,
`finished_at=now`, `error_message=None`; ONE commit (AC-J3.1). It raises the
same `AppException`s it does today (`FLYER_NOT_A_PDF`,
`FLYER_PASSWORD_PROTECTED`); the caller decides what to do with them.

**`fail_reading`**: `status=failed`, `error_message=message[:2000]`,
`finished_at=now`, commit.

**`create_reading`** stays as a synchronous convenience: builds the same
enqueue-shape row and calls `complete_reading` immediately. Existing callers
that are not the two routes (tests, `flyer_seed_service` fixtures, scripts)
keep working. `create_reading_from_attachment` is removed (its pre-checks move
into `enqueue_reading_from_attachment`; its byte fetch moves into the task -
see 2.3). Grep for callers before deleting.

### 2.3 The task (`app/tasks/flyer_read_tasks.py`, NEW)

```
def read_flyer(reading_id: str, staged_provider: str | None, staged_key: str | None) -> dict
```

Shape mirrors `dealer_kit_export_tasks.generate_catalogue_pdf`: own
`SessionLocal()`, `try / except Exception -> mark failed / finally close`,
returns a small dict, never raises (AC-J3.2). Steps:

1. `set_company_scope(db, None)` and load the row by id. Missing -> discard the
   staged object, return `{"status": "gone"}` (AC-J3.4).
2. Narrow the scope: `set_company_scope(db, frozenset({row.company_id}))` when
   `company_id` is set. This is what makes the attachment lookup and the banner
   inserts land in the reading's own company; the worker has no request to
   scope by. (`register_company_scope_listeners()` is already called by
   `worker.py`.)
3. Bytes:
 - staged: `storage_router.get_backend(staged_provider).download_file(staged_key)`.
 - library: today's steps 5 and 6 of `create_reading_from_attachment`
     (`AttachmentService(db).get_attachment`, trashed check, `extract_key`
     check, `get_file_content_for`, wrapped so a storage failure becomes
     `FLYER_SOURCE_UNREADABLE` with the same words), then
     `assert_within_limit(len(data))`.
4. **Re-load the row** (`db.expire`/re-query) after the fetch and before
   writing; if it is gone, stop (AC-J3.4). Then `complete_reading(...)`.
5. `except AppException as exc: fail_reading(db, row, message=svc.refusal_message(exc))`;
   `except Exception as exc: fail_reading(db, row, message=f"The flyer could not be read: {exc}")`
   with `logger.exception`.
6. `finally`: delete the staged object when there is one, best-effort with a
   warning (AC-J3.3); `db.close()`.

**As built, one correction to step 5.** This plan wrote `exc.message`, and there
is no such attribute: `AppException` is an `HTTPException` whose `detail` is the
`{message, detail, code}` dict the global handler serialises. Written as
planned, the read of the missing attribute raised `AttributeError` INSIDE the
handler for the original refusal - so a password-protected flyer left its row
`processing` forever with nothing recorded about why, which is the one outcome
this whole design exists to prevent. `flyer_reading_service.refusal_message(exc)`
is the shared extraction (same shape as `bulk_update_registry._exc_message`), and
`create_reading` was carrying the same latent bug on its own failure path.

Extraction runs in the RQ work-horse (a forked process on the worker), so no
threadpool is needed there. Nothing about `run_in_threadpool` in
`flyer_readings.py` is dropped for what still runs in-request (AC-K1).

**No report recompute in the job.** The brief lists it, PR #164 did it inline
only to build the 201 body. The report is never stored (that is a binding
design of this module) so there is nothing to recompute INTO; the review screen
computes it on GET (0.9 s, plain `def`, off the loop). Recorded here as a
deliberate deviation.

### 2.4 Worker

`worker.py` default `WORKER_QUEUES` becomes
`imports,respond_io,catalogue_render,flyer_read`. Own queue, for the same
reason `catalogue_render` has one: a 20 to 60 s CPU-bound PyMuPDF read should
not sit in front of every Excel import, and listing it LAST gives imports
priority (RQ drains queues in list order). One worker process serves all four
serially; that is fine at today's volume (a handful of reads a season).

The production compose is hand-edited on the server. If it pins
`WORKER_QUEUES` explicitly, `flyer_read` must be added there or the read never
runs; the PR description says so, the way
`CONTAINER-PDF-EXPORT-RUNBOOK.md` did for `DEALER_KIT_PRINT_BASE_URL`. If it
does not pin it (the runbook's reading of the situation), the new default is
picked up on the next deploy.

Locally, every worktree shares one Redis, so a lane's worker must be started
with `WORKER_QUEUES=flyer_read` (or its own Redis db) so another lane's worker,
built from a branch without this task module, cannot pick the job up and fail
it with an ImportError.

### 2.5 Routes (`app/api/v1/dealer_kit/flyer_readings.py`)

| Route | Before | After |
| --- | --- | --- |
| `POST /flyer-readings` | 201 `FlyerReadingOut` after 20 to 60 s | **202 `FlyerReadingSummary`** (`status: processing`). Still `async def`; `_read_within_limit` unchanged; then `await run_in_threadpool(svc.enqueue_reading_from_upload, ...)`. |
| `POST /flyer-readings/from-attachment` | 201 `FlyerReadingOut` | **202 `FlyerReadingSummary`**. Plain `def`; `svc.enqueue_reading_from_attachment(...)`. |
| `GET /flyer-readings` | summaries | summaries + `status`, `errorMessage`, `finishedAt`. |
| `GET /flyer-readings/{id}` | detail | detail + the same three fields; a processing/failed row returns an empty report (no special-casing needed - the empty reading matches nothing). |
| `DELETE /flyer-readings/{id}` | hard delete | unchanged; works on any status (the job tolerates a vanished row). |
| `POST .../seed`, `.../dimensions/apply` | - | Refuse a reading that is not `done` with 409 `FLYER_NOT_READ_YET` ("That flyer is still being read" / "could not be read"). Cheap guard; the FE hides both until Done anyway. |

`_summary()` gains the three fields. `_detail()` unchanged otherwise. Update the
module docstring: the "queue is deliberately NOT built" paragraph is now wrong
and must go, replaced with what was measured and why the queue was built.

**Schemas** (`app/schemas/dealer_kit.py`): `FlyerReadingSummary` gains
`status: str`, `error_message: Optional[str] = Field(None, serialization_alias="errorMessage")`,
`finished_at: Optional[datetime] = Field(None, serialization_alias="finishedAt")`.
`FlyerReadingOut` inherits them.

### 2.6 Frontend

**Contract block** at the top of
`app/(protected)/dealer-kit/services/flyerReadingService.ts` is rewritten for
the two POSTs (202, summary, `status`), and `FlyerReadingSummary` gains
`status: 'processing' | 'done' | 'failed'`, `errorMessage: string | null`,
`finishedAt: string | null`. `uploadFlyerReading` /
`createFlyerReadingFromAttachment` return `FlyerReadingSummary`. An absent or
unrecognised `status` normalises to `done`, never `processing`: every row that
predates migration 359 was read in the request and succeeded (which is what the
column's server default says), and guessing `processing` for them would poll
forever for a job nobody queued.

**Hooks** (`flyer-readings/hooks/useFlyerReadings.ts`):

- `useFlyerReadingsQuery`: `refetchInterval: (query) => query.state.data?.some(r => r.status === 'processing') ? 3000 : false` (AC-FE.3).
- `useFlyerReadingQuery`: same shape, polling while `data?.status === 'processing'` (AC-FE.4).
- `onFlyerReadingCreated`: invalidate the list, `toast.success('Reading the flyer in the background - it will appear in your uploads')`. No detail-cache seeding (there is no report yet), no `router.push`.
- Mutation result type becomes `FlyerReadingSummary`.

**Dialog** (`UploadFlyerDialog.tsx`): `onSuccess` -> `onOpenChange(false)` only
(no navigation). Description copy: drop "is read straight away and can take up
to a minute"; keep one line, e.g. "You get a report of what was found before
anything is created." Button label while pending stays "Reading the flyer" (it
is now sub-second). Fix the component docstring (it currently explains why
there is no job).

**List** (`FlyerReadingsList.tsx`): new **Status** column after Flyer:
`<span className={`${STATUS_PILL_BASE} ${statusPillClass(status)}`}>` with
labels Processing / Done / Failed; a Failed row shows `errorMessage` beside
the pill, `truncate` + `title`. Add `processing: 'bg-amber-100 text-amber-800'`
to `lib/status-pill.ts` (`done` and `failed` already exist). Row click
unchanged (any row navigates; the review screen copes). Delete unchanged
(AC-FE.5). Update the empty-state / header copy only if it mentions waiting (as
built: it does not, so it is untouched).

Test ids the pills and states are found by: `dk-fr-status-pill`,
`dk-fr-status-reason` (list), `dk-fr-review-processing`, `dk-fr-review-failed`
(review screen).

**Review screen** (`[readingId]/components/FlyerReviewScreen.tsx`): when
`data.status === 'processing'` render a waiting card ("Reading this flyer - the
report appears here when it is done") in place of the report sections and
seed panel, with the header still showing the file; when `failed`, an
`Alert variant="destructive"` with `errorMessage` and a link back to Flyers.
Sections + `SeedPanel` + `DimensionReviewSection` render only when `done`
(the ADR "always render every section" is about empty DATA; a reading that has
not happened yet has no sections to be empty). Loading and error states as
today.

As built (S3), three details this section did not spell out:

- The **promotion picker** is hidden until `done` too. It asks "which printed
  products does this offer not carry", which is a question about a report; a
  picker over a report that does not exist changes nothing and invites a click.
- The header's **page and code counts** are omitted until `done` - "0 pages, 0
  product codes" on a flyer being read right now is a figure that reads as an
  answer. The size and the time stay, and the timestamp says "added" rather than
  "read" until it is. The "Matching against the product master" line is gated on
  `done` as well, so the polling refetch does not claim a match run is happening.
- The failed alert's way out is labelled **"Read another flyer"** (journey step
  J4), pointing at the list, rather than the plain "Back to flyers" wording.

### 2.7 Test seams (agree before Phase 2 code)

- `flyer_reading_service._enqueue` - patched to a recorder in route tests.
- `tests/_fake_storage.patch_storage` covers staging, banners and the task's
  staged download, as long as the service and the task call
  `storage_router.get_backend` through the module.
- A test helper `run_read_inline(db, reading_id)` that calls
  `read_flyer(...)` with the test's session (pass the session in via a
  keyword-only `_db=` override on the task, defaulting to `SessionLocal()`), so
  the existing 800-line read suites become `POST -> 202 -> run inline -> GET`
  without touching Redis. This is AC-J3.7.

As built, `tests/_flyer_read.py` carries three names and they divide like this:

- `patch_flyer_read(monkeypatch, db)` in a suite's `api` fixture - replaces
  `_enqueue` with a recorder bound to the test's session. `.queued` is the
  assertion surface for "one job, right arguments"; the real
  `_enqueue_or_fail` around it is untouched, so a test can raise from the seam
  and exercise the Redis-is-down path for real.
- `finish_reads()` - runs every read queued since the last call and returns the
  job dicts, so a module-level `_upload` helper can drive it without threading
  the recorder through each test's fixture unpacking.
- `run_read_inline(db, reading_id, ...)` - for a test that built the row itself.

One thing the suites had to learn from this (it cost a false failure in
`test_the_list_is_newest_first`): two POSTs of the SAME bytes with the first
still `processing` are one reading, not two, because that is exactly the
idempotent re-click of AC-J2.4. A test that wants two rows finishes the first
read before posting the second.

---

## 3. Slices

Order matters: S1 unblocks the tests, S2 and S3 are the feature, S4 is FE, S5
is the evidence run.

- **S1** Migration + model + schema fields; `create_reading` kept synchronous
  over the new columns; existing suites green (they still call the routes,
  which at this point still read inline - S1 is additive).
- **S2** Service: `enqueue_reading_from_upload`, `enqueue_reading_from_attachment`,
  `complete_reading`, `fail_reading`, `_enqueue` seam. Task module. Worker
  default queue. Routes to 202. Existing suites migrated to the inline helper.
  New pytest per AC-J2.7 and AC-J3.6.
- **S3** FE: service contract, hooks (polling, toast, no push), dialog, list
  status column, review screen states, `status-pill` entry. Vitest per AC-FE.6.
- **S4** Evidence run per AC-FE.7 on this lane's stack (backend :8011 single
  worker, `WORKER_QUEUES=flyer_read` worker, prod FE build :3011,
  `AGENT_BROWSER_SESSION=flyer-read-background-job`), recorded below.
- **S5** Docs: module docstrings, this plan's Status, backlog BL-004 -> Done,
  BL-00x new row for "stuck processing sweeper" (a worker crash mid-job leaves
  a row processing forever; out of scope here).

## 4. Phasing note

Phase 1 (FE against a mock) is folded into S3 against the contract in 2.6,
built in parallel with S2 rather than before it: this is a fix to a shipped
screen whose only new UI is a status column, a toast and two review-screen
states, and a throwaway mock service would be deleted the same day. Same
deviation PR #164 recorded, for the same reason. Vitest for the FE mocks the
service module, so the FE tests do not depend on the backend landing first.

## 5. Definition of done

`PRINCIPLES.md` gates: (1) FE off any mock and showing real data - the evidence
run; (2) backfill - the `status` server default writes `done` onto every
existing row, and the migration is checked against the prod-copy DB
(`SELECT status, count(*) FROM dealer_kit.flyer_reading GROUP BY 1`); (3) no new
permission - n/a; (4) new columns reach the FE - `_summary()` is the ONE
builder, and vitest asserts the pill from a summary carrying `status`; (5)
verified from the user's perspective at 375 and 1280 by sidebar clicks.

## 6. Evidence run (S4)

Run 2026-08-16, agent-browser 0.27.0 headless, private session
`flyer-read-background-job`, this lane's stack only (backend :8011 single
uvicorn worker, `flyer_read` RQ worker on Redis db 11, FE `npm run dev` :3011).
Reached by sidebar clicks from `/`, never a deep URL: Dealer Kit -> Flyers.

What the walk proved:

| Step | Result |
| --- | --- |
| Existing rows after migration 359 | all read **Done** (the server-default backfill, seen in the UI) |
| Dialog description | "You get a report of what was found before anything is created." No waiting copy |
| `Choose from Files` -> picker -> the real `_SORENTO A3 FLYER 2025-2026_compressed.pdf` (21.1 MB, 36 pages) | selected, dialog shows the filename |
| `Read the flyer` | dialog **closed at once**; toast "Reading the flyer in the background - it will appear in your uploads"; the row was already listed as **Processing** on the next snapshot (2.77 s later, which is the snapshot round trip, not the request) |
| `POST /api/v1/dealer-kit/flyer-readings/from-attachment` | **202 in 0.162 s** (backend log). No other request in the walk exceeded a few hundred ms apart from the 3 s polling GETs |
| Console | no errors |

### The walk also found a real defect, and it is not in this feature

The row then sat at Processing and never flipped, because the RQ work-horse was
**segfaulting** (`Work-horse terminated unexpectedly; waitpid returned 11`).
Diagnosed with `PYTHONFAULTHANDLER=1`: the child dies inside
`psycopg2.connect` -> libpq `PQconnectPoll` -> `pg_GSS_have_cred_cache` ->
`libkrb5` `api_macos_ptcursor_next` -> `libxpc`. XPC is not fork-safe, so the
child dies before the task's first line, which is why nothing marked the row
failed.

- It is **macOS only**. The faulting frames are literally the macOS ccache API;
  Linux libpq has no XPC path, so the production worker does not take it. No
  application code changes because of this.
- It is **not the scheduler's fault either**, though the scheduler is what makes
  it certain: `ENABLE_SCHEDULER=true` has APScheduler open DB connections in the
  parent before the first fork, so the child inherits initialised XPC state.
- `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` does not cover it. That is the
  Obj-C abort, signal 6; this is a segv, signal 11.

Measured, same flyer, same worker, scheduler ON both times:

| Worker env | Outcome |
| --- | --- |
| as documented before this branch | segfault, 3 of 3 jobs, row stuck `processing` |
| `ENABLE_SCHEDULER` off | `done`, 36 pages |
| `PGGSSENCMODE=disable`, scheduler ON | **`done` in 25 s**, 36 pages |

`CLAUDE.md` now carries `PGGSSENCMODE=disable` in the dev-session worker command
and a lesson explaining the signature, because this kills every queue on a dev
Mac and the identical stack is in other lanes' crash reports
(`~/Library/Logs/DiagnosticReports/Python-*.ips`), including one from 2026-08-14.

The stuck row was also a live confirmation of **BL-010**: nothing sweeps a
reading whose work-horse died, so it stays `processing` forever. The idempotency
guard then correctly refused to start a second read of the same attachment
(AC-J2.4 working as designed), which is what made the stuck row visible.

Test rows created by this walk were deleted afterwards.

### The full walk, once the worker survived its fork

Re-run 2026-08-16 01:26 with `PGGSSENCMODE=disable` on the worker, everything
else identical (backend :8011, `flyer_read` worker, FE dev :3011, sidebar clicks
from `/`). This is the leg that matters, and it now completes:

| Step | Result |
| --- | --- |
| `Read the flyer` | dialog closed at once, toast "Reading the flyer in the background - it will appear in your uploads", row listed as **Processing** |
| `POST .../from-attachment` | **202** |
| Pill, no reload, no interaction | **Processing -> Done between the 10 s and 20 s poll** (the read itself took about 25 s of worker time for 21.1 MB / 36 pages) |
| Click the Done row | `/dealer-kit/flyer-readings/35292a17-...`, header "36 pages, 998 product codes, 20.1 MB", matched / unmatched / duplicate sections and the promotion picker all render |
| Delete from the list | "Confirm delete" dialog with "This action cannot be undone", row gone after confirming |
| Console | no errors at any point |

### Request latency, honestly

| Request | Measured |
| --- | --- |
| `POST .../from-attachment`, warm process | **0.162 s** |
| the same POST as the first call after a cold boot | 2.50 s (one-off import cost of the attachment and storage modules, not per-request work) |
| `GET /flyer-readings` (the list, polled) | 0.22 to 0.59 s |
| `GET /flyer-readings/{id}` (the report) | **6.3 s** on a loaded machine |

The acceptance line was "no request longer than a few hundred ms", and the write
path meets it. The report GET does not, and it is worth being straight about
why: it is the match run over 998 codes, it predates this branch (PR #164
measured 0.875 s for it on a quiet machine), and it is a plain `def` route so it
is threadpooled rather than on the loop. It is not what produced the 504 and
nothing here made it slower, but a 6 s report open on a busy box is a real
number and belongs in the backlog rather than in a footnote.

Test rows created by both walks were deleted afterwards, one of them through the
UI's own confirm-delete dialog.
