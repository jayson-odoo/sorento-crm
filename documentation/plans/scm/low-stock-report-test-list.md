# Captain's test list - low stock report (Phase 2, tester writes these RED before the coder)

One line per UAC id: test file :: test name - the assertion in words. Postgres only
(`tests/_pg_fixture.py`); seed your own chain, never `LIMIT 1` off existing rows. Fixtures to
reuse: `tests/scm/test_reorder_committed_universe.py` (`_mk_warehouse`, `_mk_product`,
`_mk_stock`, `_mk_demand`, `_mk_movement`, `_recs`), `tests/scm/test_order_summary_sheet.py`
(`_FULL_ROW` at :633), `tests/scm/test_order_summary_supply_docs.py`,
`tests/scm/test_order_sheet_export_downloads.py`, `tests/chatbot/test_outstanding_lane.py`
(`TestFieldRevealGateBeforeFetch`, `TestDateParams`, `TestToolPick`).

## S2 - container in the incoming cell (tests/scm/test_order_summary_supply_docs.py, extend)

- AC-20 :: test_open_spo_by_product_groups_by_spo_and_container - two allocations on SPO-A, one linked to an inbound shipment with container TLLU8306312 and one unlinked, yield two docs entries: {number SPO-A, container TLLU8306312, qty} and {number SPO-A, qty} with no container key; qty total equals both remainders summed.
- AC-20 :: test_spo_allocation_container_number_wins_over_shipment_container - allocation.container_number 'CMAU4318062' with a shipment whose shipping_container_number is 'OTHER' groups under CMAU4318062.
- AC-20 :: test_open_po_by_product_docs_carry_no_container_key - a PO doc entry has keys number and qty only.
- AC-21 :: test_docs_text_prints_spo_container_qty_when_container_known - _docs_text(380, [{SPO-A, TLLU8306312, 180}, {SPO-B, 200}]) == "380\nSPO-A - TLLU8306312 - 180\nSPO-B - 200".
- AC-22 :: test_export_rows_and_xlsx_rows_render_container_lines - both row builders put the three-part line in index 12 and every other cell of _FULL_ROW is unchanged against the existing golden tuple.
- AC-23 :: test_frozen_docs_without_container_key_still_print - a row whose incoming_spo_docs is [{number, qty}] (pre-slice shape) prints "SPO-A - 200".

## S1 - admission second leg (tests/scm/test_reorder_committed_universe.py, extend; new class TestDeadGuardAdmission)

Seed per test: one site-pool warehouse (segment dealer, counts_as_available true), product with stock, `products.reorder_level`, a scm.consumption_v-visible movement (use `_mk_movement`), global reorder_policy row with dead_stock_days=180, run `svc.create_run(db, [code], enqueue=False)` then `svc.run_reorder(run_id, db=db)`.

- AC-10 :: test_below_level_live_product_with_no_committed_demand_enters_as_a_level_buy - stock 40, master level 100, movement 5 days ago, no demand -> exactly one rec, rec_type buy, inputs.policy_type reorder_level, rounded_qty >= 60.
- AC-10 :: test_buyer_level_outranks_master_level_in_admission - master level 10 (not breached) but scm.reorder_level product-wide manual level 100 -> admitted; and the reverse (manual 10, master 100) -> not admitted.
- AC-11 :: test_below_level_dead_product_stays_out - same as AC-10 but movement 200 days ago -> no rec.
- AC-11 :: test_below_level_product_that_never_moved_stays_out - no movement row at all -> no rec.
- AC-12 :: test_above_level_product_with_no_committed_demand_stays_out - stock 500, level 100, moved yesterday -> no rec (the existing test at :60 already covers this; keep it, add nothing that contradicts it).
- AC-13 :: test_no_level_no_demand_stays_out - stock 0, no level anywhere, moved yesterday -> no rec.
- AC-14 :: test_named_dead_product_still_enters - product_codes=[code], movement 400 days ago, no demand -> a rec exists (G10).
- AC-15 :: test_admission_dead_days_follow_the_global_policy - dead_stock_days=30 and movement 45 days ago -> out; dead_stock_days=60 -> in.
- AC-15 :: test_admission_dead_days_default_180_without_a_global_row - no policy row, movement 170 days ago -> in; 190 -> out.

## S3 - the workbook (tests/scm/test_low_stock_report.py, new)

Seed: a completed run with order_summary_row rows via `summary_order_service.write_rows` on seeded recs, OR insert OrderSummaryRow rows directly with pool_on_hand / reorder_level / product joins; products with description, category, reorder_quantity set and unset.

- AC-30 :: test_export_route_accepts_low_stock_xlsx_and_enqueues - POST /api/v1/scm/order-summary/export {run_id, format: low_stock_xlsx} as a signed-in user -> 200, user_downloads row kind low_stock_xlsx, filename low-stock-<ddmmyyyy>.xlsx, source_entity_type reorder_run, enqueue_job called with generate_low_stock_report on queue imports job_timeout 600.
- AC-30 :: test_export_route_409_while_low_stock_in_flight - second POST while pending -> 409; an in-flight order_sheet_xlsx does NOT block low_stock_xlsx.
- AC-31 :: test_workbook_has_two_sheets_in_order_with_16_columns - sheetnames == ["Low stock", "All"]; header row of each == LOW_STOCK_COLUMNS tuple (spell it out in the assert); A2 frozen; header fill FF404040.
- AC-32 :: test_low_sheet_membership - four products: 40/100 (in), 100/100 (out), 150/100 (out), 40/NULL level (out), NULL pool_on_hand/100 (out); a hidden-by-default covered row at 40/100 IS in.
- AC-33 :: test_all_sheet_lists_every_planned_product_hidden_included - All row count == report() row count with hidden rows present; the order sheet export of the same run still drops them.
- AC-34 :: test_description_category_reorder_qty_come_from_master_data - Description == products.description (not product_name), Category == category_code, Reorder qty == products.reorder_quantity as a number, blank when NULL and blank when 0.
- AC-32 :: test_sheets_sorted_by_category_then_item_code.
- AC-35 :: test_all_sheet_over_5000_rows_refuses_422 - monkeypatch MAX_LOW_STOCK_ROWS to 2 with 3 rows -> AppException 422 "Narrow the plan first"; the order sheet's MAX_EXPORT_ROWS untouched (assert == 2000).
- AC-36 :: test_generate_low_stock_report_marks_ready_with_row_counts - task uploads to exports/low-stock/{download_id}/{filename}, mark_ready, row_count_low and row_count_all written; render raising -> status failed with error text, no exception out of the task.
- AC-37 :: test_include_supplier_false_drops_the_supplier_column_on_both_sheets.

## S5 - chat route (tests/scm/test_low_stock_report_chat.py, new)

TestClient with X-API-Key; act-as user holds scm.reorder.run; contact seeded in respond_contacts with a workspace; grants via contact_field_reveal_service.set_granted_keys.

- AC-40 :: test_422_without_contact_or_space - missing either -> 422; no run, no download row.
- AC-41 :: test_403_without_the_key_writes_nothing - code low_stock_report_not_enabled; reorder_run and user_downloads counts unchanged.
- AC-42 :: test_creates_run_marked_chat_and_download_row_then_enqueues_run_then_export - requested_via == "chat"; download kind low_stock_xlsx; enqueue_job called twice, second with depends_on the first job.
- AC-42 :: test_owner_is_the_user_linked_to_the_contact - users.respond_contact_id == contact -> run.created_by and download.user_id are that user; unlinked contact -> act-as user.
- AC-43 :: test_ready_within_budget_returns_attachments - monkeypatch the poll to see status ready with row counts -> {status ready, run_id, as_of, low_count, all_count, attachments[0].filename == storage key's last segment, mimeType xlsx, attachmentType file}.
- AC-43 :: test_wait_reads_system_settings_low_stock_sync_wait_seconds - settings row 7 -> wait_for called with 7; PUT settings with 4 -> 422, 91 -> 422, 60 -> 200 and GET echoes 60.
- AC-44 :: test_timeout_claims_delivery_and_returns_pending - poll times out -> deliver_to_contact_id set, {status pending, run_id, download_id}.
- AC-44 :: test_timeout_but_row_already_ready_returns_ready - the claim UPDATE touches 0 rows -> ready shape, deliver_to_contact_id stays NULL.
- AC-45 :: test_task_pushes_only_when_claimed - claimed row -> send_chat_attachment_for called once with identifier == contact.respond_io_id, attachment_type file, the CDN url; unclaimed row -> never called; delivered_at set exactly once.
- AC-45 :: test_push_window_closed_is_logged_not_raised - send raises AppException(422, attachment_window_closed) -> task returns ready, no exception.
- AC-46 :: test_interleaving_worker_ready_before_claim_and_claim_before_ready - drive both orders explicitly; assert exactly one delivery path fires in each.
- AC-47 :: test_supplier_column_omitted_without_purchase_orders_supplier_key.
- AC-48 :: test_requested_via_reaches_run_list_and_detail - GET /reorder-runs list item and /reorder-runs/{id} both carry requested_via "chat"; a manual run carries null.
- AC-49 :: test_busy_maps_the_in_flight_run_409_to_status_busy.

## S6 - MCP + lane gate

sorento_crm_mcp/tests/test_catalog_low_stock.py:
- AC-60 :: test_catalog_lists_low_stock_report_tool - name, GET, path, the six query params, domain inventory, restricted_fields (("scm.low_stock_report", "Low stock report over chat"),).
- AC-62 :: test_low_stock_tool_compiles_with_view_param - compiled signature has view (query-param tool).
sorento_crm_mcp/tests/test_presenters_low_stock.py:
- AC-61 :: test_ready_envelope_two_lines_and_attachments_passthrough; test_pending_envelope_one_line; test_busy_envelope_one_line; test_no_uuid_in_any_line; has_result True on all three.
tests/chatbot/test_low_stock_lane.py:
- AC-63 :: test_key_listed_in_field_reveal_keys_and_catalog (mirror TestSoKeyListedInFieldRevealKeysAndCatalog).
- AC-64 :: test_gate_refuses_before_fetch_without_key - intent low_stock_report, no grant -> reply starts with "Low stock report is not enabled for your account.", fetch not called, picker offered.
- AC-64 :: test_gate_passes_with_key_and_picks_the_tool - tool == crm_low_stock_report (not tools[0] of inventory).
- AC-66 :: test_transformer_fills_warehouse_codes_product_codes_and_dates - warehouse entity BRW -> warehouse_codes ["BRW"]; product entity -> product_codes; date_filter_start/end -> date_from/date_to; contact_id + space_id present; view render.
- AC-66 :: test_output_structurer_populates_attachments_from_envelope - attachments list non-empty so engine emits send_attachments.
- AC-62 :: existing pins stay green: test_tool_pool_is_read_only, test_domain_spec, test_tool_pick_from_domain_spec, test_field_reveal_keys_pinned_to_catalog.

## S7 - parser

- AC-70 :: tests/chatbot/test_parser_low_stock_words.py - four golden phrasings parse to intent low_stock_report with the expected warehouse / product / date fields (fixture-driven like the growth-r1 goldens); prompt-is-live and user-block parity tests stay green.
- AC-71 :: covered by S6 transformer test (DATE_PARAMS entry asserted explicitly).
- AC-73 :: console case YAML exists at tests/chatbot/console_cases/2026-09-1x-low-stock-report.yaml (not collected by pytest).
