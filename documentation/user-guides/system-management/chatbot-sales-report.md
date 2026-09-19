# Chatbot - sales report (confirmed vs outstanding, by month and product)

Use this when a WhatsApp contact wants to know how much a customer bought, or how much of a
product sold, month by month - "sales report for hanlim", "dealer sales report for hanlim",
"sales report for SRTWT7445", "project sales report for hanlim". The bot answers with one
report: how much was ordered, how much of that is a recognised sale, and how much is still
outstanding, broken down month by month with the orders behind the numbers on request.

## What to type

* **A customer name and/or a product code, plus a sales report ask** ("sales report", "sales
  performance", "how much did X buy"). You need at least one of a customer or a product; asking
  for neither is refused.
* **"dealer"** or **"project"** narrows the report to that sales channel. Neither word means all
  channels, including orders with no channel recorded.
* **A month, a year, or a date range** narrows the report to that window. See "Defaults" below
  for what happens with no date.
* **A location word.** A word ending in a warehouse suffix (e.g. "IB") matches every warehouse
  code ending in that suffix (e.g. `-IB`: `BRW-IB`, `MWH-IB`). An exact warehouse code (e.g.
  "BRW") matches only that code.
* **Narrow after the report is already on screen.** While the report (or its detail offer) is
  still on screen, reply with just the extra filter - "june 2026 only", "only SRTWT7445" - and
  the same report re-runs narrowed, with the header showing the new filter.
* **"1" for the sales order list.** After a report with at least one month, reply "1" and the
  bot lists every matching sales order, one item per order, latest date first.

**Ambiguous customer name.** When a customer name matches more than one company, the bot shows
you the matches and asks "Which customer do you mean?" with a numbered list. Reply with a
number for one company, or "all" to include every matching company in the report. This picker
carries no delivery-order hint on a sales report ask.

## Reading the report

Every reply opens with five header lines echoing what was understood:

```
Customer: HANLIM TRADING SDN BHD, HANLIM TRADING SDN BHD [A/C I]
Product: all
Channel: Dealer
Location: all
Delivery date: all
```

`Customer` and `Product` read `all` when that axis was not named. `Channel` reads `Dealer`,
`Project` or `all`. `Location` reads `all` when no location word was given, the exact code alone
when one was, or the word plus every code it resolved to in brackets when it was a suffix.
`Delivery date` reads `all`, or an exact range `dd/mm/yyyy to dd/mm/yyyy`.

**A product code also covers every code that starts with it.** Typing "SRT5674" matches the
product `SRT5674` itself and every sibling code that starts with it, such as `SRT5674-N` - so
the report never comes back empty just because the sales actually sat on a variant of the code
typed. When more than one code matched, the header lists them comma separated: `Product: SRT5674,
SRT5674-N`. A code that only ever matches itself prints bare, and a very wide prefix (more than
10 matching codes) collapses to a count, e.g. `Product: SRT56 (37 products)`.

Then one block per month, latest month first:

```
*_Sep 2026_*
Sales orders: 31
Ordered: RM 182,450.00 (Qty: 3,120)
Confirmed (DO): RM 96,300.50 (Qty: 1,540)
Outstanding: RM 86,149.50 (Qty: 1,580)
*_By product_*
SRTWT7445: RM 50,000.00 (Qty: 900) (Confirmed: RM 40,000.00, Qty: 720)
SRTKT39SS: RM 31,200.00 (Qty: 400) (Confirmed: RM 0.00, Qty: 0)
```

`Sales orders` is the count of sales orders with a line in that month. `Ordered` is everything
on those lines. `Confirmed (DO)` and `Outstanding` split that same total two ways, so
**Ordered always equals Confirmed (DO) plus Outstanding**, for both the money and the quantity.

Say this plainly, because it is easy to read "outstanding" as a problem: Sorento only counts a
sale as made once the sales order line has been transferred to a Delivery Order. **Confirmed
(DO)** is that recognised sale. **Outstanding** is what has been ordered but has not yet been
transferred to a delivery order - not cancelled, not a mistake, just not yet moved across.
Cancelled sales orders and cancelled lines are never counted anywhere in this report.

Under the customer's own numbers sits a breakdown list, ranked by ordered value, highest first:

* Ask about a **customer** and the breakdown is **By product**.
* Ask about a **product** and the breakdown is **By customer**.
* Name both a customer and a product and there is no breakdown at all - the month's own four
  lines are the whole answer, because there is nothing left to break down.

**Asking about a product that covers more than one code prints By product too**, so you can
still see which of those codes actually sold. Since a product code also covers every sibling
code that starts with it (see above), a product-only ask over such a family prints **both**
breakdowns - By product first, then By customer. Naming a customer alongside that same family
prints By product only; naming a customer alongside a single, non-family code still prints no
breakdown at all.

Every matching row is listed; nothing is ever shortened with "+N more".

If nothing matches at all, the report still prints its header, then one line: `No sales
found.` and no offer to pick anything further.

## Which month a line falls in

A sales order line is counted in the month of its own delivery (required) date. A line with no
delivery date falls back to the sales order's own order date. This means a single sales order
with lines due in two different months is counted once in each of those months' `Sales orders`
totals - it is not double-counted as one order, it is one order contributing a line to each
month it actually touches. A line dated for a future month shows up under that future month,
same as any other.

## Defaults

* **A customer-only report, or a customer-and-product report, with no date named shows all
  dates.** The header prints `Delivery date: all`.
* **A product-only report with no date named shows the current year** instead of everything -
  otherwise a bare product code alone would pull years of history. Say the words "all dates" and
  the bot drops that default and shows everything.

## Getting the orders behind the numbers

After a report with at least one month, the bot ends with:

```
Reply 1 for the sales order list.
```

Reply "1" and the bot lists every matching sales order over the whole filtered window, one item
per order, latest order date first:

```
1. *SO Number:* SO421287
*Customer:* HANLIM TRADING SDN BHD
*Location:* BRW-IB, MWH-IB
*Order Date:* 12/09/2026
*Ordered:* RM 12,400.00 (Qty: 210)
*Confirmed (DO):* RM 6,200.00 (Qty: 105)
*Outstanding:* RM 6,200.00 (Qty: 105)
```

Every matching sales order is sent; long lists are chunked into several WhatsApp messages the
way any long chatbot reply is, not shortened. This offer stays open across a narrowing reply
("only SRTWT7445") - the bot re-runs the report and re-arms the same offer over the narrower
set. Reply "no" or "stop" to close it, or ask about something else entirely to move on.

## Amounts

Every amount prints in RM, with two decimal places and thousands separators, e.g. `RM
1,234.50`. A line priced at zero (this happens on some lines in the data) still counts its
quantity - it prints `RM 0.00` next to the real quantity, not as a missing row.

## Access: who can see this report

The admin grants this per contact. Open the contact, go to **Access**, and on the **Field
reveals** card tick **Sales report**. It is off by default.

Without that grant, any sales report ask gets one line back: `Sales report is not enabled for
your account.` and nothing is fetched.

The sales report is **not available through the in-app AI assistant** - it only answers over
WhatsApp, to a contact who holds the grant.

## Why does my number look different

* **Confirmed (DO) is a recognised sale; Outstanding is not yet one.** If a figure looks lower
  than expected, check whether a chunk of it is sitting in Outstanding because the order has not
  been transferred to a delivery order yet.
* **A line is bucketed by its delivery (required) date, not its order date**, when it has one.
  An order placed in one month with lines due in a later month shows those lines under the later
  month, not the month it was placed.
* **Cancelled orders and cancelled lines are never counted**, in any total, on any month.
* **The report only covers the contact's own company scope** - a contact tied to one company
  ledger never sees another company's sales orders, the same as every other chatbot report.

## See also

* [Chatbot - outstanding report (sales order backlog and delivery order outstanding)](chatbot-outstanding-report.md)
* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md)
* [System Management - Data reference for admins](data-analysis.md)
