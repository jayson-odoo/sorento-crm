# PLAN: goods chain PO->SPO key query stops growing with key count (GOODSCHAIN-INDEX-QUERY)

Status: in progress (small fix track: backend only, one index migration, no auth change)

## Incident

PROD 27 Oct 2026 ~10:00: Stock Debt timed out. `transferred_allocations`
(`app/services/scm/goods_chain.py`, from #1870/#1874) reads `spo_allocations` with
`po_line_id IN (...) OR (from_po_number, btrim(from_po_line_ref), product_id, company_id) IN ((...) x N)`.
No index covers the key, so Postgres seq-scans per call (6.3 s on the 20 Oct clone, about two
calls per Stock Debt request), and the literal row-IN overflows `max_stack_depth` at large N.

## Fix

1. Migration: `CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_spo_allocations_from_po_key ON
   spo_allocations (from_po_number, btrim(from_po_line_ref), product_id, company_id)`, the exact
   name and shape the owner adds by hand on prod, so that one is reused.
2. `transferred_allocations`: the OR becomes two reads (`po_line_id IN`, then the key), the key
   passed as one `unnest` of four arrays joined to the table, so the SQL text does not grow with N.
3. `_po_lines_feeding`: the same key-as-unnest join over purchase_orders / purchase_order_lines.
4. Test: more than 5,000 keys, identical output, no stack-depth error.
