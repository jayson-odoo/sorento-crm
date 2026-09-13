# Supply Chain - Upload the data a reorder plan is built from

Four uploads sit on the Reorder Planning page: the sales order book, the purchase order book,
the order inquiry sheet, and the reorder-level listing. Use this flow whenever you have a fresh
export of any of these to load. The order inquiry sheet is the odd one out: it is the migration
tool for the order inquiry Excel you keep by hand rather than a feed the plan is computed from,
and it is described in full under "Upload order inquiry sheet" below. Closed sales and purchase
history no longer upload here at all - once the AutoCount integration is connected, that history
arrives on its own; see "Sales and purchase history" below.

## Where

Open **[Supply Chain → Planning → Reorder Planning](/scm/reorder)** (URL: `/scm/reorder`). The
page is titled **Reorder Planning**. Click **Actions** in the list toolbar (next to **Start
Plan**) to see the upload entries:

* **Upload sales orders**
* **Upload purchase orders**
* **Upload order inquiry sheet**
* **Upload reorder levels**
* **Refresh**

The same two order-book uploads are also reachable from their own lists: **Upload sales orders**
is under the **Start** button on **[Supply Chain → Orders → Sales Orders](/scm/sales-orders)**,
and **Upload purchase orders** is under **Actions** on
**[Supply Chain → Orders → Purchase Orders](/scm/purchase-orders)**. All three open the same
dialog.

## Upload sales orders / Upload purchase orders

The file is the **whole book** - orders still outstanding and orders already completed alike, not
a filtered export of one or the other.

1. Click **Upload sales orders** or **Upload purchase orders**. The dialog is titled the same as
   the button you clicked.
2. Drag in or browse to the file.
3. Click **Test** to read the file without writing anything. The result shows how many rows were
   read, how many would import, and how many would be skipped or only warned about.
4. Click **Confirm upload**. The write happens on the worker - the dialog closes and a toast
   confirms the upload was queued, with a **View job** link. The job also shows in the **Upload
   activity** drawer (the icon in the top header) and, once it finishes, in
   **[System Management → Import Jobs](/system-management/import-jobs)** as **Outstanding Sales
   Orders Import** / **Outstanding Purchase Orders Import**.

### What's captured

* **A debtor named with both a code and a name that Sorento does not already hold is created as
  a customer**, and the order links to it. A row that states only a code with no name is not
  enough to create a customer from - the order still imports, carrying that code under
  **Customer code**, with no customer linked, until a later upload or a manual edit supplies the
  name.
* **A line whose item code does not match anything in the product master is skipped**, and
  listed on the Test result as a row problem (`no product with this code`).
* **A line whose warehouse code is not recognised is kept, not skipped** - it still counts as
  demand or supply, it is just not tied to a location. It is listed on the Test result
  (`no warehouse with this code`) so the code can be corrected and the file re-uploaded.
* **A sales order that cannot be classified** - its agent carries no demand class and its
  customer carries no market segment - **no longer blocks the whole file**. The order still
  imports with no demand class, and the affected order numbers are listed on the Test result so
  the agent or customer master can be fixed and the order re-classified on the next upload.
* A purchase book can also carry shipping-order lines (SPO); those are read and reported
  separately and file into the SPO allocations list rather than the purchase order book - see
  [Upload SPO allocations](../purchasing/upload-spo.md).

## Upload order inquiry sheet

This is the migration tool for the order inquiry Excel you have been keeping by hand. Sales
orders, purchase orders and shipping orders already arrive from AutoCount on their own, so the
sheet is no longer read for any of those: every row on it becomes an **order inquiry** on the
sales order line it names, linked to the purchase order or shipping order that line is waiting
on. Completed history migrates too, so you can load the whole workbook, not just this month.

### What the sheet must contain

* **SO NO** and **ITEM CODE** are required; a sheet without both is refused with nothing
  written.
* **QTY**, **DELIVERY DATE**, **STOCK LOCATION** and **REMARK** are what the row is raised
  with.
* The **DELIVERY DATE** cell may read `ORDER BACK` instead of a date. Both kinds of row are
  raised; the words only decide whether the row reads **ORDER BACK** or **ORDER** on the
  worklist.
* The **REMARK** cell may name the PO or SPO the line waits on, several joined with `&`, for
  example `202606-S0024 & 202607-S0043`. `ORDER` on its own means nothing was ordered yet.
* Every tab with a recognisable header row is read. The same row restated on several tabs
  (month, roll-up, snapshot) is raised **once**, not once per tab.

### Steps

1. Click **Upload order inquiry sheet**. The dialog is titled the same and reads "Raises the
   sheet’s rows against the sales order line and its PO/SPO."
2. Drag in or browse to the file under **Order Inquiry file**.
3. Click **Test**. Nothing is written; the panel below tells you what Confirm would do.
4. Click **Confirm upload**. The write happens on the worker, the dialog closes, and a toast
   confirms it was queued with a **View job** link.

### What the preview tells you

Seven tiles:

| Tile | Reads |
| --- | --- |
| **Rows** | Every row read off every tab. |
| **Will raise** | Rows that will become an order inquiry. |
| **Already raised** | Rows whose sales order line already carries an order inquiry. Those lines are left exactly as they are, links included. |
| **No SO line** | Rows no sales order line could be found for. |
| **Orders adopted** | Sales orders this upload brings into planning for the first time. |
| **Rows linked** | Rows that will be placed on at least one PO or SPO. |
| **Documents not found** | Documents the sheet cites that could not be linked. |

Under the tiles, a line says how many sheets were read and how many were skipped, then up to
three lists:

* **Sales orders not in the CRM** - the sheet names them, we do not hold them. Nothing is
  created for those rows; fix the number or wait for the order to arrive from AutoCount.
* **Documents we could not link** - the cited PO or SPO is not here, has no line for that item,
  or has no room left. The rows are still raised, just unlinked.
* **Rows with no matching line** - one entry per row as `SO · item · qty · reason`, with the
  reason in the same words the job page uses: "No sales order line for this item", "No line for
  this item at that stock location", "Quantity exceeds what the line ordered".

A list with nothing in it is absent rather than shown empty. **Confirm upload** is disabled when
**Will raise** is 0: there is nothing left for it to do, and pressing it would only queue a job
that writes nothing.

### What gets created

* **One order inquiry row per sheet row**, on the sales order line matched by SO number, item
  code, stock location, and a quantity that fits what that line ordered. A line with no
  warehouse of its own accepts any stock location.
* **Whether the line is still open makes no difference.** A closed sales order and a fully
  delivered line migrate the same as an open one, which is the point of loading the history.
* **Two rows for the same line are both raised** when their quantities together still fit what
  the line ordered. The sheet is what splits a line, never the upload.
* **The upload never creates a sales order or a sales order line**, and never writes a location
  onto one. AutoCount owns the order book.
* **A line that already carries an order inquiry is skipped**, whoever raised it. So
  re-uploading the same sheet writes nothing new: every row comes back under **Already raised**.
* Each raised row carries the note **Migrated from order inquiry sheet** followed by the file
  name, so you can tell it from a row the board raised. Read it from the info icon in the
  **Instruction** column.
* A row on a line that was already delivered is filed as answered, with its links intact. It
  stays on the worklist to be read, but purchasing is not asked to buy the goods again, and
  ticking it for a bulk action says "This row has already been answered".

### Which PO or SPO a row is linked to

1. **What AutoCount records for that sales order line comes first**, whatever the remark says.
   A shipping order is taken before a purchase order, and where a purchase order was turned
   into a shipping order, the link lands on the shipping order with its source PO named beside
   it.
2. **The remark is used only for what AutoCount leaves.** Cited documents are tried in the
   order they are written, so `A & B` fills from A first and asks B for the rest.
3. **A closed or fully received document links like an open one.** What counts is how much of
   what it ordered nothing else has claimed.
4. **If the document has less room than the row needs**, the part that fits is linked and the
   row reads as partly linked.
5. **If nothing is cited and AutoCount records nothing**, the row is raised unlinked. The
   upload does not go hunting for some other document that would fit; that is still
   **Auto link all...** on the Order Inquiries page, run when you want it.

The document the sheet cited stays on the row either way, so where the sheet and the book
disagree you can see both. To see what a row actually ended up on, open the document icon beside
**Outstanding PO/SPO**; the dialog is titled **Backing documents** and lists each PO or SPO with
its quantity, location and expected date.

### How you'll be notified

The toast reads "Upload queued. Processing in the background." and carries **View job**. The job
also shows in the **Upload activity** drawer (the icon in the top header) and, once it finishes,
in **[System Management → Import Jobs](/system-management/import-jobs)** as **Order Inquiry
Import**, where every row of the sheet has an outcome of its own, including the ones that were
left alone.

### Where the rows appear

Open **Procurement → Supply Chain → [Order Inquiries](/project-sales/order-inquiries)**. The
page opens on every row, so leave the **Confirmed** filter empty; a migrated row is confirmed the
moment it is raised. Each row carries the quantity, delivery date and stock location the sheet
stated, the instruction it was raised with, and the note naming the file it came from.

### Who can upload it

Anybody who can run a reorder plan. It is the same permission, so no new access is needed to
migrate the sheet.

## Upload reorder levels

The reorder level and reorder quantity listing. Unlike the other three uploads, this one writes
**immediately** - there is no background job, and the result shows in the dialog itself.

1. Click **Upload reorder levels**.
2. Drag in or browse to the file.
3. Click **Test** to see what would change: **New levels**, **Updated**, **Unchanged**, and **Kept
   yours**.
4. Click **Confirm upload**.

A level you set by hand is never silently overwritten by the file - a level you changed manually
that disagrees with the file is listed under **Kept yours**, naming the product, the location,
your value, and the file's value, and your value is the one that stays.

## Sales and purchase history

Closed sales and purchase history are no longer uploaded here. Once the AutoCount integration is
connected, that history arrives on its own, continuously, rather than through a file you export
and load by hand.

## See also

* [Run a reorder plan](run-a-reorder-plan.md)
* [Print the order summary](print-the-order-summary.md)
* [Upload SPO allocations](../purchasing/upload-spo.md)
* [Upload the product master](../purchasing/upload-product-master.md)
