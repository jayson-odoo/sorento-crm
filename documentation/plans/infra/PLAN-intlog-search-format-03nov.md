# PLAN: Integration Log search box + pager number format (INTLOG-SEARCH)

Status: built, fix round 2 INTLOG-SPEED-2 (page reset, trigram index migration il_0002, empty pager), awaiting crew pass (track: migration, online index; no auth/RBAC change)

Follow-up to INTLOG-SPEED (`_archive/infra/PLAN-intlog-speed-03nov.md`, PR #2129, merged), found by crew's browser pass.

## Problems
1. The Integration Log search box did nothing. The list sends `query`
   (`integrationLogService.ts`), and `GET /api/v1/integrations/logs/` (`logs.py`) had no such
   parameter, so FastAPI dropped it.
2. The shared pager formatted numbers inconsistently: `9951 - 10000 of 19,950+` vs `of 1304`
   (`components/ui/data-grid-pagination.tsx`).

## Fix
1. `query` on the route -> `IntegrationLogService._apply_search`:
   - every term is a case-insensitive substring of `integration_channel`, `business_table`,
     `business_id` as text (the grid shows its first 8 characters), `endpoint`,
     `external_reference`, `error_code`, `error_message`; LIKE wildcards and backslashes in the
     term are literal;
   - a term that is a UUID also matches `id` and `correlation_id` exactly. It still searches the
     text columns (review round): `external_reference` holds other records' UUIDs, e.g. the
     stock inquiry id procurement stores there;
   - blank is ignored; it ANDs with every filter and goes through the same capped count.
2. The pager formats from, to and count with one en-US thousands format on every grid
   (no grid passes its own `info`; checked all 195 users of `DataGridPagination`).

## Measured in the sandbox (synthetic 1.7M rows, warm cache)

| Search | Count | Page |
| --- | --- | --- |
| common term (`respond`) | 30 ms | fast (stops at 50) |
| rare substring or a pasted UUID that matches nothing | 1.0 s | 3.6 s |

A rare term reads the whole table (no index serves `ILIKE '%x%'`). Accepted for now: it costs
only when someone searches, never on page load. Trigger to revisit: crew measures a rare-term
search on the prod clone over ~10 s; then the fix is a `pg_trgm` GIN index on the searched
columns, built CONCURRENTLY through `app/utils/online_index.py` like il_0001.

## Tests (red first)
- BE `tests/test_integration_logs_search.py`: each text column, business_id prefix, full UUID on
  each id column and in external_reference, combined with a filter, literal wildcards and
  backslash, blank term.
- FE `components/ui/data-grid-pagination.capped.test.tsx`: `1 - 50 of 1,304`,
  `9,951 - 10,000 of 19,950+`.

## Fix round 2 (INTLOG-SPEED-2, crew pass on 086a3235, 12 Nov 2026)
The trigger above arrived: crew timed an 8-character Business ID search at 19.5-28 s on the dev
copy. Also: a search or filter change on page 2 stayed on page 2, and an empty list read
`1 - 0 of 0`.

1. **Page reset.** `IntegrationLogsList.tsx` calls the shared `useResetPageOnFilterChange` with
   the search and every filter (never on mount, so Back to page 2 keeps page 2).
2. **Trigram index.** The search matches ONE expression, `online_index.INTEGRATION_LOG_SEARCH_EXPR`
   (the seven columns plus `id` and `correlation_id` as text, space-separated), with one ILIKE; a
   UUID in another spelling is also searched in its stored form. `il_0002_integration_log_search`
   builds `ix_integration_log_search_trgm`, a GIN `gin_trgm_ops` index on exactly that expression,
   CONCURRENTLY through `online_index` at 512MB (as il_0001; a timeout leaves the deploy green and
   `scripts/ensure_goods_chain_indexes.py` retries it on backend start), then ANALYZEs the table
   once: without statistics on the expression a common term went through the index (3-4 s).
   The index is migration-owned, not on the model (repo convention, `app/models/certificate.py`).
3. **Empty pager** reads `0 of 0` on every grid.

Measured (sandbox, 1.3M synthetic rows, 1.9 GB, warm service call, count + page):

| Search | Before | After |
| --- | --- | --- |
| Business ID, 8 chars | 2,887 ms | 18 ms |
| Full UUID (business_id / correlation_id) | 3.4-3.6 s | 109-111 ms |
| REF number | 3,005 ms | 45 ms |
| No match | 2,818 ms | 2 ms |
| Common term (channel / error code) | 149-243 ms | 71-162 ms |
| 2-char term (no trigram) | 142 ms | 180 ms |

Build: 134 s through the migration, 544 MB; ANALYZE 0.6 s.

Tests (red first, 15a0fcab8): `tests/test_integration_logs_search_index.py` (EXPLAIN of the route's
SQL uses the index for a Business ID prefix, a full UUID and a word; ANALYZE after a fresh build
only), `IntegrationLogsList.pageReset.test.tsx`, the `0 of 0` pager case.
