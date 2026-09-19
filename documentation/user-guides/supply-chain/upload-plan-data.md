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

## The Order Inquiries page

Open **Procurement → Supply Chain → [Order Inquiries](/project-sales/order-inquiries)**. The page
is what replaces the monthly order-book Excel; a **List** / **Schedule** toggle sits top right of
the page. There is no "Plan until" line on the page any more - the cut-off date that used to show
there now lives inside the **Auto link all...** dialog.

The page opens on **To confirm**: every row CS has raised that you have not yet signed off. See
"Confirming a row" below for what that means and how it works.

### Stage cards

Three cards sit above the grid: **Buy**, **Purchased**, **Incoming**. Every unit is counted in one
card only, the furthest it has reached:

* **Buy** - nothing bought yet.
* **Purchased** - on a purchase order, its container not booked yet.
* **Incoming** - on a shipping order, either linked to the row directly or found through the
  purchase order the row is linked to.

Click a card to filter the grid to that stage. A row marked `used` (see "A row already covered
by stock" below) never counts toward any of the three cards, or toward the Schedule matrix
cards, so the card totals and what you see when you click into one always agree.

A fourth tile, **To confirm**, sits beside the three stage cards. It shows how many rows are
still waiting on your sign-off; click it to return to the To confirm view from anywhere else on
the page. See "Confirming a row" below.

### Month tabs

A row of tabs sits above the grid, and above the Schedule matrix too: one tab per delivery month
that has rows, with the row count in brackets, **All** first. Click a tab to narrow to that month.

### Filters and search

Click **Filters** to open the popover: **Location**, **Agent**, **SO month**, **PO number**,
**SPO number**, **Linked**, **Confirmed**, **Supplier**, **Project**, **Raised by**, **Raised on**.
**Clear filters** resets every one of them. On a short screen the popover's own content scrolls,
so every field stays reachable even when there isn't room to show them all at once.

A cancelled row no longer shows on the list by default. Filters > State = Cancelled shows them.

**Raised by** names whoever raised that particular row - not simply whoever most recently pressed
Confirm on the sales order. A row raised well before the order's last confirm still names its own
original raiser.

**Confirmed** is the sign-off filter: **To confirm**, **Confirmed**, **Changed**, **Rejected**,
**All**. **To confirm** is what the page opens on; see "Confirming a row" below for what each
value means.

The search box uses multi-word narrowing: typing several words splits them on spaces and finds
rows matching ALL of them. For example, typing `SO366990 SRTWT6801` finds only rows on sales order
SO366990 whose product or item code contains SRTWT6801. The order of words does not matter; up to
ten words are used and extra spaces are ignored. Besides sales order, item code, product name,
customer, project and raiser, the search box also matches a PO number, an SPO number, and an
agent.

The grid remembers your sort order and every filter, per user, and restores them the next time
you open the page. Page number and the search box always start fresh.

### Columns

The default column order mirrors the Excel order book: **SO date**, **S/O no**, **Item code**,
**Qty**, **Delivery date**, **Project / customer**, **Supplier**, **PO**, **SPO**, **Agent**,
**Location**, **Order inquiry**, then the rest. Every row of one sales order now sits under one
order inquiry number, so the **Order inquiry** column is hidden by default - open **Columns** in
the toolbar and tick it to show it. If you have already personalised your own column order or
visibility, yours is kept.

### The PO and SPO columns

The PO and SPO on a row follow AutoCount's own linkage: the purchase order line AutoCount raised
for that sales order line, and the shipping order that purchase order line became, whatever state
the document is in, open, closed or already received. There is nothing to click for this to
happen. This runs as soon as AutoCount's purchase order or shipping order reaches the CRM, when a
row is raised or confirmed, and first on every **Auto link all...**. A row still on **To confirm**
gets the link as a draft, the same as any other draft link. Confirming a purchase order and
**Auto link all...** never move a link AutoCount states. If AutoCount covers only part of the
row's quantity, the normal automatic linking on this page covers the rest.

* A number in the **SPO** column tagged **via PO** means the shipment was found through the
  purchase order the row is linked to, not linked to the row itself.
* A number in the **PO** column tagged **via SPO** means the purchase order was read off the
  shipping order the row is linked to.
* **awaiting shipment** in the **SPO** column means the row is bought, on a purchase order, with
  no container booked yet.
* A row with neither link shows a hyphen in both columns.
* The **Supplier** column reads the shipping order's supplier when the row's only link is a
  shipping order - for example, the C-FHSS14 row on SO421886 reads supplier XIAMEN TAIYANG
  TECHNOLOGY CO.,LTD. once its only link is SPO-2026/09-0036. It used to read **Not linked** in
  that case; a row with a purchase order link reads as it always has.
* Click the number to open **Backing documents**, listing every PO and SPO behind the row with its
  quantity, location and expected date.
* A word next to the number tells you more about that document, in plain words rather than an
  icon:
  * **received** - the document is fully received. Click the word to open **Backing
    documents**, which shows `Received <n> of <n>` for that document.
  * **reallocate** - the document lands well before this row needs it, and another inquiry
    for the same item needs it sooner. Click the word for the candidate list, earliest need
    first, with the top candidate marked **Reallocate to**, and the instruction to re-key the
    line to the chosen sales order in AutoCount - the link moves by itself at the next push
    (see "When AutoCount's linkage overrides this page" below). Nothing is changed from the
    lightbox.
  * **unlink** - the document is early and no other inquiry needs the item sooner. Click the
    word; the lightbox reads "Unlink - no sooner inquiry needs this item".
  * **note** - the link on this row moved, was cleared, or was taken by AutoCount for another
    sales order. Click the word to read what happened, on which document, which sales order (if
    any), and when.

### A row already covered by stock

When CS confirms a fulfilment plan on a line whose linked document has since been fully
received, the row's goods already went into that document's location stock and were used by
earlier orders. Purchasing sees this on Order Inquiries as two rows for the same item:

* **The old row is kept as history.** It is greyed, its quantity and its documents are
  unchanged, and its Qty cell carries the word **used**. Click **used** to read why - which
  document, when it was received, and which location it landed in.
* **A new row is raised for the full quantity, with no documents.** It shows in the **Buy**
  card and is what purchasing actually buys against. Its Qty cell carries the same (i) as any
  changed row, showing **Was** the old quantity and date; the (i) beside its **Instruction**
  names the document that was received, when, and which location it landed in - so purchasing
  reads the whole story off the one new row. No separate delay row is raised for that line.

Nothing needs deciding on either row - the old one is just kept for the record, and the new one
reads as a plain buy. See [Sales order changes after planning](sales-order-changes.md) for how
this comes about on the Fulfilment Planning board.

### When AutoCount's linkage overrides this page

AutoCount's own linkage is always followed, including over a link made by hand and even when
another sales order's row is already holding that document.

* **If a buyer re-points a purchase order line to another sales order in AutoCount**, the link
  follows on the next push - nobody has to relink anything on Order Inquiries. This happens even
  when the goods have already arrived: a document that is already fully received still moves if
  AutoCount now states it belongs to a different sales order line.
  * The old row's quantity carries the word **note**, and the note records the move: which
    document, which sales order it went to, and the date.
  * The document itself now appears on the new sales order's own inquiry row, showing as
    received if it already was.
  * If AutoCount clears the reference instead of moving it, the link is removed the same way,
    with the same **note** mark.
* **If AutoCount's linkage for a row points at a document another sales order's row is already
  holding**, that other row loses only the part of the document it does not need to keep,
  whether its own link was made automatically or by hand. It gets a **note** naming the
  document, the sales order the document went to, the date and what triggered the move, and it
  is offered other supply automatically so it is not left empty. A row of the same sales order
  line is never touched this way - if another row of SO421886's own C-FHSS14 line already holds
  SPO-2026/09-0036, nothing moves.

### A row that is already fully linked

AutoCount's linkage fills in a row's PO/SPO only where it still has need left. A row that is
already linked for its whole quantity is left exactly as it is, even if the document it names is
not the one AutoCount now states for that sales order line. To correct such a row, use
**Unlink selected** (or **Unlink all...**) to take the link off; the next automatic pass links it
to AutoCount's own document.

### Frequently asked

* **Why did my row lose its PO/SPO?** Read the **note** beside the quantity. It names the
  document and the sales order AutoCount moved it to, and the date. AutoCount stated that
  document is now for another sales order's line, and AutoCount's own linkage is always
  followed.
* **Why does the PO say "via SPO"?** The purchase order was turned into a shipping order in
  AutoCount, so the row now shows the shipping order in the SPO column with the purchase order
  beside it marked **via SPO**.
* **The Supplier column used to say "Not linked" on an SPO row.** It now shows that shipping
  order's supplier instead, for any row whose only link is a shipping order.
* **I linked it by hand and it moved.** AutoCount's own linkage always wins, including over a
  link you made by hand. If AutoCount states that document is for another sales order's row,
  your row's link moves and carries a note saying so.

### Ticking rows and Actions

Every row can be ticked, except a cancelled one. Open **Actions** to see what the ticked rows can
do; each item counts only the rows it applies to, for example **Link selected (2 of 3)**:

* **Auto link all...** links every eligible row on the whole list, not only the ticked ones.
* **Choose document (1)** needs exactly one ticked row; it opens **Link to a document** so you can
  pick the PO or SPO by hand.
* **Link selected** auto-links the ticked rows that still have something left to link.
* **Unlink selected** takes a link off the ticked rows, including a row that is already fully
  linked.
* **Reject selected**, **Unlink all...**, **Upload purchase orders** and **Export Excel** round
  out the menu.

Use **Auto link all...**, **Choose document (1)**, **Link selected** and **Unlink selected** to
review and fix a row's PO/SPO link before you confirm it - AutoCount's own linkage and the
cascade already linked what they could when the row was raised, so most of what is left is a
wrong pick to correct by hand. Once you have placed or linked the documents directly in
AutoCount, the linkage reaches this page on its own within a minute; **Upload purchase orders**
and **Auto link all...** are there for re-syncing a whole file or the whole list in one go.

### Confirming a row

Once a row's link reads right, tick it and press the page's primary **Confirm (N)** button -
disabled until at least one row is ticked. To confirm many rows at once, tick lines one by one,
or tick the header to select the page and take **Select all N records** to reach every row
matching your current filters, not only the ones on screen, before pressing **Confirm (N)**. A
dialog states the count; press **Confirm** to write it.

A confirmed row leaves **To confirm** without a reload, and the **To confirm** tile's count drops
to match. Rejected and cancelled rows are skipped even if ticked, and the toast tells you how
many rows were confirmed and how many were skipped. Only confirmed rows are counted by reorder
planning - a row still on **To confirm**, or one that has come back as **Changed**, is left out
until you confirm it.

If CS changes a line you already confirmed - its quantity or delivery date - the row comes back
onto **To confirm** marked **Changed**, showing what it was and what it is now. Confirm it again
once you are happy with the new figures.

The first time this confirm step went live, rows that had already come in from the order inquiry
sheet Excel started out already confirmed; only rows raised from Fulfilment Planning needed your
first confirm.

### Schedule view

Switch to **Schedule** for the same search box, **Filters** and month tabs, above a matrix of
**Rows** (Product, Sales order, Customer or Agent) by **By** (day, week, month or year). Every
month shows, next year included. Click a cell to open the rows behind it.

### Planning from here

Ticking sales orders and running **Plan selected** from **Sales Orders** opens the Fulfilment
Planning board on its **List** view. One search box, beside the title, filters both **List** and
**Grid**; the panel's own search box is gone.

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
  worklist. The row carries the sheet's own delivery date, and the sales order line's only
  when the sheet gives none. A date typed as text such as `1.6.2026` counts too, day first.
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

Eight tiles:

| Tile | Reads |
| --- | --- |
| **Rows** | Every row read off every tab. |
| **Will raise** | Rows that will become an order inquiry. |
| **Already raised** | Rows whose sales order line already carries an order inquiry. Those lines are left exactly as they are, links included. |
| **Dates corrected** | Of those, rows that will correct a migrated row's delivery date to the sheet's own - never a new row, and never a line CS or purchasing has since amended. |
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
  re-uploading the same sheet writes nothing new: every row comes back under **Already
  raised**, except that a corrected delivery date still fixes a migrated row's date and the
  Was/Now of the row raised beside it, on any later sheet, not only the one that first
  migrated it - including when a planning change already amended the row itself, in which
  case it is the row's own Was date that is corrected, never its current one.
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

Open **Procurement → Supply Chain → [Order Inquiries](/project-sales/order-inquiries)**. A
migrated row is confirmed the moment it is raised, so it will not show on the page's default **To
confirm** view - set the **Confirmed** filter to **Confirmed** or **All** to find it. Each row
carries the quantity, delivery date and stock location the sheet stated, the instruction it was
raised with, and the note naming the file it came from.

### Who can upload it

Anybody who can run a reorder plan.

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
* [Plan a sales order nobody decided](plan-undecided-lines.md) (raises a Buy onto Order
  Inquiries as an ORDER row)
* [Buy and borrow decisions on Fulfilment Planning](local-buy-and-borrow-source.md) (the board an
  Order Inquiries row can be worked from)
* [Sales order changes after planning](sales-order-changes.md) (how a row ends up marked `used`,
  with a fresh row raised in its place)
