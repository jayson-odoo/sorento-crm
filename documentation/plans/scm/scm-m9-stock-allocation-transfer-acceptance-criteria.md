# SCM M9 - Stock Allocation (inter-warehouse transfer) - Acceptance Criteria

> Status: DRAFT (2026-07-17) - written FIRST per methodology (grilled, decisions locked below).
> Classification: MODULE (scm) capability. Public schema, normal FKs.
> Guardrail (umbrella §0): deterministic engine computes the transfer maths; the LLM is not involved.
> Builds on M3 engine (order_up_to, per-warehouse net, allocate, overstock disposition) and M8
> (daily plan, decision overlay, "Stock allocation" view already renamed from Disposition).

## Goal

Before buying, cover a warehouse's shortage of a product from another warehouse's genuine EXCESS of
the same product. The "Stock allocation" view suggests inter-warehouse transfers (overstock source ->
shortage destination); accepting one creates a draft transfer order and reduces the linked buy so we
move what we already own instead of purchasing more.

## Locked decisions (from grill 2026-07-17)

1. **Transfer-first, buy the residual.** For each shortage, cover as much as possible from other
   warehouses' excess; the buy plan orders only the leftover.
2. **Excess rule.** A source warehouse qualifies to DONATE a product only if it is genuinely
   overstocked for that product (its `net` days-of-cover > the overstock ceiling, i.e. the same
   overstock signal M3 already computes). Movable excess = `net - order_up_to` (>= 0) - donating
   never drops the source below its own order-up-to target.
3. **Transfer qty** for a (product, source, dest) = `min(source movable excess, destination shortfall
   to its order_up_to)`.
4. **Multi-source split**, largest-excess-first. No transfer cost / lead-time model in v1 (no per-pair
   data exists) - v2 adds a transfer-lane table for cost/lead-aware ranking.
5. **Accept = own decision type -> draft transfer order** (a thin new entity; none exists today).
   Confirm materializes the draft transfer; accepting auto-reduces the linked buy rec's qty.

## Criteria

### Engine (deterministic)

- **M9-E1 (Excess detection).**
  GIVEN a product with per-warehouse `net`, `order_up_to`, and days-of-cover
  WHEN the allocation pass runs
  THEN a warehouse is a valid SOURCE for that product iff it is flagged overstock (days-of-cover >
  overstock ceiling) AND `net > order_up_to`; its movable excess = `net - order_up_to`.

- **M9-E2 (Shortage detection).**
  A warehouse is a valid DESTINATION for that product iff `net < order_up_to` (shortfall =
  `order_up_to - net`), i.e. it has a real reorder need (the same signal that produced its buy rec).

- **M9-E3 (Matching + qty).**
  For each product with both sources and destinations, greedily fill each destination's shortfall
  from sources by largest movable excess first; each transfer qty = `min(remaining source excess,
  remaining dest shortfall)`. A source is never drawn below its `order_up_to`. Rounds to whole units.

- **M9-E4 (Buy reduction link).**
  The qty covered by transfers for a (product, destination) reduces that destination's buy
  recommendation by the same qty; the residual shortage remains as a (smaller) buy. If transfers
  fully cover it, the buy line drops to 0 / is removed from the plan.

- **M9-E5 (No self / no negative).**
  Never suggest a transfer within the same warehouse, of a non-positive qty, or that would push the
  source below its target or the destination above its order_up_to.

- **M9-E6 (Determinism + guardrail).**
  The allocation pass is pure deterministic maths over engine outputs; no LLM path writes any
  transfer qty. Given the same snapshot inputs it produces identical transfers.

### Data / records

- **M9-D1 (Transfer suggestion record).**
  Each suggested transfer is persisted on the run (frozen with the snapshot) with: product, source
  warehouse, destination warehouse, qty, source-excess + dest-shortfall context, and a link to the
  destination's buy rec.

- **M9-D2 (Draft transfer order on confirm).**
  Accepting a transfer + confirming materializes a draft inter-warehouse transfer order (thin new
  entity: product, from-warehouse, to-warehouse, qty, status draft/pending, source run/rec refs),
  mirroring how buy confirm -> draft PO. It is NOT a stock adjustment; on-hand does not change until
  the transfer is fulfilled (out of M9 scope).

- **M9-D3 (Reuse over invent).**
  If any existing stock-movement / picking entity can represent an inter-warehouse transfer, reuse
  it; only add a new table if none fits (search confirmed none exists today).

### UX (reorder page, "Stock allocation" view)

- **M9-U1 (Transfer rows).**
  The Stock allocation view lists transfer suggestions: SKU, From warehouse, To warehouse, Qty,
  Days-cover context, and a Reason ("cover WH-JHR shortage from WH-KL excess"). Existing
  discontinue/promote/hold disposition rows remain (a transfer is a new action alongside them).

- **M9-U2 (Accept / reject inline).**
  Each transfer row has inline Accept / Reject (own decision type). Accept stages it; Reject needs no
  new order. Confirm decisions materializes accepted transfers into draft transfer orders.

- **M9-U3 (Buy reduction visible).**
  When a transfer is accepted, the linked buy line in the Buy view shows the reduced qty (and a note
  that N units are covered by a transfer). No double-ordering.

- **M9-U4 (Warehouse names, no UUIDs).**
  Source/destination render as human-readable warehouse names/codes; no UUIDs.

### Cross-cutting

- **M9-X1 (Terminology).** "Out of stock" / "Low stock" wording (never "Stockout"); no em-dash in new
  strings; SearchableSelect for any select; confirm before reject/unlink.

## Out of scope (v2+)

- Transfer cost / lead-time-aware ranking and gating (needs a transfer-lane table).
- Transfer fulfilment lifecycle (in-transit, received) beyond creating the draft.
- Partial-fulfilment reconciliation back into net.

## Test report keying

Phase-2 test report keys each M9 id PASS/FAIL/DEFERRED; golden-set transfer scenarios (single-source,
multi-source split, full-cover-drops-buy, source-protected-at-target, no-self) authored as failing
tests first per the deterministic-engine TDD rule.
