# UAC: SALES-LEADERBOARD (draft on the card's recommended options)

Status: Draft, 7 Nov. Written on the card's recommendations (Q1-Q5 all (a)) while the owner's answers are pending;
each line names the question it depends on. Rewritten if an answer differs.
Card: `CARD-sales-leaderboard-07nov.md`. Plan: `PLAN-sales-leaderboard-07nov.md`.

Reference case: dev copy `sorento_prod_1104`, October 2026 vs September 2026 (crew run, PR #2227 comment
6704175660). Figures are the shared engine's AFTER lane SALES-SUBTOTAL-LINES (blank-item subtotal lines no
longer double counted; equal to the header totals). Before that fix lands, ERIC NG Oct reads +144,604.00 and
JENNIFER Sep +147,317.60; this lane adds no workaround.

## L1 Navigation and access
- L1-1 Sales > Leaderboard sits in the Sales menu after Sales Teams, shown only to a user holding
  `sales.leaderboard.view` (Q3). Without it the menu item is absent and `GET /api/v1/sales/leaderboard` answers 403.
- L1-2 The board reads only the companies the user may switch to; the Company filter lists exactly those.

## L2 The figure (no second calculation)
- L2-1 Every RM on the board comes from `run_ask(basis=invoiced)`: IV + CS + DN - CN, net of tax, by DocDate, posted
  only. Test: for any period and company, the board total equals the Sales & outstanding Invoiced total for the same
  period and company.
- L2-2 A cancelled document never counts; a credit note subtracts.
- L2-3 Reference: Last month on 7 Nov (Oct 2026), all companies: total RM 16,369,803.26; previous period RM
  15,894,544.36; change +3.0%; no agent RM 1,210.32.

## L3 Ranking (Q1)
- L3-1 One row per person: agent codes sharing a `person_label` are one row; a code with no `person_label` is its own
  row under its code. The row shows the person and its codes.
- L3-2 Reference ranks, October 2026: #1 LCL RM 1,856,856.61 (codes LCL in SRT and MCH), #2 SEAN RM 1,276,644.96
  (SEAN I, SEAN III, SEAN IV), #3 JUSTIN RM 1,156,644.97; 40 persons ranked.
- L3-3 Ranked by RM descending; ties by name.
- L3-4 "(no agent)" sales are never ranked; they show as one footer line with their RM.
- L3-5 A person with no sales in the period is not listed (CK LEE, Sep only, is absent in October).
- L3-6 House codes (ACC, C/S, SAMPLE) rank as any code.

## L4 Columns (Q4)
- L4-1 Rank, Sales person, Codes, Invoiced net (RM, 2 decimals), vs last period (%, 1 decimal), Customers (distinct
  customers invoiced across all the person's codes).
- L4-2 vs last period compares the same number of days just before the period (`compare_to=previous_period`). It is
  blank when the previous figure is zero or negative.
- L4-3 Reference: LCL +63.6%, SEAN -10.4%, JUSTIN +62.8%; ERIC NG RM 805,048.34 (#7) -16.7%; JENNIFER RM 291,522.87
  (#20) +27.6%.
- L4-4 No target and no commission column (card round 2: no invoiced agent target exists).

## L5 Period and filters
- L5-1 Chips: This month (default), Last month, This quarter, YTD, Custom (date range). This month runs from the 1st
  to today.
- L5-2 Filters: Company (default all granted), Brand, Category; each a clearable SearchableSelect. A brand or category
  filter ranks on the matching lines only.

## L6 Display
- L6-1 KPI row: Total invoiced with change vs last period; Sales persons ranked with the no-agent RM; Your rank (only
  when the user is linked to an agent, else the tile is absent).
- L6-2 Podium: the top 3 as cards, #1 in the middle, each with RM and change. Fewer than 3 persons: only those cards.
- L6-3 Grid: DataGrid, `tableLayout: { width: 'fixed', columnsResizable: true }`, explicit sizes, codes truncated with
  title. The signed-in user's row is highlighted (Q3).
- L6-4 Empty period: header, filters and an empty state (heading + hint, no button).
- L6-5 "Data as of" line: the latest billing document sync time.
- L6-6 375px: podium as 3 compact cards, rows show rank, name, RM with the change under the name; nothing clipped.
  1280px: as the mockup.

## L7 Assistant (Q5)
- L7-1 `crm_report_ask` accepts `group_by=sales_person` on the invoiced basis and returns the same rows and RM as the
  board for the same period and company.
- L7-2 "who's top this month" answers from `crm_report_ask` (one eval line); no new MCP tool.
