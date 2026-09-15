# UAC - Low stock report: last in from the last SPO line, All sheet matches the list

Plan: `PLAN-low-stock-last-in-and-list-scope.md`. Numbering continues the parent
(`low-stock-report-acceptance-criteria.md` ends at AC-47).

## Last in (S1)

- **AC-48** For a product whose newest visible `spo_allocations` line with `quantity_received > 0`
  is SPO `202608-S0084`, container `TLLU8306312`, `quantity_received` 180, `expected_date`
  2026-08-14, the frozen `order_summary_row` carries `last_receipt_qty = 180`,
  `last_receipt_date = 2026-08-14`, `last_receipt_spo_number = '202608-S0084'`,
  `last_receipt_container_number = 'TLLU8306312'`, and `report()` returns
  `last_receipt == {"date": "2026-08-14", "qty": 180, "spo_number": "202608-S0084",
  "container": "TLLU8306312"}`.
- **AC-49** A newer visible line with `quantity_received = 0` (open, expected later) does NOT
  displace the received line: last in still names the received SPO.
- **AC-50** A newer line that is retired and never received (hidden by
  `visible_line_clauses()`) does not answer; a retired line WITH a receipt may.
- **AC-51** A product with no received line at all freezes all four columns NULL and `report()`
  returns `last_receipt = None`; both workbooks print BLANK Last in qty / date / SPO, never 0.
- **AC-52** `picking_lines` / `picking_headers` are no longer read for last in: a product with a
  goods_received picking line and no received SPO line prints blank.
- **AC-53** When two received lines share the same key date, `created_at DESC` breaks the tie.
- **AC-54** Company scope: under a Mocha scope a Sorento-owned line on a Mocha product is not
  picked (explicit predicate on the windowed subquery).
- **AC-55** Both workbooks carry column "Last in SPO" immediately after "Last in date": the order
  sheet export has 17 columns (Remarks in Q), the low stock sheets have 17 with Supplier and 16
  without. Cell text is `"<SPO> - <container>"`, `"<SPO>"` when the line has no container, `""`
  when there is no last-in line. "Last in qty" stays numeric; "Last in date" stays `dd/mm/yyyy`.
- **AC-56** The order sheet PDF renders the new column right of Last in date, Remarks last;
  `_PDF_NUM_COLUMNS` still right-aligns Last in qty and nothing shifts wrongly.
- **AC-57** A run frozen BEFORE migration 518 (NULL in the two new columns) still exports: Last
  in qty and date print as frozen, Last in SPO prints `""`. No migration data backfill.
- **AC-58** Migration `518_osr_last_receipt_spo` upgrades and downgrades cleanly on top of
  `517_chatbot_low_stock_vocab`; `alembic heads` shows one head.
- **AC-59** The response schema for `report()` / order summary routes declares the two new keys
  (a route test asserts `spo_number` and `container` survive `response_model`).

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
  `export_guard_stats.row_count`; every row with a Last in date has Last in qty > 0 and a Last
  in SPO; three products spot-checked against `/procurement/spo-allocations/last-receipt`
  agree on SPO number and quantity (that tool may name a NEWER unreceived line, in which case its
  previous received line is the one the sheet names - record it in the evidence).
