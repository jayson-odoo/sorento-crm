# Hand test: Product costing (lane PRODUCT-COSTING, PR #2321)

## URL

crew test copy

## Setup

1. Apply the `crew-migration:` SQL from PR #2321 to the dev DB, if the copy runs on the shared dev DB.
2. Sign in as an admin. Admin passes every permission check.
3. Have a second user ready, a salesperson, for the access check in step 18. That user does not
   hold `products.cost.view`.
4. Supplier costs are real dev data. The figures below assume CGB9032B (WB 245) has its primary
   supplier cost at RMB 34.50, as in the owner's workbook.
   - Read the "Cost" column in step 4.
   - If the cost differs, the expected landing cost = cost / 1.6 x 1.1 + 8.

## Steps

1. From `/`, open the sidebar: Products > Products > Costing.
2. Click Settings, then the Exchange rates tab.
   - If RMB has no row effective 01/11/2026, add one: Currency RMB, Effective from 01/11/2026,
     "Units per MYR 1", Rate 1.6, Add rate.
3. In Settings:
   - Open the "SST and method" tab and confirm SST 1.1 and Primary supplier.
   - Open the "Transport by category" tab and set the category of CGB9032B to Add, 8, then Save.
   - Close Settings.
4. Search "CGB9032B" and read the row.
5. Click the row's expand control to see its suppliers.
6. Clear the search. Open Filters, turn "Has cost" on, then turn it off.
7. In the party picker type "304-R017" and pick RELATED - BATHPLUS SDN BHD.
8. If the header shows "Set up costing", click it, enter mark-up 8, cost method Company default,
   and save.
9. Click "Add products", tick CGB9032B, and add it.
10. Click Edit, set the CGB9032B Mark-up to 10 (type it), and click Save.
11. Open the CGB9032B row menu, then History.
12. Click Edit, clear the CGB9032B Mark-up, and click Save.
13. Click Export, then open the downloaded xlsx.
14. Open the CGB9032B row menu and choose "Remove from party". Do nothing during the countdown.
15. Reload the page.
16. Click "Clear party" (the X beside the picker).
17. Click Settings, then the Exchange rates tab. Add RMB, Effective from a date next month, Rate 1.63.
18. Sign out. Sign in as the salesperson and open the Products menu.

## Expected

1. A page titled "Costing" opens. The party picker reads "Company standard". No filter is on, and
   every product is listed, including inactive ones and products with no cost.
2. RMB 01/11/2026 shows Units per MYR 1 = 1.6, MYR per unit 0.625, status In force. Dates read
   dd/mm/yyyy.
3. SST 1.1 and Primary supplier are shown, and the rule saves without error.
4. The CGB9032B row reads:

   | Column | Value |
   |---|---|
   | Cost | RMB 34.50 |
   | Rate | 1.6 |
   | SST | 1.1 (or 1.10) |
   | Transport | + RM 8.00 |
   | Landing (RM) | 31.72 |
   | Cost method | Primary supplier |
   | Mark-up | 149.06% (when its list price is 79.00; otherwise (list - 31.72) / 31.72) |
   | Final (RM) | equals List price (AutoCount) |

   There is no Margin column. Products with no cost show a reason ("No cost", "Set a primary
   supplier"), never 0.00.
5. One row per linked supplier, each with its own landing cost. A currency with no rate shows
   "No rate for <CUR> on <dd/mm/yyyy>".
6. With "Has cost" on, costless rows disappear and the URL gains `has_cost=1`. With it off, they
   come back.
7. The view changes to Bath Plus: the URL gains `party=`, the chips show "Party mark-up", "Cost
   method", "Rates as of" and "Products", and a Margin column appears.
8. The chip shows Party mark-up 8.00 %.
9. CGB9032B appears with Final 34.26 and Margin 130.61% (when the list price is 79.00).
10. While you type, the field keeps focus. After Save, CGB9032B shows Mark-up 10.00 % with the
    "Set on this row" marker, and Final 34.89.
11. History shows the mark-up going from none to 10.00 %, with your name and the time.
12. CGB9032B is back at 8% (no marker) and Final 34.26.
13. The title row reads `Costing - 304-R017 RELATED - BATHPLUS SDN BHD - as of <today dd/mm/yyyy>`.
    The CGB9032B row has numeric cells: landing 31.71875, final 34.25625.
14. A "Removing" countdown toast with Cancel appears, and no confirm dialog.
15. CGB9032B is no longer in Bath Plus's list (Products count down by 1).
16. The view returns to "Company standard" and `party=` leaves the URL.
17. The new row shows status Scheduled. The RMB 01/11/2026 row stays In force.
18. There is no "Costing" item under Products. Opening `/master-data-management/costing` shows
    "You do not have access to costing." with no grid or figures.
