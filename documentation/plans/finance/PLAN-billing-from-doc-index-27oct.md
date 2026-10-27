# PLAN: index billing_document_lines.from_doc_no (BILLING-FROM-DOC-INDEX)

Status: in progress (crew lane, size S; index-only migration, so not strictly the small fix track:
one coder pass, tests first, one reviewer, no screen changes so no browser pass).

## Problem

DOC-RELATIONS (#1912) finds an SO's / DO's billing documents through
`finance.billing_document_lines.from_doc_no`:

- `sorento_crm_backend/app/services/document_relations.py` `billing_ids_for_sales_order`
  (`from_doc_no == so.so_number`, `from_doc_no IN (<the SO's DO numbers>)`) and
  `billing_ids_for_delivery_order` (`from_doc_no == order.order_number`).
- The billing list's `sales_order_id` / `delivery_order_id` filters reuse both
  (`app/services/finance/billing_document_query_service.py`, the `sales_order_id` branch).

`BillingDocumentLine.__table_args__` (`app/models/finance.py`) indexes only
`sales_order_line_id`, `product_id` and the `(document_id, source_ref)` unique key, so every SO / DO
detail view reads the whole lines table (backfilled from 2023-09-01).

## Shape

`ix_finance_billing_document_lines_from_doc_no ON finance.billing_document_lines (from_doc_no)`.

- Plain column, no expression: the lookups compare `from_doc_no` raw (`==` / `IN`), no
  `lower()` / `btrim()`.
- Not `(company_id, ...)`: the company filter in those queries is on `BillingDocument.company_id`
  (the joined header), not the line's own column, so a company-leading index would not match.
  A document number is already near-unique, the `from_doc_type` / company checks run on the few
  rows it returns.

## Build

Same owner rules as GOODSCHAIN-INDEX-QUERY (`app/utils/online_index.py`): CONCURRENTLY, outside a
transaction, under the repo migration limits, fail-soft (a timeout logs a WARNING and the revision
still succeeds). The retry is the same background `scripts/ensure_goods_chain_indexes.py` that
`start.sh` runs on every backend start; it now also ensures this index.

`online_index` gains one fix it needs for a schema-qualified table: an INVALID leftover is dropped
by its schema-qualified name (an unqualified `DROP INDEX` resolves along search_path and would miss
`finance.`).

## Tests (red first)

`tests/test_migration_bfd_idx_0001_billing_from_doc_no.py`: revision chains to one head; the model
declares the index; the migration builds it VALID on a scratch schema; it fails soft behind live
work; an INVALID leftover in a non-search_path schema is dropped and rebuilt; the retry script
builds it; the planner uses it (EXPLAIN).
