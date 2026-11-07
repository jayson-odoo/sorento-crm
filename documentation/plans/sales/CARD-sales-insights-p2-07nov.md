# CARD: SALES-INSIGHTS-P2 (leaderboard phase 2: drilldown, perspectives, targets, customisable)

Status: Asked (crew-ask on PR #2231, 7 Nov). Evidence SQL sent to crew; the mockup is drawn on its output. Build waits
for the owner's answers. Track: full (size L). Figures depend on SALES-SUBTOTAL-LINES (#2230).
Plan: `PLAN-sales-insights-p2-07nov.md`. Evidence: `evidence/sales-insights-p2-oct-dev.sql`.
Mockup: `mockups/sales-insights-p2-07nov.html` (after the evidence run).

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

## Questions (max 5)

1. Top selling: (a) link both ways, board Product view <-> Top selling items report / (b) merge: Top selling menu
   entry opens the board's Product view. Rec (a).
2. Who drills: (a) perspectives and other people's drilldown need `sales.reports.view`, own row drill for everyone /
   (b) anyone with `sales.leaderboard.view` drills anyone. Rec (a).
3. Target: (a) Target column labelled with the target's own basis + period (FANNY "x% of 2026, ordered") /
   (b) only like-for-like invoiced targets, blank otherwise / (c) no target until invoiced targets exist. Rec (a).
4. Customise: (a) Open as report into Sales & outstanding + saved views + sidebar star, no dashboard /
   (b) also a home dashboard with pinned views (new widget module). Rec (a).
5. Drill UI: (a) same screen, chip + view switch, URL state / (b) side drawer per row with Customers / Items tabs.
   Rec (a).
