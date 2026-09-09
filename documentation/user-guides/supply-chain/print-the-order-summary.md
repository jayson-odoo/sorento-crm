# Supply Chain - Print the order summary

The order summary is the same paper sheet a buyer used to fill in by hand, now built from the
plan's own figures. Use it to see what to order, print it, or hand it to a supplier.

## Where

From a reorder plan (see [Run a reorder plan](run-a-reorder-plan.md)), open the **Actions** menu
on the Lines tab toolbar and choose **Order summary**.

## What the sheet shows

One row per product, with the plan's columns in the sheet's own order: **Item code**, **BRW on
hand**, **Reorder level**, **Project qty**, **Dealer o/s**, **Order qty**, **Delivery**,
**Project / customer**, **Supplier**, **BRW PO qty**, **BRW incoming qty**, **Last in qty**,
**Last in date**, **Remarks**.

* **BRW on hand / BRW PO qty / BRW incoming qty** count the site pool only (active,
  non-project warehouses) - stock or supply sitting in a project bin is not on the sheet.
* **Delivery** and **Project / customer** come from the project's own Order Inquiry: one
  "Month - qty" line and one "Name - qty" line per entry. A product with no inquiry row shows
  a blank Delivery cell even when it has Project demand elsewhere on the grid.
* **Supplier** is the chosen supplier, or the suggested one if none has been chosen yet.
* **Remarks** shows the MOQ (for example "MOQ 1000") only when there is one.

Every figure on the sheet is the plan's own - nothing is typed twice.

## Export

Click **Export** on the toolbar and choose **PDF** or **Excel**:

* **PDF** downloads a landscape sheet with one row per product, the same 14 columns.
* **Excel** downloads a workbook of the same rows.

Only products with something to order are included. If more than 2,000 such products would be
on the sheet, the export is refused ("Narrow the plan first") - narrow the plan's scope (fewer
warehouses or products) and export again.

## See also

* [Run a reorder plan](run-a-reorder-plan.md)
* [Upload the data a reorder plan is built from](upload-plan-data.md)
