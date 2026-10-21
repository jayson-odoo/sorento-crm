# UAC: PLAN-BATCH-HELD-CANCEL (21 Oct 2026)

Plan: `PLAN-batch-held-cancel-21oct.md`. Shape: an order with a pending AutoCount change (old lines
cancelled by the book, replacement lines added) and Cancel SO saved on replacement lines (SO394881).

- U1. The board's Saved (N) and Confirm (N) name the same lines: the saved Cancel SO lines plus the
  book-cancelled lines the press retires. Never Confirm (N) with Saved (0).
- U2. One Confirm on that order applies the AutoCount change and transfers the saved Cancel SO lines, in the
  same press. No second press, no "commits after the pending change is applied" text.
- U3. The results panel says per order what happened: "SO394881: applied the AutoCount change; 12 lines
  transferred to Cancel SO". The header counts the order: "1 of 1 orders confirmed".
- U4. Simulate confirm shows the same plan without saving: "Simulation, nothing was saved: 1 of 1 orders
  would confirm", "SO394881: would apply the AutoCount change; would transfer 12 lines to Cancel SO".
- U5. A press the server refuses ends in the server's sentence on that order; nothing is written for it and the
  saved Cancel SO decisions are still saved on the board.
- U6. A Cancel SO on a line the change does not name still rides along as before (AC-F23 unchanged).
- U7. A staged rejection on such an order still reads "commits after the pending change is applied" (out of
  scope, follow-up).
