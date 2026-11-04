# SO-number inventory: where a sales order is shown, and whether its customer + project are

Lane OI-UX-FILTER-SNAPSHOT, owner 3 Nov 19:35: "show PROJECT and CUSTOMER anywhere a sales order
(or a list of SOs) is shown". Crew answer (a): grids get the SO list's Customer + Project columns
(`scm/sales-orders/components/SalesOrdersGrid.tsx:521-550`); compact places print one line
`CUSTOMER / project` via `components/common/SoCustomerProject.tsx`. Backend helper for payloads
that lack the fields: `app/services/scm/so_party.py` (`so_parties`, `with_party`).

Paths: `FE` = `sorento_crm_frontend/app/(protected)`, `BE` = `sorento_crm_backend/app`.
Status column: `done` = fixed on this lane, `already` = showed both before, `todo` = open.

## A. Already showed both (no change)

| file:line | UI |
|---|---|
| FE/scm/sales-orders/components/SalesOrdersGrid.tsx:480 (+ SalesAgentDetail.tsx:484 tab) | grid (reference) |
| FE/scm/sales-orders/[id]/components/SalesOrderDetail.tsx:1746 | detail header + Order card |
| FE/scm/components/PlanRowDialog.tsx:446 | loading-plan dialog grid |
| FE/scm/reorder/components/PlanRowDialogs.tsx:248, :310 | dialog grids |
| FE/project-sales/fulfilment-planning/components/FulfilmentPlanningClient.tsx:303 | grid |
| FE/project-sales/fulfilment-planning/components/FulfilmentPlanningSheet.tsx:294, :389 | side sheet |
| FE/project-sales/fulfilment-planning/components/BoardCellBreakdownDialog.tsx:560 | dialog grid |
| FE/project-sales/fulfilment-planning/components/CellStockTableGroups.tsx:160 | stock drill row |
| FE/project-sales/order-inquiries/components/OrderInquiryHeadersList.tsx:375 | grid |
| FE/project-sales/order-inquiries/components/orderInquiryWorklistColumns.tsx:1109 | grid |
| FE/project-sales/order-inquiries/[id]/components/OrderInquiryGeneralTab.tsx:56 | detail card |
| FE/scm/purchase-orders/[id]/components/PoLinePlacementsBody.tsx:148 (inquiry rows) | dialog grid (combined label) |

## B. Stock Debt (owner named it first) - done on this lane

| file:line | UI | change |
|---|---|---|
| FE/project-sales/stock-debt/lib/stockDebtDemandColumns.tsx (Sales order col) | live + snapshot drill Demand grid | Customer + Project columns after Sales order |
| FE/project-sales/stock-debt/components/StockDebtCellDialog.tsx (Assigned to) | live drill Supply grid | `AssignedToList`: each SO + `CUSTOMER / project` |
| FE/project-sales/stock-debt/components/SnapshotDrillDialog.tsx (OI group title) | snapshot drill OI groups | `CUSTOMER / project` under the OI number |
| FE/project-sales/_shared/components/RequestReserveDialog.tsx (header) | Request CS to reserve | SO number + `CUSTOMER / project` |
| BE/services/scm/stock_debt_service.py `cell()`; BE/services/scm/stock_debt_snapshot_service.py `lines()` | APIs | `customer_name`, `project_label` on demand lines + `assigned_to` |

The remaining rows (groups C and D below) are tracked in the PR body as they land.
