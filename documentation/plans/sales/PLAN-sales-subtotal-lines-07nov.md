# PLAN: AutoCount subtotal lines excluded from line-based sales sums (SALES-SUBTOTAL-LINES)

Status: in review (small fix track plus one additive migration; lane SALES-SUBTOTAL-LINES, 7 Nov 2026, PR #2230)

## Problem

Some AutoCount invoices carry a blank-item "subtotal" line: no item code, no UOM, no qty, no unit
price, no from-doc, and a `net_amount` equal to the running subtotal of the lines above it. The
line-sum path (`invoiced_sales.signed_line_amount()`, summed by the `billing_document_lines`
dataset `_base`) counts it as a sale, so the document is double counted (line sum > header
`local_net_total`). Seen on 6 documents and 15 company-months Jan-Oct 2026 (SRT, MCH) on the dev
copy. Header totals are right; targets read the header and are unaffected.

## Findings (read, not guessed)

- AutoCount marks the line in `IVDTL.DtlType` (`REF-autocount-billing-schema.md` section 3 cut
  note and 6.5), but the CRM payload does not carry it: `CanonicalBillingDocumentLine`
  (`app/schemas/canonical_documents.py:441`) has no line type field and the shared service does
  not send one. So there is no explicit flag to read in the CRM today; the rule must be exact.
- Line-based sums that can see a no-product line: only the `billing_document_lines` dataset
  (`app/services/reports/datasets/billing_document_lines.py` `_base`), which serves Top selling,
  the report ask on the invoiced basis, the Sales and outstanding screen and the chatbot. The
  other line reads (`achievement_service._achieved_invoiced` product-scoped lines,
  `invoiced_sales` product-month quantities) already require `product_id`, which a subtotal
  line never has.

## Rule (exact, never fuzzy)

A line is a subtotal line when ALL hold:
1. shape: `item_code`, `product_id`, `uom`, `quantity`, `unit_price`, `from_doc_type`,
   `from_doc_no`, `from_line_ref` and `sales_order_line_id` are all null (blank item code counts
   as null);
2. at least one counted line precedes it in the document (by `line_no`, then `source_ref`);
3. its `net_amount` equals EXACTLY the sum of the counted lines above it, either since the start of
   the document or since the previous subtotal line;
4. the document's lines do NOT already add up to its header `net_total` (review round 1: a
   document that balances double counts nothing, so a charge line that happens to equal the lines
   above it, e.g. item 50.00 + freight 50.00 on a 100.00 invoice, stays a sale).

"Counted" = every line that is not a subtotal line (so a freight charge line above a subtotal is
part of it). Evaluated top to bottom.

## Design

- New column `finance.billing_document_lines.is_subtotal boolean not null default false`, set by the
  billing ingest on every push from the whole document (the ingest replaces the lines whole), and
  backfilled by the migration with the same rule as a recursive SQL walk.
- `invoiced_sales.counted_line()` is the one predicate; `billing_document_lines._base` applies it.
- The document view keeps showing every line (nothing is deleted). The invoiced report's
  "Billing document lines" detail table reads the same `_base`, so a subtotal line is left out of
  that table too: intended, it is a sales listing, and the document page shows the line.
- Read-only reconciliation SQL: `documentation/plans/sales/SQL-sales-subtotal-reconcile.sql`.

## Tests

- Ingest of a fixture invoice with a subtotal line marks only that line; a freight line with no
  qty is not marked; a re-push that edits the lines re-decides.
- Dataset sum over the fixture equals the header `local_net_total`.
- Kill test: removing the predicate turns the dataset test red.
