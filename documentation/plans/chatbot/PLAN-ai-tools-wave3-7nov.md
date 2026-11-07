# PLAN: AI-TOOLS-WAVE3 (stock, amounts owed, opportunities, projects in the assistant registry)

Status: Build. Track: small fix track by shape (registry entries + one core flag, no migration, no new slug), but
it touches RBAC reads, so the security reviewer runs.
Lane AI-TOOLS-WAVE2 (wave 3), stacked on wave 2 (#2210, head 3d45ab16); its PR targets the wave 2 branch until
#2210 merges.

Parent: `PLAN-ai-tools-wave2-sales-5nov.md`. Same rules: one `crm_query`, each entity under its screen's slug and
own rule, exclusions stated, dd/mm/yyyy, code-rendered tables, no per-screen tool.

## Measured facts (base 3d45ab16)

- Stock: `Stock` (`app/models/inventory.py:115`, company scoped). Screen `GET /api/v1/inventory/stock/balance` on
  `inventory.stock.view` (`api/v1/inventory/stock.py:243`), module `inventory`. Staff rows: active warehouses only
  (`inventory_service.py:839`), no per-user warehouse rule, zero rows kept. Grid status is the `Stock.status`
  property (`inventory.py:144`); the SQL status filter `_stock_status_clause` (`inventory_service.py:48`) disagrees
  with it when the product has no reorder level (every positive row reads overstock). Not fixed here (separate bug).
- A contact's stock answer goes through `crm_inventory_stock_balance_list` only, with the stock-visibility policy,
  the `inventory.sellable` grant and `chatbot_stock_allowed` (`chatbot/agent/tools.py:112,151,165`). `crm_query`
  is offered on a linked user's WhatsApp turn too (`query_tools.py:33`).
- Amounts owed: per document `billing_document.outstanding`/`due_date` (wave 2). Per customer
  `Customer.ar_outstanding`, `ar_as_of` (`models/order.py:170-172`, AutoCount), shown on the billing documents
  screen under `finance.billing_documents.view` (`CustomerOutstandingMeta.tsx`,
  `billing_document_query_service.customer_outstanding` :374). `ar_ageing_json` exists but nothing writes it
  (grep: only the model and `customer_merge.py`), so there are no ageing buckets to read.
- Opportunities: `SalesOpportunity` (`models/sales.py:201`), `sales.opportunities.view` / `.view_own`
  (`api/v1/sales/opportunities.py:36,40`), own rule `own_scope.opportunity_clause` (`own_scope.py:161`), list
  `opportunity_service.list_opportunities` (:572) with company scope only. Stage = `statuses.label` by `status_id`.
- Projects: `Project` (`models/projects.py:298`), list `project_service.list_projects` (:1093): company, and drafts
  hidden unless the viewer owns them (`_draft_visible_to` :1012). Own rule `own_scope.project_clause` (:122) under
  `projects.projects.view_own`. Estimated value `ProjectSalesProfile.estimated_sales_value`.
- Quotations: no company-wide list (per project only, `api/v1/projects/quotation_documents.py:117`) and the value
  is computed from versions, not stored: wave 4.

## Changes

1. `stock` + `warehouse` lookup. Fields: on hand, reserved, available, damaged, reorder level (product), status
   as the grid shows it (`inventory_service.stock_status_expr`, a SQL CASE next to the property, parity test over
   every edge), last count date. Scope: active warehouses. `EntityDef.panel_only`: off the staff panel the entity
   refuses and names the stock tool, so the visibility policy and the stock switch are never bypassed.
2. `customer.ar_outstanding` and `customer.ar_as_of` behind `finance.billing_documents.view` (the screen that
   shows them). The hint routes "who owes us" here and per-invoice / overdue to `billing_document`; an ageing
   question is answered with "not available" (note on the field).
3. `opportunity`: number, title, customer, prospect, agent (the `agent` argument), stage, outcome, expected
   amount, expected close date (`period`), source, lost reason, created at. Own rule as the screen.
4. `project`: code, title, stage, outcome, estimated value, owner, approval state, critical, last activity,
   created at. Scope: drafts only to their owner (`EntityDef.scope` now receives the user id). Own rule as the
   screen.

## Tests (no LLM; red first)

`tests/chatbot/agent/test_ai_tools_wave3.py`: each entity's slug, own rule and scope; stock status parity with the
property; panel-only refusal off the panel; AR field gate; drafts; agent and period arguments; company isolation.

## Tokens

`crm_query` + `crm_describe` schemas measured with OpenAI `responses/input_tokens` (free): before 1,086 tokens,
9 index lines. After: in the PR.

## Eval prompts (crew, live)

- "stock of <product code> in every warehouse" / "which items are low in stock at <warehouse>"
- "who owes us the most" / "outstanding of <customer>" / "overdue invoices of <customer>"
- "open opportunities of <agent> closing this month" / "opportunity value won last quarter"
- "my projects that are critical" / "estimated value of open projects per owner"
