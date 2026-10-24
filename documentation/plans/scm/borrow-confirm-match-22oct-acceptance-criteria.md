# UAC: Confirm accepts every Borrow the list offers (BORROW-CONFIRM-MATCH)

Plan: `PLAN-borrow-confirm-match-22oct.md`.

- UAC-1: With "Borrow from another order" OFF, a Borrow at a location whose stock a later order of
  the SAME sales agent holds, ranked AHEAD of the asking line, confirms. No "held for an order
  ranked ahead of this line" refusal.
- UAC-2: After UAC-1 the donor line reads short (or covered from elsewhere) in the planning
  assignment; its cover is not left intact on the borrowed units. The order-back hangs on the
  asking line, as for any location borrow.
- UAC-3: With the switch ON, a Borrow naming the donor sales order still needs "authorised by" in
  the reason when the donor shares the agent and is ranked ahead (unchanged).
- UAC-4: Every other Confirm check on a location borrow stays: wrong product, wrong location, no
  ownership group, closed donor, more than the donor line holds.
- UAC-5: On the Fulfilment board, when the server refuses an order ("Nothing was written") that
  also has a staged rejection held back, the held-back note does not say "was confirmed". When the
  order did confirm, it still says "was confirmed, but its staged rejection could not ride along".
