# PLAN: Stock position report (all suppliers)

Status: Plan, behaviour card posted, waiting on owner answers (Q1-Q5). Track: standard (new endpoint +
page, no migration expected); confirmed once Q1 is answered.

Lane: STOCK-POSITION-REPORT. Owner request 27 Oct 2026: reproduce the supplier stock sheet ("<SUPPLIER> STOCK AS AT
<date>") inside the CRM for ALL suppliers in one report, one row per item code, with a Supplier column.

Mock: `documentation/plans/inventory/mockups/stock-position-report.html` (static, for review).

## Column map (each column -> the code that already computes it)

| Column | Source today | New? |
| --- | --- | --- |
| Supplier | `product_suppliers.is_primary_supplier` (`app/models/procurement.py:114`) | rule only (Q4) |
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

## Open questions (posted as crew-ask)

Q1 where, Q2 outstanding dealer, Q3 sales basis, Q4 supplier rule, Q5 warehouse columns + PL in totals.
