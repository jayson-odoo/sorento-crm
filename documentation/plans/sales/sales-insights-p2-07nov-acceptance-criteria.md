# UAC: SALES-INSIGHTS-P2

Status: Agreed, 7 Nov: owner "Ok" on card + mockup v7 (Q1-Q5 all (a), plus customer names, Channel, Basis switch,
self-service option A). Each line names the question or ask it rests on. Contract: the plan's "Contract" section.
Card: `CARD-sales-insights-p2-07nov.md`. Plan: `PLAN-sales-insights-p2-07nov.md`.
Mockup: `mockups/sales-insights-p2-07nov.html`.

Reference case: dev copy `sorento_prod_1104`, October 2026 vs September 2026, counted lines (#2230), crew evidence
rounds 1 and 2 (PR #2231 comments 6705369461, 6705387753). Customers by code.

## P1 One engine, View by (card row 1)
- P1-1 The leaderboard has a View by switch: Sales person (default) / Customer / Product / Brand / Category / Channel. Every view
  is `run_ask(basis=invoiced, group_by=<view>)` with the board's period, compare window and filters; no other sales
  SQL. Test: each view's total equals the Sales person view's total for the same period and filters.
- P1-2 Switching view keeps the period, compare window, company, brand, category and every drill chip.
- P1-3 Reference, October: total RM 16,369,803.26 in every view; Customer view 1,075 customers, #1 304-R015
  RM 845,188.21 (+633.6% vs Sep RM 115,217.76); Product view #1 AC-EXP-006 RM 735,826.08; Brand view #1 SORENTO
  RM 8,880,157.22 (-7.9%); BRAVAT change blank (Sep RM -59,775.00).
- P1-4 Columns: Rank, name, RM, vs last period, Customers (distinct); Product view adds Brand, Category, Qty;
  Customer view shows the customer NAME with its code underneath, and Companies (owner ask); Sales person view as #2227 (+ Target, P4). Podium only on Sales
  person.

## P2 Drilldown (Q5)
- P2-1 Clicking a row adds it as a filter chip and moves view: Sales person -> Customer; Customer -> Product;
  Product / Brand / Category -> Customer. The other views stay one tab away under the same chip.
- P2-2 A chip's x removes it; browser Back returns to the previous view and chips; the URL alone reproduces the view
  (a shared link opens the same view).
- P2-3 Reference: Sales person LCL -> Customer view: RM 1,856,856.61, 24 customers, #1 304-R015 RM 845,188.21, #2
  300-S289 RM 417,103.08; Product view under the same chip: 684 items, #1 AC-EXP-006 RM 735,826.08.
- P2-4 The person chip filters by person label (the new `sales_person` filter word), so a code AutoCount sent that is
  not a CRM agent drills by its code, and a person with several codes (SEAN I / III / IV) drills as one.

## P3 Top selling (Q1)
- P3-1 Product view has "Open in Top selling items" carrying period, brand and category; Top selling items has
  "Product ranking" back to the board's Product view with its period. Both stay; no route is removed.

## P4 Target (Q3)
- P4-1 Sales person view: Target column = the person's all-products amount agent target whose period holds the
  board's end date: "<achieved %> of <period>, <basis>", achieved from `achievement_service` (the Targets screen's
  figure); like for like (invoiced, period = the board's window) shows the % alone.
- P4-2 Blank when the person has no such target or its amount is 0; the column is hidden while no row has a target.
  Reference: October on dev, hidden (FANNY I / III / IV are RM 0.00).
- P4-3 No commission, tier, rate or payout appears in any response (test scans every key).

## P5 Customise (Q4)
- P5-1 Every view has "Open as report": Sales & outstanding, Invoiced tab, rows = the view, chips as filters, the
  period. The report runs at once with them; saving a view there uses the existing saved views.
- P5-2 Sales person is selectable in Sales & outstanding's Rows picker and as a filter.

## P6 Who sees what (Q2)
- P6-1 Everyone with `sales.leaderboard.view` sees the Sales person view on every basis and can drill their own row.
- P6-2 Every other view, drilling another person, and a customer / product drill need the basis slug: Invoiced
  `sales.reports.view`, Delivered / Ordered / Undelivered `order_management.orders.view`. Without it the tabs are
  absent, other rows are not clickable, and the API answers 403.

## P7 Assistant (card row 6)
- P7-1 `crm_report_ask` accepts the `sales_person` filter on the invoiced basis; "LCL's top customers last month"
  returns the board's P2-3 rows.

## P9 Channel (owner ask)
- P9-1 A Channel filter (multi-select, clearable) and a Channel View by tab, on the existing sales type: Invoiced lists
  Dealer / Project team / Other / Set apart / Mixed sales order types / Sales order type not set / No sales order;
  the order bases Dealer / Project team / Other. All ticked = the total.
- P9-2 Reference, Invoiced October: Dealer RM 9,665,663.40, Project team RM 5,532,136.98, No sales order
  RM 1,136,680.81, Sales order type not set RM 35,322.07.

## P10 Basis switch (owner ask)
- P10-1 Invoiced / Delivered / Ordered / Undelivered orders, each the Sales & outstanding tab's own definition through
  `run_ask`; rank, View by, drill, Channel and Open as report work on each.
- P10-2 Undelivered opens on every open line ("All open", the report's default); the period chips narrow it to lines
  due in the period; "vs last period" is blank.
- P10-3 Reference, October all companies: Delivered RM 10,797,078.52 (-21.2%), Ordered RM 14,697,054.39 (-10.2%),
  Undelivered due in October RM 3,899,975.87, all open RM 77,309,379.57.

## P11 Remember the last setup (self-service option A)
- P11-1 Opening the board with no view in the URL restores the user's last basis / view / period / filters in that
  browser; it still renders when the browser refuses storage.

## P8 Layout
- P8-1 Usable at 375px and 1280px; reached from `/` by the sidebar.
