# Chatbot - "last purchase cost" answer

Use this when a WhatsApp contact asks what was last paid for a product - "last purchase cost for
M218", "what did we pay for M218", "上次采购价 M218", "harga belian terakhir M218". The bot answers
with the newest purchase order line for that product, one row per warehouse location. This
answer is **hidden for every contact by default** and only reachable once an admin reveals it on
that contact's record.

Asking the everyday selling-price question - "how much do we sell M218 for", "how much does it
cost", "berapa harga" - is not this feature and stays on the normal stock / product answer; only
the purchasing-cost phrasing above routes here.

## The reply

One block per `(product, warehouse)` pair, newest purchase order first. A worked example for
product M218 at warehouse BRW-SMC:

> PO Number: PO-2026/09-0013
> Product Code: M218
> PO Quantity: 19
> PO Date: 2026-09-08
> Cost / unit: CNY 110.00
> Discount / unit: CNY 66.00
> Cost after discount / unit: CNY 44.00
> Warehouse: BRW-SMC

**All three money figures are per unit.** The purchase order's discount is recorded as one lump
sum for the whole line, not per unit, so the bot divides it (and the line's total) by the
quantity to get `Discount / unit` and `Cost after discount / unit`. The currency shown is
whatever currency that purchase order line was raised in, not always MYR.

**`Discount / unit` and `Warehouse` only appear when there is one.** A line with no discount
recorded skips the `Discount / unit` line entirely; a line raised with no warehouse stated skips
the `Warehouse` line entirely. Nothing renders as a blank or a zero.

**A cancelled purchase order, or a cancelled line on an otherwise-open order, never answers** -
the bot looks past it to the next newest line. A line with no cost recorded at all never
answers either; a cost question with no cost is not an answer.

**A product family answers one row per member per location.** Asking about a family code (a code
prefix that resolves to several product variants, e.g. SRTWC8517) returns the latest purchase
cost for every member of that family, at every warehouse it was bought into - not just the first
match.

## Permission: the Field reveals card

This answer is off for every contact until an admin turns it on for that specific contact.

To reveal it: open the contact's record, go to **Access**, and on the **Field reveals** card
tick **Last purchase cost**.

Without the grant, a contact asking for the last purchase cost gets exactly this reply, and the
bot never looks the cost up at all:

> Sorry, you are not allowed to access purchase cost

**Field reveals** is the same card that also controls **PO supplier** and **Outstanding SO on
stock answers** - one screen, one switch per restricted answer, each off by default until an
admin ticks it for that contact.

## Not on the in-app AI assistant

This is a WhatsApp chatbot answer only. The in-app AI assistant (the one staff use inside the
CRM) does not offer this tool at all - it is deliberately kept out of that assistant's tool
search, the same way every cost-restricted lookup is.

## Admin: rolling this answer out

The vocabulary that lets the bot recognise a "last purchase cost" question ships as a new,
unlabelled version of the parser prompt - deploying the code does not change what any customer
sees. The answer only becomes reachable once that version is moved into use:

1. Grant **Last purchase cost** on a test contact (see above).
2. Open **[Prompts](/system-management/ai-assistant/prompts)** (System Management > AI Assistant
   > Prompts), open **chatbot_semantic_parser**, and **Publish** the new version so it carries the
   **production** label.
3. Test with the granted contact.

**Rollback** is moving the **production** label back to the previous version. No redeploy is
needed either way.

## See also

* [Chatbot - outstanding report (sales order backlog and delivery order pending)](chatbot-outstanding-report.md)
* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md)
* [System Management - Data reference for admins](data-analysis.md)
* [Procurement - Data analysis for the AI assistant](../procurement/data-analysis.md)
