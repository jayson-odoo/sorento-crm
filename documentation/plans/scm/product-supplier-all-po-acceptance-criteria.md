# UAC: product_suppliers from the whole purchase-order history

Plan: `PLAN-product-supplier-all-po.md`. Script:
`sorento_crm_backend/scripts/backfill_product_supplier_from_last_po.py`.

## AC-ALL.1 One link per (product, supplier) pair with non-cancelled PO history

Given product P has purchase-order lines under supplier X (issue 2024-03-01) and
supplier Y (issue 2026-05-01), neither PO cancelled,
when `run(db, apply=True, all_suppliers=True)`,
then `product_suppliers` holds exactly two rows for P: (P, X) and (P, Y).

## AC-ALL.2 The newest pair is the only primary

Given AC-ALL.1,
then (P, Y).is_primary_supplier is True and (P, X).is_primary_supplier is False,
and P's link to the DEFAULT supplier is deleted (DEFAULT is not the newest pair).

## AC-ALL.3 Terms come from that supplier's newest priced line

Given supplier X's lines for P are: 2024-01-10 unit_cost 10.00 currency CNY (line
currency NULL, order currency CNY); 2024-03-01 unit_cost 11.50, line currency USD, order
currency CNY; 2024-06-01 unit_cost NULL,
when the sweep runs,
then (P, X).unit_cost = 11.50 and (P, X).currency = 'USD' (newest PRICED line; the line
currency beats the order currency; the unpriced newer line is ignored).

## AC-ALL.4 No priced line means no invented price

Given supplier Z has only NULL-cost lines for P,
then (P, Z) is created with unit_cost NULL and currency NULL.

## AC-ALL.5 A keyed price is never overwritten

Given (P, X) already exists with unit_cost 12.00 currency MYR,
then after the sweep it still reads 12.00 / MYR and `terms_filled` does not count it.
Given (P, W) already exists with unit_cost NULL and W has a priced line 7.25 CNY,
then after the sweep it reads 7.25 / CNY and `terms_filled` counts it once.

## AC-ALL.6 Cancelled POs do not exist for this sweep

Given supplier Q's only PO for P has status 'cancelled',
then no (P, Q) link is created.
Given P's newest PO (supplier R) is cancelled and its newest non-cancelled PO is
supplier Y,
then (P, Y) is primary and no (P, R) link exists.

## AC-ALL.7 Idempotent

Given the sweep has been applied once,
when it is applied again with the same flags,
then the report shows created 0, promoted 0, terms_filled 0, default_removed 0, and the
`product_suppliers` row count is unchanged.

## AC-ALL.8 Dry-run writes nothing

Given the data of AC-ALL.1,
when `run(db, apply=False, all_suppliers=True)`,
then the report shows pairs_seen 2, created 2, and `product_suppliers` for P is exactly
the rows that existed before the call.

## AC-ALL.9 Without the flag, today's behaviour holds

Given AC-ALL.1's data plus a supplier Q known only through a cancelled PO,
when `run(db, apply=True)` (no flag),
then P has exactly one non-DEFAULT link, (P, Y), primary - and no (P, X), no (P, Q).

## AC-ALL.10 The order sheet's Supplier column agrees

Given a product whose newest PO is cancelled and whose newest non-cancelled PO names
supplier Y,
when `summary_order_service._last_po_supplier_map(db, [product_id])` runs,
then it names Y.

## AC-ALL.11 CLI

`python scripts/backfill_product_supplier_from_last_po.py --apply --all-suppliers` is
accepted; `--all-suppliers` without `--apply` is a dry-run. The report printed by
`_print_report` shows `pairs_seen` and `terms_filled` when the flag is on.

## AC-ALL.12 DEFAULT is never a secondary link

Given the DEFAULT supplier has an OLDER non-cancelled PO line for product P and supplier
Y has a newer one,
when `run(db, apply=True, all_suppliers=True)`,
then no (P, DEFAULT) link exists afterward and `default_removed == 1` - DEFAULT is only
ever linked when it IS the primary pair, never created or kept as a secondary one.

## AC-ALL.13 Cost is never written without its currency

Given a priced PO line for (P, supplier) whose LINE currency and ORDER currency are both
NULL,
when the sweep runs,
then the created link has `unit_cost` NULL and `currency` NULL - `unit_cost` and
`currency` are written together or not at all, never a cost with no currency.
