# UAC: CONSIGN-OWN-BIN-EMAIL

Plan: `PLAN-consign-own-bin-email-02nov.md`

- UAC-1: Confirming a consignment line's Borrow at its own bin sends purchasing no email line
  for it (and no email at all when it is the only line).
- UAC-2: Buy 4 + own-bin Borrow 6 on a consignment line: the email has one line for it, remark
  `ORDER 4`, never `ORDER BACK`.
- UAC-3: A consignment line's Borrow from another bin still emails `ORDER BACK <that bin>`.
- UAC-4: A planner-keyed Buy on a consignment line still emails `ORDER`.
- UAC-5: A sales order line's Borrow at its own bin emails exactly what it did before.
- UAC-6: Re-confirming the same own-bin Borrow unchanged sends nothing.
