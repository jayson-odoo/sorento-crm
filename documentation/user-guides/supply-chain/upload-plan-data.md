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
is under **Actions** on **[Supply Chain → Orders → Sales Orders](/scm/sales-orders)**, and
**Upload purchase orders** is under **Actions** on
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

Open **Procurement → Supply Chain → [Order Inquiries](/project-sales/order-inquiries)**. This
worklist - one row per order inquiry line - is what replaces the monthly order-book Excel. It now
sits behind the **Lines** toggle top right of the page (**Documents** opens by default; see
[Order inquiries: the Documents view and the OI detail
page](order-inquiry-documents.md) for the header list and the per-order-inquiry detail page). Once
you are on **Lines**, a **List** / **Schedule** toggle sits above the grid. There is no "Plan
until" line on the page any more - the cut-off date that used to show there now lives inside the
**Auto link all...** dialog.

The **Lines** view opens on **To confirm**: every row CS has raised that you have not yet signed
off. See "Confirming a row" below for what that means and how it works.

### Stage cards

Three cards sit above the grid: **Buy**, **Purchased**, **Incoming**. Every unit is counted in one
card only, the furthest it has reached:

* **Buy** - nothing bought yet.
* **Purchased** - on a purchase order, its container not booked yet.
* **Incoming** - on a shipping order, either linked to the row directly or found through the
  purchase order the row is linked to.

Click a card to filter the grid to that stage. A row marked `used` (see "A row already covered
by stock" below) never counts toward any of the three cards, or toward the Schedule matrix
cards, so the card totals and what you see when you click into one always agree. A row whose
sales order line has been cancelled (see "A row on a cancelled line" below) drops out of **Buy**
only - if it already holds a purchase order or shipping order link, it still counts in
**Purchased** or **Incoming**.

A fourth tile, **To confirm**, sits beside the three stage cards. It shows how many rows are
still waiting on your sign-off; click it to return to the To confirm view from anywhere else on
the page. Click it a second time to leave that filter, the same as pressing **Buy**,
**Purchased** or **Incoming** a second time. See "Confirming a row" below.

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

When the same sales order line was raised before, an info icon sits beside its **Raised at**
date - a re-confirm cancels the earlier row and raises a new one, so the date you see moved on
too. Hover the icon for **Previously raised**, listing each earlier raise with its time and who
confirmed it, newest first. A row raised for the first time shows no icon.

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

The default column order mirrors the Excel order book: **SO date**, **S/O line**, **Item code**,
**Qty**, **Taken**, **Remaining**, **Delivery date**, **Customer**, **Project**, **Supplier**,
**PO**, **SPO**, **Agent**, **Location**, **Order inquiry**, then the rest. **S/O line** prints
the sales order number and its line together, e.g. `SO402757 · L5`, and is a link straight to
that exact line on the sales order (this column's own Excel export still heads it **S/O NO**, so
a sheet you download stays lined up with the original order book). **Taken** is how much of the
row's own quantity is already on a PO or SPO link; **Remaining** is Qty minus Taken, minus
anything covered by an **Included with** companion (see below) - both print a dash on a notice
row, and both read as nothing owed on a row whose sales order line is cancelled. **Customer** and
**Project** sort independently of each other. A pre-order shows **PRE-ORDER** in the **Project**
cell. Every row of one sales order now sits under one order inquiry number, so the **Order
inquiry** column is hidden by default - open **Columns** in the toolbar and tick it to show it.
If you have already personalised your own column order or visibility, yours is kept.

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

A used row lands on **To confirm** once, the moment it becomes used - whether that happens on a
replan or because a sheet re-upload rebuilds it. See "Confirming a row" below for what confirming
it does.

A row **Included with** another item (a "supplied with" companion, like a seat cover that ships
inside its pedestal and cistern) carries no Was of its own, so its Qty cell's (i) lists each of
those items' own change instead - hover it for one line per item, e.g. "with SRTWCX8605-S-RL-PJ:
Was 182 on 01/06/2026, now 280 on 01/03/2027".

### A date move on a line already bought

When the book moves a line's delivery date and you have already been asked to buy for that line,
the row you already know is restated in place - the same row, never a second one. Its **Delivery
date** carries a **Changed** tag, and its Qty **(i)** reads **Was** the old quantity and date, the
same as any other changed row. Every PO/SPO link the row already held stays exactly as it was.
Only a line with nothing bought for it yet gets an ordinary new row instead.

### A row on a cancelled line

A sales order line can be cancelled without anyone telling purchasing directly - an edit on the
sales order, a cancellation pushed from AutoCount, or a sales order deleted in AutoCount. When
that happens, every live row of that line is greyed the same way a **used** row is, and its Qty
cell carries a plain `cancelled` tag beside the quantity. A row that is both **used** and on a
cancelled line shows both.

* It drops out of the **Buy** card and the **Buy** figure - purchasing is no longer asked to buy
  for a line nobody wants any more.
* If it already holds a purchase order or shipping order link, that link is left alone and the
  row still counts in **Purchased** or **Incoming** - the system does not decide whether to keep
  or drop that link; that stays purchasing's call.
* The row lands on **To confirm** once, so purchasing sees it. Ticking it and pressing
  **Confirm** means "seen": the row itself is not cancelled, it stays on the list, still greyed
  and still tagged `cancelled`, and simply leaves **To confirm**. Nothing about its quantity,
  links or state changes.

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
* **Why is a row grey with a `cancelled` tag?** The sales order line it sits on has been
  cancelled - by an edit on the sales order, or by AutoCount. See "A row on a cancelled line"
  above.
* **Do I need to cancel the PO linked to it?** No. The system leaves any purchase order or
  shipping order link exactly as it is; whether to cancel or reuse it is your call.
* **Why did To confirm suddenly fill up?** The first time this change went live, every existing
  row on a cancelled line and every existing used row landed on **To confirm** once, so purchasing
  could see them and sign off. Tick **Select all N records** and press **Confirm (N)** to clear
  them in one go; after that, only the rows that newly become cancelled or used arrive there.

### Ticking rows and Actions

Every row can be ticked, except one whose own state is cancelled. A **used** row and a row on a
cancelled line stay tickable - see "A row on a cancelled line" above. Open **Actions** to see
what the ticked rows can do; each item counts only the rows it applies to, for example
**Link selected (2 of 3)**:

* **Auto link all...** links every eligible row on the whole list, not only the ticked ones.
* **Choose document (1)** needs exactly one ticked row; it opens **Link to a document** so you can
  pick the PO or SPO by hand.
* **Link selected** auto-links the ticked rows that still have something left to link.
* **Unlink selected** takes a link off the ticked rows, including a row that is already fully
  linked.
* **Reject selected**, **Unconfirm**, **Unlink all...** and **Upload purchase orders** round out
  the menu. See "Unconfirming a row" below for what **Unconfirm** does.

**Export Excel** queues a workbook of the current filters instead of downloading one straight
away: a toast reads "Preparing the order inquiry export - it will appear in My Downloads.", and
the file lands in **My Downloads** once it is ready. Pressing it again while one is still being
prepared does nothing but tell you it already is, with a toast reading "An order inquiry export
is already being prepared - check My Downloads." Unlike the OI detail page's own **Export Excel**
(see [The Documents view and the OI detail
page](order-inquiry-documents.md#fixing-a-link-without-leaving-the-page)), this export is not
tied to one order inquiry, so there is no download history for it - only **My Downloads**. Needs
the **Order Inquiries** view permission and a signed-in user.

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
to match. Rejected rows, and a row whose own state is cancelled, are skipped even if ticked, and
the toast tells you how many rows were confirmed and how many were skipped. Only confirmed rows
are counted by reorder planning - a row still on **To confirm**, or one that has come back as
**Changed**, is left out until you confirm it.

A **used** row and a row on a cancelled line (see "A row already covered by stock" and "A row on
a cancelled line" above) are ticked and confirmed the same way as any other row - their checkbox
is enabled. These are not "cancelled rows" in the sense above: confirming one only marks it seen
and does not touch its state, quantity or links.

If CS changes a line you already confirmed - its quantity or delivery date - the row comes back
onto **To confirm** marked **Changed**, showing what it was and what it is now. Confirm it again
once you are happy with the new figures.

The first time this confirm step went live, rows that had already come in from the order inquiry
sheet Excel started out already confirmed; only rows raised from Fulfilment Planning needed your
first confirm.

### Unconfirming a row

Took on a row by mistake, or want to hold it until a reconfirm CS has not actually made yet? Tick
**Confirmed** or **Changed** rows and open **Actions → Unconfirm** to put them back on **To
confirm**. The confirmer's name and time are cleared, no email goes out, and a plain **Confirm**
reverses it. A row still on **To confirm**, or one already **Rejected** or cancelled, is skipped
even if ticked, and the toast counts how many rows went back and how many were skipped.
**Unconfirm** needs the same permission as **Confirm**.

An unconfirmed row is not counted by reorder planning until it is confirmed again.

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
on. Load the whole workbook, not just this month's tab - every tab with a recognisable header row
is read - but only an order's still-open lines can take a row: a closed sales order, or one whose
lines are all closed or cancelled, has nothing left to pair a row to (see "Rows with no matching
line" below).

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
  this item at that stock location", "Quantity exceeds what the line ordered", or, when every
  line of the order is closed or cancelled, "No open line left: every line is closed or
  cancelled".

A list with nothing in it is absent rather than shown empty. **Confirm upload** is disabled when
**Will raise** is 0: there is nothing left for it to do, and pressing it would only queue a job
that writes nothing.

### What gets created

* **One order inquiry row per sheet row**, paired within its own sales order to an open line by
  date: every open line sorted by its own required date, this upload's own sheet rows for that
  order sorted by delivery date, matched earliest to earliest, one each. Item and stock location
  still have to fit; a line with no warehouse of its own accepts any stock location. A line's own
  ordered quantity does not stop the pairing - a row bigger (or smaller) than what the line
  ordered still lands there, and the difference shows as the usual "Was {qty} on {date}" note;
  only a row bigger than everything the order has left open in total is refused as exceeding the
  order.
* **A closed or cancelled line is never paired.** Only an order's still-open lines are
  candidates.
* **A second sheet row for the same item becomes a second row** on the line its date order gives
  it, once every open line already has one row from this upload - the sheet is what splits a
  line, never the upload.
* **The upload never creates a sales order or a sales order line**, and never writes a location
  onto one. AutoCount owns the order book.
* **A row the sheet raises onto a line that is already cancelled** lands on **To confirm**
  straight away instead of starting confirmed, the same as a fresh used row does - see
  "A row on a cancelled line" above.
* **A line that already carries an order inquiry is skipped**, whoever raised it. So
  re-uploading the same sheet writes nothing new: every row comes back under **Already
  raised**, except that a corrected delivery date still fixes a migrated row's date and the
  Was/Now of the row raised beside it, on any later sheet, not only the one that first
  migrated it - including when a planning change already amended the row itself, in which
  case it is the row's own Was date that is corrected, never its current one, and including
  the row that replaced a migrated row a later reconfirm superseded, where the sheet's own
  row becomes the Was it never got.
* Each raised row carries the note **Migrated from order inquiry sheet** followed by the file
  name, so you can tell it from a row the board raised. Read it from the info icon in the
  **Instruction** column.
* A row on a line that was already delivered is filed as answered, with its links intact. It
  stays on the worklist to be read, but purchasing is not asked to buy the goods again, and
  ticking it for a bulk action says "This row has already been answered".

### What a re-upload rebuilds

Purchasing keeps the book; customer service plans supply against it on Fulfilment Planning. Once
CS has acted on a line, re-uploading the sheet later (after a rollback, for example - see
"Rolling an upload back" below) rebuilds what CS did rather than overwriting it:

* **A line whose delivery already arrived** comes back exactly as it was: the sheet's row for
  that delivery is raised as the greyed **used** row again, carrying its received document,
  rather than skipped or raised plain, and it lands on **To confirm** again for you to sign off.
  CS's own fresh row for the line is not re-raised by the upload itself; that is the plan's own
  doing, not the sheet's.
* **A line CS has since confirmed a different quantity or date for** comes back already settled
  to what CS decided, with the sheet's own figure kept as the Was.
* **A line CS planned entirely from stock** (nothing bought against it) comes back plain, exactly
  as the sheet states it - it is never given a false Was/Now.
* **A DELAY notice** (or any notice that isn't itself the buy) a confirm raised beside the line's
  own row is left untouched either way; it never stands in for the row itself, so the row beside
  it still rebuilds as above.
* **A top-up CS added on top of the sheet's own quantity** leaves the sheet's row plain, once the
  sheet's quantity plus the top-up together add up to what CS decided to buy for the line.
* **More than one sheet row landing on the same line CS has already planned** are all raised
  plain, the same as an ordinary upload - the rebuild never guesses which row a decision belongs
  to when there is more than one candidate for it.

### When it will not guess

The rebuild above only fires on an exact match. When it cannot find one, it raises nothing for
that row and, on the Test preview, counts it under its own warning:

> N rows could not be matched automatically and need a person's eye (a used-row or top-up line
> whose quantity or date does not line up exactly)

This happens when:

* **a delivery's quantity or date no longer matches any of CS's planned deliveries** - usually
  because the sheet or the plan was corrected after CS worked the line;
* **a top-up line's quantities don't add up** to what CS decided to buy for the line in total.

The Test preview only counts these rows; to see which row by name, click **Confirm upload** and
check **[System Management → Import Jobs](/system-management/import-jobs)**, where each is
labelled **Beside a used-row line, but no exact quantity/date match** or **Beside a top-up line,
but the quantities do not sum to plan**. Check the named row against the plan on Fulfilment
Planning or the sales order line on Order Inquiries, fix whichever side is wrong, and upload the
sheet again - the rebuild reads it fresh every time, so there is nothing else to do once the two
agree.

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

Open **Procurement → Supply Chain → [Order Inquiries](/project-sales/order-inquiries)**, then
switch to **Lines**. An ordinary migrated row is confirmed the moment it is raised, so it will not
show on the **Lines** view's default **To confirm** filter - set the **Confirmed** filter to
**Confirmed** or **All** to find it.
The two exceptions land on **To confirm** instead, needing your sign-off: a row rebuilt as
**used** (see "A row already covered by stock" above), and a row landing on a line that is
already cancelled (see "A row on a cancelled line" above). Each row carries the quantity, delivery
date and stock location the sheet stated, the instruction it was raised with, and the note naming
the file it came from.

### Rolling an upload back

If a mistaken upload has to be taken back out, for example after an importer fix ships and the
file needs re-loading, an operator runs a rollback from the command line - there is nothing to
click in the CRM for this. A rollback no longer removes a row Fulfilment Planning has since
worked on. It keeps:

* a **used** row, with its received document;
* a row CS has already confirmed a different quantity or date for;
* a top-up row;
* and any other sheet row sitting on the same sales order line as one of the above, even one
  that carries none of those marks itself.

Always run it as a dry run first (its default) and read what it reports before re-running to
apply it. Both the dry run and the real run report the same two counts either way: how many rows
it would remove, and how many it keeps - and for every kept row, the sales order, item,
quantity, date and which of the reasons above kept it.

Run a rollback when customer service is not in the middle of confirming a plan on one of these
rows: a confirm on a row the rollback is checking waits until the rollback has finished.

### Uploading the same book twice

Once nothing on it has changed, uploading the same book a second time writes nothing new -
every row, rebuilt rows included, comes back under **Already raised**.

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

* [Order inquiries: the Documents view and the OI detail page](order-inquiry-documents.md)
* [Run a reorder plan](run-a-reorder-plan.md)
* [Print the order summary](print-the-order-summary.md) (its "OI worksheet Excel" prints this
  worklist's own ORDER INQUIRY layout, scoped to a reorder plan instead of this page's filters)
* [Upload SPO allocations](../purchasing/upload-spo.md)
* [Upload the product master](../purchasing/upload-product-master.md)
* [Plan a sales order nobody decided](plan-undecided-lines.md) (raises a Buy onto Order
  Inquiries as an ORDER row)
* [Buy and borrow decisions on Fulfilment Planning](local-buy-and-borrow-source.md) (the board an
  Order Inquiries row can be worked from)
* [Sales order changes after planning](sales-order-changes.md) (how a row ends up marked `used`,
  with a fresh row raised in its place)
