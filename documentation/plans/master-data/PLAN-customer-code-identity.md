# PLAN - customer-code-identity (CUSTOMER-CODE-IDENTITY)

Status: in progress (lane branch `crew/customer-code-identity`, PR #1390); full track (an
additive migration). Re-scoped by the owner on 30 Sep 2026: this PR carries ONLY the
SO-level customer name (section "Scope"). Everything else is parked (section "Parked").
UAC: `customer-code-identity-acceptance-criteria.md`.

## Problem (owner, 30 Sep 2026)

AutoCount identifies a debtor by code, and a user can edit the debtor name on a sales order,
so one debtor code carries several names across documents. The CRM showed the customer
master's name on every SO screen, so the name the order was actually issued under was lost,
and (the parked half) the CRM had also forked duplicate customer rows per name.

Owner rulings, verbatim: "for the SO customer, how about, we have customer name field in SO,
and we take the customer_name in ingestion? we use that as source of truth?" and "so the
customer name supposed to show up in subsequent flow like fulfilment planning, order
inquiries, reorder planning, all SCM related places that uses customer name from SO"; then
"no, don't focus on ingestion of customer, we focus on ingestion of sales order to take
customer name first".

## Scope (this PR)

- **D1 The SO keeps its own name.** New column `sales_orders.debtor_name` (`app/models/order.py`,
  next to `debtor_code`; migration `sdn_0001_so_debtor_name`). `document_ingest_service
  ._header_values` writes it from the payload's `customer_name` on every SO push that sends
  one, exactly as it writes `debtor_code`; a push without one leaves the stored name alone.
  `orders` (delivery orders) already carries `orders.debtor_name`. A document never writes
  `customers.customer_name`.
- **D2 Screens show the order's name, master as fallback.** S1 of the display inventory below:
  `scm/sales_order_service.serialize` (SCM Sales Orders list + detail, and the list search),
  `scm/customer_label.CUSTOMER_LABEL_SQL` (reorder demand popovers, order-qty ledger,
  container requests, trend drill; the trend drill now groups by customer key and prints the
  name on the customer's most recent order rather than one row per spelling), and
  `order_service.so_outstanding_rows` (chatbot / MCP `so_outstanding`).
- **D3 Contract.** No wire change: `customer_name` was already accepted on `sales_orders`;
  what the CRM does with it changed. Documented in the plan only; the contract version stays.
- Migration also re-creates `uq_customers_company_code_name_lower` if missing (same
  definition as 305): a no-op on main, it puts the shared dev DB, where the parked lane's first
  migration attempt had dropped it, back in step with main.

## Display inventory (30 Sep; `BE/` = `sorento_crm_backend/app/`, `FE/` = `sorento_crm_frontend/app/(protected)/`)

- **S1, done here.** `BE/services/scm/customer_label.py:27` `CUSTOMER_LABEL_SQL`, which feeds
  `scm/trajectory_service.py:190` (trend drill), `scm/container_request_service.py:855`
  (container requests) and `scm/demand_breakdown_service.py:470,596,695,865` (reorder demand
  popovers, order-qty ledger) and their FE consumers `FE/scm/reorder/components/PlanTrendPopover.tsx`,
  `PlanDemandPopover.tsx`, `PlanRowDialogs.tsx`, `PlanOrderQtyLedger.tsx`,
  `FE/scm/loading-plan/components/ContainerRequest*.tsx`;
  `BE/services/scm/sales_order_service.py:565` `serialize` (`FE/scm/sales-orders/components/SalesOrdersGrid.tsx:513`,
  `FE/scm/sales-orders/[id]/components/SalesOrderDetail.tsx:1835`) and its search at :1346;
  `BE/services/order_service.py:332` `so_outstanding_rows` (chatbot / MCP `so_outstanding`).
- **S2, follow-up lane.** `BE/services/scm/reorder_run_service.py:3946` (net breakdown,
  `FE/scm/reorder/components/PlanExplainDrills.tsx:149`); `BE/api/v1/scm/reorder_runs.py:640`
  (candidate orders, `RunPlanningModal.tsx:230`); `BE/services/scm/demand.py:1046` (run-scope OI
  rows, order summary export `summary_order_service.py:856`, `tasks/export_tasks.py:788`);
  `BE/services/scm/demand_source_service.py:103` (set-aside project demand);
  `BE/services/scm/summary_order_service.py:1987` (demand drill, `DemandDrillPopover.tsx:195`);
  `BE/services/scm/spo_conversion_service.py:1125,1323,3536` (`PlanRowDialog.tsx:462,1716`,
  `PoPlanCard.tsx:79`, `SpoPlannerTable.tsx:1281`); `BE/services/scm/coverage_service.py:381`;
  `BE/services/outstanding_report_service.py:282,344`; `BE/services/sales_report_service.py:355,462,662`;
  `BE/services/reports/datasets/sales_order_lines.py:98`; `BE/services/stock_transfer_service.py:504`
  (`StockTransfersPanel.tsx:396`, `StockTransferDetail.tsx:203`);
  `BE/services/procurement_service.py:2911` (SPO document lines);
  `BE/services/planning_change_service.py:2381`; `BE/services/project_fulfilment_board_service.py:984,1354,1540,1732`
  (`FulfilmentBoardListView.tsx:505`, `BoardCellBreakdownDialog.tsx:405`, `PileQueueDialog.tsx:115`);
  `BE/services/project_supply_service.py:10543` (`PlansClient.tsx:149`);
  `BE/services/project_so_reconciliation_service.py:1415` (`FulfilmentPlanningClient.tsx:333`,
  `FulfilmentPlanningSheet.tsx:148`); `BE/services/order_inquiry_worklist_service.py:229,1198,2237`,
  `order_inquiry_header_service.py:99,172,264`, `project_order_inquiry_service.py:3454,5465`
  (`orderInquiryWorklistColumns.tsx:1067`, `OrderInquiryHeadersList.tsx:358`,
  `OrderInquiryGeneralTab.tsx:81`); `BE/services/scm/purchase_order_service.py:498`
  (`PoLinePlacementsBody.tsx:155`); `BE/services/sales/opportunity_service.py:607`
  (`SalesOpportunityDetail.tsx:140`); MCP presenters `sorento_crm_mcp/sorento_crm_mcp/presenters.py:441,708,1973,2466,2541,2752`
  render the backend fields above and change with them.
- Checked, no SO customer name: stock debt service and drawer, front planning engine,
  unplanned demand, loading plan service. Excluded: project SO worksheets (party-based) and
  DO-based `orders` joins.

## Parked (follow-up lane; code on branch `crew/customer-code-identity-parked`)

The original task - one CRM customer per debtor code - was built, reviewed and then parked by
the owner ("i won't activate the transfer of customer first"). The parked branch holds, with the
security-review and code-review fixes applied but the suite not fully rerun:

- code-only customer identity through one shared rule (`customer_rules.pick_customer_by_code`)
  for the ESB resolver, back-create, masters-push adoption, order-import upsert, manual create
  and the customer listing import, with the `customer_ambiguous` warning for legacy duplicates;
- `customers.name_aliases` and the "Also known as" header line; master-feed renames keep the
  former name;
- the CUSTOMER-KEY-AUTOKEY (a) fold-in: a code-adopted customer holding a same-source,
  same-integration AutoKey ref updates, keeps its ref, warns `ref_mismatch`;
- migration `cci_0001_customer_code_identity`: merge duplicate-code rows (survivor = ref
  holder, else most orders, else oldest; FKs repointed from `pg_constraint`; loser names as
  aliases) and swap the pair unique index for `(company_id, lower(btrim(customer_code)))`;
- the read-only blast-radius report `scripts/report_customer_code_duplicates.py`;
- contract 2.8 notes.

Trigger to unpark: the owner activates the AutoCount customer master transfer. Open items
recorded by the reviews for that lane: the merge would fold roughly 900 rows (the importer's
own measurement was 2,391 customers over 1,453 codes), so the owner sees the report's totals
first; S2 of the display inventory above rides with it or with its own lane.
