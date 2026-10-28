# PLAN: API-NONBLOCKING - blocking route handlers run in the threadpool, not on the event loop

Status: Review (track: standard, backend only, no behaviour change, no migration). PR #1951.
Lane: API-NONBLOCKING. UAC: `api-nonblocking-acceptance-criteria.md`.

## Why

Prod runs gunicorn with uvicorn workers (`sorento_crm_backend/gunicorn.conf.py:44`, `WORKERS`
env, prod has 8). The owner approved going to 4 (28 Oct; each worker about 0.9 GB, see
`documentation/plans/deploy/PLAN-backend-memory-28oct.md` on PR #1950). FastAPI runs an
`async def` handler ON the worker's event loop and a plain `def` handler in anyio's threadpool.
An `async def` handler that never awaits holds the loop for its whole run: every other request
on that worker, `/health` included, waits behind it. With 4 workers, 4 slow reports at once
stall the API, and a handler holding the loop past gunicorn's `timeout` (120 s,
`gunicorn.conf.py:52`; uvicorn heartbeats from its main loop) gets the worker SIGABRTed
(`WORKER TIMEOUT`).

## Measured on main (30a40cf0, AST over `app/`, nested defs excluded)

| route handlers | count |
|---|---|
| plain `def` (threadpool) | 972 |
| `async def` that awaits | 63 |
| `async def` that never awaits | **943**, in 128 files |

`LESSONS-LEARNT.md:63` says "~40 remain": wrong, it is 943.

Heavy handlers named in the brief, all still `async def` with no await on main:
`order_management/orders.py:1822` (sales report), `:1578` (outstanding report),
`projects/quotation_documents.py:705` (xlsx), `projects/sales_orders.py:949` (xlsx),
`system/jobs.py:296` (CSV export), `system/modules_runtime.py:394` (zip export),
`complaints/complaints.py:1504`, `marketing/promotions.py:372`,
`procurement/stock_inquiries.py:320` (PDF export enqueue: DB + Redis).

A second class the "no await" rule cannot see: `async def` handlers that `await file.read()`
(or `request.form()`) and then run the whole Excel parse and DB import synchronously on the
loop, e.g. `order_management/customers.py:56`, `orders.py:1403`, `:1474`,
`procurement/grn.py:95`, `:154`, `packing_lists.py:141`, `spo_allocations.py:273`,
`projects/quotations.py:1085`, `projects/schedules.py:143`. And `/health` itself
(`app/main.py:643`) runs its DB check synchronously before its one await.

Already safe and untouched: Stock Debt `stock_debt.py:45/144/213`, chat turn
`external/chat.py:172`, ingest `ingest.py:994` (plain `def`).

The August attempt (`origin/fix/api-blocking-event-loop`, bb5cf8e904, never merged) removed
`async` from every no-await handler, made the pool env-tunable (8+7) and set the anyio limiter
to pool capacity. Reused: the mechanical approach and its test-helper fix for tests that call a
handler under `asyncio.run`. Not reused: the branch is 3 months stale (918 routes then, 2007
now), and the pool / limiter change rests on a premise checked below.

## Decisions

1. **One PR, two phases as separate commits.** Phase 1 = the heavy handlers above plus the
   upload-then-import class plus `/health`. Phase 2 = the remaining no-await handlers, swept
   mechanically per domain. One PR because the CI guard (3) needs a clean baseline; a ratchet
   list of 900 entries would be noise. Phase 2 commits can be dropped from the PR if the owner
   prefers a follow-up.
2. **How each handler is converted (as shipped).** No await -> drop `async` (FastAPI runs it in
   the threadpool; nothing else changes). Awaits only `file.read()` and then does sync work ->
   plain `def` reading the already-spooled upload with `file.file.read()` (the precedent in
   `dealer_kit/assets.py:93-102`; Starlette's `UploadFile.read` is that same call in a thread).
   The async SCM / comment upload helpers (`upload_intake.read_upload*`,
   `form_comments.read_uploads`) became sync; callers that keep other awaits read through
   `run_in_threadpool`. Handlers whose only work is building an async stream
   (`sla/conversation_events.py:138`) stay `async` and go on the allow-list.
3. **Guard:** `tests/test_no_blocking_async_routes.py` walks every mounted route
   (`app.routes`) and fails when an endpoint is a coroutine function whose body (nested defs
   excluded) has no `await` / `async for` / `async with`, unless it is on an allow-list in that
   file with a reason. Runs in the normal backend suite, so CI fails a new offender.
4. **Why the conversion is safe (thread semantics).** 972 routes already run in the threadpool.
   The auth dependencies stay `async def` (`app/dependencies.py:280`, `:652`, AC-12) so the audit
   actor is stamped on the request's own context; a `def` handler runs in a copy of that context
   (anyio copies contextvars), so it still sees the actor, and the per-request `AuditContext` is
   one mutable object shared by reference (`app/audit_context.py:246`). No converted handler
   calls `asyncio.get_running_loop` / `create_task` (AST scan; `projects/tasks.py:91`'s
   `create_task` is a service method).
5. **Threadpool / DB pool:** see "Sizing" below.
6. **A race this lane widens is closed here.** The public one-time approval link
   (`procurement_service.submit_approval`) checked `used_at` without a lock; on the loop, one
   worker ran it start to finish. Now the token row is read `FOR UPDATE`
   (`tests/test_approval_token_single_use.py`, red-first).

## Proof

- Red-first: `tests/test_api_nonblocking.py`, one case per heavy handler: the real route on one
  event loop, database stand-in blocks 1.5 s on first touch, `/health` on the same loop must
  answer within 0.75 s of the slow part starting. 16 cases (9 reports/exports/PDFs, the two audit
  listings, 4 uploads incl. order tracking, `/health` itself), every one red against main
  (1.51-3.02 s).
- Kill test: re-add `async` to one converted handler -> its case goes red.
- Response equality: Phase 1 report/export handlers called before/after on the same seeded data,
  bytes (xlsx/CSV/zip) or parsed JSON compared.
- Phase 2: an AST check that every Phase 2 change is exactly `async def` -> `def` (no other
  token changed), plus the route table (path, methods, response model, dependencies) identical
  before/after. Result: 942 converted functions byte-identical in AST (body, args, decorators);
  the 30 that differ are exactly the upload / chained-await edits above. Route table: 2006
  routes, same SHA256 with the coroutine flag set aside; 979 route entries flipped to `def`.
- Full backend suite + SCM suite; failures compared name-for-name with main.

## Sizing (threadpool / DB pool at 4 workers)

Facts from code:

- Threadpool: anyio's default limiter, 40 threads per worker process; nothing in the backend
  overrides it (no `current_default_thread_limiter` / `total_tokens` anywhere in `app/`).
- DB pool: `app/database.py:13-14`, `pool_size=10, max_overflow=20` = 30 connections per worker,
  SQLAlchemy's default `pool_timeout` 30 s. The analytics connector's read-only engine is separate
  and small (`analytics_connector/datasets.py:308`, 2+3).
- One request holds one session (`get_db`), so at most one pooled connection per request.
- Prod reaches Postgres through pgbouncer (`documentation/runbooks/prod-edge-lockdown.md:71,141`;
  `tests/test_blue_green_deploy_guards.py:121` uses `pgbouncer:6432`). Its `pool_mode`,
  `default_pool_size` and `max_client_conn` are not in this repo.

What changes at 4 workers with this lane:

- Before: 972 routes were already `def` and could use up to 40 threads at once; the 943 blocking
  ones serialised on the loop. Client-side connection ceiling 8 x 30 = 240 at today's 8 workers.
- After: every route can run concurrently up to 40 per worker; ceiling 4 x 30 = 120 client
  connections, half of today's.
- Load (owner, 28 Oct 14:35 MYT): 2,098 requests in an hour, about 0.6 per second. Little's law:
  in-flight requests = rate x mean duration. Even a pessimistic 2 s mean is about 1.2 in flight
  across the whole API. A burst of 4 slow reports plus ordinary traffic is under 10 per worker,
  well inside 40 threads and 30 connections.

Recommendation: **no change to the thread or pool numbers in this PR.** 40 threads and 30
connections per worker are enough for report bursts at 4 workers, and halving the worker count
halves the connection ceiling the database side has to absorb.

The one real edge, not new and not made worse here: the auth dependencies stay `async def`
(AC-12) and do their session lookup on the loop (`app/dependencies.py:280`, `:652`;
`user_session_service.resolve_session` commits). If one worker ever had all 30 connections
checked out, the next request's auth checkout would wait up to `pool_timeout` (30 s) ON the
loop. That needs 30+ concurrent DB requests in one worker, which the load above is two orders of
magnitude away from. Trigger to act: `QueuePool limit of size 10 overflow 20 reached` in the
backend log, or pgbouncer `SHOW POOLS` showing `cl_waiting > 0`. Then the fix is to cap the
anyio limiter below the pool (for example 24 threads against 30 connections) so threads can
never take the connections the loop needs.

Owner check (read-only, prod), to confirm the database side fits 120 client connections:

```bash
# pgbouncer admin console: pool mode, per-pool server connections, client cap, live waiting
psql -h 127.0.0.1 -p 6432 -U <admin> pgbouncer -c 'SHOW CONFIG;' | grep -E 'pool_mode|default_pool_size|max_client_conn|max_db_connections'
psql -h 127.0.0.1 -p 6432 -U <admin> pgbouncer -c 'SHOW POOLS;'
# Postgres: the hard cap and what is connected now
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -c "SHOW max_connections" -c "SELECT state, count(*) FROM pg_stat_activity GROUP BY 1"'
```

If `max_client_conn` is below 4 x 30 plus the RQ workers plus n8n, raise it or lower
`max_overflow`. That is a one-line change, made once the numbers are known.

## Not built, with the trigger

- Handlers kept `async` that still do a cheap sync query before their first await (reviewer
  S2): `scm/proforma_invoices.py:191,240` (`assert_supplier`), `scm/import_mapping.py:128-129`.
  Pre-existing, one indexed lookup each. Trigger: either shows up in the slow-handler list.
- `project_quotation_document_service.accept_issue` (:1063, public quotation sign) has the same
  check-then-set shape as the approval link: two simultaneous signs can both see
  `accepted_at is None` and the second overwrites the first signature. Pre-existing across
  workers, lower stakes (one customer double-tapping). Trigger: owner says fix; the fix is
  `db.refresh(record, with_for_update=True)` before the check.

- `users.py:779` (profile update) and `settings.py:1315` (sign-in background) still await
  `request.form()` and then do one S3 put plus a small update on the loop. Both are rare,
  single-user admin actions. Trigger: either shows up in the slow-handler list.
- `/audit/logs` and `/audit/activity` stop freezing their worker but are not faster: a COUNT
  over all of `audit_logs` (415k rows) still takes about 37 s on prod. Trigger: already met
  (owner data 28 Oct); needs its own lane, because the fix (a default date window) changes what
  the screen shows.

## Coordination

PR #1950 (BACKEND-MEMORY) changes `gunicorn.conf.py`, `app/uvicorn_worker.py`,
`lookup_lists.fill()`. This lane does not touch those files.
