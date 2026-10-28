# PLAN: Stock position report (all suppliers)

Status: Review (28 Oct): Q1-Q5 built on the owner's answers. Q3 is on SALES-UNIFIED's shared function (#1916,
merged), and Stock Debt is on the shared last-PO helper (#1901, merged). Track: standard (no migration, no
RBAC change).

Lane: STOCK-POSITION-REPORT. Owner request 27 Oct 2026: reproduce the supplier stock sheet ("<SUPPLIER> STOCK AS AT
<date>") inside the CRM for ALL suppliers in one report, one row per item code, with a Supplier column.

Mock: `documentation/plans/inventory/mockups/stock-position-report.html` (static, for review).
UAC: `documentation/plans/inventory/stock-position-report-acceptance-criteria.md`.

## Column map (each column -> the code that already computes it)

| Column | Source today | New? |
| --- | --- | --- |
| Supplier | the last PO's supplier, `scm/last_po_supplier.py` (shared with the low stock report; Q4) | shared helper extracted |
| Brand | `products.brand_id` (`app/models/product.py:252`) | no |
| One column per warehouse | on hand per warehouse, `stock_status_service.stock_status` (`app/services/stock_status_service.py:115-120`, reads `Stock.quantity_on_hand`); pool vs project by `pool_predicate.is_site_pool` (`app/services/scm/pool_predicate.py:75`) | dynamic column set only |
| Incoming BRW (open SPO to the pool) | `stock_status_service._spo_rows` (`:299`), allocated less received over `spo_supply.open_incoming_clauses()` (`app/services/scm/spo_supply.py:58`), split where the SPO row's warehouse `is_site_pool` | split only |
| Total stock | warehouses + Incoming BRW (sheet: 40 + 244 + 352 = 636) | arithmetic |
| Incoming (Project) | same `_spo_rows`, SPO rows whose warehouse is `segment = project` | split only |
| Total incoming | Incoming BRW + Incoming (Project) (sheet: 352 + 880 = 1232) | arithmetic |
| Open packing list not on an SPO (NEW) | `stock_status_service._incoming_pl` (`:363`), the `counted` figure: still to land, net of the open SPO rows on that packing list (rule R3) | no |
| Outstanding dealer | `stock_status_service.so_outstanding_clauses()` (`:195`) restricted to `sales_orders.demand_class <> 'project'` (`app/models/order.py:668`) | sign / meaning (Q2) |
| Outstanding PO | `stock_status_service._purchase_order_rows` (`:258`) = `scm.po_ordered_v` (`alembic/versions/337_scm_on_order_from_spo.py:82`): supplier PO ordered less transferred to SPO (`qty_received` is AutoCount's TransferedQty, `app/models/procurement.py:928-930`) | no |
| Monthly sales (12-month average) | `container_request_service.history` + `_series` (`app/services/scm/container_request_service.py:1740,1761`): 12 FULL months, zero-filled, mean over all 12, SO ordered qty by order date | basis (Q3) |
| Highest / month | same `_series`, `peak_qty` | no |

Every quantity is already computed for ONE item by the Stock Status panel; the report batches those same
helpers over a list of product ids (one refactor: `product_id` -> `product_ids`, the panel calls it with one id),
so the panel and the report cannot disagree.

## Where it lives

The reporting engine (`app/services/reports/registry.py`, `engine.py`, screen `components/reports/ReportPage.tsx`)
is built for transactional row sets over a period: a detail table of fixed catalog columns, sorted by the
definition's fixed `order_by` (`engine.py:509`) and then client-side (`ReportPage.tsx:213`), capped at 5,000 rows
(`engine.py:52`). Fitting this report would need two engine extensions (a dynamic per-warehouse MEASURE column
group; `TickGroup` only renders booleans, `registry.py:275`) and the packing-list netting (container-number
matching in Python, `stock_status_service.py:363`) rewritten as SQL, a second copy of rule R3.

Recommendation: a dedicated read endpoint `GET /api/v1/inventory/stock-position` (DataGrid contract: page,
limit, sort, dir, query + supplier / brand / warehouse filters, every column sortable server-side) and an
Excel export, rendered on Inventory > Stock position as a DataGrid next to Stock status. Item code links to
Stock status for that item.

## Example rows (seeded data shaped like the sheet rows)

Seeds: warehouses BRW, MWH, WH3, DC1, RSW (pool) + one project bin; item A (CWCX605-RL shape), item B
(SRTWC286-SH-NEW shape), item C (CWC7606-SH shape).

| Item | BRW | MWH | WH3 | DC1 | RSW | Inc BRW | Total stock | Inc Project | Total inc | PL not on SPO | Out dealer | Out PO | Monthly | Highest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 40 | 0 | 0 | 244 | 0 | 352 | 636 | 880 | 1232 | 40 | -70 | 1820 | 284 | 850 |
| B | 42 | 846 | 81 | 0 | 0 | 84 | 1053 | 51 | 135 | 0 | -59 | 75 | 181 | 864 |
| C | 98 | 85 | 0 | 594 | 0 | 0 | 777 | 0 | 0 | 0 | 0 | 0 | 93 | 216 |

Seeded so: A has an open SPO 352 to BRW, an open SPO 880 to the project bin, a packing list of 100 still to
land with 60 of it on an SPO (counts 40), dealer SO lines owing 70, a supplier PO line ordered 2,000 with 180
transferred to SPO, and 12 months of SO lines summing 3,408 (avg 284) with an 850 month. B and C likewise
(B: 12-month sum 2,172; C: 1,116).

## Decisions (Q1-Q5): owner answers, 27 Oct ~16:55

- **Q1 (a):** its own page, Inventory > Stock position.
- **Q2 (a):** Outstanding dealer = dealer SO still owed (`so_outstanding_clauses`, demand class not
  `project`, NULL counted as dealer), printed negative as the sheet prints it.
- **Q3:** "our sales calculation should be the same across all, using a shared function". Monthly sales and
  Highest / month come from SALES-UNIFIED's ONE function, `invoiced_sales.quantity_by_product_month`
  (#1916: IV + CS + DN - CN line quantity, by document date, cancelled excluded, every sales type). This
  report adds only the window (12 full months before this one, `container_request_service.history_window`),
  the mean over all 12 (an empty month is 0) and the peak (`_series`). The SO-ordered basis and the page's
  basis switch are removed: no second calculation. Built after #1916 merged (decided: wait, not stack).
  Companies: a session's scope is the shared function's default; an unrestricted caller (an integration
  key with no contact, scope None) passes `company_ids` = every company, the same set every other column
  of this report reads for it, since the shared function refuses an unrestricted scope (#1916 security
  review L6); an unresolved scope reads nothing.
- **Q4:** supplier = the LAST PO's supplier, ONE shared rule: `app/services/scm/last_po_supplier.py`.
  Measured: Stock Debt (`stock_debt_service._last_supplier_map`) and the low stock report
  (`summary_order_service._last_po_supplier_map`) were two functions with different tiebreaks (line
  `created_at` vs PO `created_at` + `supplier_id`), and Stock Debt also falls back to the primary product
  supplier. The helper takes STOCKDEBT-PERF's ordering (#1901): `issue_date` desc NULLS last, line
  `created_at`, `po_number`, line id. The low stock report, this report and (since #1901 merged,
  28 Oct) Stock Debt's `_last_supplier_map` read it. No PO =
  no supplier (no link fallback: the live links nearly all name DEFAULT). Not moved in this lane, named
  as follow-ups: `supply_origin` and `scripts/backfill_product_supplier_from_last_po.py` still spell the
  older tiebreak in their own SQL. A PO with no supplier is skipped (the next-newest PO names it), the
  low stock report's old behaviour. Stock Debt keeps its primary-supplier fallback on top; its one
  behaviour change is that a product whose newest PO names no supplier now shows the next-newest PO's
  supplier (or, with no supplier-named PO at all, the primary flag) instead of none.
- **Q5:** the user picks which warehouse columns show, with the DataGrid's own Columns chooser and the saved
  per-user column preferences (listing key = the page path). The grid mounts once the warehouse columns are
  known, so a saved choice applies to them. Export to Excel writes only the shown warehouse columns (`wh`).
  Hiding a column does not take that warehouse out of Total stock (a display choice, not a filter).
  Known limit (review round 2, S2): the shared column-preferences hook saves visibility for the columns
  present at save time, so a hidden warehouse that holds no stock on the day of a later column change loses
  its "hidden" entry and comes back visible when it holds stock again. Rare (a warehouse column only leaves
  when that warehouse is empty everywhere); fixing it is a change to the shared hook
  (`lib/listing-column-preferences/useListingColumnPreferences.ts`: carry saved entries for absent ids),
  left for a follow-up rather than widened into this lane.
- Side effect kept from round 1: an open SPO to an INACTIVE site-pool warehouse still counts in Incoming BRW
  (an SPO is supply until the book closes it, `spo_supply`), while that warehouse's on-hand is no column.

## Performance

Every request computes every item, then filters, sorts and pages in Python. On-hand, dealer SO and PO are
summed in SQL per (product, warehouse) with ids as text (28 Oct: fetching one row per line was ~80% of the
time). Sandbox, synthetic supplier of 3,000 items + 36,000 SO lines, head after that change: build_rows
0.4 to 1.7 s. No prod-copy measurement yet. Trigger for moving the rest into SQL: a page load over ~2 s
on the live item count, which the hand test shows.

## Built (27 Oct)

- `GET /api/v1/inventory/stock-position` and `/export` (`app/api/v1/inventory/stock_position.py`), service
  `app/services/stock_position_service.py`. Sorting, filtering and paging all happen on the server, over rows
  that are fully computed. Sort keys: `item_code`, `description`, `supplier_name`, `brand_name`,
  `wh:<code>`, and each figure key. Round 1 had a `sales_basis` switch; Q3 (owner, 27 Oct) removes it: one
  shared sales calculation, `invoiced_sales.quantity_by_product_month` (#1916).
- Shared helpers: `stock_status_service._spo_rows` / `incoming_pl_by_product` take a product-id list (None =
  every product) and `po_outstanding_clauses` was extracted, so the single-item panel calls the same code
  with one id. `container_request_service.history_window` / `ordered_qty_by_month` were pulled out of the
  loading plan's `history`.
- FE: Inventory > Stock position (`app/(protected)/inventory-management/stock-position/`), a DataGrid with
  the item code pinned and a row link to Stock status. Filters: supplier, brand, warehouse, sales basis.
  Export to Excel comes from the server workbook.
- Warehouse filter: offers the report's own warehouse columns; keeps the items holding stock there; the
  columns stay whole. A value that is not an id matches nothing. An unknown `wh:<code>` sort is 422.
- Tests: `tests/scm/test_stock_position.py` (16, seeded per column), vitest `StockPositionGrid.test.tsx`,
  `stockPositionService.test.ts`.
