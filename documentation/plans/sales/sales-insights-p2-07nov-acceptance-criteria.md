# UAC: SALES-INSIGHTS-P2

Status: Draft on the card's recommended options (Q1-Q5 all (a)); rewritten to the owner's answers before the red
tests. Each line names the question it rests on.
Card: `CARD-sales-insights-p2-07nov.md`. Plan: `PLAN-sales-insights-p2-07nov.md`.
Mockup: `mockups/sales-insights-p2-07nov.html`.

Reference case: dev copy `sorento_prod_1104`, October 2026 vs September 2026, counted lines (#2230), crew evidence
rounds 1 and 2 (PR #2231 comments 6705369461, 6705387753). Customers by code.

## P1 One engine, View by (card row 1)
- P1-1 The leaderboard has a View by switch: Sales person (default) / Customer / Product / Brand / Category. Every view
  is `run_ask(basis=invoiced, group_by=<view>)` with the board's period, compare window and filters; no other sales
  SQL. Test: each view's total equals the Sales person view's total for the same period and filters.
- P1-2 Switching view keeps the period, compare window, company, brand, category and every drill chip.
- P1-3 Reference, October: total RM 16,369,803.26 in every view; Customer view 1,075 customers, #1 304-R015
  RM 845,188.21 (+633.6% vs Sep RM 115,217.76); Product view #1 AC-EXP-006 RM 735,826.08; Brand view #1 SORENTO
  RM 8,880,157.22 (-7.9%); BRAVAT change blank (Sep RM -59,775.00).
- P1-4 Columns: Rank, name, Invoiced net (RM), vs last period, Customers (distinct); Product view adds Brand, Category,
  Qty; Customer view adds Company and Sales persons; Sales person view as #2227 (+ Target, P4). Podium only on Sales
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
- P6-1 Everyone with `sales.leaderboard.view` sees the Sales person view as on #2227 and can drill their own row.
- P6-2 Customer / Product / Brand / Category views, and drilling another person, need `sales.reports.view`; without
  it the tabs are absent, other rows are not clickable, and the API answers 403.

## P7 Assistant (card row 6)
- P7-1 `crm_report_ask` accepts the `sales_person` filter on the invoiced basis; "LCL's top customers last month"
  returns the board's P2-3 rows.

## P8 Layout
- P8-1 Usable at 375px and 1280px; reached from `/` by the sidebar.
