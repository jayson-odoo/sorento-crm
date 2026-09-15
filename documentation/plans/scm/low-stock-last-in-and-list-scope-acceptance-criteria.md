# UAC - Low stock report: last in from the last SPO line, All sheet matches the list

Plan: `PLAN-low-stock-last-in-and-list-scope.md`. Numbering continues the parent
(`low-stock-report-acceptance-criteria.md` ends at AC-47).

## Last in (S1) - owner ruling 15 Sep: the MCP pick, received or not; cell like PO qty

- **AC-48** For a product whose newest visible `spo_allocations` line is SPO `202608-S0084`,
  container `TLLU8306312`, `allocated_quantity` 180, `expected_date` 2026-08-14 (any
  `quantity_received`), the frozen `order_summary_row` carries `last_receipt_qty = 180`,
  `last_receipt_date = 2026-08-14`, `last_receipt_spo_number = '202608-S0084'`,
  `last_receipt_container_number = 'TLLU8306312'`, and `report()` returns
  `last_receipt == {"date": "2026-08-14", "qty": 180, "spo_number": "202608-S0084",
  "container": "TLLU8306312"}`.
- **AC-49** A newer visible line with `quantity_received = 0` (not yet received) IS the last in:
  it displaces an older received line, exactly as
  `last_receipt_rows(product_ids=[p], top_n=1)` picks it. A test asserts the sheet's pick equals
  that function's `spo_number` for the same seed.
- **AC-50** A line hidden by `visible_line_clauses()` (retired and never received) never answers;
  a retired line WITH a receipt may.
- **AC-51** A product with no visible SPO line freezes all four columns NULL, `report()` returns
  `last_receipt = None`, both workbooks print BLANK Last in qty and Last in date, never 0.
- **AC-52** `picking_lines` / `picking_headers` are no longer read for last in: a product with a
  goods_received picking line and no SPO line prints blank.
- **AC-53** Two lines sharing the same key date: `created_at DESC` breaks the tie.
- **AC-54** Company scope: under a Mocha scope a Sorento-owned line on a Mocha product is not
  picked.
- **AC-55** The "Last in qty" cell on BOTH workbooks (order sheet xlsx + PDF, low stock Low + All)
  is TEXT `"202608-S0084 - TLLU8306312 - 180"`; `"202608-S0084 - 180"` when the line has no
  container; `""` when there is no line. Column count and order are unchanged (16; 15 without
  Supplier). "Last in date" stays `dd/mm/yyyy` of the SPO line's date.
- **AC-56** The order sheet PDF renders the Last in qty cell with the list class (one line, left
  aligned like the PO / incoming cells), not the numeric class.
- **AC-57** A run frozen BEFORE migration 518 (SPO/container NULL, qty and date present) prints
  the bare quantity text (`"300"`) and its date; no data backfill.
- **AC-58** Migration `518_osr_last_receipt_spo` upgrades and downgrades cleanly on top of
  `ptag_0009_combos_tags` (re-parented from the plan's originally-named
  `517_chatbot_low_stock_vocab`, which `ptag_0009_combos_tags` had already merged on top of
  by the time this lane branched - `./scripts/alembic-reparent.sh`); `alembic heads` shows
  one head.
- **AC-59** The order summary route's response declares the two new keys (a route test asserts
  `spo_number` and `container` survive `response_model`).

## All sheet matches the list (S2)

- **AC-60** A run with 5 planned products, 2 of them `hidden_by_default = true`: the All sheet
  prints exactly the 3 visible products; the Low sheet is the subset of those 3 with
  `pool_on_hand < reorder_level`; a hidden product below its raw level is NOT on either sheet.
- **AC-61** `export_low_stock` returns counts `{"low": n_low, "all": 3}` for that run, and the
  chat reply / `row_count_low` / `row_count_all` on `user_downloads` carry the same figures.
- **AC-62** The low-stock export route's guard uses `export_guard_stats`: for the run above it
  reports `row_count = 3`, equal to the plan list's Lines count (`recommendation_count`) and to the
  order-sheet export guard. `low_stock_guard_stats` no longer exists (importing it fails).
- **AC-63** The cap `MAX_LOW_STOCK_ROWS` (5,000) is applied to the visible All rows, not the
  frozen total: a run with 5,100 frozen rows of which 200 are hidden exports.
- **AC-64** `export_report` (order sheet) behaviour is unchanged: it calls the shared
  `visible_rows` and drops the same hidden codes as before (existing S7 tests stay green).

## Real-data verification (0915 copy, lane stack)

- **AC-65** On a fresh run from the UI: low stock All row count == plan list Lines count ==
  `export_guard_stats.row_count`; every row with a Last in date has a non-empty Last in qty text naming an SPO; three
  products spot-checked against `/procurement/spo-allocations/last-receipt?product_ids=` agree on
  SPO number, container and SPO quantity.
