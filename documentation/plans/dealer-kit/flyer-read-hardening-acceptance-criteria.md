# Flyer read hardening: user acceptance criteria

Status: met. See the PLAN's "After the fix" table for the measurements.
Plan: `documentation/plans/dealer-kit/PLAN-flyer-read-hardening.md`
Supersedes nothing. Extends `flyer-seeding-acceptance-criteria.md` (S7.3, S7.4).

## Journey

**Actor.** A marketing designer who holds the printed flyer and wants the Kit to
know what is on it. They hold `dealer_kit.page.edit`, and they reach this from
the sidebar: Dealer Kit, then Flyer readings.

**Where they arrive from.** Two real starting points, and today only one of them
works:

1. They have the flyer PDF on their laptop, freshly exported by the agency.
2. The flyer is already IN the system. Marketing uploads the season's flyer to
   Resource Management as a matter of course, long before anybody thinks about
   the Kit. Today the designer has to download it out of the CRM and upload it
   back into the CRM, which is a round trip the system can spare them.

**What the system already knows.** Everything about the file it is holding: its
name, its size, its type, the folder it lives in, who uploaded it and when.
So the second path asks for nothing except "which one", and derives the rest.

**Step 1: open "Read a flyer".** One decision: where the flyer is coming from.
The dialog offers both sources side by side. Upload is unchanged and stays the
default, because the designer who just got the file from the agency should not
have to file it somewhere first.

**Step 2 (library path): pick the file.** They see the same file browser they
already know from complaints, purchase requests and packing lists: the folder
tree on the left, a searchable list on the right. Only PDFs are offered, because
nothing else can be read as a flyer, and offering a spreadsheet only to refuse
it a moment later is a decision the system can make for them. One file, then
confirm.

**Step 3: the read.** The button goes quiet while the flyer is read. The real 36
page flyer takes roughly fifteen seconds, not the "about a second" the current
copy promises, so the wait is named honestly rather than left to feel like a
hang. Crucially, everybody ELSE in the system keeps working while it happens:
today this read freezes the worker handling it for its whole duration.

**Step 4: the report.** Identical for both sources. They land on the review
screen and see what was found: matched codes, unmatched codes with suggestions,
printed sizes that disagree with the master, duplicates. Nothing has been
created yet.

**What they hold at the end.** A flyer reading in their company's scope, from
either source, identical in every respect once created. Nobody else was
disrupted while it was produced.

---

## Phase 2A: the read stops jamming the system

### AC-J1 [BE] A flyer read does not block the event loop
**Given** the backend is serving requests
**When** a flyer reading is created from the real 36 page A3 flyer (998 codes)
**Then** an unrelated cheap request (`GET /health`) issued while the read is in
flight completes in under one second
**And** it does not wait for the read to finish.

Baseline measured on `main` before the fix: that probe took **57.5 seconds** on a
single worker. See the plan's Diagnosis section.

### AC-J2 [T] The regression is pinned by a test
**Given** the bounded test fixture `tests/fixtures/dealer_kit/flyer_sample.pdf`
**When** the upload route is exercised while the loop is measured
**Then** the test fails if `create_reading` is called on the event loop again.

The pin is on the SHAPE (heavy work runs off the loop), not on a wall clock
number, because a timing threshold on CI hardware is a flaky test.

### AC-J3 [BE] Every dealer-kit route that does heavy sync work is off the loop
**Given** the dealer-kit routers
**When** they are swept for `async def` handlers calling synchronous work
**Then** none remain that block the loop
**And** the routes already declared plain `def` (list, get, seed, dimensions
apply, delete) are confirmed to be threadpooled by FastAPI, not just assumed.

Measured: the seed route completes in 2.83 seconds for 961 products and does not
perturb the probe at all. It was never the jam.

### AC-J4 [BE] The documented timings match reality
**Given** the docstrings in `flyer_readings.py`, `flyer_reading_service.py` and
the FE upload dialog, all of which currently claim the real flyer reads in
"about a second"
**When** they are read by the next person deciding whether to queue this work
**Then** they state the measured figure and the conditions it was measured under,
because the decision to keep extraction in-request was justified BY that number.

---

## Phase 2B: read a flyer that is already in the system

### AC-A1 [BE] A reading can be created from an existing attachment
**Given** a PDF attachment readable in the caller's company scope
**When** they POST its id to the flyer readings from-attachment route
**Then** a flyer reading is created that is indistinguishable from one created by
upload: same extraction, same banners stored, same report
**And** it lands in the caller's company scope exactly as an upload does.

### AC-A2 [BE] The same permission guards both sources
**Given** a caller without `dealer_kit.page.edit`
**When** they POST to the from-attachment route
**Then** they get a 403 naming that permission, exactly as the upload route does.

### AC-A3 [BE] Another company's attachment is not readable
**Given** an attachment belonging to a company outside the caller's scope
**When** they POST its id
**Then** they get a 404, not a 403, so the id's existence is not confirmed
**And** no reading is created.

### AC-A4 [BE] The same validation applies to both sources
**Given** an attachment that is not a PDF, is password protected, or is over the
50 MB ceiling
**When** they POST its id
**Then** they get the same status and the same words the upload route gives for
that failure (`FLYER_NOT_A_PDF`, `FLYER_PASSWORD_PROTECTED`, `FLYER_TOO_LARGE`)
**And** the size is refused from the attachment's recorded size, before the bytes
are fetched from storage.

### AC-A5 [BE] Upload still works, unchanged
**Given** the existing upload route
**When** a flyer PDF is uploaded
**Then** its behaviour, status codes, messages and response body are unchanged.

### AC-A6 [BE] Attachments can be filtered to PDFs
**Given** the resource attachments list endpoint
**When** it is called with a mime type filter
**Then** only attachments of that mime type are returned
**And** calling it without the filter returns what it returned before.

### AC-A7 [FE] The dialog offers both sources
**Given** the "Read a flyer" dialog
**When** it opens
**Then** it offers "Upload a file" (the default, unchanged) and "Choose from
Files"
**And** switching between them does not lose what was already selected in the
other.

### AC-A8 [FE] The library source reuses the existing file browser
**Given** the "Choose from Files" source
**When** it is opened
**Then** it renders the shared link-attachment browser already used by
complaints, purchase requests, stock inquiries and packing lists, not a new one
**And** it is restricted to a single selection
**And** it lists only PDFs.

### AC-A9 [FE] Errors from either source read the same
**Given** a flyer that cannot be read
**When** it fails from either source
**Then** the message shown is the backend's message, in the dialog, in the same
place.

### AC-A10 [E2E] The library path reaches the review screen
**Given** a PDF attachment in the file library
**When** the designer navigates by sidebar clicks to Dealer Kit, Flyer readings,
opens "Read a flyer", chooses the library source, picks the file and confirms
**Then** the browser lands on the review screen for a new reading
**And** the backend records the from-attachment call, not a multipart upload.

Verified by an **agent-browser** evidence run, not a committed spec. The standing
order is that no project carries a playwright trace, and a new spec would be a
new trace, so this AC is met by a reproducible run whose steps and output are
recorded in the commit. What that costs is honest to state: this path has no
committed regression guard, so a later change can break it without a test going
red. The repo-wide replacement for the 40 existing specs is a separate pending
decision, and this AC joins that queue rather than pre-empting it.

### AC-A11 [FE] Both sources work at 375px and 1280px
**Given** the dialog at both widths
**When** either source is used
**Then** nothing is clipped and the confirm button is reachable.
