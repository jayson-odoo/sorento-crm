# Chatbot - outstanding report (sales order backlog and delivery order outstanding)

Use this when a WhatsApp contact asks about outstanding quantity for a product, a customer, or both - "SRTWT7445 outstanding", "SRTWT7443 sales order outstanding for IB", "SRTWT7445 outstanding in 2026", or "outstanding dealer quantity for HANLIM". The bot answers with one report: how much has been ordered but not yet moved to a delivery order, and how much has a delivery order but has not yet been delivered.

## Why there are two numbers

"Outstanding" means two different things at Sorento, and both matter because a delivery order is raised before the goods actually leave:

* **Sales order outstanding** - what a customer has ordered that has not yet been transferred to a delivery order at all. This is the sales order backlog.
* **Delivery order outstanding** - what already has a delivery order raised, but the goods have not yet gone out the door.

The bot always names which one it is answering. It never prints the bare word "outstanding" as a heading.

## How to ask

* **A product code and/or a customer name, plus the word "outstanding"** (or "o/s", or "backlog"). You can ask for a product only, a customer only, or both. At least one of them is required.
* **A scope word** picks which number you want:
  * "sales order" or "SO" - sales order outstanding only.
  * "delivery order" or "DO" - delivery order outstanding only.
  * "both" - both blocks.
  * No scope word at all - the bot asks (see "The scope question" below).
* **A location word.** A word ending in a warehouse suffix (e.g. "IB") matches every warehouse code ending in that suffix (e.g. `-IB`: `BRW-IB`, `MWH-IB`). An exact warehouse code (e.g. "BRW") matches only that code.
* **A date or a year.** Filters sales orders and delivery orders to that order-date window. **No date means all dates** - the report prints `Order date: all`.

**Ambiguous customer name.** When a customer name matches more than one company, the bot shows you all the matches and asks "Which customer do you mean?" with a numbered list. Reply with the number for one company, or "all" to include every matching company in the report. The outstanding ask then continues with the header showing the customer(s) you picked. This picker has no delivery-order hint on an outstanding ask.

## The scope question

If the message does not name a scope word ("sales order", "delivery order", or "both"), and the contact is allowed to see sales order figures, the bot asks one question before running anything. The question is prefaced by the same four header lines that appear on the report:

> Product: SRTWT7445
> Customer: all
> Location: all
> Order date: all
> Outstanding for which document?
> 1. Sales orders (not yet transferred to DO)
> 2. Delivery orders (not yet delivered)
> 3. Both

Answer with the number, or the word itself ("sales orders", "delivery orders", "both", "both lists", "all"). The report then runs with the same product, customer, location and date window already given in the first message - nothing needs to be repeated. After you see the report, you can narrow the search by date or location while the detail offer is still on screen, and the bot will re-show the offer with the narrowed figures.

## Reading the report

Every reply opens with a four-line header echoing what was understood:

> Product: SRTWT7445
> Customer: all
> Location: IB (BRW-IB, MWH-IB)
> Order date: 01/01/2026 to 31/12/2026

`Product` reads `all` when no product was named. `Customer` reads `all` when no customer was named. `Location` reads `all` when no location word was given, an exact code alone when one was, or the token plus every code it resolved to in brackets when it was a suffix. `Order date` reads `all` when no date was given, or an exact range `dd/mm/yyyy to dd/mm/yyyy`.

Then one or both blocks, depending on scope. Both blocks follow the same line order:

> *Sales order outstanding*
> Sales orders: 12
> Ordered: 2,411
> Transferred to DO: 0
> Outstanding: 2,411
> Order date range: 05/01/2026 to 28/08/2026
> *_By location_*
> BRW-IB: 1,200 (O/S: 1,200)
> MWH-IB: 1,211 (O/S: 1,211)
> *_By customer_*
> Dealer A Sdn Bhd: 900 (O/S: 900)
> Dealer B Trading: 811 (O/S: 811)
> Dealer C Hardware: 700 (O/S: 700)

`Sales orders` is the count of open sales orders. `Ordered` is the total quantity on all the sales order lines; `Transferred to DO` is how much of that has already moved to a delivery order; `Outstanding` is the rest. **Ordered always equals Transferred to DO plus Outstanding** - the same three numbers, one population, so they always add up.

The delivery order block follows the same line order:

> *Delivery order outstanding*
> Delivery orders: 3
> DO qty: 640
> Delivered: 0
> Outstanding: 640
> DO date range: 03/02/2026 to 30/08/2026
> *_By location_*
> BRW-IB: 640 (O/S: 640)
> *_By customer_*
> Dealer A Sdn Bhd: 640 (O/S: 640)

`Delivery orders` is the count of delivery orders still outstanding. `DO qty` is the total quantity on those delivery orders; `Delivered` is how much has already been delivered; `Outstanding` is the rest. **DO qty always equals Delivered plus Outstanding**.

Each block's own `By location` and `By customer` lines break its own total down, ranked by the outstanding quantity descending (highest outstanding first). Every line ends in `(O/S: n)` - the outstanding quantity for a sales order line, or the outstanding quantity for a delivery order line, at that location or customer. Only names with outstanding above zero are listed. Nothing is ever shortened with "+N more" and no matching row is ever left out.

If a scope has nothing open, its block prints one line instead: `No open sales order.` or `No outstanding delivery order.`

## Getting the detail behind a number

After a report with at least one non-empty block, the bot offers a detail pick. If only one scope has rows, the offer is a single sentence:

> Reply 1 for the sales order list.

If both scopes have rows, the offer is numbered:

> Reply with a number for detail:
> 1. Sales order list
> 2. Delivery order list
> 3. Both lists

Reply "1" for the sales order list - one row per sales order (its lines rolled up into one), listed latest date first:

> 1. *SO Number:* SO331785
> *Customer:* Dealer A Sdn Bhd
> *Product:* SRTWT7445
> *Location:* BRW-BB
> *Ordered:* 410
> *Transferred to DO:* 0
> *Outstanding:* 410
> *Order Date:* 20/12/2024

Reply "2" for the delivery order list - one row per outstanding delivery order, listed latest date first:

> 1. *DO Number:* DO220456
> *Customer:* Dealer A Sdn Bhd
> *Product:* SRTWT7445
> *Location:* BRW-IB
> *DO Qty:* 640
> *Delivered:* 0
> *Outstanding:* 640
> *DO Date:* 03/02/2026

Reply "3" (or "both lists") to see both lists in one reply, sales order list first, then delivery order list.

Every matching row is sent; long lists are chunked into several WhatsApp messages the way any long chatbot reply is, not shortened. This offer stays open across picks and casual turns - you can pick option "1", then pick option "2" on the next message, without asking the question again.

## Leaving the question

While the scope question or detail offer is on screen, you can close it and move on. Reply "no" or "stop" and the bot answers "Okay, noted." with no offer to pick. You can also ask about something else entirely - the new question closes the offer and the bot answers your new ask. If you send an unclear or unrelated reply ("hi", "hmm"), the bot repeats the offer once to give you a chance to clarify. A second unclear reply closes the offer and the bot treats it as a greeting or low-signal message. Any numbered answer to the offer, or any new question, closes the offer and moves forward.

## A miss

When neither requested scope has anything open, the report still prints its header and its "No open sales order." / "No outstanding delivery order." lines, then the bot offers to escalate to the Sorento customer service team. The offer arrives with the numbered list of who it can be routed to, and a reply of "yes" (no name picked) assigns automatically - the same escalate offer the bot uses whenever any question comes up empty. You can also reply "no" or ask about something else to close this offer without escalating.

## Access: who can see sales order figures

**Everyone with order enquiries access sees delivery order outstanding figures** - that half of the report is on by default, the same as today.

**Sales order figures are gated separately**, per contact, on that contact's own record: open the contact, go to **Access**, and on the **Field reveals** card tick **Sales order outstanding**.

Without that grant:

* The scope question is never asked - there is nothing to choose, so the report simply runs against delivery orders only, with no offer to pick.
* If you explicitly ask for sales orders (the word "SO", "sales order", or "both"), you get one extra line after the four header lines and before the delivery order block: `Sales order figures are not enabled for your account.` - then the delivery order outstanding block runs as normal.

**Field reveals** is the same card that also gates the chatbot's last purchase cost answer - one screen, one switch per restricted answer, each off by default until an admin ticks it for that contact.

## See also

* [Chatbot - "last purchase cost" answer](chatbot-last-purchase-cost.md)
* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md)
* [System Management - Data reference for admins](data-analysis.md)
