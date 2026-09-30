# PLAN - Stock Debt must not distribute PO or SPO quantity across SOs by its own walk (PO-NO-AUTO-ASSIGN)

Status: in progress, 30 Sep 2026, small fix track (no migration, no auth/RBAC change, no new ingest surface, backend only). UAC: `po-no-auto-assign-acceptance-criteria.md`.
Domain: SCM, Stock Debt view (`_assignments(view=True)`) and the shared supply assignment.

## The owner's words

30 Sep 2026, Stock debt drawer B2155-NL-BLUE, PO 202609-S0109 line 8 (15,000) spread by the walk
over SO373923 line 224 (36), SO382618 lines 2776/2864/3072/3168 (100 each) and more: "we cannot
distribute the PO quantity like that, cause the PO quantity is ordered for a reason, and the user
is yet to do linking in AutoCount, so it will be premature to allocate to other SO by our
calculation."

The three questions the lane put back, and the owner's answer (30 Sep 2026, verbatim): "i think
this applies for SPO also though, most SPO should have linkage already but we shouldn't
prematurely auto assign the SPO, unlinked PO quantity count based on the delivery date of the PO
line lor, it should still contribute to the stock debt quantity, yeah SO line should show short".

## The problem, measured (origin/main 950785de2, `sorento_crm_backend/`)

- `StockDebtService._supply` (`app/services/scm/stock_debt_service.py:906`) reads on hand, every
  open SPO line (`incoming_by_location`) and, since R42, every open PO line (`po_by_location`,
  `:1010-1038`; outstanding = `qty_ordered - qty_received`, `project_supply_service.py:9388-9403`)
  as `SupplyEvent`s of kind `on_hand` / `spo` / `po`.
- `supply_assignment.assign` (`app/services/scm/supply_assignment.py:506`) applies the pinned
  holds first (`:579-651`: confirmed on-hand allocations, OI placements on an SPO or PO line, the
  landed-goods pin, and in the view the PO line's book S/O pin from `book_so_pins`) and then runs
  ONE chronological walk (`_walk`, `:706-810`) in which EVERY counted event, documents included,
  joins its ownership group's free pile and is drawn by demand lines first-come by required date
  and clears the group's open shortfalls when it lands.
- So a PO line with no link (or an SPO line with no placement) is handed out to whichever SO
  lines of the group are due next. That is the 15,000 spread the owner refused.
- Month balance (R37, `_months` `:915`): free supply dated in M less what lines due in M were
  short at their own date. Unchanged by this plan (owner's answer 2).

## The rule (R45, 30 Sep 2026, Stock Debt view only)

1. **A document covers a sales-order line only through a link.** In the view, a PO line and an
   SPO line are PIN-ONLY supply: an OI placement (`order_inquiry_links.po_line_id` /
   `spo_allocation_id`), the AutoCount S/O reference on the line (`purchase_order_lines
   .from_so_line_ref`, and now `spo_allocations.from_so_line_ref` the same way) and, for the
   landed part, the existing landed-goods pin. The walk never assigns a document to a line, and
   a document never clears a shortfall.
2. **Unlinked quantity is still supply in its month.** What no link took stays free on the PO
   line's Delivery date (R42) or the SPO's arrival date, credits its month exactly as today, and
   the Supply tab lists it with its Free quantity. Nothing is excluded from the balance.
3. **A line only unlinked supply could have covered reads Short**, and books its shortfall in its
   own month. No new status.
4. **On hand is unchanged.** Stock on the floor is still drawn first-come by required date; the
   pins on it (decisions, landed goods) still bind first.
5. **The board and the ladder are unchanged.** `assignments_for` never passes `view`, so the
   walk there still nets a PO or SPO as free supply (plan v7 R29; AC-PO-8, AC-PO-15 keep
   pinning it).

## Design (simplest thing that works)

- `SupplyEvent.pin_only: bool = False` (`supply_assignment.py`). `assign()` keeps a pin-only
  event out of `_walk` (it enters no pile and clears no shortfall); pins still take from it
  through `left`, and what is left is `free` and credited by `_months` as today.
- `StockDebtService._supply(..., documents_pin_only=view)` stamps `pin_only=True` on every
  `spo` and `po` event it builds for the view. `_assignments` passes `view`.
- `_book_so_holds` asks about SPO events too: `spo_allocations.from_so_line_ref` resolved through
  the same `order_link_service.book_sales_orders_by_ref`, placed quantity from
  `order_inquiry_links.spo_allocation_id`. `book_so_pins` carries the event's own kind and
  document fields onto the hold rather than hard-coding PO.
- No wire change, no FE change: `free_qty` on the Supply tab is already the unlinked figure.
- Tests first: `tests/scm/test_stock_debt_routes.py` (the route half), `test_supply_assignment.py`
  (the pure half). The R42 tests that asserted a walk draw from a PO in the view are rewritten
  to R45 and say so.

## Coordination

Lane SPO-RECEIVED-PIN (PR #1388) converts a placement on a received SPO into an on-hand hold in
`_holds`. This lane does not touch `_holds`; the two overlap only in `stock_debt_service.py`'s
imports and `_assignments`, and either merge order works.

## Out of scope

- The board and the ladder (`assignments_for`).
- Any change to how a link is made: that stays in AutoCount and on the Order Inquiry page.
