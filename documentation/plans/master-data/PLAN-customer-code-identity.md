# PLAN - customer-code-identity (CUSTOMER-CODE-IDENTITY)

Status: in progress (lane branch `crew/customer-code-identity`); full track (migration,
external ingest surface). UAC: `customer-code-identity-acceptance-criteria.md`.

## Problem (owner, 30 Sep 2026)

AutoCount identifies a debtor by code. The CRM back-creates a customer when the (code, name)
pair is not found, and a user can edit the debtor name on a sales order or DO, so one debtor
code now exists several times in `customers` (300-1001 three times, 300-4002 and 300-H030
twice). The ingest resolver picks one of them arbitrarily (`ORDER BY id DESC ... first()`),
so orders for the same debtor scatter across rows and the integration cannot be trusted.

Evidence (origin/main 950785de2, `sorento_crm_backend/`):

- `customers` uniqueness is (company, lower/trim code, lower/trim name):
  `app/models/order.py:199-205`, `alembic/versions/305_company_composite_unique.py:82`.
- Resolver: ref first, else code match ordered by id desc, else create by code and name:
  `app/services/master_ref_resolver.py:315-333, 359-367`; `app/services/scm/customer_back_create.py:52-58`.
- Masters push adopts by code AND name: `app/services/master_ingest_service.py:640-653`.
- Order import debtor upsert (pair match): `app/services/order_service.py:2203-2248`.
- Manual create (pair conflict check): `app/services/order_service.py:3647-3662`.
- Customer master import keys on the pair: `app/services/customer_import_service.py:277-316`.
- Migration 220 already merged duplicate pairs once, repointing FKs discovered from
  `pg_constraint` - the pattern this plan reuses.

## Decisions

- **D1 Code is identity.** Within a company, `lower(btrim(customer_code))` identifies the
  customer. Every matcher (resolver, back-create, masters adoption, order import upsert, manual
  create conflict, customer import) matches by code alone. Names are labels.
- **D2 Names are kept, never used to fork.** A document naming an existing code with a
  different name links to the existing row and keeps that name on itself (D7). The master name
  is never written by a document. The master feeds (ESB masters push, customer listing import)
  do own the name: they rename, and the name they replace is kept in the customer's
  `name_aliases` (new JSONB list column, case-insensitive dedupe), as are the names of the rows
  the merge folds away. One column, not an alias table: one list per customer, read in one
  place (the detail header).
- **D2b CUSTOMER-KEY-AUTOKEY (a), folded in.** The wrapper's `/debtorbypage` exposes no AutoKey,
  so the Customer entity keys on AccNo (`AED_SORENTO:300-1003`) while the SO/PO feeds link the
  row under its AutoKey (`AED_SORENTO:2613`). The masters-push adopt branch treats customers
  like products: a code-adopted row already holding a same-source ref is updated, keeps its
  stored ref, warns `ref_mismatch`, never links the AccNo ref and never raises
  `ReferenceConflict` (`master_ingest_service._apply_scoped`).
- **D3 Ambiguity is refused, not guessed.** While legacy duplicates exist (the merge is a held,
  owner-approved migration), a code matching more than one row resolves to the row holding the
  integration reference, else the row with the most orders (`orders` + `sales_orders`), else the
  oldest, and the verdict carries the new warning `customer_ambiguous` (added to the contract
  vocabulary). After the merge and the unique index this branch is unreachable.
- **D4 Unique index replaces the pair index.** `uq_customers_company_code_lower` on
  `(company_id, lower(btrim(customer_code)))` replaces `uq_customers_company_code_name_lower`.
  Two indexes carrying two identity rules would drift; the pair index is implied by the new one.
- **D5 Merge migration.** One alembic revision: (1) add `name_aliases`; (2) merge duplicate-code
  groups per company, survivor per D3, repointing every FK discovered from `pg_constraint`
  (migration 220's mechanism), with unique-collision handling (a child row that would collide
  with one the survivor already has is deleted; a loser's `main` contact is demoted to
  `stakeholder` when the survivor has a `main`); survivor fill-only on empty contact and
  classification columns; losers' names into `name_aliases`; delete losers; (3) swap the
  unique indexes. Destructive: held by crew for the owner. A read-only report script shows the
  blast radius first (`scripts/report_customer_code_duplicates.py`).
- **D6 Odd names merge too.** 300-1001 "MODERNMED SDN BHD" next to "1 LIVING DEPOT" is still the
  same debtor code, and AutoCount is the truth for debtors. Recommended to the owner via
  `crew-ask`; the report flags names that share no word with the survivor's.
- **D7 The SO keeps its own name (owner, 30 Sep).** "We have customer name field in SO, and we
  take the customer_name in ingestion, we use that as source of truth." The ingested
  `customer_name` is stored on the order itself: new column `sales_orders.debtor_name`
  (`app/models/order.py`, next to `debtor_code`), written by
  `document_ingest_service._header_values` whenever the payload sends one, exactly as
  `debtor_code` is. Delivery orders already carry `orders.debtor_name` (`app/models/order.py`,
  written by the AutoCount DO ingest `autocount_doc_ingest_service.py:328`). A document never
  writes `customers.customer_name`; only the master feeds (ESB masters push, customer listing
  import) rename, and D2's alias rule applies to those renames only. The back-create still
  uses the document's name for a brand-new row, since there is no other name to give it.
- **D8 Every SO-facing screen shows the SO-level name, master as fallback (owner, 30 Sep).**
  Sliced (crew-ask, recommendation (a)): S1 = this PR; S2 = a follow-up lane for the rest.
  Inventory (working tree, 30 Sep; `BE/` = `sorento_crm_backend/app/`, `FE/` =
  `sorento_crm_frontend/app/(protected)/`):
  - **S1, done here.** `BE/services/scm/customer_label.py:27` `CUSTOMER_LABEL_SQL` (now
    `COALESCE(so.debtor_name, c.customer_name, ...)`), which feeds
    `scm/trajectory_service.py:190` (trend drill), `scm/container_request_service.py:855`
    (container requests) and `scm/demand_breakdown_service.py:470,596,695,865` (reorder demand
    popovers, order-qty ledger) and their FE consumers `FE/scm/reorder/components/PlanTrendPopover.tsx`,
    `PlanDemandPopover.tsx`, `PlanRowDialogs.tsx`, `PlanOrderQtyLedger.tsx`,
    `FE/scm/loading-plan/components/ContainerRequest*.tsx`;
    `BE/services/scm/sales_order_service.py:565` `serialize` (SCM Sales Orders list + detail,
    `FE/scm/sales-orders/components/SalesOrdersGrid.tsx:513`,
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

## Slices

1. Tests red: resolver, back-create, masters adoption, order import upsert, manual create,
   contract vocabulary, migration merge (scratch schema).
2. Backend: `customer_rules.customer_code_key`, resolver code-only match with D3 ambiguity and
   alias recording, back-create by code, masters adoption by code, order import upsert, manual
   create conflict, customer import keyed by code, model + schema + migration, report script.
3. Frontend: `name_aliases` on the customer type and "Also known as" under the detail header.
4. Hand-test script `laneboard/scripts/<PR>.md`, `crew-migration` SQL for the test copy.

## Out of scope

- Merging customers across companies (never: the code is per company, D1).
- Renaming a customer from a document push (the master name stays; D2).
- Deduplicating `orders.debtor_name` text: it stays as the document printed it.
