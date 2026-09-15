# Test list - low stock last in + list scope (tester writes these RED first)

All pytest, Postgres only (`tests/_pg_fixture.py`), private DB. Seed every chain yourself
(CI DB is empty). Never seed `picking_lines.qty_accepted` as a stand-in for a receipt.

## tests/scm/test_order_summary_sheet.py (edit)
- Replace the picking-line seed behind `row["last_receipt"]["qty"] == 300` (line ~143) with an
  `spo_allocations` line `allocated_quantity=300, expected_date=today-5, spo_number, container_number`;
  assert the four keys (AC-48). Add a NEWER open line (`quantity_received=0`) and assert it wins
  and equals `last_receipt_rows(product_ids=[pid], top_n=1)[0]["spo_number"]` (AC-49).
- Column tuples at ~382 / ~419 / ~628 UNCHANGED (16). Fixture dict at ~654 gains `spo_number` /
  `container`; assert the xlsx "Last in qty" cell text `"202608-S0084 - TLLU8306312 - 300"`, the
  no-container variant `"202608-S0084 - 300"`, the pre-518 variant `"300"`, and `""` (AC-55, AC-57).
- PDF html test: the Last in qty cell carries the list class, not num (AC-56).

## tests/scm/test_summary_order_service.py (add)
- `test_last_receipt_map_ignores_goods_received_pickings` (AC-52).
- `test_last_receipt_map_tiebreak_created_at` (AC-53).
- `test_last_receipt_map_retired_unreceived_line_never_answers` (AC-50).
- `test_last_receipt_map_company_scoped` (AC-54) - mirror `tests/test_spo_last_receipt.py`'s scope test.
- `test_report_last_receipt_none_when_no_spo_line` (AC-51).

## tests/test_spo_last_receipt.py (add)
- `test_last_in_map_one_row_per_product_newest_any_status` - the new helper, three products,
  mixed open/received lines, qty = allocated_quantity, same pick as `last_receipt_rows`.

## tests/scm/test_low_stock_report.py (edit + add)
- INVERT `test_all_sheet_lists_every_planned_product_hidden_included` ->
  `test_all_sheet_matches_the_plan_list_hidden_dropped` (AC-60).
- `test_low_sheet_membership`: a hidden product below its raw level is absent (AC-60).
- `test_workbook_has_two_sheets_in_order_with_16_columns` stays; add an assertion on the Last in qty cell text (AC-55).
- `test_include_supplier_false_drops_the_supplier_column_on_both_sheets`: unchanged (15 columns).
- `test_export_low_stock_counts_are_the_visible_counts` (AC-61).
- `test_low_stock_guard_uses_export_guard_stats` (AC-62): `from app.services.scm.summary_order_service
  import low_stock_guard_stats` raises ImportError; route guard row_count == recommendation_count.
- `test_cap_applies_to_visible_rows` (AC-63) - monkeypatch `MAX_LOW_STOCK_ROWS` small.

## tests/scm/test_order_summary_routes.py (add)
- `test_report_route_carries_last_receipt_spo_and_container` (AC-59).

## Alembic
- `tests/test_alembic_single_head.py` or equivalent already in CI; run `alembic heads` locally (AC-58).
