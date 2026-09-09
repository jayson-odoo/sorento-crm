# Supply Chain - Print the order summary

The order summary is the same paper sheet a buyer used to fill in by hand, now built from the
plan's own figures. Use it to see what to order, print it, or hand it to a supplier.

## Where

From a reorder plan (see [Run a reorder plan](run-a-reorder-plan.md)), open the **Actions** menu
on the Lines tab toolbar and choose **Order summary**.

## What the sheet shows

One row per product, with the plan's columns in the sheet's own order:

* **Product**, **On hand**, **SO demand** (Project and Retail quantities, each with a drill-down
  for the sources behind it), **Order qty**.
* **Delivery** - the quantities due, grouped by month.
* **Project / customer** - the customer or project names behind the Project quantity, with the
  quantity for each in brackets.
* **Supplier** - the chosen supplier, or the suggested one if none has been chosen yet.
* **Remarks** - open purchase order quantity plus incoming SPO quantity (for example "PO 400 +
  incoming 89 = 489"), the last goods-received date and quantity (for example "Last in
  21/07/2026, 300"), and the MOQ, each only when there is something to show.

Every figure on the sheet is the plan's own - nothing is typed twice.

## Export

Click **Export** on the toolbar and choose **PDF** or **Excel**:

* **PDF** downloads a landscape sheet with one row per product, the same nine columns.
* **Excel** downloads a workbook of the same rows.

Only products with something to order are included. If more than 2,000 such products would be
on the sheet, the export is refused ("Narrow the plan first") - narrow the plan's scope (fewer
warehouses or products) and export again.

## See also

* [Run a reorder plan](run-a-reorder-plan.md)
* [Upload the data a reorder plan is built from](upload-plan-data.md)
