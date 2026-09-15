# PLAN - Low stock report: last in from the last SPO line, All sheet matches the list

Status: implemented - awaiting review
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

## Owner rulings, second round (15 Sep, overturning the captain's R1 and R3)

- "for last in, please refer to our MCP service, i think even haven't GR we also show as last
  in" - the line is the NEWEST visible `spo_allocations` line per product, received or not,
  exactly `spo_last_receipt_service.last_receipt_rows(product_ids=..., top_n=1)`'s pick:
  ordered by `coalesce(expected_date, issue_date, created_at::date) DESC, created_at DESC`,
  `visible_line_clauses()`, company scoped. No `quantity_received` filter.
- "for last in quantity, it is SPO - container number - quantity, same like our PO qty" - NO new
  column. The "Last in qty" cell becomes a TEXT cell shaped like the BRW PO qty document line:
  `"<SPO> - <container> - <qty>"`, `"<SPO> - <qty>"` when the line names no container, `""` when
  the product has no visible SPO line. It is one document, so no total line above it (the PO cell
  prints a total only because it sums several documents).

## Captain rulings still standing (flag to the owner; overturn = one-line change)

- **R2 - date = the SPO line's date** (the coalesce key above), the same date the MCP row leads
  with; only 2,043 allocations carry an approved GRN date against 74,300 ESB-stated receipts.
- **R2b - quantity = the SPO line's quantity (`allocated_quantity`)**, the figure the MCP row
  prints as "SPO quantity". `quantity_received` is not used in the cell: the owner's ruling shows
  unreceived lines too, and mixing "received if any else ordered" would hide which one a cell
  states. If the owner wants received-first, swap the column in `last_in_map` and one test.
- **R4 - no backfill.** Frozen rows are the run's evidence; the chat tool always creates a fresh
  run; the buyer re-runs the plan for the on-screen sheet. Migration adds two nullable columns,
  touches no row.
- **R5 - one scope helper.** `export_report`'s hidden-code drop becomes a shared
  `summary_order_service.visible_rows(db, rep) -> list[dict]` that `export_report` and
  `low_stock_report_service._split` both call. `low_stock_guard_stats` is DELETED; the low-stock
  export route reads `export_guard_stats` (already hidden-adjusted). Parent AC-32 superseded.

## Slices (one lane, one branch `fix/low-stock-last-in-list-scope`, one PR)

### S1 - Last in from the newest SPO line, MCP shape (BE)
- `app/services/spo_last_receipt_service.py`: add `last_in_map(db, product_ids) ->
  dict[product_id, {"spo_number", "container_number", "qty", "date"}]` - one windowed query
  (`row_number() over (partition by product_id order by key desc, created_at desc)`), the SAME
  filters as `last_receipt_rows`'s per-product branch (`visible_line_clauses()`, explicit company
  predicate on `SPOAllocation` because `.subquery()` loses the listener), `qty = allocated_quantity`,
  `date = coalesce(expected_date, issue_date, created_at::date)`. Lift `key_expr` to a module-level
  helper both functions share. No receipt filter.
- `summary_order_service._last_receipt_map` body becomes a call to that map (keep the name and the
  `write_rows` call sites; the value contract becomes `{date, qty, spo_number, container}`). Drop
  the picking-lines SQL entirely.
- `write_rows` (~355) also freezes `row.last_receipt_spo_number` and
  `row.last_receipt_container_number`.
- Migration `518_osr_last_receipt_spo` (down_revision `ptag_0009_combos_tags` - re-parented from
  the originally-named `517_chatbot_low_stock_vocab`, which `ptag_0009_combos_tags` had already
  merged on top of by the time this lane branched): two nullable `VARCHAR(100)` columns on
  `scm.order_summary_row`; model `OrderSummaryRow` gains both.
- `report()` row `last_receipt` becomes `{"date", "qty", "spo_number", "container"}` (new keys None
  on a run frozen before 518; readers use `.get`). `app/schemas/scm_order_summary.py`: extend the
  typed shape if one exists (`response_model` drops undeclared fields - a route test asserts it).
- Cell helper `_last_in_text(receipt) -> str` in `summary_order_service`: `"<SPO> - <container> -
  <qty>"`, `"<SPO> - <qty>"` without container, `"<qty>"` when frozen before 518 (no SPO number),
  `""` when no receipt. Used by `_export_rows`, `_export_xlsx_rows` and
  `low_stock_report_service._sheet_row` for the "Last in qty" cell. Column lists, widths and PDF
  index tuples are UNCHANGED (16 columns stay 16); `_PDF_NUM_COLUMNS` drops index 13 (the cell is
  text now) and `_PDF_LIST_COLUMNS` gains it, matching the PO/incoming cells' class.

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
  `crm_procurement_spo_allocations_last_receipt_list` (the sheet now reads the same pick).
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
