# PLAN: DO date required (DO-IMPORT-DATE)

Status: built, in review (small fix track: no migration, no auth/RBAC change, no new ingest surface)

Owner, 29 Oct 2026: "there shouldn't be any undated DO; fix why there is no date instead of
circumventing it".

## Evidence (crew, dev DB copy, read-only)

11 live DOs have no DO date. None come from AutoCount, all have 0 lines: 10 type RMA created in one
batch on 2026-08-28 09:27:30 (e.g. RMA-M2608-0172, RMA-M2608-0181) and 1 type SAMPLE (MKTPT-0802,
delivery date set, DO date blank).

## Root cause

`OrderService.import_excel_tracking` maps the Master sheet's "Date" to `orders.order_date`
(`order_service.py` master_mapping). `parse_date_value` returns None for a blank or unparseable
cell, and the row is created (or an existing DO updated, wiping its date) with no check. The column
is nullable (`models/order.py` `order_date`) and `OrderCreate.order_date` is optional, so the API
accepts an undated DO too. `bulk_import_orders` (JSON bulk import) has the same gap.

## Change

1. Excel tracking import: a Master row whose Date is blank or unparseable is refused with a per-row
   error, the same way a missing Doc. No. is (`MISSING_DOC_DATE` / `INVALID_DOC_DATE` outcome codes).
   The row is not created and an existing DO keeps its date.
2. API: `OrderCreate.order_date` is required and non-null; `OrderUpdate` rejects an explicit
   `order_date: null` (omitting it still leaves the stored date alone). `OrderResponse` keeps it
   optional so existing NULL rows still read. `bulk_import_orders` refuses a new row with no date
   and a row that would blank an existing date.
3. Read-only report `scripts/report_undated_dos.py`: lists live undated DOs (number, type, created
   at, delivery date, line count, cancelled, AutoCount or not, company) for the owner to decide
   delete vs fill. Changes no data. Run from `sorento_crm_backend/`:
   `venv/bin/python scripts/report_undated_dos.py`.
4. No DB constraint here: NOT NULL waits until the owner has cleaned the 11 rows.

## Follow-up (not in this lane)

For REPORT-OUTSTANDING-SUMMARY: once the owner has cleaned the existing rows (the report below
prints none), the "undated DO" exclusion in the delivered-sales / pending-delivery dataset
(066b966e60, #1401), `Order.order_date.isnot(None)` in `_fixed_filters`
(`app/services/reports/datasets/delivery_order_lines.py:92`), is dead code: remove it there,
along with a NOT NULL migration on `orders.order_date`. Left in place here on purpose.

## Tests (red first)

`tests/test_do_date_required.py`: import refuses a blank and an unparseable Master date with the
per-row error and creates nothing; an existing DO keeps its date; POST without order_date is 422;
PUT with order_date null is 422; PUT without order_date leaves it; reading a legacy NULL row works;
bulk import refuses an undated new row.
