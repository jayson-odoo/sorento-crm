# PLAN: product_suppliers from the WHOLE purchase-order history (`--all-suppliers`)

Status: implemented (10 Sep 2026), PR pending
Domain: scm / master data
Lane: `feat/product-supplier-all-po` (`.claude/worktrees/product-supplier-all-po`)
UAC: `product-supplier-all-po-acceptance-criteria.md`
Parent: `PLAN-reorder-feedback-9sep.md` S15 (rulings 1-2), merged in #797

## Journey

The buyer opens a product's Suppliers tab and sees every supplier the company has
actually bought that product from, with the price last paid to each, and the one it was
bought from most recently marked primary. Today the tab shows the code DEFAULT (or, after
the S15 backfill, only the last supplier) because `product_suppliers` was never derived
from the purchase-order book.

## Measured, 10 Sep 2026, prod copy `sorento_ai_automation_0907`

| Fact | Count |
|---|---|
| Products with PO history | 5,353 |
| Distinct (product, supplier) pairs across every PO | 7,746 |
| Products bought from 2+ suppliers | 1,648 (31%); max 32 (RPACC, a catch-all code) |
| Pairs last bought before 2024 | 2,980 (38%) |
| Pairs already in `product_suppliers` | 2 |
| PO lines with NULL `unit_cost` | 24,112 of 91,533 (26%) |
| PO status | active 539, cancelled 39, closed 5,757 |
| Pairs that exist ONLY through cancelled POs | 4 |
| PO currency | CNY 4,096, MYR 1,278, USD 960, EUR 1 |

## Rulings (owner, 10 Sep 2026)

1. **Terms:** each link takes `unit_cost` + `currency` from THAT supplier's newest PRICED
   PO line for the product (`unit_cost IS NOT NULL`). `moq` / `order_multiple` stay NULL -
   a PO never states them. `last_purchase_price` is left NULL: nothing in `app/` or the
   frontend reads it (grep, 10 Sep), so writing it would be a value nobody sees.
2. **Old pairs:** link ALL of them. `effective_to` stays NULL; the buyer retires a link by
   hand if wanted.
3. **Cancelled POs are excluded** - from the pair set, from the "newest PO" that picks the
   primary, and from `summary_order_service._last_po_supplier_map` (the order sheet's
   Supplier column), so the script and the sheet keep naming the same supplier.

## What exists (do not rebuild)

- `scripts/backfill_product_supplier_from_last_po.py` - `run(db, apply, drop_default_all,
  default_supplier_code)`, `_last_po_suppliers(db)`, `main()` with company-scope setup.
  One link per product (the last-PO supplier), DEFAULT link deleted unless DEFAULT is the
  last-PO supplier. Tests: `tests/scm/test_supplier_last_po_s15.py` (AC-S15.6) on
  `tests._pg_fixture.blank_session`.
- `summary_order_service._last_po_supplier_map` (line ~849) - same `DISTINCT ON` shape.
- Currency cascade: the LINE's currency wins over the ORDER's -
  `COALESCE(pol.currency, po.currency)`, `upper(btrim(..))`, exactly as
  `currency_rate_service.list_rates` reads it. Reuse that expression.
- `resolve_standard_lead_time_days(settings)` for a created link's lead time.
- FE `ProductSupplierTermsRow` already appends a row's own currency to the select when it
  is not among the rated ones (lines 118-120), so a seeded `CNY` renders even though only
  MYR has a rate today. No FE change.

## Design (simplest thing that works)

One flag on the existing script. No new script, no new table, no new endpoint.

### `run(..., all_suppliers: bool = False)`

`all_suppliers=False` keeps today's behaviour byte-for-byte except ruling 3 (cancelled
excluded). `all_suppliers=True`:

1. `_po_supplier_pairs(db)` - raw SQL under `company_sql_predicate`, cancelled excluded:
   per `(product_id, supplier_id)`: `product_code`, `supplier_code`, `newest_issue_date`,
   `newest_created_at` (the pair's newest line, `issue_date DESC NULLS LAST, created_at
   DESC`), and from the pair's newest PRICED line `unit_cost` + `currency`
   (`upper(btrim(COALESCE(pol.currency, po.currency)))`, NULL when no priced line). Two
   `DISTINCT ON (pol.product_id, po.supplier_id)` selects (one unfiltered for recency, one
   `WHERE pol.unit_cost IS NOT NULL` for terms) joined in Python by pair is fine; one CTE
   is also fine. Whichever reads shorter.
2. The product's PRIMARY pair = the pair with the newest line (same ordering as
   `_last_po_suppliers`; derive it from the pair rows rather than a second query).
3. Per pair, excluding the DEFAULT supplier unless it is the primary pair (DEFAULT is a
   placeholder; the existing rule that deletes a non-primary DEFAULT link stands):
   - no link -> **create**: `is_primary_supplier = (pair is primary)`,
     `standard_lead_time_days = resolve_standard_lead_time_days(settings)`, `unit_cost`,
     `currency` from the pair (NULL allowed).
   - link exists -> `is_primary_supplier` set to `(pair is primary)`; `unit_cost` and
     `currency` are **filled only when the link's `unit_cost` IS NULL** - a value the
     buyer keyed is never overwritten. When filling, both columns are written together
     from the pair (a cost without its currency is not a price).
4. Every other link of the product: `is_primary_supplier` cleared, nothing else touched.
5. DEFAULT link handling unchanged: deleted unless DEFAULT is the primary pair;
   `drop_default_all` unchanged.
6. Report gains `pairs_seen`, `terms_filled` (existing links whose NULL cost was filled;
   created links carry their terms silently, they are counted under `created`). Samples
   stay `"<product_code> -> <supplier_code> (created|promoted|filled)"`.
7. Idempotent: a second `--apply` reports 0 created / 0 promoted / 0 filled / 0 removed.

### CLI

`--all-suppliers` (store_true) added to `main()`, passed through. Docstring at the top of
the script gains a WHAT IT DOES paragraph for the flag and the three rulings above.

### `summary_order_service._last_po_supplier_map` + `_last_po_suppliers`

Both gain `AND po.status <> 'cancelled'`. `_last_receipt_map` beside it is a GRN read and
is not touched.

## Not in scope

- Rates for CNY/USD/EUR - keyed by the buyer under SCM > Policies > Currency rates; the
  product Suppliers tab offers only rated currencies by design.
- Any FE change. Any new endpoint. Running the script on prod (owner's `docker cp` step,
  needs go, `--dry-run` first).

## Test list (tester writes these red first; `tests/scm/test_supplier_all_po.py`, blank_session)

- T1 default path unchanged: `run(apply=True)` without the flag creates ONE link per
  product and ignores a pair whose only PO is cancelled.
- T2 two suppliers: P bought from X (older) and Y (newer) -> two links, Y primary, X not,
  P's DEFAULT link deleted.
- T3 terms: X link `unit_cost`/`currency` = X's newest PRICED line; a newer UNPRICED X
  line does not blank it; line currency beats order currency; a pair with no priced line
  gets NULL `unit_cost` and NULL `currency`.
- T4 keyed terms kept: an existing link with `unit_cost=12` keeps 12 and its currency; an
  existing link with NULL `unit_cost` is filled and counted in `terms_filled`.
- T5 cancelled: a pair that exists only via a cancelled PO gets no link; when P's NEWEST
  PO is cancelled, primary goes to the newest non-cancelled supplier.
- T6 idempotent: second `run(apply=True, all_suppliers=True)` reports all zeros and the
  row count is unchanged.
- T7 dry-run with the flag writes nothing and reports the plan (`pairs_seen`, `created`).
- T8 `_last_po_supplier_map` skips a cancelled PO (shared-DB `chain` fixtures, as
  `test_supplier_last_po_s15.py` does).
- T9 `main()` parses `--all-suppliers` (argparse namespace only; do not run the sweep).

Run ONLY `pytest tests/scm/test_supplier_all_po.py tests/scm/test_supplier_last_po_s15.py
-q` in this lane. Never the full scm suite on the shared DB.

## Rollout

1. PR from this lane; CI green; single alembic head (no migration in this lane).
2. After merge + deploy, owner runs on prod: `--dry-run --all-suppliers`, reads counts
   against the table above (expect ~7,700 pairs, ~5,350 products), then `--apply
   --all-suppliers`. Needs an explicit go.
3. Archive this plan + UAC to `documentation/plans/_archive/scm/` when the prod run is done.

## Rulings addendum (review, 10 Sep)

1. **Primary tie, final deterministic tiebreak:** when two suppliers tie on BOTH
   `issue_date` and `created_at` (measured live: PACKAGING BOX, suppliers 400-N004 and
   400-X008, tied from a same-transaction import), `supplier_id` (desc) is the last
   ORDER BY key everywhere a "primary"/"newest" supplier is picked - the `pairs` CTE in
   `_po_supplier_pairs`, `_last_po_suppliers`, `_pick_primary`, and
   `summary_order_service._last_po_supplier_map` - so `--all-suppliers`, the default
   path, and the order sheet's Supplier column never disagree on a tied product.
2. **Priced-line tiebreak:** the `priced` CTE's `ORDER BY` also falls through to
   `pol.created_at DESC, pol.id DESC` below `po.created_at DESC`, so two priced lines on
   the SAME PO for the same product resolve the same way every run (matches
   `PurchaseOrder.lines`'s own ordering, `app/models/procurement.py:782`).
3. **Cost and currency, together or not at all:** a priced PO line whose line AND order
   currency are both NULL (0 rows on prod today) no longer writes a cost with no
   currency; `unit_cost`/`currency` are always written together or neither is, on both
   create and fill.
