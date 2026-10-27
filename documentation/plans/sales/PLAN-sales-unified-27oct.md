# PLAN: Sales unified (one sales definition + AutoCount-matching reports)

Status: Build, round 3 (27 Oct 2026): card approved (Lavish 16:12, Q2 to Q5 (a)); Q1 re-ruled (b)
at 16:2x; round 3 (section 2.9) fixes the sales order type at the source, Q6 to Q10 open. Track: full (size L: migration, new permission slug, finance
figures). crew-lane: SALES-UNIFIED.
UAC: `sales-unified-27oct-acceptance-criteria.md` alongside. Mock: `mockups/sales-unified-27oct.html`.

Owner (27 Oct): "Our sales definition must be very clear and unified" and CRM sales should tally
with the AutoCount reports (weekly sales by debtor type by sales agent, comparison by year, Mocha
weekly by debtor type by agent, top selling items).

Paths: backend under `sorento_crm_backend/`, frontend under `sorento_crm_frontend/`. Line numbers
on origin/main 14e29e1e.

## 0. Owner rulings

- **27 Oct 16:3x**: "we shouldn't hide anything for our figures, should show, for the sales". No
  agent or document is hidden from any CRM sales figure or report view; every total is all sales
  (Jan 2026 Sorento 14,742,279.29). No Excluded group exists.
- **27 Oct 16:12 (Lavish), verbatim**: "reuse our reporting engine and calculation as much as
  possible, and all these should be tally with how the MCP tool for chatbot calculate, all using a
  shared function to calculation". Applied: every report is a reports-engine definition on the
  existing billing dataset; the engine is extended only where it cannot express a report (2.8).
  One module, `app/services/sales/invoiced_sales.py`, feeds the engine datasets, and the MCP /
  chatbot sales tools run the same engine definitions, so a figure is computed once. A test asserts
  the MCP tool's route returns the report's figure for the same filter (AC-30).
- **Review closed: Q2 (a), Q3 (a), Q4 (a), Q5 (a)** as recommended in round 1.
- **27 Oct 16:2x, Q1 re-ruled (b)**: "ultimately, the sales type should depend on sales order". The
  Dealer / Project team split of invoiced sales comes from the SALES ORDER (its type), reached
  billing line -> DO -> SO, the chain lane DOC-RELATIONS (#1912) builds in
  `app/services/document_relations.py` (reused, coordinated by crew-note). A document that cannot
  be traced to a sales order goes to its own visible bucket, **No sales order**: never hidden,
  never guessed. The tally shows how far the SO-based split lands from the AutoCount agent-list
  figures (Jan Dealer 6,513,047.67, Project team 6,084,471.57).
- **Consequence of Q1 (b)**: agent groups are not built. The blocks are the sales type, the rows are
  agents, so an agent who sold both types appears in both blocks; no agent list decides anything.
  Q5 (the fixed pair of groups) has nothing left to apply to. Set-apart customers stay (Q3 (a)).

## 1. What exists (measured in code)

- **Billing documents are stored and already summed once.** `finance.billing_documents` /
  `billing_document_lines` (`app/models/finance.py:61`, `:180`) hold IV/CS/CN/DN from AutoCount.
  `app/services/reports/datasets/billing_documents.py:54-57` applies the formula (credit note
  negative, `local_net_total`, posted only, `doc_date`). Only the Yearly comparison on Basis =
  Invoiced reads it (`reports/definitions/sales_yearly.py:47`), plus the chatbot's
  `crm_sales_analysis`, which runs that same report through `engine.run`
  (`app/api/v1/sales/analysis.py:219-338`). Nothing reads `billing_document_lines` for a figure.
- **The stored `billing_documents.demand_class` guesses.** The ingest decides it with
  `classify_document` (`app/services/scm/demand_class.py:73`): the first linked SO line's order
  type, else the note's invoice, else **the agent's class, else the customer's market segment**
  (`app/services/finance/billing_document_ingest_service.py:604-628`). The last two rungs are the
  guess Q1 (b) forbids, and the first rung reads only the stored `sales_order_line_id`, which
  DOC-RELATIONS found stale (SO427775: its invoice came from a DO whose lines never resolved).
  The reports therefore stop reading the stored column; the sales type is derived at read time.
- **Every other sales figure is a sales order or delivery order figure**, with three meanings of
  "delivered", two of "ordered", two date rules and mixed tax (inventory in section 5).
- **Debtor type is dropped.** AutoCount `Debtor.DebtorType` arrives as `market_segment_code` on the
  customers push (`app/schemas/canonical_masters.py:149-154`); `_customer_columns` folds it to a
  market segment and drops anything unknown as `segment_unknown`
  (`app/services/master_ingest_service.py:485-490`). `customers.debtor_type` exists but is a
  different, CRM-owned concept (`project | project_cash | cash_sales`, `app/models/order.py:184`).
- **The kernel already draws blocks.** `WorkbookSpec.sheet_per` names a multi-select param; the
  engine runs one pivot per chosen value (`app/services/reports/engine.py:972-1010`), on screen and
  in the workbook. The Yearly comparison uses it for its DEALER / PROJECT TEAM blocks.

## 2. Behaviour card

### 2.1 The one definition

**Sales = Invoices + Cash sales + Debit notes - Credit notes**, on AutoCount's `LocalNetTotal`
(MYR, net of tax), filed by `DocDate`, cancelled documents excluded. Item quantity and amount from
lines the same way, credit note lines negative.

- Header amount: `billing_documents.local_net_total`, signed.
- Line amount: `billing_document_lines.net_amount * billing_documents.currency_rate`, signed by the
  document type (lines carry no local amount). Header figures (agents, debtor types, totals) use
  the header; item figures use lines; the item report says so under its filter bar.
- `app/services/sales/invoiced_sales.py` owns: the posted filter, the signed amount and quantity,
  the agent (2.2), the debtor type (2.3) and the sales type (2.4). Every invoiced dataset imports
  from it; the sign is applied nowhere else (the dataset's own `_signed` moves there).

### 2.2 Who a sale belongs to (agent)

Company setting **Sales agent on a sale**: `document` (Sorento) or `customer` (Mocha). Column
`companies.sales_agent_source`, default `document`, CHECK (`document`, `customer`), on the existing
Companies modal. Read in SQL by joining the document's company, so one expression serves any run.
No agent shows `(no agent)`; an unresolved code shows as sent.

### 2.3 Debtor type

Column `customers.autocount_debtor_type` (varchar 50, upper and trimmed). The master ingest stores
it whenever `market_segment_code` arrives, whether or not it also folds to a market segment. No
hard-coded list: a report's debtor type columns are whatever the period's sales carry; none is
`(blank)`. A document's debtor type is its customer's current one (Q2 (a)). Read-only on the
customer detail header.

### 2.4 Sales type (the blocks), derived at read time

In order, first match wins:

1. **Set apart**: the customer has a `sales.set_apart_customers` row covering the document's month
   (Q3 (a)). The AutoCount report pulls these debtors out of Dealer and Project team.
2. The sales orders the document traces to, by the DOC-RELATIONS chain (a billing line resolved
   onto an SO line, transferred from an SO by number, or transferred from a DO by number and that
   DO's SOs; a credit or debit note with no traced line inherits its invoice's orders):
   - every traced SO is `retail` -> **Dealer**; every one `project` -> **Project team**;
   - both types -> **Mixed sales order types** (visible, never split by guess);
   - traced SOs all without a type -> **Sales order type not set**.
3. Nothing traced -> **No sales order** (cash sales, manual invoices).

The buckets are the Channel values of the invoiced basis, in that order (Dealer, Project team, Set
apart, Mixed, Type not set, No sales order). With every value ticked the blocks add up to all
sales. Set-apart customers: screen Sales > Set-apart customers (DataGrid, modal create/edit,
deferred delete), read under `sales.reports.view`, written under the new slug
`sales.set_apart.edit` (seeded to admin and superadmin). Crew supplies the 4 debtor codes as a
`crew-migration`; no real code is committed.

### 2.5 Reports (reports kernel, `sales.reports.view`, Sales group)

| Report | Rows | Columns | Filters | Notes |
| --- | --- | --- | --- | --- |
| **Sales by debtor type** (new definition) | Sales agent, one block per sales type | Debtor types present, Total | Company, Channel (sales type, all ticked), Period (default this month), Agent, Debtor type | Excel: blocks on the summary sheet plus one sheet per month of the period (YTD = pick 1 Jan to month end). Untick No sales order, Mixed and Type not set to read the AutoCount report's own total. Mocha: same report, its own types (ACCOUNT I to IV), agent from the customer |
| **Yearly comparison** (existing) | Years by month, VARIANCE, per block | JAN..DEC, TOTALS | Company, Channel, Basis, As at | Basis default Invoiced; on Invoiced the blocks are 2.4's sales types. Delivered / Ordered unchanged, labelled |
| **Top selling items** (new definition, lines dataset) | Item | Item code, Description, Brand, Qty, RM, Documents | Company, Period, Channel, Debtor type, Agent | Credit notes negative; an unresolved item code still counts by its code; ranked by sorting a column (server-side) |

Every column sorts server-side (the kernel's own sort). Company scope as today
(`Dataset.company_param`, fail-closed grants).

### 2.6 Every other sales figure (section 5 inventory)

A figure called "sales" is the invoiced definition; a figure that is not invoiced says "Delivered"
or "Ordered" in its label, column headers, tool description and Excel title.

| Figure | Change |
| --- | --- |
| Chatbot `crm_sales_analysis` (`/api/v1/sales/analysis`) | Basis default Invoiced; new axes `agent`, `debtor_type` (invoiced only); runs the same definitions (2.5) through `engine.run` |
| Top selling route `/order-management/top-selling`, MCP `crm_top_selling_report` | `basis=invoiced` added and default, answered by running the Top selling items definition; ordered / delivered kept, labelled |
| Report-ask (`crm_report_ask`) | Unchanged maths; its sales measures say "ordered" / "delivered" in labels and the tool description, and point invoiced asks to `crm_sales_analysis` / top selling |
| Delivered sales report (`crm_sales_report`) | Renamed "Delivered sales report" (title, tool description, Excel) |
| Order analytics `total_value` (`crm_order_analytics`) | Relabelled "Delivered value incl. tax" |
| Sales targets | Unchanged (Q4 (a)) |
| SCM ABC, product economics, project forecast | Not sales figures; untouched |

### 2.7 Open questions

None open. Round 1 Q1 to Q5 are ruled (section 0).

### 2.8 Engine extensions (only where the kernel cannot express it)

- **None for the blocks, the YTD or the Report total.** Blocks are `sheet_per` on the Channel
  param; YTD is the period; the AutoCount-only total is the Channel filter with the non-AutoCount
  buckets unticked.
- **`Column.agg = "count_distinct"`** if the kernel lacks it, for Top selling's Documents column
  (checked during the build; dropped from the report if it needs more than that).

### 2.9 Round 3: fix the sales order type at the source (crew finding, 27 Oct)

Crew measured January 2026 Sorento on the dev clone (relayed on the PR): AutoCount sends no order
type on 4,979 of 5,000 SOs, so the agent's class decides; `sales_agents.demand_class` is hand-typed,
current-only, undated (`app/services/scm/sales_agent_service.py:224`); an SO's class is stamped once
at ingest (`app/services/document_ingest_service.py:1178`) and an agent change only fills blank SOs
(`sales_agent_service.py:145-171`); invoices copy their SO's class. Result: Project matches AutoCount
within RM 1,245, Dealer is RM 1.76M over because agents in neither AutoCount list (five codes) fall
into `retail` = Dealer, one agent is `retail` by migration 427 but Project in AutoCount, 13
dealer-suffix codes have no class, and two agents have a few SOs stamped `project`.

The owner's ruling stands (the type comes from the SO), so this lane fixes the SO's type:

1. **Agent class becomes dated data** (Q6): an agent's class from a month, to a month.
2. **A third, visible class for agents in neither list** (Q7), next to Set apart (a report-level
   customer list, unchanged).
3. **An SO's class follows the agent class in effect on the SO date** (Q8): re-derived when the
   agent's dated class changes, not stamped forever; an order type AutoCount states still wins.
   A dry-run backfill reports every SO whose class would change (count and RM per agent per
   month) before anything is written.
4. **Data proposal** (Q10): the one agent to `project`, the 13 blank dealer-suffix codes to
   `retail`, applied by the owner (crew SQL after the dry run), not committed in code.

Questions (crew-ask):
- **Q6** Where the dated class lives: (a) new `sales.agent_classes` (agent, class, from month, to
  month; one open row per agent; a Class history grid on the Sales Agents detail); (b) reuse
  `sales.team_members` with a Dealer team and a Project team; (c) a class plus a since-month on
  `sales_agents`. **Recommend (a)**: (b) allows one open team per agent, so a Dealer "team" would
  pull agents out of their real sales team; (c) remembers one change only, so a second move rewrites
  the past.
- **Q7** Agents in neither AutoCount list: (a) a third class `other`, shown "Other" everywhere,
  never counted as Dealer; (b) keep them Dealer. **Recommend (a)** (pending the owner's word on
  "Other"): it keeps Dealer equal to the AutoCount Dealer figure and nothing is hidden. Side
  effect: SCM fulfilment priority weighs only `retail` and `project`
  (`app/services/scm/demand_class.py` docstring: a third class drops out of ranking), so `other`
  is weighed as `retail` in priority (one mapping in `scm/priority.py`), keeping fulfilment as it
  is today.
- **Q8** Keeping SOs right: (a) the stored `sales_orders.demand_class` is re-derived (stated order
  type, else the agent's class on the SO date, else nothing) at ingest and whenever an agent's dated
  class changes for the months it covers; every reader (SCM, reports, chatbot) keeps reading the
  column; (b) compute it at read time everywhere. **Recommend (a)**: one column many readers
  already use, re-derived where it can go stale. The customer-segment rung is dropped for SOs (the
  "never guessed" rule): an SO with no stated type and no agent class is "Type not set".
- **Q9** Invoices: (a) the report reads the SO class through the chain at run time (built in
  round 2), so a re-derived SO moves its invoices at once; the stored
  `billing_documents.demand_class` stops being read by sales figures. **Recommend (a)**.
- **Q10** The data fix (the one agent to `project`, 13 codes to `retail`): (a) crew SQL on the
  owner's copy after the dry run, then the owner checks the tally; (b) a data migration. **Recommend
  (a)**: business data, owner-confirmed, kept out of code.

## 3. Slices (one lane, commits on this branch)

1. **S1 schema + ingest**: one migration (`customers.autocount_debtor_type`,
   `companies.sales_agent_source`, `sales.set_apart_customers`, slug `sales.set_apart.edit`);
   ingest stores the raw debtor type; Companies modal field; customer header field.
2. **S2 shared module**: `invoiced_sales.py` (2.1 to 2.4) on DOC-RELATIONS' predicates; billing
   dataset gains `debtor_type`, `sales_agent`; its `channel` becomes the sales type; new
   `billing_document_lines` dataset; set-apart routes and screen.
3. **S3 reports**: Sales by debtor type and Top selling items definitions; Yearly comparison
   default Invoiced; sidebar entries.
4. **S4 other figures**: chatbot / MCP routes on the definitions (2.6), relabels.
6. **S6 SO type at the source** (round 3, after Q6 to Q10): dated agent classes, `other`, SO
   re-derivation with a dry-run backfill, Sales Agents class history grid.
5. **S5 tally**: seeded fictional fixtures (AC-28) plus `scripts/sales_unified_tally.py`, a
   read-only script crew runs on the owner's copy: per bucket per month, with the AutoCount
   agent-list figures beside it and the gap.

## 4. Risks

- DOC-RELATIONS is not on main yet. S2 needs a set-based reverse (billing document -> sales
  orders) next to its per-record functions; asked on #1912. If #1912 merges without it, this lane
  adds it to `document_relations.py` on the same predicates.
- Read-time tracing over a year of documents: measured with `EXPLAIN ANALYZE` in the tally run.
- Billing lines carry no local amount: a non-MYR line is converted with the header rate.

## 5. Sales figure inventory (measured, 27 Oct)

1. Top selling: `app/services/sales_report_service.py:642`, SO lines, `coalesce(required_date, order_date)`.
2. Delivered sales report: `app/services/sales_report_delivered.py:225` -> `reports/datasets/delivery_order_lines.py:290`, DO lines, DO date.
3. Report-ask: `reports/datasets/sales_order_lines_ask.py:138-184`, SO lines.
4. Yearly comparison ordered / delivered: `reports/datasets/sales_order_lines.py:88`; invoiced: `reports/datasets/billing_documents.py:54`.
5. Chatbot sales analysis: `app/api/v1/sales/analysis.py:219` (runs the Yearly comparison).
6. Order analytics `total_value`: `app/services/order_service.py:1523`, DO lines incl. tax.
7. Targets achievement: `app/services/sales/achievement_service.py:174`, `:256`, `:661`.
8. Not sales: SCM ABC `app/services/scm/analytics_service.py:404`, product economics
   `app/services/scm/product_economics_service.py:116`, project forecast
   `app/services/project_forecast_service.py:126`.
9. Dead: `sales_report()` at `app/services/sales_report_service.py:281` (tests only).
10. No live dashboard sales widget (`store-admin/dashboard/components/sales-activity.tsx:25` is static).
