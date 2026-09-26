# PLAN: retail sales reports, one query layer for the report screens and the chatbot (#1267)

Status: draft, pre-grill (26 Sep 2026). Grill questions G1 to G10 are in section 9 and posted on
the docs PR as one comment. Track: full for S1 to S5 (a new permission slug in S1, a migration and
a changed external ingest field in S3, a new chatbot tool in S1). S0 is a measurement with no code.
Nothing built.
Domain: sales. Classification: **CORE extension of `order_management`** (no new module key). The
reports read `sales_orders` / `sales_order_lines`, which `order_management` owns, and they mount on
the sales report's own router (`sales_report_router`, `app/api/v1/order_management/orders.py`).
The `sales` module #1260 proposes does not exist yet; when it lands, these routes can move under
its key with no data change (named trigger, section 7).
UAC: `retail-sales-reports-26sep-acceptance-criteria.md` alongside (the contract; the journey J1
to J9 lives there and is not repeated here).
Mockup: `mockups/retail-sales-reports.html` (report A with its charts, report B, report C, the
export, and the chatbot replies, each at 1280 and 375).
Issue: #1267.

Backend paths are under `sorento_crm_backend/`, frontend under `sorento_crm_frontend/`, MCP under
`sorento_crm_mcp/`. Line numbers are on origin/main 46711c61 unless a PR branch is named.

## 1. In plain words (for the owner)

You keep three spreadsheets by hand. The CRM already holds every Sorento sales order line that
AutoCount sends, with the customer, the sales agent code, the dealer or project class and the
amount. So:

- **Report A (yearly comparison)** can be built now from data we already have: dealer and project
  sales per month for 2024, 2025 and 2026, the variance row and a line chart per block.
- **Report B (Sorento by account)** needs two things we do not hold today: the sales agent as a
  **person** (AutoCount has one code per person per account, e.g. `SEAN I` and `SEAN III`, and
  nobody has grouped them yet), and the **debtor type** of each customer (SORENTO, BRAVAT,
  CERAMIC, CABANA, PROJECT, SAMPLE). AutoCount sends the debtor type, but the CRM throws it away
  today because it only keeps "retail" or "project". Fixing that is one column.
- **Report C (Mocha by account)** needs Mocha's sales orders, and **Mocha has none in the CRM**:
  its AutoCount sales order feed was never connected. Until it is, report C cannot be produced.

Every figure is a **sales order** figure, not an invoice figure: the CRM has no customer invoice
table. Your spreadsheets look like invoiced sales. Section 4 says what that means and G1 asks you
to choose.

The report screens and the chatbot both call **one** function, so "Sean's sales this month by
brand" on WhatsApp and the Report B screen can never disagree.

## 2. Measured facts (read only)

### 2.1 What already exists and is reused

**The sales report service** (`app/services/sales_report_service.py`):
- `sales_report(db, *, product_code, customer_query, customer_ids, channel, warehouse_codes,
  date_from, date_to, detail)` (:275). Ordered, confirmed and outstanding value and quantity per
  month, summed in SQL (docstring :11-31).
- `_per_line_exprs()` (:198-220) is the money rule this plan reuses unchanged:
  `confirmed_qty = LEAST(qty_delivered, qty_ordered)` (:202), `confirmed_value =
  ROUND(line_total * confirmed_qty / NULLIF(qty_ordered, 0), 2)` per line (:204-210), outstanding
  only while the SO and the line are `open` (:211-213), `ordered = confirmed + outstanding`
  (:214-215).
- `_common_filters(...)` (:236-271): cancelled SO and cancelled line excluded (:241-242), the
  bucket date not null (:246), `channel` dealer means `demand_class = 'retail'`, project means
  `'project'` (:264-267). It takes `bucket_expr` as a parameter, so a report can bucket by
  `sales_orders.order_date` without a second copy of the predicate.
- `_bucket_expr()` (:191-195) is `COALESCE(sales_order_lines.required_date,
  sales_orders.order_date)`: the sales report files a line under its **delivery** month.
- Company scope is applied by the ORM `do_orm_execute` listener (:50-54); `sales_orders` and
  `sales_order_lines` use `CompanyScopedMixin` (`app/models/base.py:92-118`).
- Route `GET /api/v1/order-management/sales-report` (`app/api/v1/order_management/orders.py:1576`),
  permission `order_management.orders.view` (:1646), per-contact reveal key
  `sales_orders.sales_report` re-checked for API-key callers (:1713-1726). No frontend screen
  calls it; it is chatbot only.
- MCP tool `crm_sales_report` (`sorento_crm_mcp/sorento_crm_mcp/catalog.py:725-764`), presenter
  `_sales_report` (`sorento_crm_mcp/sorento_crm_mcp/presenters.py:2352`), chatbot grant
  `_SALES_REPORT_GRANT` (`app/services/chatbot/lanes/business/__init__.py:66`).

**Top X hot selling** (plan PR #1175, S1 presenter PR #1258, S2 route + S3 MCP tool PR #1263, all
open, not on main). On branch `claude/top-selling-s2-s3-j8nhan`:
- `top_selling(...)` in `app/services/sales_report_service.py:574` and
  `current_year_window(today)` (:552); route `GET /api/v1/order-management/top-selling`
  (`app/api/v1/order_management/orders.py:1848`) on the same `sales_report_router` (:1580), with
  the dealer scope helper `_top_selling_dealer_scope` (:1809).
- MCP ToolSpec `crm_top_selling_report` (`sorento_crm_mcp/sorento_crm_mcp/catalog.py:766`),
  reveal key reused, no paging params, `related_tools=("crm_sales_report",)` (:800).
- Response carries `total_count` and whole-set `totals` from window functions, so a cut never
  changes the count (PR #1263 body). Filter `sales_agent_ids` on `sales_orders.sales_agent_id`.
- Owner rulings 26 Sep that this plan inherits verbatim (PR #1175 plan
  `documentation/plans/chatbot/PLAN-chatbot-top-x-hot-selling-24sep.md:19-56` on that branch):
  no "more" / "next" / "lagi" anywhere; the header states the full count; no N and a list too
  long for one message = state the count and ask how many; no default metric; clarify, never
  assume; dealer contacts forced to their own ledgers.
- On main the older counted-set answer still pages by 5 on "more" (`app/services/chatbot/lanes/
  business/answer.py:2620-2634`, AC-1534 in `chatbot-turn-rearch-acceptance-criteria.md:215`).
  This plan's tool never takes that path.

**The reporting kernel** (`PLAN-reporting-foundation`, archived under
`documentation/plans/_archive/reports/`):
- `app/services/reports/registry.py` (Dataset, params, `WorkbookSpec` :264-294),
  `engine.py` (`_pivot` :529: one row dimension x one column dimension x measures, row, column
  and grand totals, `BLANK_VALUE` :59, `PIVOT_CELL_CAP` 5000 :47), `xlsx_renderer.py`
  (`render_workbook` :410, `_title_block` :120, `_write_money` :98, totals written as values,
  never formulas, docstring :14-16), `views_service.py` (saved views).
- Wire schema `app/schemas/report.py`: `ReportPivotLayout` (:73-86) with `row_dim`, `col_dim`
  (values and value labels), `measures`, `row_values`, `cells`, `row_totals`, `col_totals`,
  `grand_total`.
- Frontend `components/reports/ReportPivotTable.tsx:46` renders a `ReportPivotLayout`;
  `ReportPage.tsx:270` (Detail + Summary tabs, Export to Excel :455-461); `ReportFilterBar.tsx:134`;
  `ReportViewsMenu.tsx:34`.
- Its company arm is not fail-closed yet: `engine._predicates` carries a TODO "make this arm
  FAIL-CLOSED ... the day a dataset declares scope='company'" (`engine.py:310-315`); the one
  dataset today is `scope="none"` (`datasets/sponsorship_forms.py:283`).

**Charts:** `recharts` 2.15.1 (`package.json:86`) with the wrapper `components/ui/chart.tsx:5`,
used by `app/(protected)/sla-management/kpi-dashboard/SLAKpiDashboardContent.tsx:15`.
`DESIGN-LANGUAGE.md` has no chart section.

**Sales targets plan** (PR #1260, `documentation/plans/sales/PLAN-sales-targets-opportunities-
26sep.md` on `claude/sales-targets-opportunities-plan-7behob`): the same source and the same two
bases (ordered = `line_total`, delivered = confirmed value, its section 2); R2 recommends a person
counts every code sharing its `person_label`; S6 adds `sales_teams` / `sales_team_members`; G1
records "invoiced (not available: the CRM has no customer invoice table)" (:772-777).

### 2.2 The data behind each dimension

**Sales order header** `sales_orders` (`app/models/order.py:410-500`): `so_number` :421,
`customer_id` :422, `debtor_code` :428, `sales_agent_id` :433 (set from AutoCount's agent code on
ingest, `app/services/document_ingest_service.py:219`), `order_date` Date :434 (not indexed),
`demand_class` project or retail :443, `status` :451 (open, fulfilled, closed, cancelled;
AutoCount "partial" is stored as open, `document_ingest_service.py:131-145`), `source_system` :452.
No currency (MYR, `app/services/scm/money.py:28`), no header totals, no tax column.

**Sales order line** `sales_order_lines` (`order.py:503-570`): `product_id` :509, `qty_ordered`
:511, `qty_delivered` :512, `unit_price` :518, `discount` :525, `line_total` :526 (AutoCount
"Total (Inc)", tax inclusive, after discount), `required_date` :532, `line_status` :551.

**No customer invoice.** The only invoice tables are supplier proformas (`app/models/scm.py:1702`,
:1852, :1950, :2056). The DO table `orders` (`order.py:286-357`) has money columns, but its money
is documented as unusable (August 2026 sums to 136.3M against 23.2M) and DO rows only exist from
April 2026 (`documentation/plans/chatbot/chatbot-sales-report-acceptance-criteria.md:46-49`). No
AutoCount IV (invoice) document is ingested anywhere.

**Sales agent** `sales_agents` (`app/models/sales_agent.py:42-134`): one row per AutoCount code,
`sales_agent` :50; `person_label` :60 groups codes into people ("38 codes decompose to 16 people
via a `(name, I|III|IV)` split", :56-59); `company_id` NULL = shared across companies :73. **Filled
on 0 codes**: "`person_label` is NULL for every one of the 80 agents on the prod copy"
(`app/services/order_inquiry_header_service.py:96-97`); `demand_breakdown_service.py:52` says the
same. Editable today on the Sales Agents detail screen through `PATCH
/api/v1/master-data/sales-agents/{id}/annotation` (`app/api/v1/master_data/sales_agents.py:109`,
`person_label` written :125), slug `master_data.sales_agents.edit`. The established label rule is
`COALESCE(person_label, sales_agent)` (`order_inquiry_header_service.py:105`,
`demand_breakdown_service.py:132`).

**Debtor type (ACCOUNT I..IV and SORENTO / BRAVAT / CERAMIC / CABANA / PROJECT / SAMPLE).**
- AutoCount `Debtor.DebtorType` arrives on the masters push as `market_segment_code`
  (`app/schemas/canonical_masters.py:139-145`) and folds onto `market_segments.code`
  (`app/services/rules/customer_rules.py:28-47`), whose only seeded rows are `retail` and
  `project` (`alembic/versions/263_market_segments.py:107-110`). **Any other value is dropped**
  with the warning `segment_unknown` (`app/services/master_ingest_service.py:477-482`;
  documents: `document_ingest_service.py:1058-1076`). So if AutoCount's debtor type is SORENTO or
  ACCOUNT I, the CRM receives it and discards it.
- Counter-evidence: the customer Excel importer's test says "a real AutoCount listing's `Debtor
  Type` carries Trade / Cash / Local" and deliberately maps no alias for it
  (`tests/test_customer_import.py:500-523`). Which company's listing that was is not recorded.
- The same split is visible in names: a customer keeps one ledger per account, with the account in
  the name, e.g. `HANLIM TRADING SDN BHD [A/C I]` (PR #1258 goldens), `Deluxe Home Center AC (I)`
  (`customer_rules.py:4-5`), and ledger suffixes `(PROJECT)`, `(CERAMIC & ELLECI)`, `[IBORN]`
  (`app/services/chatbot/lanes/business/fetch.py:1223`,
  `documentation/plans/chatbot/PLAN-chatbot-outstanding-report.md:63`).
- The agent codes carry the same roman numerals (`SEAN I`, `SEAN III`), and the suffix "maps to
  neither company nor market segment in this database" (`sales_agent.py:61-64`).
- Conclusion: **the debtor type is not stored today**. The likely source is AutoCount
  `Debtor.DebtorType`, but that needs the S0 measurement (the raw values the masters push sends)
  and G3.

**Brand / product category.** `product_categories.category_code` is the AutoCount Item Group
(`app/services/autocount_pull_service.py:455`), shaped `<BRAND>-<CLASS>`, prefixes SRT Sorento, CB
Cabana, M Mocha, BRT Bravat, IDC, IB Iborn (`app/services/product_class_signal.py:30-37`); `brands`
(`app/models/product.py:98`) is the AutoCount Item Brand; `products.brand_id` :203. No CERAMIC,
PROJECT or SAMPLE brand or category exists, which is why the report B columns read as **debtor
types**, as the report's own title says ("Weekly Sales by Debtor Type by Sales Agent"). A product
brand breakdown (SRT / BRT / CB) is possible from lines and is offered as a separate axis (G3).

**Dealer vs project team.** `sales_orders.demand_class` (closed vocabulary project | retail,
`app/services/scm/demand_class.py:31-40`, resolved by the ladder :84-139). Prod 2026, cancelled
excluded: retail 30,571, project 5,210, null 170
(`chatbot-sales-report-acceptance-criteria.md:57`). "PROJECT TEAM" may instead mean a group of
people (the footnote "whole project team sales 16pax"); #1260 S6 adds sales teams. G4.

**HANLIM.** A customer, not an agent or a brand: `HANLIM TRADING SDN BHD` with 6 ledgers, 1,230
SOs over 37 months, all retail (`chatbot-sales-report-acceptance-criteria.md:60`). Shown apart
from the agents in report B.

**DILOOMA, PINTAR.** DILOOMA appears as a customer in chatbot replay fixtures only; PINTAR has no
hit anywhere in the repo. Both are named project debtors in report C (Mocha), so they are Mocha
customers and cannot be checked until Mocha's customers and SOs are in the CRM.

**Mocha.** Both a company and a brand:
- Company `MOCHA` (`app/models/company.py:28`, code SRT / MCH comment; plan
  `documentation/plans/inventory/PLAN-company-so-feed-flag.md:17` lists `MOCHA` / Mocha and `SRT` /
  Sorento), "a second AutoCount company" (`alembic/versions/512_integration_ref_company.py:6`), db2
  in `documentation/plans/autocount/PLAN-autocount-brands-ingest.md:13,24`.
- Brand prefix `M` inside Sorento (`product_class_signal.py:33`); "Cabana and Mocha are brands
  INSIDE the Sorento company" (`alembic/versions/371_brand_member_routing.py:4`).
- **Mocha has no sales orders in the CRM**: "its AutoCount SO feed is not connected"
  (`PLAN-company-so-feed-flag.md:10-12`), and `companies.so_feed_live` is false for Mocha
  (`app/models/company.py:31`, migration flips `code = 'MOCHA'`, plan :39).
- Report C's agents (CHONG, CHUA, JASMINE, JIMMY, KENT, SHIRLEY, SMT, TEO JM) overlap report B's
  (CHONG TECK HIN, TEO JIAN MING, KENT TEH), which fits the shared agent master ("the captain's own
  files show the same agents selling for both companies", `sales_agent.py:66-67`). So report C is
  **Mocha the company** (AutoCount db2), not the M brand inside Sorento. G2 confirms.

**History depth.** 149,383 SOs in total (`chatbot-sales-report-acceptance-criteria.md:53`); source
split autocount 75,600, scm_upload 10,730, scm_so_history 950, scm_order_inquiry 12
(`documentation/plans/scm/PLAN-scm-oi-sheet-migration.md:35`); HANLIM's 1,230 SOs span 37 months,
so Sorento SO history reaches back to about August 2023. The retired six-year history importer
(`scm_so_history`, `tests/test_ingest_parity_s4_contract.py:316-318`) means some pre-feed SOs came
from a one-off export, so **completeness per year is not known**. No explicit cutoff exists in the
ingest code.

**Not reachable from this checkout.** CI's database holds no data (LESSONS-LEARNT: "CI's database
has NO data"), and the PDF totals are on the owner's drive. So the gap between SO figures and the
PDF totals cannot be measured here. S0 measures it on the prod copy before the grill closes.

## 3. Dimension map

| Report dimension | Source | State |
|---|---|---|
| Sales amount RM | `sales_order_lines.line_total` (ordered) or the confirmed value (`_per_line_exprs`) | present; basis is G1 |
| Month, quarter, year | `sales_orders.order_date` (document date) proposed; the sales report uses `COALESCE(required_date, order_date)` | present; G1 |
| As-at date | a parameter; lines with `order_date <= as_at` | present |
| Company (Sorento, Mocha) | `sales_orders.company_id` -> `companies` | Sorento present; **Mocha has no SOs** (S4) |
| Dealer vs project team | `sales_orders.demand_class` retail / project | present (170 nulls in 2026); G4 |
| Sales agent (person) | `sales_orders.sales_agent_id` -> `COALESCE(person_label, sales_agent)` | codes present; **person labels 0 of 80** (S2 backfill) |
| Debtor type (ACCOUNT I..IV; SORENTO..SAMPLE) | proposed new `customers.debtor_type` from AutoCount `Debtor.DebtorType` | **missing** (dropped on ingest); S0 + G3 + S3 |
| Product brand (SRT, BRT, CB, M, IB) | `product_categories.category_code` prefix, or `products.brand_id` | present; offered as a second axis |
| HANLIM row | the HANLIM ledgers (customer ids) set apart | present (6 ledgers) |
| DILOOMA, PINTAR | Mocha customers, excluded or listed by id | Mocha customers not in the CRM yet |
| Footnotes ("Nov'24 ... 16pax") | typed by a person | **nowhere to store**; G8 |

## 4. Basis: sales orders, not invoices

The PDFs look like AutoCount invoiced sales (a weekly "Sales by Debtor Type" is an AR-side
report). The CRM can reproduce:

- **Ordered**: every non-cancelled SO line, as soon as the order exists (`line_total`).
- **Delivered (confirmed)**: the part of each line transferred to DO (`confirmed_value`).
- **Not invoiced**: no invoice table, no IV feed. The closest proxy for invoiced is delivered, but
  the CRM has no delivery date (`qty_delivered` is a running figure AutoCount overwrites,
  `document_ingest_service.py:243`), so delivered can only be filed under the order's own month.

Where SO figures and invoice figures will differ: orders not yet delivered (ordered basis
overstates), deliveries of older orders (filed under the order month), credit notes and returns
(not in the CRM at all), invoices raised without an SO (cash sales, not in the CRM), and the date
used (order date vs invoice date).

Proposal: build on SOs with the basis printed on every screen, export and chatbot header, measure
the gap in S0 on three months against the PDF totals, and name the trigger for an invoice feed:
**if S0 shows a monthly gap above the tolerance the owner sets in G1, an AutoCount IV (invoice)
ingest lane is planned (cross-repo ESB work plus one `sales_invoices` table), and the reports gain
an `invoiced` basis on the same query layer.** Not built before that.

## 5. Design: one query layer

**One new service function, one new route, three layout functions, one xlsx writer, one MCP
tool, one migration column (S3). No registry, no rule engine, no new table.**

### 5.1 The primitive: `sales_grid`

New module `app/services/sales_analysis_service.py`, next to the sales report, importing
`_per_line_exprs` and `_common_filters` from `sales_report_service` so the money and the
exclusions are the sales report's own.

```python
def sales_grid(
    db, *,
    rows: str,                      # one axis, required
    cols: str | None,               # one axis or None (a single column "Total")
    basis: str,                     # "ordered" | "delivered", required
    date_from: date, date_to: date, # required, inclusive, on sales_orders.order_date (G1)
    company_id: str,                # required; one company per grid
    channel: str | None = None,     # "dealer" | "project"
    sales_agent_ids: list[str] | None = None,  # already widened to the person's codes
    customer_ids: list[str] | None = None,
    exclude_customer_ids: list[str] | None = None,
    set_apart_customer_ids: list[str] | None = None,  # their sales leave the agent rows
    debtor_types: list[str] | None = None,
) -> ReportPivotLayout
```

Axes (a closed set, one `case` in the function, not a registry): `year`, `quarter`, `month`
(month of year, JAN to DEC, so years line up), `year_month`, `agent` (the person label, else the
code), `agent_code`, `debtor_type`, `channel`, `customer`, `brand` (product category prefix).

- One grouped SQL statement per grid (`GROUP BY rows, cols`), sums of per-line cents (S15 of the
  sales report), totals computed from the grouped rows in Python exactly as `engine._pivot` does
  (`engine.py:560-576`), blanks grouped under `BLANK_VALUE` ("(blank)") and sorted last, never
  dropped, so every grid's grand total equals the unfiltered total.
- Returns the kernel's `ReportPivotLayout` (`app/schemas/report.py:73`), so the frontend renders
  every table with the existing `ReportPivotTable` and the xlsx writer reuses the kernel's cell
  helpers.
- `set_apart_customer_ids` removes those customers' lines from every agent row and returns them
  as one extra row labelled with the group's name (report B's HANLIM row), outside the agent
  subtotal and inside the grand total.
- Company: the grid always names one company. The ORM listener already scopes to the caller's
  granted companies; a `company_id` outside the caller's grant is 403. Not the kernel's
  `scope="company"` arm, which is not fail-closed (`engine.py:310-315`).
- Why not the kernel's engine: `_pivot` binds to one `ReportDefinition` with one period and one
  date basis, and has no set-apart row, no year-over-year axis and no exclusion list. Adding them
  would change a shipped engine for one report family. The shapes are reused, the engine is not.
  Named trigger for folding `sales_grid` into the kernel: a second report family needs
  set-apart rows or year-over-year columns.

### 5.2 Three layouts, composed from grids

`app/services/sales_reports_layout.py`, one function per report, each returning a
`SalesReportDocument`: an ordered list of `sections` (title, one `ReportPivotLayout`, optional
`variance` row, optional `chart` series, optional `note`) plus a header (company name, report
title, period, as-at date, basis).

- **A `yearly_comparison(company, as_at, years=3, basis)`**: per channel (dealer, project), one
  grid `rows=year, cols=month` over 1 Jan of the first year to `as_at`; the variance row is the
  last year minus the one before, per month and total, computed from the grid's cells; the chart
  series are the grid's rows. Months after the as-at month print blank for the current year, not
  zero. G5 decides whether the total variance compares full year or year to date.
- **B `sorento_by_account(as_at, basis, set_apart)`**: for each month from January to the as-at
  month, one grid `rows=agent, cols=debtor_type, channel=dealer?` (G4) with `set_apart` = the
  HANLIM ledgers; then one `rows=agent, cols=debtor_type` over the year to date; then one
  `rows=[dealer salesman, HANLIM], cols=month` (the set-apart split as rows).
- **C `mocha_by_account(as_at, basis, named_debtors)`**: `rows=agent, cols=debtor_type` per month;
  per debtor type one `rows=agent, cols=month`; `rows=agent, cols=month`; `rows=debtor_type,
  cols=month`; `rows=customer, cols=month` limited to the named debtors (DILOOMA, PINTAR);
  `rows=agent, cols=quarter` plus a closing row "Total sales without Dilooma and Pintar
  (project)" from the same grid with `exclude_customer_ids` = the named debtors.

The HANLIM set and the named project debtors are **parameters**, not hard-coded names. Their
defaults are stored as a saved view of the report (`views_service.py`, the kernel's own saved
views), so no table is added for them. G7.

### 5.3 Routes

On `sales_report_router` (`app/api/v1/order_management/orders.py:1580`), permission
`order_management.sales_reports.view` (new slug, `app/rbac/permission_registry.py`), plus the
`sales_orders.sales_report` reveal key re-check for API-key callers exactly as the sales report
does (:1713-1726):

- `GET /api/v1/order-management/sales-analysis`: one `sales_grid` call, every parameter in 5.1 as
  query params, plus `n` (1 to 100) that cuts ranked rows **after** `total_count` and totals are
  taken (PR #1263's rule). This is the chatbot's route.
- `GET /api/v1/order-management/sales-reports/{key}`: `key` in `yearly-comparison`,
  `sorento-by-account`, `mocha-by-account`; params `as_at`, `basis`, `company` (A only), plus the
  saved view id. Returns the `SalesReportDocument`.
- `GET /api/v1/order-management/sales-reports/{key}/export`: the same document rendered to
  `.xlsx`, streamed. A sync download: the largest workbook (C) is under 2,000 cells. Named
  trigger for the kernel's RQ export path: an export over the sync timeout on the prod copy.

422 on an unknown axis, `rows == cols`, `date_from > date_to`, a missing basis, more than 50 ids
in a list, or an unknown key; 403 on a company outside the caller's grant.

### 5.4 Screens, Excel and charts

- Menu: Sales > Reports > Yearly comparison, Sorento by account, Mocha by account
  (`config/menu.config.tsx` SALES heading :78; the #1260 Sales group), each gated on
  `order_management.sales_reports.view`. Mocha by account is hidden while Mocha has no SO feed
  (`companies.so_feed_live`), not shown empty.
- One page component `SalesReportPage` renders a `SalesReportDocument`: `PageHeader` with the
  title, a filter row (as-at date, basis, company for A, saved view), Export to Excel as the one
  primary action, then each section as a card holding a `ReportPivotTable`. A: a recharts
  `LineChart` under each block (one line per year, months on x, the current year solid and the
  earlier years in the palette's secondary tokens). B and C: line tabs per group of sections
  (Monthly, Year to date, Dealer vs HANLIM for B; By account, By debtor type, By month, Project
  debtors, By quarter for C), tab strips scrolling at 375.
- Numbers right aligned, tabular, negatives in brackets `(12,345.00)` as the PDF prints them,
  blank for no sales, `(blank)` group last. At 375 each grid scrolls sideways inside its card
  with the first column sticky.
- Excel: one sheet per report, sections stacked in the PDF's order, the kernel's title block
  (company, report title, as-at date), header bold, number format `#,##0.00;(#,##0.00)`, totals as
  **values, never formulas** (kernel docstring `xlsx_renderer.py:14-16`), report A with a native
  openpyxl `LineChart` under each block. Every text cell passes a formula-injection guard (the
  pattern of `summary_order_service._xlsx_safe_text`, `app/services/scm/summary_order_service.py:1491`).
- The basis and the "sales orders, not invoices" line print in the header of every page and sheet.
- Empty state: a section with no sales prints its table with blanks and a "No sales in this
  period" line, never a missing section.

### 5.5 The chatbot seam

- **MCP tool** `crm_sales_analysis` (new `ToolSpec`, `sorento_crm_mcp/sorento_crm_mcp/catalog.py:15`
  shape) over `GET /sales-analysis`: domain orders, the `sales_orders.sales_report` reveal key (no
  new key), no paging params, `related_tools=("crm_sales_report", "crm_top_selling_report")`.
  Added to `PRESENTER_TOOLS` (`presenters.py:38`), `CHATBOT_READ_ONLY_TOOLS`
  (`app/services/chatbot/lanes/business/fetch.py:965`), `mcp_tool_domains` and the order domain
  seed in `app/services/chatbot/turn/policy_rows.py` (as PR #1263 did, with one migration that
  updates the live `chatbot_domains` row).
- **Parser** (`app/services/chatbot_parser_prompt.py`): `group_by` already exists (:83-98); it
  gains the values `agent`, `debtor_type`, `brand`, `month`, `quarter`, `year`. New nullable keys:
  `compare_years` (a list of years), `exclude_customers` (names, resolved by the entity resolver
  like any customer), `sales_basis` (ordered | delivered | unclear). The `sales_agent` entity kind
  and the `company` word come from the top X lane (#1175 S5) and the multi-company reply clarity
  work.
- **Person resolution**: "Sean" resolves to every code whose `person_label` is SEAN; with no label
  and more than one code starting with SEAN, the bot asks which ("SEAN I or SEAN III?"), never
  sums them silently.
- **Clarify, never assume** (owner rulings 26 Sep, carried from #1175): before any fetch, in this
  order, the lane asks:
  1. the company, when the contact is granted both and did not name one (`Sorento or Mocha?`);
  2. the period, when none was said (G6);
  3. the basis, when the message is ambiguous between ordered and delivered (G1 decides the
     default when it is simply unsaid; the header always prints it);
  4. the axis, when "by brand" could mean the debtor type column or the product brand (G3).
- **Counts and length**: every reply header states the full row count ("Agents with sales: 14").
  A grid that fits one WhatsApp message (the top X setting `chatbot_top_selling_one_message_rows`,
  default 50, reused rather than a second setting) is sent in full. A longer one with no N gets the
  header and "That list is too long for one message. How many agents do you want to see?". Never
  "more", "next" or "lagi".
- **Dealer contacts**: this tool is staff only. A contact linked to a customer
  (`respond_contact_customers`) gets "Sorry, I can only share sales figures for your own account."
  and nothing is fetched, because every answer here compares agents or accounts.
- Reply shapes (goldens, S1 to S5) are drawn in the mockup, frame 6.

### 5.6 Access

- Screens: new slug `order_management.sales_reports.view` (covers export). Grant sweep in the
  migration of S1 to the roles that hold `order_management.orders.view` today and are named by the
  owner (DoD). `security-reviewer` runs on S1 (new slug, company parameter) and S3 (ingest field).
- Chatbot: the existing `sales_orders.sales_report` reveal key, staff only (5.5).

## 6. Slices (thin, vertical, ordered for early owner value)

Each slice is its own lane and PR. Every lane is full track (PRINCIPLES.md "Small fix track" does
not apply: new slug, migration, ingest or chatbot tool), Phase 1 frontend mock first, Phase 2
tester-first, Phase 3 reviewer plus browser at 1280 and 375.

### S0. Measure (captain, read-only SQL on the prod copy; no code, no PR)

Paste into the UAC "Measured" before the grill closes:
- SOs and `SUM(line_total)` per month by company, January 2023 to September 2026, cancelled
  excluded: where does complete history start?
- For three months the owner picks: dealer and project totals on both bases and both date rules
  (order date vs delivery bucket) against the PDF's own totals; the gap in RM and percent.
- The raw `Debtor.DebtorType` values in the masters push payloads (`integration_log` rows of the
  customers push) with counts, and how many are dropped as `segment_unknown`.
- `sales_agents`: codes per company, `person_label` fill (expected 0), codes with no SO in 2026.
- HANLIM's 6 ledger customer ids; Mocha SO count (expected 0) and `so_feed_live`.
- `EXPLAIN ANALYZE` of a three-year `rows=year, cols=month` grid: the trigger for an
  `order_date` index is over one second.

### S1. Report A, yearly comparison (dealer and project), screen, chart, Excel, chatbot compare

- Backend: `sales_grid` with the axes `year`, `month`, `year_month`, `channel`; `GET
  /sales-analysis`; `yearly_comparison` layout; `GET /sales-reports/yearly-comparison` and
  `/export`; new slug and grant sweep migration.
- Frontend: Phase 1 mock of `SalesReportPage` for A with both blocks, variance row and the two
  charts, menu entry, export button, 375 and 1280; then wired.
- Chatbot: `crm_sales_analysis` ToolSpec (axes of S1 only), presenter goldens for "compare dealer
  sales 2025 vs 2026 by month" and "total project sales this year", parser keys `compare_years`
  and `group_by` month / year, the company and period clarify lines.
- Tests: pytest `tests/test_sales_grid.py` (sums equal `sales_report`'s ordered and confirmed
  figures for the same window to the cent; cancelled excluded; month and year buckets on
  `order_date`; null `demand_class` lands in `(blank)` and in the total; company scope 403 and
  isolation between two companies; variance math and brackets); route tests (401, 403 without the
  slug, API key without the reveal key 403, 422 table); xlsx test (cell positions, values not
  formulas, number format, the chart object present); vitest for `SalesReportPage` (sections,
  empty state, blank future months, export call); MCP catalog and presenter tests with goldens;
  chatbot lane tests for the clarify lines and the no-paging rule; agent-browser evidence via the
  sidebar at 1280 and 375.
- DoD: figures for three months reconcile with S0's measured totals on the prod copy; the owner
  reads report A beside the PDF.

### S2. Sales by agent as a person (report B without the account columns)

- Backend: axes `agent`, `agent_code`, `customer`; `set_apart_customer_ids`; person resolution
  (`COALESCE(person_label, sales_agent)`, one person = every code sharing the label, #1260 R2);
  `sorento_by_account` layout with only the TOTAL column (debtor type columns land in S3), the
  HANLIM row, TOTAL SALES, the year-to-date table and the DEALER - SALESMAN vs HANLIM month table.
- Frontend: report B page with the Monthly, Year to date and Dealer vs HANLIM tabs; the HANLIM set
  as a saved view parameter (a `SearchableMultiSelect` of customers).
- Chatbot: "Sean's sales this month", "sales by agent this year", "top 5 agents this year" (N
  named: cut after the count), the which-code clarify.
- Tests: person grouping (two codes one label; no label falls back to the code; an SO with no agent
  lands in `(blank)` and in the total), set-apart (HANLIM leaves every agent row, appears once,
  grand total unchanged), presenter goldens, the how-many golden for a long list with no N.
- DoD (backfill): every active Sorento code has a `person_label`, entered by the owner or the
  captain on the Sales Agents screen from the owner's own agent list (the report B rows); the
  count is pasted in the PR.

### S3. Debtor type (the account columns), report B complete, chatbot "by account"

- Backend: migration adds `customers.debtor_type` varchar(50) null; the masters push and the
  document back-create write AutoCount `Debtor.DebtorType` raw into it on every push (AutoCount
  owns it; the existing fold onto `market_segment_code` is unchanged); the column reaches both
  customer dict builders and the customer schemas (LESSONS-LEARNT: both manual builders); axis
  `debtor_type` and filter `debtor_types`; report B gains its SORENTO .. SAMPLE columns in the
  owner's order (G3).
- Frontend: report B's columns; the customer detail shows the debtor type read-only in the header
  (AutoCount owns it).
- Chatbot: "Sean's sales this month by brand" (by debtor type, or the product brand axis, per G3),
  "HANLIM by account this year".
- Tests: ingest writes the raw value on insert and on update, an unknown value is still stored
  (no fold), the segment fold is unchanged; grid by debtor type; `(blank)` for customers with none.
- DoD (backfill): a full customers masters re-push from AutoCount (ESB side) fills
  `debtor_type`; the fill rate per company is pasted in the PR. `security-reviewer`: yes (ingest).

### S4. Mocha sales order feed (dependency, mostly outside this repo)

- The AutoCount ESB pushes db2 (Mocha) SOs through the existing `POST /external/ingest/sales_orders`
  with Mocha's company code (`app/api/v1/external/company_anchor.py:39,135-174`). CRM side: verify
  the push lands under Mocha, flip `so_feed_live` for Mocha, and measure history depth (S0 rows).
- Tests: an ingest test that a Mocha-coded SO lands under Mocha and is invisible to a Sorento-only
  user. Nothing else changes in the CRM.
- DoD: Mocha SO count and first month pasted; the owner confirms three months against the PDF.

### S5. Report C, Mocha by account, quarter and named project debtors

- Backend: axis `quarter`; `exclude_customer_ids`; `mocha_by_account` layout; the named debtors as
  a saved view parameter.
- Frontend: report C with its five tabs; the "Total sales without Dilooma and Pintar (project)"
  row.
- Chatbot: "Mocha Q2 by agent without Dilooma", "Mocha ACCOUNT II by month".
- Tests: quarter buckets; exclusion leaves count and totals consistent (the excluded customers are
  named in the header); report C sections sum to each other.
- DoD: the owner reads report C beside the PDF.

### After S5 (only on a ruling)

- Weekly delivery of report B (the PDF is "produced weekly"): G9.
- Footnotes: G8.

## 7. What is not built, and the trigger for each

- **An invoice (IV) feed and an invoiced basis**: S0 gap above the G1 tolerance.
- **Folding `sales_grid` into the reports kernel**: a second report family needs set-apart rows or
  year-over-year columns.
- **Moving the routes under a `sales` module key**: #1260's `sales` module lands.
- **An `order_date` index**: the S0 `EXPLAIN ANALYZE` of the three-year grid is over one second.
- **The RQ export path**: an export over the sync timeout on the prod copy.
- **A quantity measure**: an owner ask; quantities across debtor types and brands mix basins with
  screws, so the reports are RM only.
- **Dated person labels** (a code that moves between people mid-year): an owner ask.

## 8. Risks

- **SO is not invoice.** The owner may read a mismatch as a bug. Mitigated by the basis line on
  every output, S0's measured gap, and G1's tolerance.
- **Debtor type source unproven.** If AutoCount's DebtorType is Trade / Cash / Local for Sorento,
  the account columns need another source (the ledger name suffix, or a mapping per customer set by
  hand). S0 and G3 decide before S3 starts.
- **Person labels are manual.** Report B is only as right as the 80 labels; a missing label shows
  the raw code as its own row, never a merged guess.
- **Mocha is blocked on an external feed.** S4 depends on the ESB team; S5 cannot start before it.
- **Null `demand_class`** (170 SOs in 2026): shown as `(blank)` in report A so the totals still
  reconcile, never dropped.
- **Tax inclusive amounts.** `line_total` is Total (Inc); the PDFs may be ex-tax. S0 measures,
  G1 decides.

## 9. Grill questions (posted on the PR, at most 10)

- **G1. Basis and date.** The CRM has sales orders, not invoices. Options: (a) ordered amount by
  order date; (b) delivered (transferred to DO) amount by order date; (c) either, chosen on the
  screen, with a default; (d) wait for an AutoCount invoice feed. Also: what gap against your PDF
  totals is acceptable before we build (d)? **Recommend (c) with delivered as the default** (the
  top X ruling: "selling" means delivered), printed on every header, and (d) only if S0 shows a
  monthly gap above 2 percent.
- **G2. Is "Mocha" in report C the Mocha company (AutoCount db2) or the Mocha brand inside
  Sorento?** Options: company; brand; both. **Recommend company** (report C's agents and debtor
  types are a separate ledger), which makes S4 (connecting Mocha's SO feed) a prerequisite.
- **G3. Where do the account columns come from?** Options: (a) AutoCount `Debtor.DebtorType`,
  stored raw on the customer; (b) the ledger suffix in the customer name (`[A/C I]`, `(PROJECT)`);
  (c) a mapping you maintain per customer in the CRM; (d) for SORENTO / BRAVAT / CABANA, the
  product brand on each line instead of the customer. **Recommend (a)**, confirmed by S0's raw
  values, with (d) kept as a separate "by product brand" axis for the chatbot.
- **G4. "DEALER" and "PROJECT TEAM" in report A.** Options: (a) the sales order's dealer / project
  class (`demand_class`); (b) the agents in a "Project team" sales team (#1260 S6); (c) the
  customer's debtor type PROJECT. **Recommend (a)**, the classification every other sales answer
  already uses. Does report B's per-agent table include project orders or dealer only?
- **G5. The variance row as at a date.** Options: (a) total variance = current year to date minus
  the prior year's same months; (b) minus the prior full year; months after the as-at date blank
  either way. **Recommend (a)**, so a September report does not show a large negative that is only
  "October to December not happened yet".
- **G6. Chatbot period when none is said.** Options: (a) ask ("This month, this year, or a
  range?"); (b) the current calendar year, printed in the header (the top X ruling). **Recommend
  (b)**, since it is stated rather than silent, and ask only when the words are ambiguous ("last
  quarter" at the start of a year).
- **G7. HANLIM and the named project debtors.** Options: (a) a customer list stored with the report
  (a saved view), editable by admins; (b) hard-coded names; (c) a "set apart" flag on the customer.
  **Recommend (a)**. Are there other customers you set apart like HANLIM?
- **G8. Footnotes such as "*Nov'24 whole project team sales 16pax".** Options: (a) not carried;
  (b) a free-text note per report, company and month, typed on the screen and printed in the
  export; (c) typed into the Excel after export. **Recommend (c) for now**, (b) when you want the
  notes kept in the CRM.
- **G9. "Produced weekly".** Options: (a) on demand only (open the screen, export); (b) a weekly
  scheduled Excel sent to named people by email or WhatsApp. **Recommend (a) first**, (b) as its
  own slice after S5, reusing the per-recipient schedule #1260 S5 builds.
- **G10. Who may see these reports.** Options: (a) a new "sales reports: view" permission, granted
  by role, and on WhatsApp staff only with the existing Sales report grant; (b) sales agents see
  only their own rows. **Recommend (a)**; (b) when agents are given access.

## 10. Out of scope

A report designer, a dashboard of KPIs, a quantity measure, targets and commissions (#1260), an
invoice feed (named trigger, section 7), a scheduled send (G9), footnote storage (G8), and any
change to the existing sales report or top X answers.
