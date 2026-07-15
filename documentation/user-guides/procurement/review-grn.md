# Procurement — Review and approve a GRN

A Goods Receipt Note (GRN) records what was physically received against an SPO. Use this guide to find a GRN, review its lines, change its status (Draft → Approved / Rejected), and create or delete one by hand. For **bulk uploading** GRNs from Excel, see [Upload a GRN](../warehouse/upload-grn.md) instead — this guide covers the in-app review flow.

## Where

[**Procurement → GRN**](/procurement-management/grn). The list shows columns **GRN Number**, **SPO Number**, **Picking Date**, **Number of Items**, and **Status**. Filter with the **Status** control (**All statuses** / **Draft** / **Approved** / **Rejected**) and search by GRN number, SPO number, or product. Click a row to open the GRN detail page.

## Review a GRN

On the detail page you'll see the GRN header (GRN number, SPO number, picking date, **Picking Status**) and the **Picking Lines** section — one row per received line with its product, **Expected** vs **Picked** quantity, any discrepancy, condition, batch, and location. Review the lines and quantities before changing status.

## Change the status

1. On the GRN detail page, click **Change status** (the icon button next to the status badge).
2. Pick one of **Draft**, **Approved**, or **Rejected** from the menu. The current status is disabled. The change saves immediately and the status badge updates.

A new GRN starts as **Draft**. Move it to **Approved** once the received goods are verified, or **Rejected** if the receipt can't be accepted.

## Create a GRN by hand

1. On the GRN list, click **Create GRN** (opens a full create page).
2. Fill the header: **GRN Number** *, **SPO Number**, **Picking Date** *, **Status**, **Notes**.
3. In **Picking Lines**, click **Add Line** for each received line and set **Product** *, **Qty Expected**, **Qty Received**, and **Location** *. Use **Select All** / **Bulk Remove** to manage lines.
4. Save. To edit later, open the GRN and click **Edit**.

## Delete a GRN

On the GRN detail page click **Delete** and confirm. This is a hard delete and removes the GRN and its picking lines. (To remove several at once, use the bulk-delete action on the list.)

## Bulk upload

To load GRNs and their lines from Excel rather than entering them, use **Upload GRN** and **Upload GRN Lines** on the list toolbar. Full steps and the column template are in [Upload a GRN](../warehouse/upload-grn.md).

## What's captured

A GRN stores: GRN (picking) number, SPO number, picking date, picking status (Draft / Approved / Rejected), inspection status and remarks, who picked / inspected it, totals (items picked, discrepancy, cost), and notes. Each picking line records the product, expected vs picked quantity (the discrepancy is computed), condition, batch and expiry, unit cost, and source/destination warehouse.

## See also

* [Procurement — Data analysis for the AI assistant](data-analysis.md)
* [Upload a GRN (header + lines)](../warehouse/upload-grn.md)
* [Upload an SPO](../purchasing/upload-spo.md) (GRNs receive against SPO allocations)
