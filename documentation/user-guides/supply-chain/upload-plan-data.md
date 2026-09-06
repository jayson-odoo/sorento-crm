# Supply Chain - Upload the data a reorder plan is built from

Every reorder plan is computed from four feeds: the sales order book, the purchase order book,
the Order Inquiry sheet, and the reorder-level listing. Use this flow whenever you have a fresh
export of any of these to load. Closed sales and purchase history no longer upload here at all -
once the AutoCount integration is connected, that history arrives on its own; see "Sales and
purchase history" below.

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

Carries what neither order book states: where stock is meant to land, and which purchase order a
sales order is waiting on.

1. Click **Upload order inquiry sheet**.
2. Drag in or browse to the file.
3. Click **Test**, then **Confirm upload**. Like the order-book uploads, this queues a job you can
   follow in the **Upload activity** drawer and, once finished, as **Order Inquiry Import** under
   **Import Jobs**.

The sheet only **fills a blank warehouse** on a sales-order line - it never overwrites a
warehouse the order book itself already stated. If the order book (or the AutoCount integration)
later states a location for that same line, the order book's value wins over what this sheet had
filled in.

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

* [Upload SPO allocations](../purchasing/upload-spo.md)
* [Upload the product master](../purchasing/upload-product-master.md)
