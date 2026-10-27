# PLAN: Sales unified (one sales definition + AutoCount-matching reports)

Status: Build - card + mock approved by the owner (Lavish, 27 Oct 16:12; Q1a to Q5a). Track: full
(size L: migration, new permission slugs, finance figures). crew-lane: SALES-UNIFIED.
UAC: `sales-unified-27oct-acceptance-criteria.md` alongside. Mock: `mockups/sales-unified-27oct.html`.

Owner (27 Oct): "Our sales definition must be very clear and unified" and CRM sales should tally
with the AutoCount reports (weekly sales by debtor type by sales agent, comparison by year, Mocha
weekly by debtor type by agent, top selling items).

Owner ruling 27 Oct 16:3x: "we shouldn't hide anything for our figures, should show, for the
sales". No agent or document is hidden from any CRM sales figure or report view. Agents the
AutoCount reports leave out appear as their own rows under an Ungrouped block, and every total is
all sales (Jan 2026 Sorento 14,742,279.29). The "report views hide excluded agents" idea is dropped;
there is no Excluded group.

Paths: backend under `sorento_crm_backend/`, frontend under `sorento_crm_frontend/`. Line numbers
on origin/main 14e29e1e.

## 0. Owner rulings

- **Owner ruling 27 Oct 16:3x**: nothing hidden (above).
- **Owner ruling 27 Oct 16:12 (Lavish), verbatim**: "reuse our reporting engine and calculation as
  much as possible, and all these should be tally with how the MCP tool for chatbot calculate, all
  using a shared function to calculation". Applied: every report in 2.5 is a reports-engine
  definition on the existing datasets; the engine is extended only where it cannot express a
  report, each extension named with its reason in section 2.8. The one module
  `app/services/sales/invoiced_sales.py` feeds the engine datasets, the MCP / chatbot sales tools
  and any page; the chatbot tools run the same engine definitions, so a figure is computed once.
  A test asserts the MCP tool's route returns the report's figure for the same filter (UAC AC-30).
- **Owner closed the review: Q1 (a), Q2 (a), Q3 (a), Q4 (a), Q5 (a)** as recommended in 2.7.

## 1. What exists (measured in code)

- **Billing documents are stored and already summed once.** `finance.billing_documents` /
  `billing_document_lines` (`app/models/finance.py:61`, `:180`) hold IV/CS/CN/DN from AutoCount.
  `app/services/reports/datasets/billing_documents.py:54-57` already applies the formula (credit
  note negative, `local_net_total`, posted only, `doc_date`). Only the Yearly comparison on
  Basis = Invoiced reads it (`reports/definitions/sales_yearly.py:47`), plus the chatbot's
  `crm_sales_analysis` through the same report (`app/api/v1/sales/analysis.py:219`). Nothing reads
  `billing_document_lines` for a sales figure.
- **Every other sales figure is a sales order or delivery order figure**, with three meanings of
  "delivered", two of "ordered", two date rules and mixed tax (inventory in section 5).
- **Debtor type is dropped.** AutoCount `Debtor.DebtorType` arrives as `market_segment_code` on the
  customers push (`app/schemas/canonical_masters.py:149-154`); `_customer_columns` folds it to a
  market segment and drops anything unknown as `segment_unknown`
  (`app/services/master_ingest_service.py:485-490`). `customers.debtor_type` already exists but is
  a different, CRM-owned concept (`project | project_cash | cash_sales`,
  `app/models/order.py:184-186`, CHECK at `:244`), so the AutoCount value needs its own column.
- **Dated agent membership exists, but for teams.** `sales.team_members` (`app/models/sales.py:87`)
  is dated (`valid_from`/`valid_to`) with one open row per agent. Teams carry leaders and targets;
  putting every dealer agent into one "Dealer" team would break the agent's real team. So the
  report grouping is its own small table with the same dated shape (decision D3).
- **The finance ruling Q14 (27 Sep) groups invoiced sales by the sales order type**
  (`billing_documents.demand_class`). The AutoCount reports the owner now wants to tally group by a
  monthly LIST of agents. This plan replaces Q14 for sales reports (open question Q1).

## 2. Behaviour card

### 2.1 The one definition

**Sales = Invoices + Cash sales + Debit notes - Credit notes**, on AutoCount's `LocalNetTotal`
(MYR, net of tax), filed by the document's own date (`DocDate`), cancelled documents excluded.
Quantity on lines the same way: a credit note line's quantity and amount count negative.

- Header amount: `billing_documents.local_net_total`, signed.
- Line amount (items only): `billing_document_lines.net_amount * billing_documents.currency_rate`,
  signed by the document type (lines carry no local amount). Line totals can differ from the
  header by a header-level discount or rounding; header figures (agents, debtor types, totals) use
  the header, item figures use lines, and the item report says so under the filter bar.
- One module owns it: `app/services/sales/invoiced_sales.py` (signed amount, signed quantity, the
  posted filter, and the attributions in 2.2 to 2.4). Every invoiced dataset and service imports
  from it; the sign is applied nowhere else.

### 2.2 Who a sale belongs to (agent)

A company setting, **Sales agent on a sale**: `document` (Sorento: the document's SalesAgent) or
`customer` (Mocha: the debtor's current agent). New column `companies.sales_agent_source`, default
`document`, CHECK (`document`, `customer`), edited on the existing Companies modal. A document with
no agent shows as `(no agent)`; an unresolved code shows as the code sent.

### 2.3 Debtor type

New column `customers.autocount_debtor_type` (varchar 50, raw as AutoCount sends it, upper and
trimmed). The master ingest stores it whenever `market_segment_code` arrives, whether or not it
also folds to a market segment; `segment_unknown` no longer means the value is lost. No hard-coded
list: a report's debtor type columns are whatever values the period's sales carry, and a customer
with none is `(blank)`. A document's debtor type is its customer's current type, as AutoCount's own
reports join `Debtor` at run time (Q2). Shown read-only on the customer detail header.

### 2.4 Report groups (owner-maintained data)

- **Agent groups**: `sales.agent_report_groups` (company, sales agent, group, from month, to month
  open or set). Group is `dealer` or `project_team` (Q5). One open row per agent per company; no
  overlap (checked in the service, the `team_service` rule). A sale is in the group whose row
  covers the document's month.
- **Set-apart customers**: `sales.set_apart_customers` (company, customer, from month, to month).
  A set-apart customer's sales go to the **Set apart** block whatever the agent.
- **Ungrouped**: computed, not stored. An agent with no group row for the month is Ungrouped. No
  "Excluded" group exists.
- **Order of blocks**: Dealer, Project team, Set apart, Ungrouped. Then two total rows:
  **Report total** (Dealer + Project team + Set apart: the figure the AutoCount PDF prints) and
  **ALL SALES** (everything, the company figure). ALL SALES is the total wherever one total shows.
- **Settings screen**: Sales > Report groups, two line tabs (Agent groups, Set-apart customers),
  existing DataGrid + modal create/edit + deferred-action delete. New slugs
  `sales.report_groups.view` and `sales.report_groups.edit`, seeded to admin and superadmin.
- **Seed**: crew provides the agent lists read on AutoCount; they go in as a `crew-migration` SQL
  for the owner's copy and the owner corrects on the screen. No real list is committed in code or
  test seeds (fictional codes only).

### 2.5 The four reports (reports kernel, `sales.reports.view`, Sales group in the sidebar)

| Report | Rows | Columns | Filters | Notes |
| --- | --- | --- | --- | --- |
| **Sales by debtor type** (new, Sorento and Mocha) | Sales agent, in blocks Dealer / Project team / Set apart / Ungrouped, block totals, Report total, ALL SALES | Debtor types present in the period, then Total | Company, Period (month), View (Month / Year to date), Agent, Debtor type | Excel: one sheet per month plus a YTD sheet, title "Weekly Sales by Debtor Type by Sales Agent". Mocha (no groups) is one list ending ALL SALES. Cell drill to documents |
| **Yearly comparison** (existing page) | Years by month, VARIANCE row, per block | JAN..DEC, TOTALS | Company, Group (Dealer, Project team, Set apart, Ungrouped), As at, Basis | Basis default becomes Invoiced; on Invoiced the blocks are the report groups (replaces the sales order type, Q1). Delivered / Ordered stay as labelled choices |
| **Top selling items** (new) | Item, ranked | #, Item code, Description, Brand, Qty, UOM, RM, Documents | Company, Period, Rank by (RM / Qty), Report group, Debtor type, Brand, Agent | Billing lines, credit notes negative. Unresolved item codes still count |
| **Mocha** | = Sales by debtor type with Company = Mocha | ACCOUNT I to IV (its own types) | as above | agent from the customer (2.2) |

Every column header sorts server-side (within a block for blocked reports; blocks keep their
order). Company scope as the kernel does today (`Dataset.company_param`, fail-closed grants).

### 2.6 Every other sales figure (section 5 inventory)

Rule: a figure called "sales" is the invoiced definition; a figure that is not invoiced says
"Delivered" or "Ordered" in its label, its column headers, its tool description and its Excel title.

| Figure | Change |
| --- | --- |
| Yearly comparison + chatbot `crm_sales_analysis` | Default basis Invoiced (on the shared module); Delivered / Ordered labelled |
| Top selling route `/order-management/top-selling`, MCP `crm_top_selling_report`, chatbot top selling via `crm_report_ask` | Basis `invoiced` added and made the default, reading billing lines through the shared module; ordered / delivered kept, labelled |
| Report-ask (`crm_report_ask`) sales measures | Measure `sales` (invoiced) added and made the default for "sales"; delivered / ordered / outstanding kept, labelled |
| Delivered sales report (`/order-management/sales-report`, `crm_sales_report`) | Unchanged maths, renamed "Delivered sales report" in title, tool description and Excel |
| Order analytics `total_value` (`crm_order_analytics`) | Relabelled "Delivered value incl. tax" |
| Sales targets achievement | Unchanged (each target carries its own ordered / delivered basis, a commission contract); labels already name the basis (Q4) |
| SCM ABC value, product economics, project forecast | Not sales figures; untouched |

### 2.7 Open questions (one crew-ask)

- **Q1.** On the invoiced basis, Dealer / Project team come from the agent report groups, replacing
  the sales order type grouping of finance ruling Q14. (a) yes, (b) keep sales order type.
  **Recommend (a)**: the AutoCount reports the owner tallies against group by agent list.
- **Q2.** A document's debtor type: (a) the customer's current type, (b) a snapshot at ingest.
  **Recommend (a)**: AutoCount's own report joins Debtor at run time, so (a) is what tallies.
- **Q3.** Set-apart customers carry effective months like agent groups. (a) yes, (b) a plain list.
  **Recommend (a)**: same shape as the agent groups, one rule to learn, history stays right.
- **Q4.** Sales targets keep their own ordered / delivered basis. (a) keep, (b) add invoiced.
  **Recommend (a)**: a target is a commission contract already set per target; adding invoiced is
  its own lane when the owner asks.
- **Q5.** Groups are a fixed pair (Dealer, Project team) plus computed Ungrouped. (a) fixed pair,
  (b) owner-named groups. **Recommend (a)**: the reports have exactly these blocks; a third group is
  a one-line CHECK change when it arrives.

## 3. Slices (one lane, commits on this branch)

1. **S1 schema + ingest**: one migration (`customers.autocount_debtor_type`,
   `companies.sales_agent_source`, `sales.agent_report_groups`, `sales.set_apart_customers`, two
   slugs); ingest stores the raw debtor type; Companies modal field; customer header field.
2. **S2 shared module + settings**: `invoiced_sales.py`; group/set-apart service + routes
   (`/api/v1/sales/report-groups`, `/api/v1/sales/set-apart-customers`), Report groups screen.
3. **S3 reports**: billing dataset gains `debtor_type`, `sales_agent`, `report_group`; new
   `billing_document_lines` dataset; definitions Sales by debtor type, Top selling items; Yearly
   comparison default Invoiced + group blocks; kernel extension for the Report total row.
4. **S4 other figures**: top selling route/MCP/report-ask invoiced default; relabels of 2.6.
5. **S5 tally tests**: seeded fictional fixtures reproducing the verified structure (DN counted,
   CN negative, cancelled out, tax excluded, document vs customer agent, month-dated groups,
   set-apart pulled out, ungrouped kept, Report total vs ALL SALES); crew runs the real tally.

## 4. Risks

- Billing lines have no local amount: a non-MYR line is converted with the header rate.
- Group rows edited after the fact re-group past months at once (reports are computed). Intended.
- Two migration PRs merging back to back fork main: re-check `alembic heads` before merge.

## 5. Sales figure inventory (measured, 27 Oct)

1. Top selling: `app/services/sales_report_service.py:642`, SO lines, `coalesce(required_date, order_date)`.
2. Delivered sales report: `app/services/sales_report_delivered.py:225` -> `reports/datasets/delivery_order_lines.py:290`, DO lines, DO date.
3. Report-ask: `reports/datasets/sales_order_lines_ask.py:138-184`, SO lines.
4. Yearly comparison ordered/delivered: `reports/datasets/sales_order_lines.py:88`, SO date; invoiced: `reports/datasets/billing_documents.py:54`.
5. Chatbot sales analysis: `app/api/v1/sales/analysis.py:219` (runs the Yearly comparison).
6. Order analytics `total_value`: `app/services/order_service.py:1523`, DO lines incl. tax.
7. Targets achievement: `app/services/sales/achievement_service.py:174`, `:256`, `:661`.
8. Not sales: SCM ABC `app/services/scm/analytics_service.py:404`, product economics
   `app/services/scm/product_economics_service.py:116`, project forecast
   `app/services/project_forecast_service.py:126`.
9. Dead: `sales_report()` at `app/services/sales_report_service.py:281` (tests only).
10. No live dashboard sales widget (`store-admin/dashboard/components/sales-activity.tsx:25` is static).
