# PLAN: product-grain plan buys confirmed project demand without a reorder level

Status: in progress (10 Sep 2026)
Issue: #794
Lane: `fix/product-grain-project-buy` (worktree `.claude/worktrees/product-grain-project-buy`)
UAC: `product-grain-project-buy-no-level-acceptance-criteria.md`

## Journey

Buyer opens the reorder plan. CSK2800-QT carries 914 units of confirmed unplaced Order Inquiry
Buy (Project column 914) and no reorder level (AutoCount master 0, no buyer override). Today the
row reads Suggested 0 / "Nothing" and the panel says "none set today". The buyer expects the
914 to be bought: CS already confirmed it, a missing level only says nothing about the RETAIL
top-up.

## Cause (measured in code, 10 Sep)

`app/services/scm/reorder_run_service.py::_emit_product`:

```python
if level is None:
    triggered, reason_label = False, None
recommended = float(agg["recommended_qty"]) if triggered else 0.0
project_need = min(sum(project_need over cells), recommended)   # min(914, 0) = 0
...
if level is None:
    recs.append(_build_rec(run_id, "needs_level", ..., order_qty=None, rounded=None))
```

AC-E05 (confirmed unplaced Project Buy bypasses the trigger) is honoured in `_emit_pool`
(`pool_unplannable` -> `if pool_project_need > 0 and not triggered: triggered = True`) and in
`_compute_cell`, not in `_emit_product`. Since the per-product basis is the only path a
`reorder_level` product takes (27 Aug), every no-level product with project demand suggests 0.

Surfaced on 10 Sep because the owner deleted the bulk-seeded manual-50 rows; a master level of 0
reads as unset ("0 is not a level").

## Not a data fix

Setting `products.reorder_level = 0` by query is a no-op (already 0 = unset). Inserting manual
level-0 rows recreates the 13 Aug seed problem (manual outranks master, the upload refuses to
overwrite manual, the needs-level signal disappears). Rejected.

## Change (one function)

In `_emit_product`, after `agg` and the level trigger:

- `pool_project_need = sum(c["project_need"] for c in cells)`.
- If `level is None` and `pool_project_need > 0`: `triggered = True`,
  `recommended = pool_project_need`, `reason_label = "project buy: N confirmed unplaced Buy"`,
  `rounded = eng.round_order_qty(recommended, moq, order_multiple)`, `split` as usual.
  (Same shape as the existing bypass in `_emit_pool` lines ~1607-1612.)
- A level-set product never takes the bypass: its `net` already subtracts the confirmed Buy,
  so the level trigger is the only sizing (test 5 pins this).
- Emit order: a triggered buy with a supplier emits `buy` (with the allocation) even when
  `level is None`; the `needs_level` row is emitted ONLY when `level is None` and nothing was
  bought. `exception` when triggered and no supplier, as today.
- `project_need = min(sum, recommended)` and `retail_need` remain; with the bypass
  `retail_need` is 0 for a no-level product.
- The recommendation's `inputs.needs_level` stays True on the buy row (level still unset), so
  the panel still shows "Set AutoCount level to N".

No FE change: the sheet reads `suggested_qty` / `project_buy_qty` off the summary row.

## Tests (tester writes first, `tests/scm/test_reorder_per_product.py`)

1. No level anywhere + 914 confirmed unplaced Buy (seed via `_confirmed_leg` pattern from
   `tests/scm/test_channel_read_model.py`) + linked supplier -> one `buy` row, `rounded_qty`
   914, `triggered_reason` starts "project buy", `inputs.project_need` 914,
   `inputs.needs_level` True; summary row `suggested_qty` 914, `project_buy_qty` 914,
   `retail_replenishment_qty` 0. No `needs_level` row for the product.
2. No level + retail-only open SO demand -> still exactly one `needs_level` row, no buy
   (unchanged; existing `test_a_product_with_no_level_anywhere_is_named_not_guessed_at`
   stays green).
3. No level + confirmed Buy + MOQ 100 -> `rounded_qty` 1000 (914 rounded up by MOQ/multiple
   rules already in `eng.round_order_qty`).
4. No level + confirmed Buy + no supplier -> `exception` row, `inputs.project_need` 914,
   summary `suggested_qty` 914 (mirrors `test_confirmed_project_buy_survives_a_location_with_no_supplier`).
5. Level 500, on hand 600, confirmed Buy 50 -> byte-identical to today. `net` already
   subtracts committed (project included): net 550 >= 500, no trigger, no buy, the bypass
   must NOT fire on a level-set product. Read the file's existing net arithmetic first.

## Slice 2: order sheet shows the suggestion and prints every planned product (owner, 10 Sep)

Owner, on the S14 Excel: "to the left of order qty, we need to put in our suggested quantity,
and one more column for suggestion, otherwise what's the point" and "include the rows with
suggested quantity = 0 also, otherwise the user might want to order even though we suggest 0".

### Measured (0907 copy, latest completed run, 10 Sep)

Two gates keep rows off the sheet today:

1. `summary_order_service._belongs_on_the_book`: a product gets an `order_summary_row` only
   when the run emitted a `buy` or a project need. `covered` / `needs_level` products get no
   row at all (AC-C2.2a, written when that was ~2,400 rows pre-G1).
2. `export_report` -> `_rows_to_order`: a book row prints only with chosen > 0, suggested > 0
   or shortfall > 0. On the book every row already has suggested > 0, so this gate is a
   near no-op; gate 1 is the one the owner is seeing.

Latest run: buy 374 (all on the book), covered 575, needs_level 1 (prod will carry many more
needs_level rows since the manual-50 rows were deleted). Sheet after this slice: ~950 rows,
under `_MAX_EXPORT_ROWS` 2000. The owner's ruling supersedes AC-C2.2a's exclusion.

### Change

Backend:
- Migration 508: `scm.order_summary_row.suggestion` TEXT NULL (the engine's reason for the
  row, one sentence, as the plan line already shows it).
- `write_rows`: every product with a product-grain recommendation in the run (`buy`,
  `exception`, `covered`, `needs_level`) gets a book row. `suggested_qty` stays 0 for
  `covered` / `needs_level`; `suggestion` = the first recommendation's `triggered_reason`
  (buy: e.g. "below level ..." / "project buy: 914 confirmed unplaced Buy"; covered: "N
  available ... covers ..."; needs_level: `_needs_level_label`; exception: "no linked
  supplier - cannot source this reorder"). `_belongs_on_the_book` becomes "has any
  product-grain rec"; keep the function, change the rule and the docstring.
- `_serialise_row`: add `suggestion`. Schema `scm_order_summary.py` gains the field.
- Export: `_EXPORT_COLUMNS` becomes `Item code, BRW on hand, Reorder level, Project qty,
  Dealer o/s, Suggested qty, Suggestion, Order qty, Delivery, Project / customer, Supplier,
  BRW PO qty, BRW incoming qty, Last in qty, Last in date, Remarks`. `_export_rows` /
  `_export_xlsx_rows` add the two cells (Suggested qty as a number, 0 printed as 0 - it is
  a measured figure here, unlike the blank rule for Order qty; Suggestion as text through
  `_xlsx_safe_text`). `_PDF_LIST_COLUMNS` -> (8, 9); `_PDF_NUM_COLUMNS` -> (1, 2, 3, 4, 5,
  7, 11, 12, 13). `_rows_to_order` is removed; `export_report` prints every book row.
- Confirm / decision paths must accept a row whose suggested_qty is 0 (chosen_qty > 0 on
  it is a valid decision). Check `record_decision` for any `suggested_qty > 0` guard.

Frontend:
- `summaryOrder.types.ts` gains `suggestion: string | null`; the mock store carries it.
- Wherever the order summary rows render on screen (`ReorderPlanView` / its summary tab),
  a `Suggestion` column beside Suggested qty, `truncate` + `title`. Rows with suggested 0
  now appear there too; no filter added.

### Tests (tester, `tests/scm/test_order_summary_sheet.py` + the book tests)

6. A run with one `buy` (suggested 12), one `covered` and one `needs_level` product ->
   `write_rows` writes THREE book rows; the covered and needs_level rows have
   `suggested_qty` 0 and a non-empty `suggestion`; the buy row's `suggestion` is its
   `triggered_reason`.
7. `export_report(fmt="xlsx")` header row equals the new `_EXPORT_COLUMNS`; the buy row's
   "Suggested qty" cell is 12.0 and sits immediately left of "Suggestion", which sits
   immediately left of "Order qty" (blank until chosen); the covered row prints with
   Suggested qty 0 and its suggestion text; no row is dropped for suggested 0.
8. PDF export renders the same 16 columns (existing PDF test pattern) and wraps the two
   list columns at their new indices.
9. `record_decision` on a row with `suggested_qty` 0 and `chosen_qty` 5 succeeds.
10. Existing S14 tests updated for the two new columns, nothing else changed.

## Slice 3: PO and SPO numbers under the BRW PO qty and BRW incoming qty cells (owner, 10 Sep)

Owner: "the rows where we have BRW PO and BRW incoming quantity, better put down the PO and
SPO number as new lines below for traceability".

### Source (measured in code)

- `_po_open_qty_map`: `purchase_order_lines pol JOIN warehouses` (site pool, line open),
  summed per product. The document is `purchase_orders.po_number` via
  `pol.purchase_order_id`.
- `_incoming_spo_qty_map`: `spo_allocations` (open incoming clauses, site pool), summed per
  product. The document is `spo_allocations.spo_number` (a shipping order has no header
  table; the number IS the document, D3).

### Change

Backend:
- Both maps return the breakdown as well as the total: `{pid: {"qty": total, "docs":
  [{"number": ..., "qty": ...}, ...]}}` grouped by document number, sorted by number,
  qty = the open remainder of that document for the product. A line with a NULL number
  groups under "(no number)".
- Two new JSONB columns on `scm.order_summary_row` (same migration 508 as `suggestion`):
  `po_open_docs`, `incoming_spo_docs`, the list above. `_serialise_row` exposes both; FE
  type gains them.
- Export cell text for the two columns (PDF and xlsx alike), shaped like `_month_text`:
  first line the total, then one `"<number> - <qty>"` per document:

      30
      SPO-2026/08-0012 - 30

  With no documents the cell stays the bare number (xlsx: numeric 0 / total). The H1
  "quantities as numbers" rule yields on these two columns only, when documents exist:
  traceability outranks summing a column the buyer never sums. `_PDF_LIST_COLUMNS` gains
  the two indices (after slice 2: 11 and 12); the two stay in `_PDF_NUM_COLUMNS` for
  right-alignment only if the renderer tolerates both, otherwise drop them from it.

Frontend: types only, plus the same two-line rendering in the on-screen order summary's
two cells if that grid shows them (`truncate` + `title` with the full list).

### Tests (tester, `tests/scm/test_order_summary_sheet.py`)

11. A product with two open PO lines at the pool on two POs (PO-A 4 owed, PO-B 1 owed) and
    one open SPO allocation (SPO-X 30) -> book row `po_open_qty` 5, `po_open_docs`
    `[{"number": "PO-A", "qty": 4}, {"number": "PO-B", "qty": 1}]`, `incoming_spo_qty` 30,
    `incoming_spo_docs` `[{"number": "SPO-X", "qty": 30}]`.
12. xlsx export: the BRW PO qty cell reads "5\nPO-A - 4\nPO-B - 1" and BRW incoming qty
    reads "30\nSPO-X - 30"; a product with nothing open keeps numeric 0 in both.
13. PDF: the two cells render one entry per line (same check the Delivery column's test
    makes).
14. A project-bin PO line and a received SPO allocation contribute nothing to the docs list
    (the pool predicate and open clauses still apply).
