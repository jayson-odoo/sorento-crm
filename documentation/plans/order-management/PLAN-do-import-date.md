# PLAN: DO date: import undated DOs flagged, never wipe a date (DO-IMPORT-DATE)

Status: rework DO-IMPORT-DATE-2 built, in review (small fix track: no migration, no auth/RBAC change, no new ingest surface)

Owner, 29 Oct 2026: "there shouldn't be any undated DO; fix why there is no date instead of
circumventing it". Then, 29 Oct ~22:45: "maybe we cannot be too harsh to require a date cause
these are quite manual DO", and 30 Oct ~10:00: no existing import or integration may fail;
unreadable dates are skipped in reports. The first build (refuse undated rows) is replaced by
the rule below (crew-ask on #1975, option (a), confirmed by crew 30 Oct).

## Evidence (crew, dev DB copy, read-only; not re-run in the cloud lane)

11 live DOs have no DO date. None come from AutoCount, all have 0 lines: 10 type RMA created in one
batch on 2026-08-28 09:27:30 (e.g. RMA-M2608-0172, RMA-M2608-0181) and 1 type SAMPLE (MKTPT-0802,
delivery date set, DO date blank).

Sources: AutoCount DO sync always has a date (`autocount_doc_ingest_service.py` `_parse`,
DocDate required; unchanged). SO to DO auto-create sets today (`scm/sales_order_service.py`).
Only the manual Excel tracking import and the JSON bulk import can arrive undated.

## Root cause

`OrderService.import_excel_tracking` maps the Master sheet's "Date" to `orders.order_date`.
`parse_date_value` returns None for a blank or unparseable cell, and that None was written: a new
DO became undated with no message, and an existing DO had its date wiped. `bulk_import_orders`
had the same gap, and `OrderUpdate` with `order_date: null` cleared the date.

## Change (rule: nothing fails because of a DO date; a stored date is never cleared)

1. Excel tracking import: a blank or unreadable Master Date never refuses the row and never
   clears a stored date. A DO left undated is flagged in the import summary (warning text, and
   the row's outcome code is `missing_doc_date` "No document date" or `invalid_doc_date`
   "Unreadable document date"); an unreadable date on a DO that keeps its stored date is flagged
   too; a blank on a dated DO says nothing (nothing lost). A Master sheet with no Date column
   imports with one sheet-level warning (each new DO is still flagged by name).
   AutoCount-owned DOs: the sheet Date is ignored, as before. Excel
   date serials (2000-2099) parse in both import parsers; any other number counts as unreadable.
2. JSON bulk import: same rule, warnings in its `warnings` list.
3. API: `OrderCreate.order_date` stays optional; `OrderUpdate` treats `order_date: null` as
   "unchanged" (never clears).
4. Reports: unchanged. Undated DOs stay out of delivered sales / pending delivery
   (`delivery_order_lines.py` `Order.order_date.isnot(None)`) until someone fills the date.
5. Read-only `scripts/report_undated_dos.py` lists live undated DOs (the to-fill list).
   Run from `sorento_crm_backend/`: `venv/bin/python scripts/report_undated_dos.py`.
6. The 11 existing undated DOs are left as they are. No DB constraint, no migration.

## Follow-up (not in this lane)

The undated-DO exclusion in the delivered-sales / pending-delivery dataset
(`app/services/reports/datasets/delivery_order_lines.py` `_fixed_filters`) is now the intended
behaviour, not dead code: keep it. No NOT NULL on `orders.order_date` (manual DOs may be undated).
A "No DO date" filter on the DO list is possible later if the report script is not enough.

Found in review, pre-existing, not regressions:
- The DO edit form fills an empty date with today (`sorento_crm_frontend/app/(protected)/order-management/orders/components/OrderForm.tsx`
  `order_date` default), so saving an undated DO stamps a made-up date and puts it into reports.
  Fix: leave the date empty on edit and let the form save without one (FE lane, browser check).
- The tracking sheet keeps an undated DO that has a delivery date at status "new" with no
  delivery days (`import_excel_tracking`, Overall Tracking branch), because both need the DO date.

## Tests

`tests/test_do_date_required.py`: blank and unreadable Master dates import flagged (warning +
outcome code) and undated; an existing DO keeps its date on a blank or unreadable cell; a sheet
with no Date column imports with one warning; validate-only previews the warning, not an error;
POST without order_date succeeds; PUT with order_date null keeps the date; bulk import creates
undated rows flagged and keeps stored dates; Excel serials parse; the report lists live undated
DOs only.
