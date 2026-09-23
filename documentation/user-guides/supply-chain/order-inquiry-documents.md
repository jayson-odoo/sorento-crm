# Supply Chain - Order inquiries: the Documents view and the OI detail page

Use this when you want to see order inquiries one document at a time - one row per sales order's
whole set of instructions, its own number, its own raised date, and how much of it still waits on
you - rather than the line-by-line worklist. This is what **Procurement → Supply Chain →
[Order Inquiries](/project-sales/order-inquiries)** opens on now.

## Where

Open **Procurement → Supply Chain → [Order Inquiries](/project-sales/order-inquiries)**. A
**Documents** / **Lines** toggle sits top right of the page, **Documents** selected by default.
**Lines** is today's worklist, unchanged - cards, month chips, filters, bulk actions, upload,
export - described in full in [Upload the data a reorder plan is built
from](upload-plan-data.md#the-order-inquiries-page). Your choice of view is kept in the URL, so a
link you send someone opens on the same view you were on.

## The Documents view

The grid shows one row per order inquiry - one order inquiry per sales order. Rows are ordered
oldest raised first by default.

An **All** / **Outstanding** / **Completed** toggle sits in the toolbar, **Outstanding** selected
by default. **Completed** means every line of that order inquiry has been confirmed (a cancelled
line does not count against it); when CS changes or adds a line later, the order inquiry returns
to **Outstanding**.

Columns, in order: **Raised at**, **OI no**, **S/O no**, **Raised by**, **Lines**, **Qty**,
**Customer**, **Project**, **Agent**, **SO date**, **Status**.

* **Status** shows as a badge, **Outstanding** or **Completed**.
* **Lines** shows the total line count; on an Outstanding row, hover it to read how many of those
  lines still wait for a confirm against the total.
* **S/O no** is its own link, straight to that sales order.
* Clicking anywhere else on the row opens the order inquiry itself.

**Search** matches the OI number (an old-format number still finds it too, so a number already
quoted in an email keeps working), the sales order number, the customer, the project, the agent,
and the product code or location of any line inside that order inquiry.

**Filters** narrows by **Raised by**, **Agent** and **Project**, each a clearable dropdown.

An empty **Outstanding** view reads "Nothing to confirm" with a button to switch to **All**. An
empty **All** view reads "No order inquiries yet". A search or filter with no matches reads "No
order inquiry matches this search and filter."

## The OI number

Every order inquiry now carries a number of the shape **OI-YYMM-NNNN** - the year and month it was
first raised in, then a running number that starts again at 0001 each month. The number is fixed
for life: reconfirming an order inquiry in a later month never changes it. Every order inquiry
that already existed when this shipped was given one of these numbers; its old number still finds
it through search, so a number already quoted in an old email or conversation keeps working.

## Raised at / Raised by

**Raised at** and **Raised by** are set once, the first time the order inquiry is raised, and
never change afterwards - even when CS reconfirms the sales order later. Every reconfirm is
recorded instead, on the **General** tab's **Raise history** (see below), so nothing about who
raised it or when is lost.

## Opening an order inquiry

Click a row to open the order inquiry. The header shows the OI number, its status badge, who
raised it and when ("Raised by Eling on 08/09/2026, 1:17 pm"), a pager that walks the same list you
came from (previous / next, "n / total"), a gear menu, and one primary button, **Confirm**. A
**Back to order inquiries** button sits top right.

If the order inquiry no longer exists (it was deleted, or you followed a stale link), the page
reads "This order inquiry no longer exists" with a button back to the list.

### Tabs

Tabs, in order: **Lines**, **General**, **Related PO**, **Related SPO**. **Lines** is the tab the
page opens on.

**Lines** - one row per line: **Product** (the product code, nothing else - in Sorento the code
is the product name), **SO line** (a link to that exact line on the sales order, e.g.
`SO402757 · L5`), **Qty** (the same **(i)** you know from the worklist when a line's quantity or
date changed), **Taken**, **Remaining**, **Delivery date**, **Supplier**, **PO**, **SPO**,
**Location**, **Instruction**, **State**, **Reserve**. Cancelled lines are hidden, the same as on
the worklist. A checkbox column lets you tick lines; a search box narrows by product; **Columns**
lets you show or hide columns, Taken and Remaining included; the footer totals **Qty**, **Taken**
and **Remaining**. Clicking a **PO** or **SPO** number opens the same **Backing documents**
lightbox as the worklist.

**Reserve** carries nothing on a line that has never been asked to be reserved. It shows an amber
icon reading **Request to reserve** once purchasing has asked, or a green icon reading **Reserved
\<qty\>** once CS has answered - see [Ask CS to reserve stock](#ask-cs-to-reserve-stock) and
[Reserve for purchasing](#reserve-for-purchasing-cs) below.

**Taken** is how much of the line's own quantity is already on a PO or SPO link. **Remaining** is
Qty minus Taken, minus anything already covered by an **Included with** companion (see [Upload
the data a reorder plan is built from](upload-plan-data.md#the-order-inquiries-page)). Both print
a dash on a row that is only a notice (not itself a buy), and both read as if nothing were owed -
Remaining `0` - on a row on a cancelled sales order line or a cancelled row, which the footer
leaves out entirely.

When CS moves the date on a line you have already been asked to buy, the same row is restated in
place - never a second row. You see a **Changed** tag beside the **Delivery date**, and the **(i)**
on **Qty** reads what it was, for example "Was 100 on 01/11/2026". Every PO/SPO link the row
already carried stays exactly as it was.

**General** - an **Order** card (S/O no as a link, SO date, Agent, Project, Order type), a
**Customer** card (Customer, Customer code), and a **Raise history** card: one entry per raise,
newest first, each showing whether it was the original **Raised** or a later **Reconfirmed**, who,
and when.

**Related PO** - one row per purchase order any line of this order inquiry is linked to: **PO no**
(a link to that purchase order), **Supplier**, **PO date**, **Lines linked**, **Qty linked**, with
a footer total under **Qty linked**. Reads "No purchase orders linked yet" when there is nothing
to show.

**Related SPO** - the same, for shipping orders: **SPO no** (a link to that shipping order),
**Supplier**, **Lines linked**, **Qty linked**, with a footer total. Reads "No SPOs linked yet"
when there is nothing to show.

### What the State column means

**State** reads what you still need to do with the row, the same word wherever else it shows (the
worklist, the board):

* **To buy** - nothing bought for it yet.
* **Partly on PO/SPO** - part of the quantity is on a purchase order or shipping order, part
  isn't yet.
* **On PO/SPO** - the whole quantity is on a purchase order or shipping order.
* **Done** - you've actioned the row; there's nothing left to do.
* **Cancelled** - the instruction was called off.

## Confirming

Press **Confirm**. With nothing ticked, it confirms every line still waiting in the whole order
inquiry; with lines ticked, it confirms only those. It reads **Confirm (n)** once lines are
ticked, and is disabled when nothing in scope is waiting on a confirm. Once every line is
confirmed, the order inquiry's status turns **Completed** and it drops off the **Outstanding**
view.

## Ask CS to reserve stock

Use this when you want CS to cover part of a line from stock they already hold before you buy
the balance.

1. On the **Lines** tab, tick one or more rows still open for it - an **ORDER** or **ORDER BACK**
   row with something left in **Remaining** and no reserve request already open on it. A row that
   doesn't qualify greys out **Request CS to reserve** in the gear menu with a tooltip naming why.
2. Open the gear menu and choose **Request CS to reserve**.
3. The **Request CS to reserve** dialog lists one card per selected row: item code, delivery date
   and what's left to request, a **Requested** number (defaults to the remaining, never higher),
   and a **Location** (defaults to the configured pool - see [Default location for the Reserve
   dialog](order-inquiry-reserve-email.md#default-location-for-the-reserve-dialog)). An optional
   **Note** sits below the rows, for the whole request.
4. Press **Send request**. A toast reads `Request #<n> sent to <name>`.

The rows now carry an amber **Reserve** icon reading **Request to reserve**, and the order
inquiry's header carries a **Request to reserve** badge while any request is open. One email
leaves for CS - see [Reserve request and reserved-stock emails](order-inquiry-reserve-email.md).

To pull a request back, open the row's **Reserve** icon and press **Cancel request** in the
dialog header - a short countdown with **Cancel**, no email either way.

Once CS answers, the icon turns green and reads **Reserved \<qty\>**; **Taken** already counts
it and **Remaining** is the balance still to buy by PO or SPO, the same as today. You can ask CS
to reserve again on that balance the same way.

## Reserve for purchasing (CS)

Use this when purchasing has asked you to reserve stock against an order inquiry line, and you
hold the **Reserve Stock for Order Inquiries** permission.

1. Open the order inquiry from the request email's **Open in Order Inquiries** link (you'll need
   to be logged in), or open any row's **Reserve** icon on the Lines tab yourself. The link lands
   on the dialog for the request's first row still waiting for you.
2. On the **Reserve** tab: the request line (`Request #n - requested <qty> by <name> on <date>`),
   a **Location** (defaults to the configured pool or, if none is set, the row's own site pool -
   changing it re-reads what that location can give), and **Reserved** (defaults to what the
   chosen location has, never more than requested).
3. If **Reserved** is less than **Requested**, including 0, a **Reason** box appears and blocks
   the next step until filled.
4. Press **Confirm reserved**. A toast reads `Reserved, <requester> notified`.

The icon turns green and shows the reserved quantity; one email leaves for the requester - see
[Reserve request and reserved-stock emails](order-inquiry-reserve-email.md).

**History** tab, on the same dialog, lists every request, reserve and unreserve on that row,
newest first, with who did it and when.

Once a row has nothing open, its Reserve tab shows what's net reserved and, if you hold the
permission, an **Unreserve** control: enter a **Qty** (up to what's net reserved) and an optional
**Note**, press **Unreserve**. The button becomes a countdown; the release commits once it lapses
and cannot be undone after that. Unreserving releases the newest reserve on that row first, and
sends no email. Without the permission, the Reserve tab is read-only and Unreserve doesn't show,
though you can still read History.

**Unlink never touches a reserve.** Unlinking a row (per row, or **Unlink selected**) only takes
off a PO or SPO link; a reserve link isn't offered there at all. Undo a reserve with **Unreserve**
on that row's own dialog instead.

## Fixing a link without leaving the page

The gear menu carries the same link fixes you already use on the worklist, scoped to this order
inquiry:

* **Auto link** - runs the automatic link over the ticked lines, or over every line of this order
  inquiry when nothing is ticked.
* **Choose document** - needs exactly one line ticked; opens the same dialog the worklist uses to
  pick a PO or SPO by hand.
* **Link selected** - auto-links the ticked lines that still have something left to link.
* **Unlink selected** - takes the link off the ticked lines. This is a deferred action: the button
  turns into a countdown with **Cancel**, and the unlink only happens once the countdown runs out
  - there is no confirmation box. Cancelling leaves the ticked lines ticked; the selection only
  clears once the unlink actually commits. It never touches a reserve link - see [Reserve for
  purchasing](#reserve-for-purchasing-cs) above.
* **Reject selected**, **Unconfirm**, **Export Excel** round out the menu, the same as on the
  worklist.

**Export Excel** queues a workbook of this order inquiry rather than downloading one straight
away: a toast reads "Preparing the order inquiry export - it will appear in My Downloads.", and
the file lands in **My Downloads** once it is ready. Pressing **Export Excel** again while one is
still being prepared does nothing but tell you it already is, with a toast reading "An order
inquiry export is already being prepared - check My Downloads."

**Download history** opens the list of every Excel export made from this order inquiry, newest
first, so you can come back to it later and reopen a file you already made instead of exporting it
again.

## Prev / next

The pager beside the header walks the same filtered list you opened the order inquiry from - for
example, if you opened it from **Outstanding**, previous and next step through the other
Outstanding order inquiries in that same order.

## Emails and the sales order page

The order inquiry handover, changed and undone emails, the reserve request and reserved emails,
and the "Order inquiries" link on a sales order's own page, all now open straight to this order
inquiry's detail page.

## Admin: folding old duplicate date-move notices

Read this only if you administer the CRM directly. Before date moves settled in place (see "A
date change on a line you already asked purchasing to buy restates the same row", above), some
order inquiries were left with a duplicate: a live buy row sitting beside a separate notice row
saying the same date had moved. `scripts/fold_oi_date_notices.py` (run from `sorento_crm_backend/`)
finds and folds every one of those pairs, once.

1. Run it with no flags first - `venv/bin/python scripts/fold_oi_date_notices.py` - a dry run
   (the default) that only prints what it would do: which order inquiry, which item, and which
   buy row each notice would fold into. Nothing is written yet.
2. Run it again with `--apply` to actually fold them: each notice's date moves onto its buy row
   (with the old date kept as Was), and the notice itself is cancelled with a note saying it was
   folded.
3. Run the plain dry run one more time after `--apply`. A line that carried more than one
   chained notice only shows its next one as fold-able once the one before it has actually been
   folded, so a single dry-run-then-apply pass can still leave something to fold; a dry run
   afterwards confirms there's nothing left (or shows what's next).

The script is safe to re-run - a pair it already folded no longer matches, so running it again
reports nothing for it.

## How you'll be notified

The handover, changed and undone emails purchasing already receives (see [The order inquiry
handover email](order-inquiry-handover-email.md) and [Sales order changes after
planning](sales-order-changes.md)) keep going out the same way, their links now landing on this
page. A **Request CS to reserve** and a CS **Confirm reserved** each send their own email too -
see [Reserve request and reserved-stock emails](order-inquiry-reserve-email.md). Confirming,
unconfirming, sending a reserve request, cancelling one, reserving and unreserving all show an
on-screen toast. **Export Excel** shows a toast too, then the workbook appears in **My Downloads**
once it is ready, the same as the low stock report and the order summary sheet. Both the export
and the reserve actions need the **Order Inquiries** view permission and a signed-in user.

## See also

* [Upload the data a reorder plan is built from](upload-plan-data.md#the-order-inquiries-page)
  (the **Lines** worklist: stage cards, month tabs, filters, confirming and unconfirming a row,
  Schedule view, and the order inquiry sheet upload)
* [Sales order changes after planning](sales-order-changes.md)
* [The order inquiry handover email](order-inquiry-handover-email.md)
* [Reserve request and reserved-stock emails](order-inquiry-reserve-email.md) - the automations
  behind Ask CS to reserve stock / Reserve for purchasing, the default pool setting, and the
  permission needed to reserve.
* [Plan a sales order nobody decided](plan-undecided-lines.md)
