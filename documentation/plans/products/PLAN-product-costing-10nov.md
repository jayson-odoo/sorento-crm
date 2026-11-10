# PLAN: Product costing - Purchasing vs Pricing tabs + B Plus costing view

Status: Plan (behaviour card + mock first; build only after owner approval). Track: full (expected migration + permission gating).

Lane: PRODUCT-COSTING. Source: owner + management meeting 9 Nov 2026 "Project Internal Costing",
owner's workbook Internal_Costing_Formula.xls.

## Journey (draft)

1. Purchasing staff open a product, Purchasing tab: suppliers per product (supplier code, primary flag,
   lead time, currency, unit cost) and per supplier "margin if bought from this supplier" against the
   product's standard selling price.
2. Management open the Pricing tab: cost basis, mark-up %, selling price at product level. The selling
   price does not change with which supplier is chosen.
3. Management open the B Plus costing list: selected products with the landing cost formula applied
   (supplier cost / rate x SST, then transport add or multiply, then B Plus mark-up), export to Excel.
4. Dealers and staff without the cost permission never see any cost value.

## Status log

- 10 Nov: lane opened, mapping existing data (step 1).
