# Supply Chain - Loading Plan

Use this flow to ask a supplier what to load into their next container: read what the Lines tab
suggests, search and sort it, and change the sales-order window a plan is worked out against.

## Where

Open **Procurement → Supply Chain → Loading Plan** (URL: `/scm/loading-plan`). The page is
titled **Loading Plan**.

## Start a plan

Click **Upload** in the list toolbar (the same button appears as the empty-state action on a
fresh list). The dialog is titled **Plan a container**:

* **Supplier** - required.
* **Sales orders needed** - **From** and **To** dates, both optional. The helper text reads
  "Empty = every open order counts." A sales order with no date of its own always counts,
  whichever dates you set. The **To** date cannot be before the **From** date - the dialog
  refuses with "The To date cannot be before the From date." rather than silently netting
  nothing.
* **Document** - **Stock list**, **Proforma invoice**, or **No file**. Picking a document shows
  a drop zone; picking **No file** does not, and skips straight to starting the plan from what
  is already on file for this supplier.

With a document chosen, click **Test** to read the file without writing anything, then
**Confirm and start plan**. With **No file**, click **Start plan** directly.

## The three tabs

Once a plan is open, it has three tabs: **Lines** (the default), **Supplier codes**, and
**Sent**. The header shows the supplier's name, a status badge (**Planning**, **Sent**, or
**Cancelled**), and a line reading when the plan was started, the window it covers, and which
document it was started from.

## The Lines tab

### What the table lists

* **A plan started from a file** (a stock list or a proforma invoice, matched or not) lists
  only the products and sets that file's rows name. A product your company buys from this
  supplier that the file does not mention is not on the table, even if it has open sales-order
  need.
* **A plan started with No file** lists only the products bought from that supplier under
  **Product-Suppliers**.
* **A file whose codes have not been matched yet lists no rows at all**, until those codes are
  matched on the **Supplier codes** tab.

### Stat cards

Above the table, four cards read **Outstanding**, **On hand**, **From SPO**, and **To request**.
These summarise every row on the plan and are not affected by the **Search product** box below
(see "Search the table").

### Table / Schedule and search

The card heading reads "What to ask *\<supplier\>* to cover *\<window\>*" (or "... for" when the
window is every open order). Beside it, a **Table** / **Schedule** toggle switches between the
row list and a schedule view of the same rows. A **Search product** box sits next to the
toggle: typing filters the ranked rows, the folded rows, and the Schedule view by product code,
product name, or set code (case-insensitive, matching anywhere in the text). The stat cards and
**Save (N)** are not affected by what is typed here. Clearing the box restores every row; no
match shows "No product matches" in the table body instead of rows.

### Columns

Every column header sorts by clicking it, except **Remarks** (a free-text field with no natural
order). **Suggested qty** sorts by the quantity currently shown for the row, so "what am I
asking most of" is one click away even when you have typed over the engine's own figure.

* **Product** shows the item code once. The product name only appears underneath when it
  differs from the code - a row whose name and code are the same no longer repeats itself. A
  set row keeps its **Set** badge and the driver product's code underneath, labelled "Figures
  from *\<driver code\>*".
* **On hand**, **SPO**, and **Incoming PL** are the three pieces of supply behind a row:
  * **SPO** is shipping orders already on their way, at any active location.
  * **Incoming PL** is the part of a packing list not yet placed on an SPO. A shipment that is
    already fully on an SPO does not count here and does not appear in the **Incoming PL**
    lightbox - so a container is never counted once as SPO and again as Incoming PL.
  * **Total supply** is On hand + SPO + Incoming PL.
* Clicking the **SPO** or **Incoming PL** figure opens a lightbox listing the shipments behind
  it; the rows sum to exactly the number you clicked.

### Viewing the uploaded file

If the plan was started from a stock list or proforma invoice, open the gear menu and pick
**View uploaded list** to preview it. On an Excel or CSV file, a **Search in sheet** box sits
above the preview table. Typing filters to the rows where any cell contains the text
(case-insensitive) and highlights the match; a count reads "N of M rows" while filtering, and
"No cell matches" shows if nothing does. The search covers the whole sheet, not only the first
rows the preview displays. Clearing the box restores the plain preview, and switching between
sheet tabs keeps the same search applied. A PDF or image file shows no search box.

## Change the sales orders needed window

Open the gear menu and pick **Change cut-off**. The dialog is titled **Change the sales order
cut-off**, with the note "The suggestion is worked out again against the new window." It carries
the same **Sales orders needed** **From** / **To** fields as **Plan a container**, with the same
"Empty = every open order counts." helper and the same guard against a **To** date before
**From**. Click **Save cut-off** to re-work the suggestion against the new window; this drops
any quantities you had typed but not yet saved, the same as **Refresh suggestion** does.

A plan started before this window existed keeps whatever **To** date it already had, with no
**From** date, until you set one.

## What's captured

* The supplier, the document the plan was started from (or none), and the **Sales orders
  needed** window (**From** / **To**) the suggestion is worked out against.
* Any quantity or remark you type on a row, once you click **Save (N)**.

## See also

* [Run a reorder plan](run-a-reorder-plan.md)
* [Upload the data a reorder plan is built from](upload-plan-data.md)
* [Print the order summary](print-the-order-summary.md)
