## URL
crew test copy

## Setup
- Sign in as an admin (holds sales.leaderboard.view, sales.reports.view and order_management.orders.view).
- Shared dev DB, no migration. A worker is not needed.
- Until SALES-SUBTOTAL-LINES (#2230) is on this branch, Invoiced figures carry the doubled subtotal lines (October total RM 16,514,407.26 instead of RM 16,369,803.26; only ERIC NG October and JENNIFER September differ). Delivered / Ordered / Undelivered are not affected.

## Steps
1. From `/`, open Sales > Leaderboard in the sidebar.
2. Click the "Last month" period chip (October 2026 on the dev copy).
3. Check the Basis chips read Invoiced / Delivered / Ordered / Undelivered orders and Invoiced is selected.
4. Click the LCL row.
5. Check the chip "Sales person: LCL" and the Customer tab are shown; read the first customer row.
6. Click the Product tab (the chip stays).
7. Click the chip's remove button.
8. Click the Channel tab.
9. Click the Delivered basis chip.
10. Click the Sales person tab.
11. Click the Ordered basis chip.
12. Click the Undelivered orders basis chip.
13. Click the Customer tab, then "Open as report".
14. Go back to the leaderboard, click the Invoiced chip, the Product tab, then "Open in Top selling items".
15. On Top selling items click "Product ranking".
16. Reload the leaderboard with no query string (open Sales > Leaderboard from the sidebar again).
17. Narrow the browser to 375px wide and repeat steps 4 and 8.

## Expected
- Step 2: total RM 16,514,407.26 (RM 16,369,803.26 after #2230); LCL #1 RM 1,856,856.61, SEAN #2 RM 1,276,644.96, JUSTIN #3 RM 1,156,644.97. No Target column (every agent target on dev is RM 0.00).
- Step 5: LCL invoiced RM 1,856,856.61, 24 customers; first row is customer code 304-R015, RM 845,188.21, with the customer's real name above the code.
- Step 6: 684 items; first row AC-EXP-006, RM 735,826.08.
- Step 7: back on the full Sales person board.
- Step 8: Channel rows Dealer, Project team, No sales order, Sales order type not set; the rows add up to the total (after #2230: Dealer RM 9,665,663.40, Project team RM 5,532,136.98, No sales order RM 1,136,680.81, Sales order type not set RM 35,322.07).
- Step 9: Delivered total RM 10,797,078.52, vs last period -21.2%; Channel rows Dealer RM 7,919,006.98, Project team RM 2,810,160.30, (none) RM 67,911.24.
- Step 10: Delivered #1 SEAN RM 1,181,097.92, #2 FANNY RM 894,180.38, #3 LONG RM 766,582.12.
- Step 11: Ordered total RM 14,697,054.39 (-10.2%); #1 SEAN RM 1,398,504.30, #2 FANNY RM 1,149,295.56.
- Step 12: the period chip "All open" is selected; total RM 77,309,379.57; #1 ERIC NG RM 13,880,362.08; "vs last period" cells are blank.
- Step 13: Sales & outstanding opens on the Undelivered orders tab, Summary grouped by Customer, all dates; with the company switcher on the same companies as the board, its total equals the board's RM 77,309,379.57.
- Step 14: Top selling items opens with the October period.
- Step 15: back on the leaderboard, Invoiced, Product view.
- Step 16: the board reopens on the last basis, view and period you used.
- Step 17: rows keep rank, name and RM, change on a second line; nothing is clipped; the View by switch is a dropdown or scrolls.
