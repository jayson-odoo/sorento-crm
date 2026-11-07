# CARD: SALES-INSIGHTS-P2 (leaderboard phase 2: drilldown, perspectives, targets, customisable)

Status: Asked (crew-ask on PR #2231, 7 Nov, comment 6705350934). Evidence round 1 back (comment 6705369461), mockup
drawn on it; round 2 (comment 6705387753, #2230 counted-line flags) returns identical figures; round 3 (6705556179) gives Channel and the other bases. Build waits for the owner. Track: full (size L). Figures depend on SALES-SUBTOTAL-LINES (#2230).
Plan: `PLAN-sales-insights-p2-07nov.md`. Evidence: `evidence/sales-insights-p2-oct-dev.sql`.
Mockup: `mockups/sales-insights-p2-07nov.html` (real October figures; panels "Self-service" and "Components reused" answer the owner's two mockup questions).

## The ask in one line

Owner 7 Nov ~17:45: from the leaderboard, see each sales person's customers and items; see the same sales from the
customer side and the product side ("maybe merge with top selling product"); compare with target; let users customise
by reusing the reporting tooling we already have.

## What already exists (measured; paths under `sorento_crm_backend/app/` unless marked FE = `sorento_crm_frontend/`)

- **The board (#2227).** `services/sales/leaderboard_service.py:80-172`: two `ask.run_ask` calls (invoiced,
  `group_by="sales_person"`, period and previous window), ranked by person; route `api/v1/sales/leaderboard.py:202-224`.
  FE `app/(protected)/sales/leaderboard/components/LeaderboardView.tsx` (StatCard KPIs, podium, DataGrid).
- **The one engine already groups every way the owner asked.** `services/reports/ask.py:36` dimensions `customer,
  product, brand, category, sales_agent, month, year` (+ `sales_person` on invoiced, :56); filters `customer, product,
  brand, category, sales_agent, customer_agent` (:37). Each ranked row carries `keys` (the ids behind the name, :400-410),
  so a clicked row can become a filter. **Missing: a `sales_person` FILTER** (only a dimension today); a drill by
  agent ids would miss a code AutoCount sent that is not a CRM agent (`invoiced_sales.py:134-151`, the person label
  falls back to the code as sent). One `SelectParam` on `datasets/billing_document_lines.py:239-251` over
  `inv.person_label()`.
- **Top selling items** is not its own screen: FE `app/(protected)/sales/top-selling-items/page.tsx:10-18` renders
  the generic `components/reports/ReportPage.tsx` with `reportKey="top_selling_items"`
  (`services/reports/definitions/top_selling_items.py:51-120`): same billing-lines dataset and basis as the board, rows =
  item, cols = year, export to Excel, saved views. It cannot disagree with the board (same `_base`,
  `datasets/billing_document_lines.py:40-53`).
- **Sales & outstanding** (FE `app/(protected)/sales/sales-and-outstanding/SalesAndOutstandingView.tsx:17-29`): the same
  `ReportPage`, Invoiced tab = `sales_invoiced_ask`, the very definition `run_ask` reads. "Rows" picker
  (FE `components/reports/ConfigureSummaryDialog.tsx:128`): item, customer, product, brand, category, sales agent,
  channel, month, year, account type. `sales_person` is hidden there (`billing_document_lines.py:203`).
- **The customisation we have: report saved views.** Table `report_views` (`models/report_view.py:21-48`: JSONB
  params + columns + pivot, `is_shared`, one `is_default` per report), `services/reports/views_service.py`, FE
  `components/reports/ReportViewsMenu.tsx`. Plus the sidebar star (`user_quick_access`, `models/user.py:836`; FE
  `app/components/layouts/demo1/components/menu-item-pin-button.tsx`).
- **No dashboard-widget module exists.** The home page hard-codes two SLA widgets (FE `app/(protected)/(home)/page.tsx`);
  no widget table, no per-user layout, no "pin a view to a dashboard". "Reuse our dashboarding tool" therefore means
  the report saved views + the sidebar star; a widget dashboard would be new machinery.
- **ReportSpec (#2229, draft, docs only, owner "2229 ok").** A chatbot query contract (`basis, period, frame, group_by,
  top_n, sort, measure, filters{axis: values}`) over the same `ask.CATALOGUE` / `run_ask`. Not a saved-report model.
- **Targets.** `models/sales.py:331-465`: subject agent / team / dealer, `metric` amount | quantity, `basis` ordered |
  delivered | **invoiced** (exists, `alembic/versions/tinv_0001_target_invoiced_basis.py`; Targets screen "Counts"
  select), any date range split into periods (`split_every` + `split_unit`). Achieved is computed on read
  (`services/sales/achievement_service.py:242` `achieved_by_period`, invoiced via `_achieved_invoiced` :641,
  credits a PERSON through `label_siblings` :123). Dev (crew, #2227): only TGT-000002..4 (FANNY I/III/IV), yearly
  2026, ordered, cover October.
- **Commission lives next door and must stay out.** `target_commission_tiers`, `target_tier_rates`, the header's
  commission columns; `target_service.period_progress` (:2300) already returns tier rates (`_rung_out` :2280-2290), so
  the board must NOT call it; it reads `target_periods.target_value` + `achievement_service.achieved_by_period` only.
- **Scope.** A salesperson is user -> contact -> agents (`services/own_scope.py:98-114`); no "own customers" rule on
  reports today: anyone with `sales.reports.view` sees every customer and item in Sales & outstanding.

## Behaviour, with a recommendation each

| # | Topic | Recommendation |
|---|---|---|
| 1 | One engine, perspectives | The board gains a **View by** switch: Sales person (today) / Customer / Product / Brand / Category. Every view is the same call, `run_ask(invoiced, group_by=<view>, filters, compare previous window)`; the route grows a `by` param. Same KPI row, same period chips, same filters, same "vs last period" and "Customers" columns (Product view also Qty). Podium only on Sales person. |
| 2 | Drilldown | A row click adds that row as a **filter chip** and moves to the next view: person -> Customers (tab Items beside it); customer -> Items (tab Sales persons); product / brand / category -> Customers (tab Sales persons). The chip ("Sales person: LCL x") is the way back; the URL holds view + chips + period, so browser Back and a shared link work. Same period and filters throughout. Needs the `sales_person` filter word (1 SelectParam) and nothing else. |
| 3 | Top selling | **Link both ways, do not merge.** Top selling items is the configurable report (year columns, Excel export, saved views, debtor type); the board's Product view is the ranked "who moved" view. Product view shows "Open in Top selling items" (same period / brand / category); Top selling items gets "Product ranking" back to the board. Merging would mean rebuilding export + year compare + saved views on the board (a second report engine) or deleting them. |
| 4 | Target | Person view only: a **Target** column that is honest about what it compares: "72% of 2026, ordered" = the person's all-products AMOUNT agent target whose period holds the board's end date, achieved % from `achievement_service` (the Targets screen's own figure, its own basis and period, not the board's RM). Blank when none; a tooltip / 375px second line gives target RM and achieved RM. When the target is invoiced and its period equals the board's window (a monthly invoiced target on a month chip) it reads like for like and drops the label. **Invoiced targets need no code**: the basis exists; the owner creates monthly invoiced agent targets on the Targets screen (split every 1 month). |
| 5 | Customise | **Reuse report saved views, build no dashboard.** Each view has **Open as report**: Sales & outstanding, Invoiced tab, seeded with rows = the view, the chips as filters, the period. There the user changes columns / grouping, saves a view (`report_views`: mine, shared, default) and stars the page in the sidebar. Needs: `ReportPage` reads a one-shot seed from the URL; `sales_person` visible in its Rows picker and filter. Dashboard widgets: trigger = owner asks for a home dashboard. |
| 6 | Assistant (ReportSpec) | The board's query IS a ReportSpec: `{basis: invoiced, period, group_by: by, filters: {sales_person, customer, product, brand, category}, top_n, compare: previous_period}`. `crm_report_ask` gains the `sales_person` filter word (route allow-list + MCP description), so "LCL's top customers last month" answers with the board's numbers. No new tool. |
| 7 | Who sees what | The person board stays as ruled on #2227 (everyone with `sales.leaderboard.view`). Customer / Product / Brand / Category views and drilling into ANOTHER person need `sales.reports.view` (the slug that already shows all of it in Sales & outstanding); without it a user drills only into their own row. No new slug. Never commission: the response has no commission field; a test asserts it. |
| 8 | Mobile (375px) | Switch becomes a SearchableSelect; chips wrap; grid keeps Rank, Name, RM; change, customers and target move to a second line. |

## Mapping: mock element -> existing component (FE paths)

| Mock element | Reuses |
|---|---|
| Page header, crumbs | `components/common/PageHeader.tsx` |
| Period chips + custom range | the board's own chips + `components/ui/date-range-picker.tsx` (`LeaderboardView.tsx`) |
| View by switch | `components/ui/tabs.tsx` (`TabsList variant="line"`), state in URL via `hooks/useUrlTab.ts` |
| Filter chips (drill trail) | `components/ui/badge.tsx` with a clear icon button |
| Company / brand / category filters | `components/common/SearchableSelect.tsx`, `SearchableMultiSelect.tsx` (as today) |
| KPI row | `components/scm/StatCard.tsx` |
| Podium (person view) | `app/(protected)/sales/leaderboard/components/LeaderboardPodium.tsx` |
| Ranked grid | `components/ui/data-grid.tsx` + `data-grid-table.tsx` (`onRowClick` for drill) |
| Target cell | `components/ui/badge.tsx` (basis label) + tooltip |
| Open as report | `components/reports/ReportPage.tsx` via `/sales/sales-and-outstanding` (Invoiced) + `ReportViewsMenu.tsx` |
| Open in Top selling items | `/sales/top-selling-items` (`ReportPage`, `top_selling_items`) |
| Pin | `app/components/layouts/demo1/components/menu-item-pin-button.tsx` (existing sidebar star) |

## What the evidence changed (round 1, dev copy `sorento_prod_1104`)

- **No agent target has an amount.** The 3 agent targets (TGT-000002..4, FANNY I / III / IV, ordered, 2026) and the one
  team target ("Test") are RM 0.00. The only targets with values are **164 dealer targets** (ordered; yearly or
  quarterly). So a person Target column is blank for every row today. Q3 recommendation now: build the column but hide
  it when no row has a target (as #2227 hides Codes); it lights up when amounts are entered. Dealer targets belong to
  the Customer view if anywhere; round 2 Q7 measures how they map to customers (a dealer target can cover several
  accounts). Round 2 Q7: 157 dealer target periods hold 31 Oct; 95 of them cover 2-3 accounts, 210 customers in all,
  only 9 of October's top 50 customers. A dealer target is a group of accounts, not a customer, so no dealer-target
  column on the Customer view in this lane. Trigger: the owner asks to see dealer targets on the board.
- **Customisation is barely used.** One saved report view in the whole system (`sponsorship`), zero sidebar pins on
  `/sales/*`. More reason to reuse saved views (Q4 a) than to build a dashboard.
- **Drill tells a story the board cannot.** LCL's #1 (RM 1,856,856.61) is 24 customers / 684 items, but one customer
  (304-R015) is RM 845,188.21 and three ACCOUNT category items (AC-EXP-006 / -027 / -022, no brand) are
  RM 1,123,963.15 of it; AC-EXP-006 alone RM 735,826.08 to that one customer. ACCOUNT is RM 1,135,248.96 of October
  overall. Round 2 Q8: the three items are "FOR ACCOUNT DEPARTMENT ONLY (DISBURSEMENT)" (213 Oct lines),
  "(REIMBURSEMENT)" (80) and "(OTHERS)" (12). **Finding for the owner, outside this lane:** disbursements and
  reimbursements look like pass-through charges, yet they sit inside the one sales number (SALES-UNIFIED: every
  posted IV + CS + DN - CN line), so they lift LCL to #1 on the board, Targets and the assistant alike. Excluding
  them is a change to the shared definition (its own lane, every reader inherits it), not a board filter. This
  lane ranks them like any item until the owner rules.
- **Customer view.** 1,075 customers invoiced in October; the top 12 hold 24.1%. 300-O024 bought from 8 sales persons.
- **Brand view.** SORENTO RM 8,880,157.22; "(no brand)" RM 4,328,777.30 (ACCOUNT items and unbranded lines); BRAVAT Sep
  was negative, so its change is blank (the #2227 rule).

## Owner asks after the mockup (7 Nov, Lavish)

Verbatim: "Customter need to show name, and I beed channel like dealer and project filter and view also" and "Also
need look into delivered, ordered, outstanding just like our sales report also". Taken as direction (not questions);
the figures for both come from evidence round 3 (`evidence/sales-insights-p2-round3-dev.sql`: the engine's own
statements compiled from the code, so they are what the screens show).

**Customer name.** Every customer row shows the NAME, the code underneath. Evidence and mockup carry debtor CODES only (crew real-data rule: real names never go on the branch or the PR); the mockup's names are fake placeholders, the app reads the real ones from the database. The engine already groups customers by
name (`datasets/billing_document_lines.py:163` invoiced, `datasets/sales_order_lines_ask.py:150` order bases) and
carries the ids behind each row (`ask._row_keys`); the code is a lookup by those ids. Two customers with one name in
two companies stay one row with both codes (the engine's grouping, as Sales & outstanding).

**Channel (the existing sales type, reused, no new field).**
- Invoiced: `inv.sales_type()` (`services/sales/invoiced_sales.py:306`): Set apart first, else the class of the
  invoice's traced sales orders (Dealer / Project team / Other / Mixed / Sales order type not set / No sales order),
  values and labels `SALES_TYPES` (:57), per-document LATERAL `document_sales_type()` (:330); dataset column
  `channel` (`datasets/billing_document_lines.py:69,171`), filter `channel_condition` (:79, param :249).
- Delivered / Ordered / Undelivered: the sales order's `demand_class` (`datasets/sales_order_lines_ask.py:165`
  column, :121 filter): Dealer / Project team / Other.
- The same `channel` is "Sales type" on Sales by debtor type (`definitions/sales_by_debtor_type.py:98`). Debtor /
  account type (`customers.autocount_debtor_type`) is a different field and stays a Sales & outstanding filter.
- **October, invoiced, by channel** (crew, evidence round 3, dev copy): Dealer RM 9,665,663.40 (59.0%), Project team
  RM 5,532,136.98 (33.8%), No sales order RM 1,136,680.81 (6.9%), Sales order type not set RM 35,322.07 (0.2%); they
  add up to the October total to the cent. Other, Set apart and Mixed had none.
- **How an invoice without a sales order gets a channel: it does not; it is its own bucket.** `sales_type()` traces
  the invoice to sales orders through its lines, the SO number, and the DO lines / number / header
  (`invoiced_sales.py:190` `_traced_sales_order_ids`); a credit or debit note with no trace inherits its invoice's
  (`:250` `_traced_ids`). No trace = "No sales order"; traced orders with no class = "Sales order type not set"
  (`:267`). The Channel filter lists all seven sales types, these two included, so ticking every channel gives the
  total and nothing is hidden. Recommendation: keep both as buckets; no fallback rule (e.g. the customer's usual
  channel), because that would change the one shared sales type every report and the assistant read (its own lane,
  trigger: owner asks). Fixing it at source = give the sales order a Dealer / Project type. Delivered / Ordered /
  Undelivered read the order's own class, so those two buckets do not exist there (an order with no class shows as
  "(none)").
- Both a **filter** (Channel, multi-select, clearable) and a **View by** tab. `run_ask` already has `channel` as
  dimension and filter (`ask.py:36-37`). One fix: `_params` maps filter values through `_CHANNEL_CLASS`
  (`ask.py:290`, `sales_report_delivered.py:54`: dealer / project only), so Other / Set apart / No sales order would
  raise; the lane passes invoiced values through `inv.normalise_sales_types` (422 on an unknown word).

**Basis switch (Invoiced / Delivered / Ordered / Undelivered orders), one engine.** The four Sales & outstanding tabs
(`SalesAndOutstandingView.tsx:17-29`), each `run_ask(basis=...)` (`ask.py:54-99`), so the board, the report and the
assistant agree on every basis. Rank, View by, drill and Open as report (to the matching tab) work on each.
- Needed: the `sales_person` dimension and filter on the three order bases (today invoiced only): one column per
  definition over `SalesAgent.person_label` (the order bases already join `sales_agents`,
  `sales_order_lines_ask.py:46`). Customers / Products count measures already exist there.
- Dates as the report: order bases read the line's required date, else the order date; Delivered counts confirmed
  DO quantity capped at the ordered quantity (the existing rules, `datasets/sales_order_lines_ask.py:139` `_figures`).
- **Undelivered orders is a snapshot**: what is open now. Default = every open line whatever its date (the report's
  no-period reading, `ask.OPEN_BASES`, `report_ask.py:327`); the period chips narrow it to lines due in the period;
  "vs last period" is blank (open orders have no earlier state to compare).
- Pending delivery and Unpaid invoices (the other two report tabs) are not on the board: Unpaid has no product /
  brand / category / channel (`ask.py:86-87`), Pending delivery is per delivery order. Trigger: owner asks.
- Top selling items is invoiced only, so "Open in Top selling items" shows on Invoiced only.
- Target: like for like gets likelier: FANNY's targets are ORDERED, so on the Ordered basis their period and basis
  match (still RM 0.00 today).

**Evidence round 3 (crew, PR #2231 comment 6705556179; mockup frame G).** October, all companies, the engine's own
statements: Invoiced RM 16,369,803.26 (+3.0% vs Sep), Delivered RM 10,797,078.52 (-21.2%), Ordered RM 14,697,054.39
(-10.2%), Undelivered due in October RM 3,899,975.87, Undelivered all open RM 77,309,379.57 (RM 71,768,951.72 of it
Project team). What the switch shows:
- The ranking moves with the basis: LCL #1 invoiced, #5 ordered, #7 delivered; SEAN #1 ordered and delivered. Invoiced
  "No sales order" rose from RM 359,970.26 (Sep) to RM 1,136,680.81 (Oct), consistent with LCL's ACCOUNT disbursement
  item (RM 735,826.08) carrying no sales order; no order basis sees it.
- Undelivered opens on all open lines (the report's own default, `datasets/sales_order_lines_ask.py:223`
  `all_dates_period`), and that view is dominated by long-running project orders (ERIC NG RM 13.9m, JUSTIN RM 11.0m,
  TERA RM 10.9m). Kept as the default so the board equals the Undelivered orders tab; the period chips narrow it.
- A customer row can span companies: the engine groups by name, and 13 of the 21 mockup codes exist in both SRT and
  MCH, so the Company cell lists every company of the row's ids (e.g. "SRT, MCH").

**Permissions per basis** (the existing gates, nothing widened): Invoiced needs `sales.reports.view`
(`invoiced_sales.py:369`); Delivered / Ordered / Undelivered need `order_management.orders.view` (the Sales &
outstanding tabs' own gates, `SalesAndOutstandingView.tsx:11-14`). The Sales person view on any basis stays visible
to `sales.leaderboard.view` holders (the #2227 ruling); every other view, and drilling into another person, needs the
basis slug (Q2). A basis the user may not read is absent from the switch.

## Questions (max 5)

1. Top selling: (a) link both ways, board Product view <-> Top selling items report / (b) merge: Top selling menu
   entry opens the board's Product view. Rec (a).
2. Who drills: (a) perspectives and other people's drilldown need `sales.reports.view`, own row drill for everyone /
   (b) anyone with `sales.leaderboard.view` drills anyone. Rec (a).
3. Target: (a) Target column labelled with the target's own basis + period ("x% of 2026, ordered"), hidden while no
   row has one (today: all agent targets are RM 0.00) / (b) only like-for-like invoiced targets / (c) no target column
   until agent targets carry amounts. Rec (a) (updated after evidence round 1).
4. Customise: (a) Open as report into Sales & outstanding + saved views + sidebar star, no dashboard /
   (b) also a home dashboard with pinned views (new widget module). Rec (a).
5. Drill UI: (a) same screen, chip + view switch, URL state / (b) side drawer per row with Customers / Items tabs.
   Rec (a).
