# UAC: CONSIGN-OWN-BIN-EMAIL

Plan: `PLAN-consign-own-bin-email-02nov.md`. Owner ruling 2 Nov 2026: a consignment's own-bin
Borrow is owed back like a sales order line's ("Borrow from another order" OFF, its default).

- UAC-1: Confirming a consignment line's Borrow at its own bin raises an ORDER_BACK row at that
  bin, and the purchasing email has its line, remark `ORDER BACK`.
- UAC-2: Buy 4 + own-bin Borrow 6 on a consignment line raises ORDER 4 and ORDER_BACK 6, and the
  email's one line for it reads `ORDER BACK 6 & ORDER 4`.
- UAC-3: A consignment line's Borrow from another bin still raises its row there and emails
  `ORDER BACK <that bin>`.
- UAC-4: A planner-keyed Buy on a consignment line still raises ORDER and emails `ORDER`.
- UAC-5: A sales order line's own-bin Borrow raises ORDER_BACK and emails `ORDER BACK` at the
  line's own bin, at a bin in fulfilment planning (project class) and at an active dealer bin
  flagged out of it (retail class, Retail automation row); a consignment's reads the same.
- UAC-6: Re-confirming the same decision unchanged raises no new row and sends no email line.
