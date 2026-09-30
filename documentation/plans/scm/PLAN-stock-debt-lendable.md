# PLAN: far-dated landed pins become lendable to nearer sales orders (STOCK-DEBT-LENDABLE)

Status: planning (small fix track is NOT applicable: read model + a write action; no migration)
Lane: STOCK-DEBT-LENDABLE. Base: origin/main 55421aaf (#1397).
UAC: `stock-debt-lendable-acceptance-criteria.md` alongside.

## Owner's problem (30 Sep 2026)

Product SRTSS8710, book Project. SO381065 (due 29/03/2027) is Pinned 88 "On hand BRW-BB"
because its linked SPO was received. SO396071 (due 01/09/2026) reads Short 32 and the Sep 26
cell is -76, Oct -29, Dec -207, while 88 units sit on hand held for a March-2027 order.

Owner: "would like this stock to be allocated nearer like oct, nov, dec".

## Why option B (today + lead time), not a user-chosen cutoff date

The owner first thought of a cutoff date the user picks on the view, then rejected it
himself, verbatim: "dangerous if the user wants to see the stock debt until say June, the
stock will go to Mar which gives a high stock urgency for near term". A number that depends
on how far the reader scrolled is not a number a planner can act on: two people looking at
the same product on the same morning would see two different debts. So the lendability of a
landed pin is anchored to a fact about the ORDER, not about the VIEW: the pinned line's own
required date against `as_of + product lead time + 14 days`, the same window the fulfilment
board's Borrow step already uses to decide who is "a later order that can wait"
(`ProjectSupplyService._eligible_donor`, `front_planning_engine.reserve_window_end`).

`date_from` / `date_to` / `group` / `book` keep their R14 meaning: they hide rows and never
move stock.

## Requirements

- R1 Lendable pin (read model): in the stock-debt assignment a landed on-hand pin is lendable
  when the pinned line's `required_date >= as_of + lead + 14` (the board's donor predicate,
  shared, not forked). The lendable quantity joins the chronological walk as free on hand at
  its bin, so nearer lines draw it first. The far line keeps its claim as a planned re-buy:
  status `order_back` ("Order back N") for what was lent, `pinned` for what was not.
- R2 View independence: `date_from/date_to/group/book` never change which pins are lendable
  or where stock goes. Test: same cell value with and without `date_to`.
- R3 Non-lendable pins unchanged: inside `lead + 14`, undated, TBA, unlocated keep today's
  behaviour.
- R4 Cell dialog (Demand tab): lent-from line reads "Order back N", Covered by "Lent to
  SOxxxxx (N)"; the receiving line reads Covered by "On hand <bin> (from SOxxxxx)". Supply
  tab unchanged.
- R5 Rebalance (write): one button on the cell dialog, enabled only when the cell has at
  least one lendable transfer. Runs the existing board machinery (order_borrow + order-back
  Buy) per receiving SO, Preview then Confirm. No new write path.
- R6 Product doc: this file + PLAN-r7's "landed stays with its line" note amended.
- R7 Performance: no extra query per line; landed + lead come from the batch reads.

## Design

To be filled in as the lane progresses (read model first, under TDD; UI after "mock ok").
