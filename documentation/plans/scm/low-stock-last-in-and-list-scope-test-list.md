# Test list - low stock last in + list scope (tester writes these RED first)

All pytest, Postgres only (`tests/_pg_fixture.py`), private DB. Seed every chain yourself
(CI DB is empty). Never seed `picking_lines.qty_accepted` as a stand-in for a receipt.

## tests/scm/test_order_summary_sheet.py (edit)
- Replace the picking-line seed behind `row["last_receipt"]["qty"] == 300` (line ~143) with an
  `spo_allocations` line `quantity_received=300, expected_date=today-5`; assert the four keys
  (AC-48). Add a second, newer OPEN line `quantity_received=0`, assert the received one still
  answers (AC-49).
- Column tuples at ~382 / ~419 / ~628 gain "Last in SPO" after "Last in date" (AC-55); the fixture
  dict at ~654 gains `spo_number` / `container`; assert the xlsx cell text
  `"202608-S0084 - TLLU8306312"` and the no-container variant and the blank variant.
- PDF html test: Remarks is the last `<th>`, "Last in SPO" precedes it (AC-56).

## tests/scm/test_summary_order_service.py (add)
- `test_last_receipt_map_ignores_goods_received_pickings` (AC-52).
- `test_last_receipt_map_tiebreak_created_at` (AC-53).
- `test_last_receipt_map_retired_unreceived_line_never_answers` (AC-50).
- `test_last_receipt_map_company_scoped` (AC-54) - mirror `tests/test_spo_last_receipt.py`'s scope test.
- `test_report_last_receipt_none_when_no_received_line` (AC-51).
- `test_report_pre_518_row_prints_blank_spo` (AC-57): insert an `order_summary_row` with the
  two new columns NULL, export, assert `""`.

## tests/test_spo_last_receipt.py (add)
- `test_last_received_map_one_row_per_product_received_only` - the new helper, three products,
  mixed open/received lines.

## tests/scm/test_low_stock_report.py (edit + add)
- INVERT `test_all_sheet_lists_every_planned_product_hidden_included` ->
  `test_all_sheet_matches_the_plan_list_hidden_dropped` (AC-60).
- `test_low_sheet_membership`: a hidden product below its raw level is absent (AC-60).
- `test_workbook_has_two_sheets_in_order_with_17_columns` (rename from 16) (AC-55).
- `test_include_supplier_false_drops_the_supplier_column_on_both_sheets`: 16 columns now (AC-55).
- `test_export_low_stock_counts_are_the_visible_counts` (AC-61).
- `test_low_stock_guard_uses_export_guard_stats` (AC-62): `from app.services.scm.summary_order_service
  import low_stock_guard_stats` raises ImportError; route guard row_count == recommendation_count.
- `test_cap_applies_to_visible_rows` (AC-63) - monkeypatch `MAX_LOW_STOCK_ROWS` small.

## tests/scm/test_order_summary_routes.py (add)
- `test_report_route_carries_last_receipt_spo_and_container` (AC-59).

## Alembic
- `tests/test_alembic_single_head.py` or equivalent already in CI; run `alembic heads` locally (AC-58).
