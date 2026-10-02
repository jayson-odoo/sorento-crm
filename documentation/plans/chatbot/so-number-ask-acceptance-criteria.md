# UAC: SO-number ask (SO-NUMBER-ASK)

Plan: `PLAN-so-number-ask.md`. Every case runs as a chat turn (Chatbot Console, never WhatsApp).

## Miss (no data from anyone else)

- AC-SO-01: A linked dealer asks `status of SO999999` (no such SO). Reply is one miss line naming
  `SO999999`. No DO rows, no customer names, no Customer/Product/Dates header.
- AC-SO-02: An order ask naming nothing (`my orders`) from a linked dealer still runs on the links
  (AC-CS-30 unchanged).

## Found, in scope (contact holds `sales_orders.outstanding`)

- AC-SO-03: `status of SO421624` (open, partly delivered, own link) replies exactly:
  `*SO421624* - <debtor name>` / `Ordered 15 Sep 2026 - Open` / `Delivery: partly delivered`.
- AC-SO-04: an open SO with nothing delivered reads `Delivery: not delivered yet`.
- AC-SO-05: a closed SO with every line delivered reads `- Closed` / `Delivery: fully delivered`.
- AC-SO-06: a closed SO with less delivered than ordered reads `- Closed` / `Delivery: partly delivered`.
- AC-SO-07: a cancelled SO reads `- ❗ Cancelled` and has no delivery line.
- AC-SO-08: no DO list is printed (the SO->DO link is empty in the data).
- AC-SO-09: no escalate offer and no "I could not find" under a found card.

## Out of scope / several / no key

- AC-SO-10: an SO that exists on a customer the dealer is not linked to replies with the scope
  refusal `Sorry, that isn't under your account. I can only check on <links>.` and nothing about
  that SO (no status, no customer name). `<links>` names each group by its group name
  only: `HANLIM TRADING SDN BHD`, several groups `A, B and C`; never a `(6 accounts)` count,
  never `and N more` (owner rule, 2 Oct 2026).
- AC-SO-11: an SO of another company is not found (AC-SO-01's miss line).
- AC-SO-12: `SO421624 SO999999`: one card for SO421624, then `I could not find SO999999.`
- AC-SO-13: a contact without `sales_orders.outstanding` gets `Sales order figures are not
  enabled for your account.` and no SO data.
- AC-SO-14: a contact with no enforced scope (staff) sees any SO of its own company.
