# PLAN: portal AI extract off the event loop

Status: implemented, tested, reviewed. Branch `fm/ai-extract-blocking-loop`.
UAC: `documentation/plans/ai-extract/ai-extract-off-the-loop-acceptance-criteria.md`
Classification: defect fix inside the existing `public` router. No new module,
no schema, no permission, no migration.

## Defect

`sorento_crm_backend/app/api/v1/public/ai_extract.py::ai_extract` is
`async def` and calls the synchronous `AIExtractService.extract(...)`
(`app/services/ai_extract/extract_service.py`) inline. FastAPI runs an
`async def` handler ON the event loop, so the whole extract (PDF render +
LLM round trip, measured 5.8 to 9.8 s per image on 2026-08-13) freezes every
concurrent request on that gunicorn worker. Same class as the flyer read
defect fixed in PR #164 (`documentation/plans/dealer-kit/PLAN-flyer-read-hardening.md`).

## Fix

- `ai_extract` becomes plain `def`. FastAPI then dispatches the whole handler
  to its threadpool, which is what every other handler in this file already
  gets. Read upload bytes with `f.file.read()` (the sync file object) instead
  of `await f.read()`. There is no streaming size enforcement in this route
  (each file is read whole before the total is checked), so `async` bought
  nothing here - unlike the flyer upload route, which stays `async def` to
  refuse oversized bytes as they arrive.
- Sibling `ai_extract_schema` (same file) and
  `app/api/v1/master_data/ai_extract_field.py::ai_extract_field` (the caller
  of `extract_against_attachment`) are already plain `def`; nothing to do.
- Sweep of other `async def` handlers doing heavy sync work: results recorded
  in the "Sweep" section below. Identical instances fixed in this branch;
  anything bigger reported, not fixed.

## Capacity note (same trade as PR #164)

Off the loop is not free: an extract now holds one of anyio's default 40 shared
worker threads for its whole duration (5.8 to 9.8 s per image, up to 12 files a
request), and that pool also serves every sync dependency and sync handler in
this mostly-sync codebase. The fix turns "one slow request freezes the worker"
into "N concurrent slow requests exhaust the sync pool". The next lever, when it
is needed, is either a dedicated `CapacityLimiter` for the extract or moving
the extract onto RQ with a 202 and a row to watch (BL-004 records the same
option for the flyer read).

## Regression tests (`tests/test_ai_extract_route_off_the_loop.py`)

Same shape as `tests/test_dealer_kit_flyer_from_attachment.py` AC-J2/AC-J3:

1. **Spy, by shape.** Monkeypatch the route module's `AIExtractService.extract`
   with a spy that records whether `asyncio.get_running_loop()` raises inside
   it, POST a small PNG through the real route with a real portal token on a
   blank Postgres schema, assert the spy ran off the loop.
2. **Loop stays responsive, by ordering not wall clock.** Stub `extract` to
   block on a `threading.Event`. Fire the extract POST from a background
   thread via `TestClient`, then issue a cheap request (`GET /health` or the
   schema GET) from the test thread and assert it COMPLETES while the event is
   still unset (i.e. before the extract is released). Then set the event and
   assert the extract request finishes 200. No sleeps as assertions.
3. **Sweep by routing metadata.** No route mounted under
   `/api/v1/public/portal/ai-extract*` has a coroutine endpoint.

Postgres only (`tests/_pg_fixture.blank_session`), rows seeded by the test with
a marker prefix, deleted after.

## Sweep

Method: enumerate every `async def` handler under `app/api` (691 matches, about
684 routes), keep the ones whose body or the service it calls synchronously does
heavy work (LLM, PDF/image, storage byte transfer, sync outbound HTTP, openpyxl,
zip, alembic). Plain SQLAlchemy in an async handler is a repo-wide pattern and
was excluded from the count.

### Fixed in this branch (identical instances)

- `app/api/v1/public/ai_extract.py::ai_extract` - the target. Now plain `def`.
- `app/api/v1/master_data/product_specifications.py::preview_spec_search` -
  `async def` with no awaits, calls `understand_phrase` which resolves an LLM
  provider and blocks on the model round trip. Now plain `def`.

### Already correct

- `app/api/v1/public/ai_extract.py::ai_extract_schema` and
  `app/api/v1/master_data/ai_extract_field.py::ai_extract_field` (the
  `extract_against_attachment` caller) - plain `def`.
- AI assistant, RAG, ideation, dealer-kit pages, embeddings, MCP tools, portal
  attachment download, and every RQ-enqueued import/export - either plain `def`
  or off-request.
- Attachment webhooks - already dispatched on a `threading.Thread`.
- The multimodal CRM media endpoint - out of scope of this task by instruction
  (and its router is plain `def`).

### Bigger, reported not fixed (see BL-009)

About 40 `async def` handlers do heavy synchronous work on the loop. They fall
in five families, each a change to a shared helper or a whole router rather than
a one-line handler swap, so they are one follow-up, not this branch:

1. Storage byte transfers and PIL thumbnails inline: `resources/attachments.py`
   `download_attachment` (the one heavy call in that file not wrapped in
   `run_in_threadpool`), `public/portal.py` `portal_upload_attachment`,
   `complaints.py` and `procurement/stock_inquiries.py` response-attachment
   uploads (via `entity_attachment_service.create_response_attachment`),
   `user_management/users.py` `update_current_user_profile` avatar upload.
2. Excel imports parsed inline: `excel_macro_stripper.maybe_strip` (openpyxl
   load + save of the whole workbook), `validate_*_import`, and
   `store_import_source_file` (storage upload) in `procurement/packing_lists.py`,
   `procurement/grn.py` (two routes), `procurement/spo_allocations.py`,
   `order_management/customers.py`, `order_management/orders.py` (two routes);
   and the SCM intake family where `app/services/scm/upload_intake.py::read_upload`
   is itself `async def` calling `maybe_strip` synchronously, used by every
   preview/apply route in `scm/purchase_history.py`, `scm/outstanding_import.py`,
   `scm/reorder_levels.py`, `scm/fulfilment.py`.
3. Sync Respond.io / n8n HTTP (`RespondClient` is a sync `httpx.Client`):
   conversation reads and assignee syncs in `complaints.py`,
   `procurement/purchase_requests.py`, `procurement/stock_inquiries.py`,
   `sla/sla_tracking.py`; user and contact syncs in `user_management/users.py`,
   `user_management/contacts.py` (`bulk_sync_contacts` loops N blocking calls
   in one request), `user_management/access_agents.py`; webhook retries in
   `integrations/logs.py` and `resources/attachments.py::resubmit_attachment_webhook`.
4. Module runtime: `system/modules_runtime.py` `upload_module_zip` (zip extract,
   copytree, programmatic `alembic upgrade heads` - the heaviest single call
   found), `export_module`, `remove_module`.
5. Suspected: `user_management/settings.py::test_smtp_connection` (blocking
   smtplib), `system/jobs.py::export_job_rows` (sync generator into
   `StreamingResponse`, probably iterated in a threadpool by Starlette).

Cheapest systemic fix for families 1 to 3: make the shared helper the boundary
(`create_response_attachment`, `store_import_source_file`, `maybe_strip`,
`RespondClient` calls) and either flip the handlers to plain `def` where they
have no awaits, or wrap the helper call in `run_in_threadpool`. A routing
metadata test like AC-J3 per router then keeps them fixed.
