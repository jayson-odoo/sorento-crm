# Chatbot - "last purchase cost" answer

Use this when a WhatsApp contact asks what was last paid for a product - "last purchase cost for
M218", "what did we pay for M218", "上次采购价 M218", "harga belian terakhir M218". The bot answers
with the newest purchase order line for that product, one row per warehouse location. This
answer is only given to a contact whose linked CRM user has the **View Product Cost** permission
(see "Who sees cost" below).

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

## Who sees cost

Purchase cost follows one rule everywhere: the **View Product Cost** permission on the person's
role. The same rule decides the cost columns and tabs on the CRM screens, the in-app AI assistant
and this WhatsApp answer.

On WhatsApp the person is the CRM user linked to the contact. So a contact gets the answer when:

1. A CRM user is linked to the contact (shown in the **User** column of the Contacts list), and
2. that user is **Active**, and
3. that user's role has **View Product Cost** (admins have it by default).

A contact with no linked user, or whose linked user is inactive or lacks the permission, gets
exactly this reply, and the bot never looks the cost up at all:

> Sorry, you are not allowed to access purchase cost

A dealer asking about "my cost" without that permission gets their promotions instead, as before.

To give someone cost on WhatsApp, give their user a role with **View Product Cost** (User Management >
Access > Roles) and make sure their contact is linked to that user. To take it away, remove the permission
or unlink the contact. The change applies from their next message.

There is no per-contact cost switch any more: **Last purchase cost** is no longer on the contact's
**Access > Field reveals** card, and **Copy access** does not copy it. On the Contacts list the
**Cost** column (Visible / Hidden) and the **Cost** filter show the result of the rule above for
each contact; they cannot be edited there.

## On the in-app AI assistant

Staff asking the in-app AI assistant get the same answer under the same rule: their own role needs
**View Product Cost**.

## Admin: rolling this answer out

The vocabulary that lets the bot recognise a "last purchase cost" question ships as a new,
unlabelled version of the parser prompt - deploying the code does not change what any customer
sees. The answer only becomes reachable once that version is moved into use:

1. Link a test contact to an active user whose role has **View Product Cost** (see above).
2. Open **[Prompts](/system-management/ai-assistant/prompts)** (System Management > AI Assistant
   > Prompts), open **chatbot_semantic_parser**, and **Publish** the new version so it carries the
   **production** label.
3. Test with that contact.

**Rollback** is moving the **production** label back to the previous version. No redeploy is
needed either way.

## See also

* [Chatbot - outstanding report (sales order backlog and delivery order pending)](chatbot-outstanding-report.md)
* [Read a chatbot turn trace, and retry a failed one](troubleshoot-chatbot-turn-failures.md)
* [Chatbot - product spec visibility](chatbot-spec-visibility.md) - a different, per-contact
  chatbot gate, on this same contact's **Profile** tab rather than **Access**.
* [System Management - Data reference for admins](data-analysis.md)
* [Procurement - Data analysis for the AI assistant](../procurement/data-analysis.md)
