# PLAN: goods chain PO->SPO key query stops growing with key count (GOODSCHAIN-INDEX-QUERY)

Status: in review, PR #1899, reviewer READY 27 Oct (small fix track: backend only, one index migration, no auth change)

## Incident

PROD 27 Oct 2026 ~10:00: Stock Debt timed out. `transferred_allocations`
(`app/services/scm/goods_chain.py`, from #1870/#1874) reads `spo_allocations` with
`po_line_id IN (...) OR (from_po_number, btrim(from_po_line_ref), product_id, company_id) IN ((...) x N)`.
No index covers the key, so Postgres seq-scans per call (6.3 s on the 20 Oct clone, about two
calls per Stock Debt request), and the literal row-IN overflows `max_stack_depth` at large N.

## Fix

1. Migration `gc_idx_0001_spo_from_po_key`, both halves of the key, the exact names and shapes
   the owner built by hand on prod (a VALID one is kept; an INVALID one, which the owner's
   interrupted first CONCURRENTLY build left on prod, is dropped and rebuilt CONCURRENTLY and
   checked `indisvalid` after):
   - `ix_spo_allocations_from_po_key ON spo_allocations (from_po_number, btrim(from_po_line_ref), product_id, company_id)`;
   - `ix_purchase_order_lines_src_key ON purchase_order_lines (btrim(source_ref), product_id, company_id)`
     (crew profiling: `_po_lines_feeding` over ~949 keys walked every line of 208 POs, 1.2 s;
     28 ms with the index).
2. `transferred_allocations`: the OR becomes two reads (`po_line_id IN`, then the key), the key
   passed as one `unnest` of four arrays joined to the table, so the SQL text does not grow with N.
3. `_po_lines_feeding` and Stock Debt's `_follow_totals`: the same key-as-unnest join over
   purchase_orders / purchase_order_lines.
4. Test: 9,000 keys, identical output, no stack-depth error (red on main: stack depth limit
   exceeded); migration test for build / keep VALID / rebuild INVALID.

## Follow-up (not this PR)

The Stock Debt board computes every product (~6k) before paging; the Python side is ~1.5 s of
a ~3 s request on the local clone after both indexes (crew profiling, 27 Oct).

## Measured

CONCURRENTLY build on the local clone `sorento_prod_1020` (PG 17.7, crew, 27 Oct):
`ix_spo_allocations_from_po_key` 434.2 ms (88,343 rows / 28 MB), `ix_purchase_order_lines_src_key`
721.3 ms (152,480 rows / 35 MB); drops 3.7 ms / 0.8 ms. Never stalls a deploy: the build is
CONCURRENTLY under the repo's migration limits (`app/utils/migration_timeouts.py`), a timed-out
build warns and the revision succeeds, and `start.sh` retries it in the background
(`app/utils/online_index.py`, `scripts/ensure_goods_chain_indexes.py`).
