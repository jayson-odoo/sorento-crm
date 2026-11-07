# PLAN: AutoCount subtotal lines excluded from line-based sales sums (SALES-SUBTOTAL-LINES)

Status: verified on the dev copy, awaiting CI and merge (small fix track plus one additive migration; lane SALES-SUBTOTAL-LINES, 7 Nov 2026, PR #2230)

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

## Round 2 (crew verification, PR #2230 comments 6704618301, 6704659700, 6704685087)

Round 1 removed RM 1,494,224.00 (25 documents, 0 false exclusions). Still off: 41 documents.

- **SRT Jan, PSWR26-0001 (+RM 64,434.70).** Its `SubTotal` line (no item, UOM, qty or price) carries
  `from_doc_type = DO`, which the round 1 shape test refused. Fact-based widening: a from-doc
  reference (and a resolved SO line) no longer disqualifies a subtotal line; every other
  condition, the exact sum and the header guard stay.
- **MCH Jan-May and Aug (40 documents, +RM 138,356.80): AutoCount item packages.** Cause: the AutoCount
  `IVDTL` of `AED_V2_MOCHA` holds one PARENT row per package set (no ItemCode, `ParentDtlKey = 0`,
  carries Qty, UnitPrice and SubTotal, description "... SET PACKAGE ...") and N CHILD rows
  (`ParentDtlKey` = the parent's DtlKey); the FIRST child repeats the parent's Qty, UnitPrice and
  SubTotal. The shared service sends every row and never selects `ParentDtlKey` (its
  `presets.py:774-782, :843-866`; crew lane SS-PACKAGE-LINES carries it onto canonical lines). The
  CRM stores exactly what it is pushed (`billing_document_ingest_service.py` `_create` / `_update`:
  lines replaced whole, unique only on `(document_id, source_ref)`), so both rows were summed.
  `Seq` is NOT a safe key (M2601-1517: parent Seq 48, child Seq 16).
- **CRM rule (`is_duplicate`, exact):** a line naming no item and no UOM, stating quantity, unit price
  and net, whose quantity, unit price, discount and net are repeated exactly by a line in the same
  document that names an item; one real line excuses one copy; same header guard. The children
  are counted (they carry the item codes); the parent row stays on the document.
- **Reconciliation:** `SQL-sales-subtotal-reconcile.sql` is generated from the migration's
  `VERDICT_SQL` (a test asserts it carries it verbatim). Query 1 adds the dry-run counts
  (`subtotal_lines`, `package_copies`, `docs_marked`, `docs_still_off`); Query 2 lists every 2026
  document whose counted lines differ from its header (target 0 rows).
- **Trigger for the next step:** once SS-PACKAGE-LINES ships `ParentDtlKey` on canonical lines, the
  CRM reads it (a line some other line names as its parent is the copy) and keeps this rule only
  for rows ingested before it, unless MCH 2026 is re-pulled.

### Review round 2 and contract v2.13

- **Copies need an exact balance (review round 2 blocker).** A document with a subtotal line or
  header-only money never balances, so the header guard was off and a charge equal to an item line
  could be taken as a package copy, which then hid the subtotal. Copies are now taken only when
  the document's lines less the copies equal `net_total` exactly; otherwise none is. A document
  carrying both a package and a subtotal stays counted whole: a visible miss in reconcile Query
  2, never a guess.
- **Explicit parents (contract v2.13, SS-PACKAGE-LINES ss PR #226).** Billing lines accept
  `parent_line_ref` and `line_type` (stored, echoed on read; `CONTRACT_VERSION` 2.11 -> 2.13, 2.12
  left to the lane that holds it). A parent named by at least one child is not summed when its
  children's net adds up to its own exactly; the SS relay's "drop any parent with a child" would
  lose SRT package sales, whose children carry no money (RUNBOOK, AED_SORENTO). A document carrying
  `parent_line_ref` is decided by it alone. Rows ingested before 2.13 keep the exact inferred
  rule and its backfill, so no re-push is needed for the figures.
- `SQL-sales-subtotal-reconcile.sql` is written by `sorento_crm_backend/scripts/gen_subtotal_reconcile_sql.py`.
  Target for Query 2: no rows other than `rounding` (a foreign-currency document can differ by a
  cent between `net_amount x rate` and `local_net_total`).
- A dev copy that already ran the round 1 SQL takes the round 2 crew-migration SQL as is
  (`ADD COLUMN IF NOT EXISTS`); one stamped at `sbt_0001_billing_subtotal_lines` by alembic needs
  `alembic downgrade -1 && alembic upgrade head` (additive, safe). Prod has never run it.

## Verification on the dev copy (crew, head e0f10875, PR #2230 comment 6705356432)

Shipped reconciliation SQL, read-only, on sorento_prod_1104: `diff_after` 0.00 in all 22 company-months
of 2026; Query 2 returns 0 rows. Overstatement removed: SRT RM 1,558,658.70 (Jan 64,743.70, Mar 3,287.40,
Apr 33,761.70, May 383,429.50, Jun 414,281.60, Jul 279,476.80, Aug 87,756.40, Sep 147,317.60, Oct
144,604.00), MCH RM 138,356.80 (Jan 49,640.30, Feb 27,740.20, Mar 12,822.40, Apr 15,409.90, May
32,650.00, Aug 94.00). Unchanged: SRT Feb, Nov; MCH Jun, Jul, Sep, Oct, Nov. False exclusions 0: all
257 documents with excluded lines (all years; 33 subtotal, 267 package-copy lines) balance to their
header exactly. API on the copy: SRT Oct 13,151,657.03, ERIC NG Oct 805,048.34, MCH Jan 3,424,512.45,
MCH May 2,591,192.47, each equal to the header.
