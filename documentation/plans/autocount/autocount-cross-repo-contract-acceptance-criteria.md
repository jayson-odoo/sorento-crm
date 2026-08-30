# UAC: AutoCount cross-repo contract (Appendix A of shared-service plan 22)

Companion to `PLAN-autocount-cross-repo-contract.md`. Every AC is pinned by a pytest in
`sorento_crm_backend/tests/`; the file is named per group. Postgres only (`tests/_pg_fixture.py`).

## A1 - Company-anchored ingest (`test_external_company_anchor_scope.py`, `test_master_ingest_routes.py`)

- **AC-A1-1** `POST /external/ingest/{entity}` with no `companyCode` and no integration binding
  returns 422 `COMPANY_ANCHOR_REQUIRED`; nothing is written.
- **AC-A1-2** An unknown or inactive `companyCode` returns 422 `UNKNOWN_COMPANY`. An unresolvable
  integration BINDING returns 422 `COMPANY_BINDING_INVALID` naming the bound value and pointing at
  `config_json.company_code` - including when the body's own `companyCode` is valid, because the
  caller must not be blamed for a Sorento configuration row it never sent.
- **AC-A1-3** `companyCode` matches `companies.code` or `companies.autocount_ref`, case-insensitive.
  `autocount_ref` carries no unique index, so a value naming more than one active company returns
  422 `COMPANY_ANCHOR_AMBIGUOUS` stating how many, rather than picking one by scan order.
- **AC-A1-4** An integration whose `config_json.company_code` is set ingests with no body code; a
  body code that disagrees with the binding returns 422 `COMPANY_ANCHOR_AMBIGUOUS`.
- **AC-A1-5** A created master row carries `company_id` = the anchor (the NULL-company regression).
- **AC-A1-6** Adoption is company-scoped: the same code existing only in company B does not get
  adopted by a push anchored to A; A gets a new row and B's row is unchanged.
- **AC-A1-7** A `source_ref` already linked to a row in company B, pushed under A, is `failed` with
  `errors.source_ref` naming the other company; B's row is unchanged.
- **AC-A1-8** `POST /external/read/{entity}` is anchored the same way; a ref resolving to another
  company's row is reported in `not_found`.
- **AC-A1-9** The three existing anchor tests keep passing unchanged (GRN path untouched).

## A2 - Sales agents (`test_ingest_sales_agents.py`)

- **AC-A2-1** `POST /external/ingest/sales_agents` creates a row with `sales_agent` (upper/trim),
  `description`, `is_active`, `person_label`, `company_id NULL`.
- **AC-A2-2** A re-push updates those four columns and leaves `internal_note`, `follow_up`,
  `demand_class`, `location_group` exactly as they were.
- **AC-A2-3** First sync adopts an existing shared row with the same code (`updated`, linked).
- **AC-A2-4** `dry_run=true` returns the verdict + diff and writes nothing.
- **AC-A2-5** Read-back returns code/description/is_active/person_label.
- **AC-A2-6** No key -> 401; key without `master_data.sales_agents.edit` -> 403.
- **AC-A2-8** The same unqualified ref `agent:X` pushed anchored to company A, then anchored to
  company B (different `integration_id` allowed) -> `created` then `updated`; exactly one shared
  row (`company_id NULL`); the second call is not `failed`.
- **AC-A2-7** Migration 445 grants `master_data.sales_agents.delete`, `scm.sales_orders.delete`,
  `scm.purchase_orders.delete` to holders of the matching `.edit`, idempotently; downgrade mirrors.

## A3 - Documents (`test_ingest_documents.py`)

- **AC-A3-1** A SO record with header + 2 lines creates `public.sales_orders` + 2
  `public.sales_order_lines`, all stamped with the anchor `company_id`, header linked by ref;
  `projects.sales_orders` untouched.
- **AC-A3-2** Re-push with line 1 changed, line 2 absent, line 3 new -> line 1 updated in place
  (same id), line 2 deleted, line 3 created; header `updated`. A line absent from the payload that
  something else references (`scm.loading_plan_line.po_line_id` is CASCADE,
  `stock_transfers.so_line_id` is SET NULL) keeps its id and its quantities and is
  `line_status='cancelled'` instead, and the referring row is still there afterwards.
- **AC-A3-3** First sync with no ref but an existing `so_number` in the same company adopts it;
  an existing `so_number` already linked to another ref -> `failed`.
- **AC-A3-4** A line whose `product_ref` is unknown makes the whole record `retryable`; no header,
  no lines, no reference written.
- **AC-A3-5** Absent `customer_ref` leaves `customer_id` NULL; an unknown one is `retryable`.
- **AC-A3-6** Each canonical status maps to the documented Sorento value for SO and for PO; an
  unknown status is `failed` with `errors.status`.
- **AC-A3-7** `status: cancelled` on a re-push updates the header to `cancelled` and lines to
  `cancelled`; nothing is deleted.
- **AC-A3-8** `dry_run=true` writes nothing for a create and for an update.
- **AC-A3-9** Read-back returns the header in canonical names plus `lines[]` with per-line
  `source_ref` and `entity_id`.
- **AC-A3-10** PO: the same as A3-1/2/4 against `public.purchase_orders` with `supplier_ref`.
- **AC-A3-11** Guards: `sales_orders` ingest requires `scm.sales_orders.edit`, read `.view`; PO
  likewise.

## A4 - Deletions (`test_ingest_deletions.py`)

- **AC-A4-1** `POST /external/ingest/{entity}/deletions` with `{"source_refs": [...]}` returns 200
  with per-ref verdicts and a summary; > 1000 refs -> 413; missing array -> 422.
- **AC-A4-2** A ref that does not resolve (or resolves to another company) -> `not_found`.
- **AC-A4-3** A warehouse with no dependents -> `deleted`; row gone; integration reference gone.
- **AC-A4-4** A customer referenced by a sales order -> `deactivated`; `is_active=false`; the order's
  `customer_id` is intact; the reference stays.
- **AC-A4-5** A product referenced by a line -> `deactivated`; `is_discontinued=true`; `is_active`
  unchanged.
- **AC-A4-6** A sales order whose line is referenced (e.g. `stock_transfer`) -> `deactivated`
  with `status='cancelled'`; a sales order with no external referrers -> `deleted` with its lines.
- **AC-A4-7** `dry_run=true` reports the verdict each ref would get and writes nothing.
- **AC-A4-8** Guard: requires the entity's `.delete` slug (403 without it) on top of the ingest
  guard; `test_external_permission_coverage` still passes.
- **AC-A4-9** A batch with one ref that errors mid-way still returns verdicts for the others.
