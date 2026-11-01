# UAC: a picked customer stays picked (CHATBOT-PICK-CARRY)

Plan: `PLAN-chatbot-pick-carry-1nov.md`. Customers named by role only (public repo).

- **AC-1** "Dealer <customer> oct total sales", "1", "invoiced": the report runs on exactly the ledgers of option 1, for
  1 Oct to 31 Oct 2026, channel Dealer, basis invoiced, whatever the parser echoes beside the pick at turn 2 (the option's
  code, its name, or nothing).
- **AC-2** A ledger of another customer that shares an account code with one of the picked ledgers is never in the report.
- **AC-3** The basis question is still asked at turn 2, and no figure runs before it is answered.
- **AC-4** At turn 3 "2" is Delivered over the same customer, never option 2 of the customer list.
- **AC-5** A customer or product word typed this turn with no settled row of its own still resolves as today.
- **AC-6** The roster, the sales basis wording and the prompt are unchanged.
