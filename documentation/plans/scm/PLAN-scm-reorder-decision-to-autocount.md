# PLAN - a reorder decision becomes a PO: buy / use stock / partial, keyed in AutoCount, linked back

**Status:** Drafted 20 Aug 2026 evening from the captain's live-test ruling ("the decision
should be either buy or use stock, or partial, so that I can raise PO; the user should go
AutoCount to create PO, and upload the outstanding PO to the system, in which we will link
to the order inquiry"). NOT yet groomed with the captain - awaiting his pass on the open
questions at the bottom. Not implemented.

**Serves:** the Reorder Planning screen (`/scm/reorder`). Sibling of
`PLAN-scm-proforma-to-spo.md` (same AutoCount-as-system-of-record doctrine, same
worksheet-handoff pattern).

## 1. Journey

Actor: the buyer, on a plan's Buy view, one product row at a time.

1. **She reads the row**: need, available, suggested qty, suggested level, last-purchase
   facts, margin. (The 20 Aug fix set makes these honest - level un-shadowing, last-bought
   signal, PO outstanding.)
2. **She decides, on the row**: **Buy N / Use stock N (from named bins) / a mixture**
   (partial), or Skip - with a reason. The FE already models exactly this
   (`lib/planDecisions.ts` PlanDecisionKind = buy | use_stock | use_po | skip, mixture +
   reason) but today it dies in React state. This plan persists it.
3. **The buy portion lands on the PO worklist** ("Joey executes, she does not decide" -
   existing `PoWorklistView`). She **exports the worksheet** (one file per supplier run,
   consolidated-packing-list export pattern): item codes, quantities, supplier, the plan
   row references. Today she retypes; the worksheet kills that.
4. **Joey keys the PO in AutoCount** and flips the existing `keyed_status` marker
   (not_keyed -> keying -> keyed) on the worklist row. AutoCount stays the system of
   record for ordering.
5. **The next outstanding-PO book upload closes the loop.** The existing
   `order_link_service` claim machinery (SO number + item code, idempotent, re-run on
   every upload) already re-attaches the keyed PO to sales orders / order inquiries. This
   plan extends the claim with the originating `run_id` / `recommendation_id` so the
   return trip also closes the PLAN row - the board shows "keyed and now on order",
   distinct from "decided but never keyed".

Nothing is asked that can be derived: supplier, qty, and references flow from the decided
row; the only human inputs are the decision itself, the reason, and Joey's keyed flip.

## 2. What already exists (diagnosis, 20 Aug - reuse, do not re-implement)

- FE decision model: `lib/planDecisions.ts` (kind, mixture, reason) - client-side only,
  `usePlanLines.decide` writes to state and nothing else.
- Location-grain persisted states: `decision_service.py` proposed -> accepted | adjusted |
  dismissed (+ append-only `scm.recommendation_override`), `confirm_decisions` already
  drafts one `purchase_orders` row per supplier. Guard at `decision_service.py:86` limits
  decisions to `buy` recs.
- Product-grain: `scm.order_summary_row.chosen_qty` / `chosen_supplier_id` via
  `OrderDecisionSheet`; `chosen_qty = 0` is a valid "use the pool".
- AutoCount handoff marker: `keyed_status` (not_keyed | keying | keyed) persisted on both
  `order_summary_row` and `reorder_recommendation`; surfaced on `PoWorklistView`.
- Return linkage: `order_link_service` / `scm.order_link_claim` (SO number + item code,
  order-independent, idempotent, re-run after every upload incl. the PO book).
- Export precedent: `consolidated_packing_list.py` + its route.

## 3. The gaps this plan fills

1. **Persist the decision mixture.** Endpoint accepting {kind, buy_qty, stock_takes
   [bin, qty], po_qty, reason} per row; relax `decision_service.py:86` so a use_stock /
   partial / skip decision is recordable on non-buy recs too (a needs_level row the buyer
   overrides is a real decision).
2. **Worksheet export** from the PO worklist: per supplier, the buy portions with item
   codes + quantities + plan references. File format: whatever Joey keys fastest from
   (start with xlsx; captain to confirm).
3. **Close the loop to the plan row**: carry `run_id` / `recommendation_id` on the claim
   (or a sibling table) so the outstanding-PO upload flips the plan row to "on order",
   and the board can show decided-vs-keyed-vs-arrived without a manual cross-check.

## 4. Open questions for the captain

- Worksheet grain: one file per supplier per export, or one file for the whole run with a
  supplier column?
- Does a `use_stock` decision write actual stock holds (reserve rows), or is it a recorded
  intention only? (Holds would collide with the project-sales ladder's reservations -
  needs a ruling.)
- Skip/dismiss with reason: surfaced anywhere later (audit page?), or row-only?
- Partial where the buy half is keyed but the stock half fails (bin empty by then): who
  gets told?
