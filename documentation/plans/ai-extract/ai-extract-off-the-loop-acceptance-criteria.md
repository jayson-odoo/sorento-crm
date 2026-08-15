# Portal AI extract off the event loop: acceptance criteria

Status: met on branch `fm/ai-extract-blocking-loop`.
Plan: `documentation/plans/ai-extract/PLAN-ai-extract-off-the-loop.md`
Same shape as `dealer-kit/flyer-read-hardening-acceptance-criteria.md` AC-J1 to
AC-J3 (PR #164), which fixed the same class of defect for the flyer read.

## Journey

**Actor.** A portal contact (dealer, salesperson, customer) on a WhatsApp portal
link, uploading a photo of a receipt or delivery order so the form pre-fills.
Meanwhile: every other user of the CRM on the same backend worker.

**What happens today.** The contact taps upload and waits 6 to 10 seconds per
image for the extract. That wait is theirs to pay. What is not theirs to pay
is that, for the whole of it, every other request that lands on the same
gunicorn worker (an office user opening an order, another portal contact
loading their form, the health probe) waits too, because the handler was
`async def` and ran the whole extract on the event loop.

**What happens after.** The contact's wait is unchanged. Nobody else notices
that an extract is running.

## Criteria

### AC-1 [T] The extract call runs off the event loop, pinned by shape
**Given** the portal extract route with a real portal token on a blank schema
**When** a small image is posted and `AIExtractService.extract` is spied on
**Then** the spy observes no running event loop in the thread that calls it.

The pin is on the SHAPE (off the loop or not), never on a wall clock, because a
timing threshold on CI hardware is a flaky test.

### AC-2 [T] The loop stays responsive while an extract is in flight
**Given** `AIExtractService.extract` stubbed to block until released
**When** an extract request is started and, while it is parked, a cheap
unrelated request (`GET /health`) is issued
**Then** the cheap request completes before the extract is released
**And** if it cannot, the test fails loudly within a bounded time instead of
hanging CI.

Proven by request ORDERING (the cheap request joins before the release event is
set), not by elapsed time.

### AC-3 [BE] No AI-extract route, and not `preview_spec_search`, is a coroutine endpoint
**Given** the mounted routes under `/api/v1/public/portal/ai-extract*` and the
handler `product_specifications.preview_spec_search` (the second identical
instance found by the sweep, an LLM call in an `async def`)
**When** they are read from FastAPI's routing metadata
**Then** none is a coroutine function, which is exactly the property FastAPI
keys threadpool dispatch on.

### AC-4 [T] Upload bytes reach the service intact through the sync read path
**Given** two files posted in one request
**When** the route reads them with `f.file.read()` instead of `await f.read()`
**Then** the service receives both, in order, byte-identical, with their
filenames.

### AC-5 [Doc] The rest of the class is reported, not silently left
**Given** the sweep of every `async def` handler under `app/api`
**Then** identical instances (LLM call in an `async def` with no awaits) are
fixed on this branch, and the bigger families (storage uploads, inline Excel
parsing, sync Respond.io HTTP, module zip install) are recorded in the plan's
Sweep section and as `BL-008` in `documentation/backlogs/backlog.md`.
