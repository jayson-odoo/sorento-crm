# PLAN - Low stock report: last in from the last SPO line, All sheet matches the list

Status: planned (owner GO 15 Sep 2026)
Domain: scm
Owner ruling source: chat, 15 Sep 2026 (prod run f857ca19-2c11-4a58-a27b-a203cd858b0b, `low-stock-15092026.xlsx`)
UAC: `low-stock-last-in-and-list-scope-acceptance-criteria.md`
Parent: `documentation/plans/scm/PLAN-low-stock-report.md` (PR #909, merged 14 Sep)

## The two defects, measured

1. **Last in qty prints 0 on every row that has a date.** `summary_order_service._last_receipt_map`
   reads `picking_lines.qty_accepted` of `goods_received` pickings. On the 13 Sep prod copy that
   column is NULL on 10,567 of 10,567 GR lines (the figure lives in `quantity_picked`, never
   copied). The date comes from `picking_headers.picking_date`, so the date prints and the qty
   prints `0`. `write_rows` freezes both into `scm.order_summary_row.last_receipt_qty /
   last_receipt_date`, so every run since S14 carries the wrong figure. The existing test
   `tests/scm/test_order_summary_sheet.py::143` seeds `qty_accepted=300` by hand, which is why it
   never caught this.
2. **The All sheet prints 1,266 rows while the plan list shows 833.** `low_stock_report_service._split`
   prints every `order_summary_row` of the run (AC-32 of the parent plan), while the plan list, the
   Decisions tile and the order-sheet export all drop `reorder_recommendation.hidden_by_default`
   rows (`plan_scope.hidden_by_default`: covered + manual level policy + net above level). The
   owner now rules the All sheet must match the list.

## Owner rulings (15 Sep 2026)

- "for last in we should look at last SPO's received quantity, just like how we use MCP tool to
  get last in quantity via spo allocation" - the source is `spo_allocations`, the same module the
  chatbot's last-in tool reads (`app/services/spo_last_receipt_service.py`), not GR picking lines.
- "when there is last in, we need to mention the SPO number and container number also".
- "I prefer All to match the list exported, and we fix the last in quantity and last in date".

## Captain rulings (flagged to the owner in the same message; overturn = one-line change)

- **R1 - received lines only.** The last-in line is the newest VISIBLE `spo_allocations` line per
  product **with `quantity_received > 0`**, ordered by the MCP tool's own key
  `coalesce(expected_date, issue_date, created_at::date) DESC, created_at DESC`, company scoped,
  `spo_supply.visible_line_clauses()` applied. Measured on 0913 for the latest run's 872 products:
  784 have any SPO line, 778 have a received line, and for 125 the newest line overall is an
  UNRECEIVED open line - printing that one would show a date with a blank quantity, which is
  "incoming", not "last in". 746 of the 778 received lines carry a container number.
- **R2 - date = the SPO line's date** (the same coalesce key), because only 2,043 allocations
  carry an approved GRN date while 74,300 carry an ESB-stated `quantity_received` (parent module
  docstring). One rule, one column.
- **R3 - one new column, "Last in SPO"**, immediately after "Last in date", on BOTH workbooks
  (order sheet `_EXPORT_COLUMNS` + PDF, and `LOW_STOCK_COLUMNS`), text `"<SPO> - <container>"` or
  `"<SPO>"` when the line names no container, blank when there is no last-in line. "Last in qty"
  stays a NUMBER (H1 rule, quantities are numbers) rather than becoming a `_docs_text` cell: there
  is exactly one document, so the total-then-lines shape would print the quantity twice.
- **R4 - no backfill.** Frozen rows are the run's own evidence; the chat tool always creates a
  fresh run, and the buyer re-runs the plan for the on-screen sheet. The migration adds the two
  columns nullable and touches no row.
- **R5 - one scope helper.** `export_report`'s hidden-code drop becomes a shared
  `summary_order_service.visible_rows(db, rep) -> list[dict]` that `export_report` and
  `low_stock_report_service._split` both call. `low_stock_guard_stats` is DELETED; the low-stock
  export route reads `export_guard_stats` (already hidden-adjusted). The parent's AC-32 wording
  ("hidden covered rows included") is superseded by this plan.

## Slices (one lane, one branch `fix/low-stock-last-in-list-scope`, one PR)

### S1 - Last in from the last received SPO line (BE)
- `app/services/spo_last_receipt_service.py`: add `last_received_map(db, product_ids) ->
  dict[product_id, {"spo_number", "container_number", "qty", "date"}]` - one windowed query
  (`row_number() over (partition by product_id order by key desc, created_at desc)`), filters
  `quantity_received > 0` + `visible_line_clauses()` + explicit company predicate on
  `SPOAllocation` (the `.subquery()` loses the listener, same as `last_receipt_rows`). Reuse the
  module's `key_expr` (lift it to a module-level helper so both functions share it).
- `summary_order_service._last_receipt_map` body becomes a call to that map (keep the name, the
  callers, and the `{date, qty}` contract, extended with `spo_number`, `container`). Drop the
  picking-lines SQL.
- `write_rows` (line ~355) also freezes `row.last_receipt_spo_number` and
  `row.last_receipt_container_number`.
- Migration `518_osr_last_receipt_spo` (down_revision `517_chatbot_low_stock_vocab`): two nullable
  `VARCHAR(100)` columns on `scm.order_summary_row`. Model `OrderSummaryRow` gains both columns.
- `report()` row `last_receipt` becomes `{"date", "qty", "spo_number", "container"}` (the two new
  keys None on a run frozen before 518 - readers use `.get`).
- `_EXPORT_COLUMNS` + `_XLSX_COLUMN_WIDTHS` + `_PDF_LIST_COLUMNS`/`_PDF_NUM_COLUMNS` indices +
  `_export_rows` / `_export_xlsx_rows`: insert "Last in SPO" after "Last in date" (Remarks shifts
  to Q, width 16). Cell text helper `_last_in_spo_text(receipt) -> str`.
- `low_stock_report_service`: `LOW_STOCK_COLUMNS` + `_LOW_STOCK_WIDTHS` + `_sheet_row` get the same
  column at the same position; `_SUPPLIER_INDEX` unaffected.
- `documentation/reference` / schemas: `app/schemas/scm_order_summary.py` `last_receipt` shape if
  it is typed there (check; `response_model` drops undeclared fields - assert in a test).

### S2 - All sheet matches the list (BE)
- `summary_order_service.visible_rows(db, rep)`: the hidden-code filter lifted out of
  `export_report`; `export_report` calls it.
- `low_stock_report_service._split`: `rows = svc.visible_rows(db, rep)` before sorting; low rows
  stay a subset of All.
- Delete `low_stock_guard_stats`; `app/api/v1/scm/order_summary.py` low-stock export route and
  `app/api/v1/scm/low_stock_report.py` (chat) read `export_guard_stats`. Cap stays
  `MAX_LOW_STOCK_ROWS` on `all_rows` after the filter.
- Parent plan `PLAN-low-stock-report.md` AC-32 note: add one line "superseded by
  PLAN-low-stock-last-in-and-list-scope (15 Sep)". Outline user guide for the low stock report:
  the sentence that says the All sheet includes covered/hidden rows changes to "the same rows the
  plan list shows"; the Last in columns gain the SPO column (guide-writer).

### Not in scope
- Backfilling frozen runs (R4). Per-warehouse last-in. Changing the MCP tool
  `crm_procurement_spo_allocations_last_receipt_list` (it keeps its newest-line-any-status shape).
- FE: no grid renders `last_receipt` today (only `types/summaryOrder.types.ts` names it); add the
  two optional fields to that type and nothing else.

## Tests (tester writes RED first, `tests/scm/`)
See `low-stock-last-in-and-list-scope-test-list.md`.

## Verification
- pytest: `tests/scm/test_low_stock_report.py tests/scm/test_order_summary_sheet.py
  tests/scm/test_order_summary_supply_docs.py tests/scm/test_summary_order_service.py
  tests/test_spo_last_receipt.py` on a PRIVATE DB (never the shared dev copy).
- Real-data check on `sorento_ai_automation_0915` (prod copy of 15 Sep 03:00 MYT): run a plan
  from the UI on lane stack :3085/:8085, export the low stock workbook, assert: All row count ==
  plan list Lines count == `export_guard_stats.row_count`; every row with a Last in date has a
  Last in qty > 0 and a Last in SPO; spot-check three products against
  `GET /api/v1/procurement/spo-allocations/last-receipt?product_ids=...`.
- Browser pass via agent-browser from the sidebar (Reorder planning > plan > Actions > Low stock
  report Excel), evidence under `documentation/plans/scm/evidence/low-stock-last-in/`.

## Lane infra
- Worktrees: coder `fix/low-stock-last-in-list-scope`, tester `test/low-stock-last-in-red`.
- Private test DBs: `sorento_lsli_ci` (coder) and `sorento_lsli_red_ci` (tester), each
  `createdb -O sorento_crm` + the create_all recipe in memory
  `project_private_test_db_from_ci_base_owner_mismatch` (or clone `sorento_ai_automation_tg`).
- Stack slot :3085 / :8085 (free at 15 Sep 10:30 MYT), runtime DB `sorento_ai_automation_0915`
  once the restore finishes, redis db 4.
