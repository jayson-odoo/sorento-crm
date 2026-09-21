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
is the product name), **Qty** (the same **(i)** you know from the worklist when a line's quantity
or date changed), **Delivery date**, **Supplier**, **PO**, **SPO**, **Location**, **Instruction**,
**State**. Cancelled lines are hidden, the same as on the worklist. A checkbox column lets you tick
lines; a search box narrows by product; **Columns** lets you show or hide columns; the footer
totals **Qty**. Clicking a **PO** or **SPO** number opens the same **Backing documents** lightbox
as the worklist.

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

## Confirming

Press **Confirm**. With nothing ticked, it confirms every line still waiting in the whole order
inquiry; with lines ticked, it confirms only those. It reads **Confirm (n)** once lines are
ticked, and is disabled when nothing in scope is waiting on a confirm. Once every line is
confirmed, the order inquiry's status turns **Completed** and it drops off the **Outstanding**
view.

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
  clears once the unlink actually commits.
* **Reject selected**, **Unconfirm**, **Export Excel** round out the menu, the same as on the
  worklist.

## Prev / next

The pager beside the header walks the same filtered list you opened the order inquiry from - for
example, if you opened it from **Outstanding**, previous and next step through the other
Outstanding order inquiries in that same order.

## Emails and the sales order page

The order inquiry handover, changed and undone emails, and the "Order inquiries" link on a sales
order's own page, all now open straight to this order inquiry's detail page.

## How you'll be notified

Nothing new here beyond what you already know: the handover, changed and undone emails purchasing
already receives (see [The order inquiry handover email](order-inquiry-handover-email.md) and
[Sales order changes after planning](sales-order-changes.md)) keep going out the same way, their
links now landing on this page. Confirming or unconfirming shows an on-screen toast, same as on
the worklist.

## See also

* [Upload the data a reorder plan is built from](upload-plan-data.md#the-order-inquiries-page)
  (the **Lines** worklist: stage cards, month tabs, filters, confirming and unconfirming a row,
  Schedule view, and the order inquiry sheet upload)
* [Sales order changes after planning](sales-order-changes.md)
* [The order inquiry handover email](order-inquiry-handover-email.md)
* [Plan a sales order nobody decided](plan-undecided-lines.md)
