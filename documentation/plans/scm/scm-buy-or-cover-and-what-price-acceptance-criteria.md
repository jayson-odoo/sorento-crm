# S12 - Buy or cover, from where, and at what price

Status: S12a, S12b, S12c implemented. One open decision for the user (see the end).

## Why

Two decisions the screen currently pretends do not exist.

### 1. "Use stock" has no source, so it means nothing

> "when there is nothing on hand, there isn't a use stock function, i mean there is, actually
> the use stock is use from BRW, not from BRW-IB"

The button was built on a wrong reading. **Use stock does not mean "use this line's own
on-hand"** - that is already netted into the suggestion and was never a choice. It means
**cover this location's shortage from stock held somewhere else**.

MWC7624-RL-S10 on the live run says it exactly:

| line | needs | own on hand | suggested buy | free elsewhere |
| --- | --- | --- | --- | --- |
| BRW-IB | 1 | **0** | 1 | 231 at DC1-BB, 5 at BRW-BB, 1 at PJ-SR |
| DC1-BB | 419 | 231 (netted) | 188 | 5 at BRW-BB, 1 at PJ-SR |

The BRW-IB line is offered "Use stock" with nothing at BRW-IB to use, and the DC1-BB line
cannot be fully covered at all - only 6 units exist anywhere else. So the honest answer there
is neither buy-everything nor cover-everything but **a split: use 6, buy 182**.

### 2. The system does not say what it thinks

> "you need to suggest me also, whether to buy or use stock, if half half also need to
> suggest, and also need to suggest use stock from where"

Offering three buttons and no opinion pushes the analysis back onto the buyer for all 4,229
lines. The plan already knows where stock sits and what each location needs; it has to say so.

### 3. The price is a decision too, and we are blind to half of it

> "should i use the last price, or should i rfq to get new price from supplier, so I need to
> know the last PO for this product and this supplier, and the last purchase date, i will know
> how has the market changed and make decision ... i am not sure how smart can we suggest
> whether to use the same price or need new price cause we are blind to market condition"

Right, and the honest position is narrow: **we cannot see the market, so we must not pretend
to.** What we can see is how OLD the price is and how much it has moved before. That is enough
to say "this price is 14 months old, it has moved twice in the last two years, worth an RFQ"
and nothing more.

## Journey

At the row, the buyer sees a **suggested action**, not a menu:

1. **"Buy 182, use 6 from BRW-BB"** - the split, with the source named.
2. They accept it, or change the split, or change the source.
3. Where nothing is free anywhere, the row says **Buy 188** and the cover option is not
   offered as if it were available.
4. On the cost, the row says what we last paid this supplier and when, and whether that price
   is old enough to be worth re-quoting.

## Acceptance criteria

### S12a - what can actually cover this line

* **AC-S12a.1 [BE]** GIVEN a line short by N, WHEN cover is computed, THEN it returns only
  stock at OTHER locations, in warehouses that count as available, net of that location's own
  committed demand. A location's own on-hand is never offered: it is already in the net.
* **AC-S12a.2 [BE]** GIVEN several locations hold free stock, WHEN cover is proposed, THEN
  each source is named with the quantity it can give, largest first.
* **AC-S12a.3 [BE]** GIVEN free stock is less than the shortage, THEN the proposal is a SPLIT:
  cover what exists, buy the rest. Neither half is rounded away.
* **AC-S12a.4 [BE]** GIVEN a source in a different segment from the line (project stock
  covering dealer demand, or the reverse), THEN it is still offered but MARKED as
  cross-segment, never silently mixed.
* **AC-S12a.5 [BE]** GIVEN two lines that could both draw on the same free stock, WHEN one is
  decided, THEN the other's available figure drops by what was taken. The same unit is never
  promised twice.

### S12b - the row states an opinion

* **AC-S12b.1 [FE]** GIVEN any line, WHEN it renders, THEN it shows a suggested action in
  words - "Buy 188", "Use 6 from BRW-BB", or "Use 6 from BRW-BB and buy 182".
* **AC-S12b.2 [FE]** GIVEN the suggestion, WHEN the buyer accepts it, THEN it is one click.
* **AC-S12b.3 [FE]** GIVEN no free stock anywhere, THEN Use stock is not offered as an
  available action, and the row says why rather than leaving a dead button.
* **AC-S12b.4 [FE]** GIVEN a cover decision, WHEN it is taken, THEN the source and quantity
  are recorded with it. "Use stock" without a source is not a decision that can be saved.

### S12c - the price behind the buy

* **AC-S12c.1 [FE][BE]** GIVEN a line with a chosen supplier, WHEN the cost is inspected, THEN
  it shows the last purchase order to THAT supplier for THAT product: price, date, quantity.
* **AC-S12c.2 [FE]** GIVEN the last price is older than a configurable age, THEN the row
  suggests re-quoting, stating the age as the reason.
* **AC-S12c.3 [FE]** GIVEN past purchases at more than one price, THEN the movement is shown
  (what it was, what it became) so the buyer can judge the trend themselves.
* **AC-S12c.4 [FE]** The system NEVER claims to know the market price. Every suggestion here
  is stated as a fact about our own purchase history and its age.
* **AC-S12c.5 [BE]** GIVEN the plan's own draft purchase orders, WHEN the last paid price is
  read, THEN they are excluded. A `draft_recommendation` PO is this planner's proposal, and
  reading it back as evidence would let the system cite itself.
* **AC-S12c.6 [BE]** GIVEN a purchase line recorded at 0.00, WHEN the last paid price is read,
  THEN it is not treated as the price and is counted separately. 637 such lines exist and 116
  pairs would take one as their newest price; "our last price was 0.00" invites an order at
  zero, and calling a change from 26.15 to 0.00 a 100% fall is arithmetic on a non-price.
* **AC-S12c.7 [FE][BE]** GIVEN the plan is costing a line at exactly 0.00, THEN the row says
  so, above every other price question, and shows the last figure we actually paid beside it.

## Implementation notes

* Backend: `app/services/scm/price_history_service.py`, `GET
  /api/v1/scm/reorder-runs/{run_id}/price-history`, keyed `"{product_id}:{supplier_code}"`.
* Frontend: `lib/priceAdvice.ts` (wording only, the codes are the backend's),
  `components/PlanPriceCell.tsx`, the `Price basis` column on `PlanLinesGrid`.
* The advice codes, in the order they outrank each other: `zero_cost`, `unknown_age`,
  `stale`, `moving`, `no_history`, `recent`.
* The gap the row reports is against the cost **the run froze**, not today's
  `product_suppliers.unit_cost`. Re-reading the master would compare the paid price against a
  figure that was never in the plan, and the gap would move whenever somebody edited the
  supplier record.
* Live shape at the time of writing (run of 2026-08-10, 2,374 product-supplier pairs):
  `no_history` 1,565, `stale` 760, `zero_cost` 48, `recent` 1. Every real purchase on record
  came from one 2020 import, so `stale` being near-universal is the honest answer, not a
  defect in the rule.

## Open decision for the user: the plan is costing 24 buy lines at zero

Found while building S12c, NOT changed unilaterally, because it contradicts a decision
already taken and tested (`tests/scm/test_cost_from_po_history.py`: "a purchase order
recording zero is a price of zero").

The engine's cost cascade (`reorder_engine.last_purchase_costs`) takes the newest priced PO
line as the cost, and deliberately keeps a 0.00 as a real price. The consequences on the live
run:

* 24 buy lines covering **11,675 units** are costed at exactly 0.00, with cash impact 0.00.
  They clear any budget unchallenged and rank with no cash pressure behind them.
* All 637 zero-cost lines come from the single 2020 order import. 202 of them sit on a PO that
  ALSO carries a priced line for the same product, which reads much more like a banded or
  continuation row than a genuinely free item.
* The cascade also does not filter PO status, so a `draft_recommendation` PO the planner wrote
  itself is readable as "what we last paid" on the next run. Only 4 exist today; it grows with
  every run.

S12c makes both visible on the row rather than silently reversing the decision: a zero-costed
line reads **Priced at zero** in the `Price basis` column, above every other price question,
with the last figure we actually paid beside it.

**The question for the user:** should the engine stop treating a zero purchase line as the
price for the NEXT order, and fall through to the contract figure, then to unknown? Unknown
puts the line in "No price", which is exactly the behaviour already agreed in S10e - an
unpriced shortage stays in the plan, visibly unpriced, for a human to price. That is a
one-line change to the cascade plus an update to two tests.

## Decisions taken

1. **The on-hand offset checkbox is removed.** It was built on the same wrong reading - it
   asked the buyer whether to use stock already counted in the net, which is not a decision.
   Its replacement is the buy/cover split, which is one.
2. **Cover is proposed, never executed.** It records what the buyer decided and keeps the line
   out of the purchase order. It does not create a transfer: allocation stays with CS, per the
   standing decision.
3. **Free means surplus, not on-hand.** A location holding 500 against its own demand of 500
   has nothing to give. Using its raw on-hand would rob one location to fill another and the
   engine would propose it again next week.

## Deferred, deliberately

The commercial layer recapped in the same conversation is NOT in this slice, and is recorded
here so it is not lost: continue or discontinue with the notification to salesmen and
marketing; monthly sales rate and whether an item sells well; who is selling it and who is
buying it; repeat-order signal; the push list; margin from cost against selling price; new
items to promote from the catalogue, including before they reach port; the segment tool;
telling customers about a discontinued item when their PO arrives, together with incoming and
stock; and production status by supplier.

These are Phase 2 and Phase 3 in `scm-reorder-level-basis-acceptance-criteria.md`. They need
the commercial data (selling price, salesman, customer, repeat orders) that the purchasing
plan does not currently carry.
