# Chatbot - outstanding report (sales order backlog and delivery order pending)

Use this when a WhatsApp contact asks about outstanding quantity for a product - "SRTWT7445
outstanding", "SRTWT7443 sales order outstanding for IB", "SRTWT7445 outstanding in 2026". The
bot answers with one report: how much has been ordered but not yet moved to a delivery order,
and how much has a delivery order but has not yet been delivered.

## Why there are two numbers

"Outstanding" means two different things at Sorento, and both matter because a delivery order
is raised before the goods actually leave:

* **Sales order outstanding** - what a customer has ordered that has not yet been transferred
  to a delivery order at all. This is the sales order backlog.
* **Delivery order pending** - what already has a delivery order raised, but the goods have
  not yet gone out the door.

The bot always names which one it is answering. It never prints the bare word "outstanding" as
a heading.

## How to ask

* **A product code plus the word "outstanding"** (or "o/s", or "backlog"). A product code is
  required - a customer-only ask with no product stays on the older order answer, not this
  report.
* **A scope word** picks which number you want:
  * "sales order" or "SO" - sales order outstanding only.
  * "delivery order" or "DO" - delivery order pending only.
  * "both" - both blocks.
  * No scope word at all - the bot asks (see "The scope question" below).
* **A location word.** A word ending in a warehouse suffix, e.g. "IB", matches every warehouse
  code ending in `-IB` (`BRW-IB`, `MWH-IB`, and so on) and every matching code is printed next
  to it. An exact warehouse code, e.g. "BRW", matches only that code.
* **A customer name.** Filters the report to that customer.
* **A date, or a year.** Filters sales orders and delivery orders to that order-date window.
  **No date means all dates** - the report prints `Order date: all`.

## The scope question

If the message names a product with the word "outstanding" but no scope word, and the contact
is allowed to see sales order figures, the bot asks one question before running anything:

> Product: SRTWT7445
> Outstanding for which document?
> 1. Sales orders (not yet transferred to DO)
> 2. Delivery orders (not yet delivered)
> 3. Both

Answer with the number, or the word itself ("sales orders", "delivery orders", "both"). The
report then runs with the same product, date window, customer and location already given in
the first message - nothing needs to be repeated.

## Reading the report

Every reply opens with a four-line header echoing what was understood:

> Product: SRTWT7445
> Customer: all
> Location: IB (BRW-IB, MWH-IB)
> Order date: 01/01/2026 to 31/12/2026

`Customer` reads `all` when no customer was named. `Location` reads `all` when no location word
was given, an exact code alone when one was, or the token plus every code it resolved to in
brackets when it was a suffix. `Order date` reads `all` when no date was given, or an exact
range `dd/mm/yyyy to dd/mm/yyyy`.

Then one or both blocks, depending on scope:

> *Sales order outstanding*
> Ordered: 2,411
> Transferred to DO: 0
> Outstanding: 2,411
> Sales orders: 12
> Order date range: 05/01/2026 to 28/08/2026
> *_By location_*
> BRW-IB: 1,200 (O/S: 1,200)
> MWH-IB: 1,211 (O/S: 1,211)
> *_By customer_*
> Dealer A Sdn Bhd: 900 (O/S: 900)
> Dealer B Trading: 811 (O/S: 811)
> Dealer C Hardware: 700 (O/S: 700)

`Ordered` is everything the sales order lines carry; `Transferred to DO` is how much of that has
already moved to a delivery order; `Outstanding` is the rest. **Ordered always equals
Transferred to DO plus Outstanding** - the same three numbers, one population, so they always
add up.

The delivery order block reads the same way, with its own identity:

> *Delivery order pending*
> DO qty: 640
> Delivered: 0
> Pending: 640
> Delivery orders: 3
> DO date range: 03/02/2026 to 30/08/2026
> *_By location_*
> BRW-IB: 640 (O/S: 640)
> *_By customer_*
> Dealer A Sdn Bhd: 640 (O/S: 640)

`DO qty` always equals `Delivered` plus `Pending`.

Each block's own `By location` and `By customer` lines break its own total down, and every one
of those lines ends in `(O/S: n)` - the outstanding quantity for a sales order line, or the
pending quantity for a delivery order line, at that location or customer. Nothing is ever
shortened with "+N more" and no row is ever left out.

If a scope has nothing open, its block prints one line instead: `No open sales order.` or
`No pending delivery order.`

## Getting the detail behind a number

After a report with at least one non-empty block, the bot offers a numbered detail pick,
listing only the scopes that had rows:

> Reply with a number for detail:
> 1. Sales order list
> 2. Delivery order list

Reply "1" for the sales order list - one row per sales order (its lines rolled up into one),
each row:

> 1. *SO Number:* SO331785
> *Customer:* Dealer A Sdn Bhd
> *Location:* BRW-BB
> *Ordered:* 410
> *Transferred to DO:* 0
> *Outstanding:* 410
> *Order Date:* 20/12/2024

Reply "2" for the delivery order list - one row per delivery order:

> 1. *DO Number:* DO220456
> *Customer:* Dealer A Sdn Bhd
> *Location:* BRW-IB
> *DO Qty:* 640
> *Delivered:* 0
> *Pending:* 640
> *DO Date:* 03/02/2026

Every matching row is sent; long lists are chunked into several WhatsApp messages the way any
long chatbot reply is, not shortened.

## A miss

When neither requested scope has anything open, the report still prints its header and its
"No open sales order." / "No pending delivery order." lines, then the bot offers to escalate to
the Sorento customer service team. The offer arrives with the numbered list of who it can be
routed to, and a reply of "yes" (no name picked) assigns automatically - the same escalate
offer the bot uses whenever any question comes up empty.

## Access: who can see sales order figures

**Everyone with order enquiries access sees delivery order pending figures** - that half of the
report is on by default, the same as today.

**Sales order figures are gated separately**, per contact, on that contact's own record: open
the contact, go to **Access**, and on the **Field reveals** card tick **Sales order outstanding**.

Without that grant:

* The scope question is never asked - there is nothing to choose, so the report simply runs
  against delivery orders only.
* Asking for sales orders explicitly (the word "SO" / "sales order", or picking "Both") gets one
  extra line after the four header lines and before the delivery order block:
  `Sales order figures are not enabled for your account.` - then the delivery order pending
  block runs as normal.

**Field reveals** is the same card that also gates the chatbot's last purchase cost answer and
PO supplier answer - one screen, one switch per restricted answer, each off by default until an
admin ticks it for that contact.

## See also

* [Chatbot - "last purchase cost" answer](chatbot-last-purchase-cost.md)
* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md)
* [System Management - Data reference for admins](data-analysis.md)
