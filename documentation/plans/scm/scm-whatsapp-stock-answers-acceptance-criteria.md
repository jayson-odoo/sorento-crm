# UAC - S12: WhatsApp stock and cost answers

Plan: `PLAN-scm-whatsapp-stock-answers.md`. Verified through the n8n test workflow and the MCP tests; Friday station 12.

## A. Stock answer
- AC-S1 Asking stock for SRTWCY7405-PJ returns, per warehouse, on hand, outstanding SO, available and incoming; BRW-IB reads incoming 332 with "SPO-2026/08-0061, 1 Aug 2026, overdue N days".
- AC-S2 An item with no stock and no incoming but an open active PO line answers "On PO: <number>, <qty> expected <date>"; a draft recommendation PO is never named.
- AC-S3 An item with no stock, no incoming and no PO answers "Nothing on order".
- AC-S4 A dealer contact under a restricted visibility mode sees neither available nor outstanding SO nor the PO / SPO lines; a staff contact sees all five.
- AC-S5 The five numbers agree with the board popover's location table for the same product and warehouse on the same day.

## B. Cost answer
- AC-S6 Asking the last incoming cost of SRTWT7443 answers "RMB 65.50 on KL20260717 (17 Jul 2026), KAILU, cites 202605-S0060" and the previous PI price from the same supplier when one exists.
- AC-S7 A product with no PI line answers from the newest inbound shipment line cost and says so.
- AC-S8 A dealer contact asking for cost is refused by the policy; the bot says it cannot share cost.

## C. Prompt
- AC-S9 The n8n test workflow answers the three Friday items with the wording above and calls exactly one tool per question.
