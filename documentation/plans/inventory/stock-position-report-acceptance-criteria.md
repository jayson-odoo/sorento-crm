# UAC: Stock position report

Plan: `PLAN-stock-position-report-27oct.md`. Q1-Q5 are the owner's answers of 27 Oct ~16:55 (plan, "Decisions"). Test: `sorento_crm_backend/tests/scm/test_stock_position.py` unless named.

| AC | Criterion | Test |
| --- | --- | --- |
| AC-1 | Inventory > Stock position lists every item with something to show (stock, incoming, packing list, outstanding or sales in 12 months), one row per item. An item with nothing is no row. | `test_items_with_nothing_to_show_are_not_rows` |
| AC-2 | One column per ACTIVE SITE-POOL warehouse holding stock, headed by its code alone. Project bins and inactive locations get no column. | `test_columns_are_active_site_pool_warehouses_holding_stock_project_bins_and_inactive_are_not`, vitest `StockPositionGrid.test.tsx` |
| AC-3 | Incoming BRW = open SPO still to come on site-pool warehouses. Incoming (Project) = the same on project locations. Total incoming = the two. | `test_incoming_counts_only_open_spo_still_to_come_split_pool_and_project` |
| AC-4 | Total stock = the warehouse columns + Incoming BRW (sheet: 40 + 244 + 352 = 636). | `test_the_sheet_rows_foot_column_by_column` |
| AC-5 | Packing list, no SPO = quantity still to land minus the open SPO rows on that packing list (the Stock Status panel's rule R3), netted per item and in neither total. | `test_packing_list_open_is_what_no_spo_carries_and_stays_out_of_total_incoming`, `test_packing_list_netting_is_per_item_on_a_shipment_carrying_two` |
| AC-6 | Outstanding dealer = open non-project SO lines still owed (Stock Status's SO rule), printed negative. | `test_outstanding_dealer_is_dealer_so_still_owed_printed_negative` |
| AC-7 | Outstanding PO = open supplier PO quantity not yet transferred to SPO. | `test_outstanding_po_is_ordered_less_transferred_on_open_lines` |
| AC-8 | Monthly sales = mean over the last 12 FULL months (empty months count as 0) of the ONE shared sales quantity (`invoiced_sales.quantity_by_product_month`: IV + CS + DN - CN, by document date, cancelled excluded). Highest / month = the largest of those months. No basis choice. | `test_monthly_sales_is_the_shared_invoiced_quantity_12_full_month_mean_and_peak`, `test_monthly_sales_reads_the_one_shared_sales_function`, `test_sales_basis_is_no_longer_a_choice` |
| AC-9 | Supplier = the last PO's supplier, by the one shared rule (`scm/last_po_supplier.py`, also the low stock report's). No PO = none. Supplier, brand, warehouse and item code/description filters narrow the rows. | `test_supplier_is_the_last_po_supplier_and_filters_on_it`, `test_supplier_reads_the_shared_last_po_rule`, `tests/scm/test_last_po_supplier.py`, `test_brand_item_code_and_warehouse_filters` |
| AC-16 | The user picks which warehouse columns show (Columns chooser), saved per user; the export writes only those; totals are unchanged. | `test_export_writes_only_the_warehouse_columns_the_user_shows_totals_unchanged`, vitest `StockPositionGrid.test.tsx`, `stockPositionService.test.ts` |
| AC-10 | Every column sorts on the server and pages. An unknown sort (including `wh:<unknown>`) is 422. | `test_every_column_sorts_on_the_server_and_pages`, vitest |
| AC-11 | No figure counts another company's warehouse or documents bound to it. | `test_another_companys_warehouse_is_no_column_and_its_stock_no_figure` |
| AC-12 | Readable by the Stock Status permissions only. | `test_read_needs_one_of_the_stock_status_permissions` |
| AC-13 | Export to Excel writes every filtered row, in the screen's order and headers. | `test_export_writes_every_row_with_the_screen_headers`, vitest `stockPositionService.test.ts` |
| AC-14 | A row opens Stock status for its item. The page is usable at 375px and 1280px, with the item code pinned. | vitest, browser pass |
| AC-15 | The Stock Status panel's figures are unchanged by the shared helpers. | `tests/scm/test_stock_status.py` |
