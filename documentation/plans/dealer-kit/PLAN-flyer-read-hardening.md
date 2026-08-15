# PLAN: flyer read hardening

Status: implemented, verified, reviewed. Ready for PR.
UAC: `documentation/plans/dealer-kit/flyer-read-hardening-acceptance-criteria.md`
Classification: CORE change inside the existing `dealer_kit` module. No new
module, no new schema, no new permission, no new table, no migration.

Two things, one branch:

- **A.** The flyer read jams the system. Diagnose first, then fix what the
  evidence names.
- **B.** Let the designer pick the flyer from the file library instead of only
  from their laptop.

---

## A. Diagnosis

The captain's two observations were in tension and had to be reconciled before
anything was changed:

1. "the flyer uploading, catalogue building is jamming the system" (desktop).
2. "eh but if i use in phone is ok" (same period).

A fully dead backend stalls every client, so observation 2 was the constraint
that had to survive the explanation, not the one to explain away.

### How it was measured

Local stack in a disposable worktree, never production. Backend booted on port
8010 (one worker) and 8011 (four workers, matching the production gunicorn line)
against the local database. The real document
`_SORENTO A3 FLYER 2025-2026_compressed.pdf` was used: 20.1 MB, 36 A3 pages, 998
distinct codes, 961 of which match the master. While a read was in flight, a
second shell polled `GET /health` every 0.5 seconds and recorded per request
latency.

### What was measured

| Measurement | Result |
| --- | --- |
| `extract_flyer` on the real flyer, quiet machine, in process | **17.7 to 18.2 s** |
| `POST /flyer-readings` end to end, loaded machine | **39 to 62 s** |
| `GET /health` issued during that read, **1 worker** | **57.5 s** (idle: 6 to 100 ms) |
| `GET /health` during that read, **4 workers** | 59 of 60 probes normal, worst 1.9 s |
| `GET /flyer-readings/{id}` (report recompute, 998 codes) | 0.875 s, no probe impact |
| `POST /flyer-readings/{id}/seed` (961 products, 340 collections, 36 sections) | 2.83 s, no probe impact |
| `extract_flyer` run in a worker thread, event loop lag | max 830 ms, p50 68 ms, zero ticks over 1 s |

Profile of the extraction (cProfile, 29.7 s under the profiler):

- `_spans` calling PyMuPDF `get_text("dict")`: 21.3 s, 72 percent. Native.
- `_artwork` calling `get_image_info`: 6.6 s, 22 percent. Native, including
  3.3 s of pixmap md5.
- Our own Python (`_read_card`, `_centre_x`): 2.0 s, under 7 percent.

So the cost is PyMuPDF's, not an accidental quadratic of ours, and there is no
cheap algorithmic win hiding in this module.

### Trigger, masking condition, symptom

**Trigger.** `upload_flyer_reading` (`app/api/v1/dealer_kit/flyer_readings.py:207`)
is `async def` and calls `svc.create_reading` synchronously. That call runs
`extract_flyer` over the whole document, then uploads nine page banners to
object storage (two objects each), then commits, and the route then calls
`_detail`, which recomputes the match report. All of it executes on the event
loop, for 40 to 60 seconds with the real document.

**Masking condition.** Production runs `gunicorn --workers 4`
(`sorento_crm/docker-compose.yml:84-92`). One blocked worker is one quarter of
capacity, not the whole backend. Measured: with four workers, 59 of 60
fresh-connection probes were unaffected. The desktop browser that started the
upload is separately parked on its own 40 to 60 second request, and holds
keep-alive connections (`--keep-alive 5`) that can be pinned to the blocked
worker for its duration. The phone opens its own fresh connections and was not
waiting on any upload, so it lands on a free worker and behaves normally.

That is the reconciliation. Observation 2 is not evidence against a blocking
loop; it is evidence about worker count. On a single worker the same read makes
the entire backend unavailable for 57.5 seconds, which is what a future
single-worker deployment or a second concurrent read would produce.

**Symptom.** For the duration of a read: one worker serves nothing at all; the
uploading tab hangs; any client connection pinned to that worker hangs with it.

### What was ruled out, and on what evidence

- **The catalogue build / seed.** 2.83 s for 961 products, and it is a plain
  `def` route, so FastAPI already threadpools it. The probe was untouched
  throughout. It was never part of the jam, and the seed docstring's "about
  0.4 s matching" claim is close enough to be harmless.
- **The report recompute on GET.** 0.875 s, plain `def`, no probe impact.
- **The other dealer-kit routes.** A sweep of `app/api/v1/dealer_kit/` finds
  exactly one `async def` handler, the upload. Everything else is plain `def`.
- **Connection pool exhaustion.** The blocking window holds a single session for
  a single request. Nothing about the measurement is pool shaped.
- **A purely client-side stall.** Ruled out by the 57.5 s `GET /health`: that
  probe was a separate process on a separate connection, and it waited.

### Where the wrong number came from

Three docstrings assert the real 36 page flyer reads in "about a second"
(`flyer_readings.py:12-17`, `flyer_reading_service.py:19-25`,
`UploadFlyerDialog.tsx:24-27`), and the in-request design was justified by that
number, with an explicit stated threshold: "It stops being true if extraction
reaches roughly ten seconds". Measured, it is 17 to 18 seconds quiet. By its own
criterion the reasoning had already lapsed. The number is corrected in this
branch; the queue is deliberately not built (see below).

---

## A. The fix

**Move the heavy work off the event loop, keep the route synchronous to the
caller.** `await run_in_threadpool(...)` from `fastapi.concurrency`, which is
already this repo's idiom (`app/api/v1/resources/attachments.py` uses it in ten
places for exactly this reason: hashing, storage puts, zip validation).

The upload route keeps `async def`, because `_read_within_limit` genuinely needs
`await file.read(...)` to enforce the ceiling as the bytes arrive, which is a
deliberate design worth preserving. Everything after that read moves into the
threadpool: `create_reading` and the `_detail` that follows it.

Validated before proposing: PyMuPDF releases the GIL enough for this to work.
Running `extract_flyer` in a worker thread while an asyncio loop ticks gives a
maximum loop lag of 830 ms and zero ticks over one second, against a 57.5 s
freeze today. This check was not optional. A C extension that holds the GIL
would have made the threadpool fix a no-op, and the plan would have had to go
straight to the queue.

**What this does and does not buy.** It stops one read from freezing a worker.
It does not make the read fast: it is still 15 to 60 seconds of work, and the
designer still waits. That is accepted for now, and the queue is explicitly not
built in this branch, per the brief. What changes is that the reasoning is no
longer resting on a wrong number: the docstrings now record the measurement and
name the queue as the next step when artwork rasterisation lands, so the
decision can be re-taken on facts.

**Sweep.** All other dealer-kit routes are plain `def` and are confirmed, not
assumed, to be threadpooled by FastAPI. No other change is needed there.

Out of scope by instruction: `ai_extract.py`, filed separately as
`ai-extract-blocking-loop` and since fixed (plain `def`, no streaming ceiling
to keep) in `documentation/plans/ai-extract/PLAN-ai-extract-off-the-loop.md`,
whose Sweep section and BL-009 record the rest of the class.

---

## B. Read a flyer that is already in the system

### What already exists

A reusable "pick an existing attachment" dialog already exists and is already
reused by four modules: `ComplaintLinkAttachmentBrowserDialog`, in
`app/(protected)/complaint-management/complaints/components/`. It renders the
folder tree plus a searchable, checkbox file list, supports
`maxSelections={1}`, and is imported today by complaints, purchase requests,
stock inquiries and packing lists. Two near-identical forks exist under products
and promotions; they are not touched here and are logged to the backlog.

Reuse it. Two gaps have to close first:

1. It is link-oriented: it always calls an injected
   `linkAttachment(entityId, attachmentId)` and closes. It needs an optional
   `onConfirm(selected)` escape hatch for a pick-and-return flow.
2. It has no type filter prop, and the backend list endpoint has no mime filter
   at all (`attachment_type_id` is a document class, not a mime type).

### Backend

**1. Mime filter on the attachments list.** Add optional `mime_type` /
`mime_types` query params to `GET /api/v1/resource-management/attachments/`,
following the existing `attachment_type_id` / `attachment_type_ids` pair
convention, and thread them into `AttachmentService.list_attachments`. The
`Attachment.mime_type` column already exists and is already selectable and
sortable (`app/services/resources_service.py:1084-1085`); only the filter is
missing. Omitting the params must leave the endpoint's behaviour exactly as it
is: this endpoint has many callers.

**2. New route: create a reading from an attachment.**

```
POST /api/v1/dealer-kit/flyer-readings/from-attachment
body: { attachmentId, promotionId? }  ->  201 FlyerReadingOut
```

Plain `def`, so FastAPI threadpools it: it does a storage download plus the same
extraction, and must not sit on the loop either. Same `dealer_kit.page.edit`
permission as the upload, declared the same way, so a caller without it gets the
same 403 naming the same slug.

Order of operations, and the order matters:

1. Load the attachment through the normal ORM path. Company scope is enforced by
   the global `do_orm_execute` listener (`app/services/company_scope.py:208`),
   so an attachment outside scope simply is not found. Not found is a 404, never
   a 403, matching `get_reading`'s reasoning: a 403 would confirm the id exists.
2. Refuse a non-PDF mime with the existing `FLYER_NOT_A_PDF` message.
3. Refuse an oversized file from the attachment's RECORDED size, with the
   existing `assert_within_limit`, **before** fetching bytes. Downloading 200 MB
   to then refuse it is the version of this that costs money.
4. Fetch bytes with `AttachmentService.get_file_content`
   (`app/services/resources_service.py:2000`), which dispatches S3 or R2 per
   row.
5. Re-assert the limit on the actual byte length, because the recorded size is
   metadata and metadata drifts.
6. Hand the bytes to the same `svc.create_reading` with the attachment's
   filename. From here the two sources are the same code path, which is what
   makes "indistinguishable once created" true rather than aspirational.

The reading lands in the caller's company scope by the same stamping the upload
uses. No new column, no new permission, no migration.

**3. Upload route untouched** beyond moving its heavy call into the threadpool.

### Frontend

**Dialog.** `UploadFlyerDialog` gains a second source. Two tabs inside the
existing dialog: "Upload a file" (default, unchanged) and "Choose from Files".
Switching tabs does not clear the other tab's selection. No explanatory prose
beyond the existing one-line hint, per the design mandate.

**Picker.** Move `ComplaintLinkAttachmentBrowserDialog` to
`components/common/LinkAttachmentBrowserDialog.tsx` and update its four existing
import sites. It is used by four modules already and a fifth importing it out of
`complaint-management/complaints/components/` is not defensible. The move is
mechanical; no behaviour changes. Then add the two props it needs: optional
`onConfirm(selected)` and an optional mime filter passed through to
`getAttachments`. Both are additive and default to today's behaviour.

**Service and hook.** `flyerReadingService.ts` gains
`createFlyerReadingFromAttachment(attachmentId, promotionId?)` next to the
existing `uploadFlyerReading`, using `apiFetch` and `extractApiError` like its
neighbour. `useFlyerReadings.ts` gains the matching mutation hook. Both sources
land on the same review screen by the same `router.push`.

---

## Phasing

This is a fix to a shipped feature, not a new surface, so Phase 1 is scoped to
the one genuinely new piece of UI (the second tab and the picker wiring) and is
built against the real endpoints as they land rather than against a mock service
that would be deleted the same day. That deviation from the standard Phase 1
mock is recorded here and in the PR description.

- **S1.** Threadpool the read. Regression test on the shape. Docstring
  corrections. Sweep confirmed.
- **S2.** Mime filter on the attachments list, with tests that the unfiltered
  behaviour is unchanged.
- **S3.** From-attachment route, with tests: happy path, auth denial,
  out-of-scope 404, non-PDF, oversized, and equivalence with the upload path.
- **S4.** Move the shared picker to `components/common`, add `onConfirm` and the
  type filter prop, update the four import sites. Vitest for the new props.
- **S5.** The dialog's second tab, service, hook. Vitest for both tabs.
- **S6.** Evidence run for the library path, sidebar clicks, confirming the
  from-attachment call reaches the backend. Originally a Playwright spec; see
  "The e2e spec, and why it is not here" below.

## After the fix, measured the same way

Same repro, same document, same probe, single worker:

| Measurement | Before | After |
| --- | --- | --- |
| `GET /health` during a read, quiet machine | **57.5 s** | **0.69 s max**, 0 of 42 probes over 1 s |
| `GET /health` during a read, loaded machine | (not taken) | 1.54 s max, 4 of 52 probes over 1 s |
| `POST /flyer-readings` end to end | 39 to 62 s | 17.8 s quiet, 35.3 s loaded |

The loaded row is reported rather than dropped, because it is the one that does
not fully meet AC-J1's "under one second" and the reason matters. It was taken
with the frontend production server, a Chrome instance and another agent's test
suite running on the same machine. The residual is GIL handoff during PyMuPDF's
native work, not the loop being blocked: the loop keeps ticking throughout,
which is the difference between 1.5 s and 57.5 s. If it ever needs to be flat,
that is the queue, not a bigger threadpool.

Verified in a real browser (production build, sidebar clicks, not a deep URL):
the library path reaches the review screen and the backend logs
`POST /api/v1/dealer-kit/flyer-readings/from-attachment - Status: 201 - Duration: 1.092s`.
At **375px and 1280px** the list, both dialog tabs and the nested picker have no
horizontal overflow, the picker's confirm button is reachable, and after the
nested dialog closes `body` keeps `pointer-events: auto` and a real click, with
actionability checks rather than a synthetic event dispatch, lands on the outer
dialog. That last check was the reviewer's specific concern about nesting one
Radix modal inside another.

## The e2e spec, and why it is not here

This branch originally added
`sorento_crm_frontend/e2e/dealer-kit-flyer-library-read.spec.ts` for AC-A10. It
was removed before merge under a standing order that no project carries a
playwright trace: a NEW spec is a new trace, so fixing it and shipping it was
not an option. AC-A10 is met instead by an agent-browser evidence run whose
steps and output are recorded in the commit.

Two things worth keeping honest about that trade:

- **The library path ships with no committed regression guard.** A later change
  can break it without a test going red. The behaviour is verified, but only at
  a point in time.
- **The spec was also wrong.** Its `waitForURL(/attachments/)` could never
  match, because the Files entry always lands on
  `/resource-management/attachment-directories`. It was found by the pipeline's
  test step, not by review, and it would have failed on first run. That is worth
  recording because it is an argument on both sides: the spec was load-bearing
  enough to catch, and shallow enough to be wrong in a way nobody noticed.

The 40 pre-existing specs are untouched, along with `playwright.config.ts` and
the dependency. What replaces them repo-wide is a separate open decision.

## AC-A10 and AC-A11: the evidence run

Run with `agent-browser` 0.27.0, headless, on 15 Aug 2026. Chrome is uninstalled
on this machine and playwright is not used, so this is the sanctioned tool.

Stack: worktree backend on `:8010` with a single worker, worktree production
build on `:3011`, real login through the sign-in form (no minted cookie). The
whole journey is reached by **sidebar clicks only** - never a deep URL - because
a deep URL hides a missing nav entry, wrong `moduleKey` or broken permission
gating, which is exactly what AC-A10 is asserting about.

**Run it in your own session.** The shared `default` agent-browser session is
driven by every other agent on the machine; the first attempt at this walk had
its tab navigated to another lane's stack (`localhost:3022`) mid-run and failed
on refs that had been valid a second earlier. Set `AGENT_BROWSER_SESSION` to
something of your own and the walk is stable. `agent-browser session list` shows
who else is up.

Steps, both widths:

1. `set viewport <w> <h>` **first** - it resets the browsing context, so a
   viewport set after login throws the session away.
2. `open /signin`, fill the form, `Continue`. Below the breakpoint the sidebar is
   behind the header menu button, so open that first; the clicks after it are the
   same on both widths.
3. Sidebar: `Dealer Kit` -> `Flyers`. Lands on `/dealer-kit/flyer-readings`.
4. `Read a flyer` -> the dialog reports
   `Upload a file selected=true | Choose from Files selected=false` (AC-A7).
5. `Choose from Files` -> `Choose a file` opens the shared picker, titled
   "Choose a flyer". Its list is every attachment in the library and all of it is
   PDFs (AC-A8), fetched with the six positive mime spellings (AC-A6):
   `GET /api/v1/resource-management/attachments/?...&mime_types=application%2Fpdf&mime_types=application%2Fx-pdf&mime_types=application%2Facrobat&mime_types=applications%2Fvnd.pdf&mime_types=text%2Fpdf&mime_types=text%2Fx-pdf` -> 200
6. Pick one file: the picker reports `Selected (1)` (single select), and
   `Use this file` returns the filename to the dialog, which now reads
   `Flyer PDF <name> / Change file`.
7. `Read the flyer` -> the review screen.

What each width produced:

| | 1280x900 | 375x812 |
|---|---|---|
| File | `Tera CB2519SS CB2839.pdf` (1 page, 155 KB) | `Mocha A3 Flyer 13032026_compressed (1).pdf` (16 pages, 26.5 MB) |
| Call | `POST /api/v1/dealer-kit/flyer-readings/from-attachment` -> **201** | same -> **201** |
| Route reached | `/dealer-kit/flyer-readings/f811b523-...` | `/dealer-kit/flyer-readings/399ecc86-...` |
| Read time | ~4s | ~54s |
| `Use this file` | enabled, in viewport | enabled, in viewport |
| Horizontal overflow, list | none (`scrollWidth 1280 == innerWidth`) | none (375 == 375) |
| Horizontal overflow, review | none | none |
| Console errors | none | none |

Backend, same request:

```
POST /api/v1/dealer-kit/flyer-readings/from-attachment - Status: 201 - Duration: 1.473s
```

No multipart upload was made in either run: the only flyer-readings write is the
from-attachment POST, which is the second half of AC-A10.

Two honest notes. The 26.5 MB flyer took **54 seconds**, at the far end of the
"can take up to a minute" the dialog now promises and a fresh argument for the
enqueue-and-watch item in the backlog. And both files extracted zero product
codes, so the review screen shown is its empty-report shape; the matched-code
report is covered by the extraction suites, not by this walk. Both readings were
deleted through the API afterwards, so the run left nothing behind.

## Deviations from this plan, recorded during implementation

1. **A 502 `FLYER_SOURCE_UNREADABLE`** was added to the from-attachment route to
   wrap a storage download failure. Without it a bucket error reaches the global
   handler and the designer sees "Internal server error" with no words, for a
   thing they can work around by uploading the file instead. Accepted: it is a
   message, not a new permission or column.
2. **The shared picker gained `title` and `confirmLabel`** on top of the two
   props this plan named. "Link Existing Attachment" is the wrong copy for a
   pick-and-return flow, and hardcoding a second wording inside the component
   would have been worse. Accepted.
3. `mime_type` / `mime_types` are threaded through the `neighbours` pager as
   well as the list query, so the two cannot drift.

## Definition of done

The five gates in `PRINCIPLES.md`. Notes specific to this branch: no new
permission (gate 3 is not applicable, and deliberately so, matching S7.3's
reasoning); no new column (gate 4 not applicable); no backfill (gate 2 not
applicable, nothing gains a column). Gates 1 and 5 apply in full.

## Backlog

Four items are deferred here, and they live as rows **BL-004 to BL-007** in
`documentation/backlogs/backlog.md`, which is the single register for deferred
work: the enqueue-and-watch read, the two remaining forked link-attachment
browsers, the flyer whose mime was lost on import being unpickable, and AC-A10
having no committed regression guard.
