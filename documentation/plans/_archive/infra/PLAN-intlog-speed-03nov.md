# PLAN: Integration Log page speed (INTLOG-SPEED)

Status: merged (#2129, 3 Nov 2026; crew GO on the prod clone: page 1 0.5 s cold, 3 ms warm, vs 19-26 s on main). Small fix track.

## Problem (measured by crew, 3 Nov 2026, on the 20 Oct prod clone: 1.2M rows, 1.5 GB)

- `IntegrationLogsList.tsx` -> `GET /api/v1/integrations/logs?page=1&limit=50` ->
  `IntegrationLogService.list_integration_logs` (`app/services/integration_service.py`).
- It ran an exact `q.count()` over the whole table, with the list's ORDER BY still attached
  (a disk sort of 1.2M rows), then `ORDER BY created_at DESC LIMIT 50`.
- 9.7 s cold, 3.2 s warm. With `ix_integration_log_created_at` the page query is 3 ms; the count
  still takes 1.5-1.9 s.
- The endpoint also ignored `sort`/`dir`, so a column header click re-fetched the same order.

## Fix

1. Capped count, every request. The count runs without ORDER BY over a subquery limited to
   `offset + 10,000 + 1` rows. At or under the cap the total is exact; over it the reply says
   `total = offset + 10,000` and `total_capped = true`. The window grows with the offset, so the
   current page is always inside the counted range and Next stays enabled while capped. A
   filtered list (drill-downs from System Health) is exact whenever it matches 10,000 rows or
   fewer, which is every drill-down in practice; a broad filter (status=success) would otherwise
   count ~1M rows, so the cap applies to it too.
   Deviation from the brief ("with filters keep an exact count"): the capped count is exact for
   every result under the cap and bounded for every result over it, with one code path.
2. `pagination.total_capped` (default false) on a lane-local `IntegrationLogPagination` /
   `IntegrationLogListResponse` (`app/schemas/integration.py`). Not on the shared
   `PaginationResponse`: other lists' tests assert its exact shape and they do not cap.
3. Server-side sort on every visible column (`sort`, `dir`), whitelisted, `id` as tiebreaker;
   default `created_at desc`, which uses `ix_integration_log_created_at` backward
   (EXPLAIN asserted in `tests/test_integration_logs_list_speed.py`).
4. FE: `DataGridPagination` takes `recordCountCapped`; the list passes it from the reply and the
   info reads `1 - 50 of 10,000+`.
5. FE cancellation (owner, 3 Nov): the list's `queryFn` hands React Query's AbortSignal to
   `apiFetch`, so a filter, page or sort change aborts the superseded request instead of stacking.
   The browser itself aborts on a full reload. A cancelled HTTP request does not stop a running
   Postgres statement in a sync FastAPI route, which is why the count itself had to be bounded.

Owner's prod numbers, 3 Nov: all five indexes VALID; page query = Index Scan Backward using
`ix_integration_log_created_at` (cost 0.43..9.98); table est. 1,738,190 rows; the endpoint took
275 s / 148 s / 80 s on three reloads. All of it was the exact count.

No migration: `ix_integration_log_created_at` is already in `il_0001_integration_log_indexes`.

## Tests (red first)

- BE `tests/test_integration_logs_list_speed.py`: capped total + flag, exact total under the cap,
  window grows with offset, last page under the cap, sort per column asc/desc, unknown sort
  falls back to created_at desc, count SQL has no ORDER BY, EXPLAIN of the default page query
  uses `ix_integration_log_created_at`.
- FE: pagination renders `10,000+` and keeps Next enabled when capped; the list forwards the flag.

## Measured in the sandbox (synthetic 1.7M rows, 1.8 GB, warm cache)

| Query | Time |
| --- | --- |
| old exact count, ORDER BY attached | 832-3,845 ms |
| new capped count, no filter / status=failed / no match | 1.4 / 11.8 / 0.3 ms |
| page, `created_at desc` (default) | 0.5-1.4 ms |
| page, sorted on status / channel / business_table / business_id / retry_count / processed_at | 220-310 ms each |

A non-default sort reads every matching row before it can return the top 50 (status and
channel too: the `id` tiebreak forces an incremental sort over a group of ~1M equal values).
Warm, that is a quarter of a second; on a cold prod cache it is a full-table read, the same I/O
class as the old count, but only when someone clicks a header, not on every page load. Owner
rule says every column sorts server-side, so this is accepted rather than gated. Trigger to
revisit: the clone measurement shows a header sort over a few seconds; then the choice is a
`statement_timeout` on this route or composite `(col, id)` indexes, decided with that number.

Not changed: the detail page's record counter (`hooks/useListPager.ts`) reads a capped total as
exact ("3 / 10000"); its Prev/Next still work because the window moves with the offset.
