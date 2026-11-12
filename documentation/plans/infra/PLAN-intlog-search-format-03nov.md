# PLAN: Integration Log search box + pager number format (INTLOG-SEARCH)

Status: built, fix round INTLOG-SPEED-2 (main merged, 200-char search cap, Business Table one line, guide updated), awaiting merge (small fix track: no migration, no auth/RBAC change)

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
