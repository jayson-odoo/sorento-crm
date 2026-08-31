# PLAN: Fulfilment planning feedback batch, 31 Aug (incoming = SPO only, transfer charge configurable, lightbox navigation)

Status: PLANNED - mockup with captain, no code started
Captain rulings: 31 Aug 2026 production walk-through (screenshots on the session)
Lane: TBD when implementation starts
UAC: `scm-planning-feedback-31aug-acceptance-criteria.md` (same folder)

## Why

The captain planned a real order batch in production (76 units) and came back with three
engine findings and four navigation asks. All verified against `origin/main` code and the
prod-copy DB before this plan was written.

Verified facts this plan stands on:

- `supply_borrow_candidates_for` (`app/services/project_supply_service.py:2465`) offers
  BOTH shipping orders and purchase-order lines as "Borrow incoming / Use incoming"
  documents (`SA_KIND_SPO`, `SA_KIND_PO`), SPO ranked before PO (R27/R35), PO only when no
  single SPO covers the whole unit (R33).
- `202607-S0067` is a REAL `purchase_orders` row (source `scm_upload`, issued 22 Jul 2026,
  no expected date). The "S" in the number is the captain's own PO numbering, not an SPO
  prefix. The engine's label was correct; the captain's ruling is that the OFFER is wrong.
- `TRANSFER_DAYS = 2` (`app/services/scm/front_planning_engine.py:159`) is a literal,
  charged at `front_planning_engine.py:1144` on any option whose stock is not already at
  the asking line's own location. It is why "Take from the pool" showed fulfilled 02/09
  (8 days late) beside "Use our locations" at 31/08: pool bin BRW vs own bin BRW-IB.
- Fulfilment settings already live on the priority policy row
  (`app/services/scm/priority.py:186` `FULFILMENT_SETTINGS_DEFAULTS`,
  `save_fulfilment_priority`), read by the engine through
  `ProjectSupplyService._fulfilment_settings()`. `transfer_days` joins that row; no new
  table (one preference = a column, per PRINCIPLES).

## Captain rulings (the contract)

R-A. **Incoming means SPO. A PO must never be named by "Use incoming" or "Borrow
     incoming".** A PO is still on order with a computed date; operations treat "incoming"
     as goods on the water. This retires the PO half of R29/R30 (ladder v7 S4). A unit that
     only a PO could cover falls through to the pool step, then Buy - that is the point,
     not a regression.
- R-B. **No transfer charge by default, and the charge is configurable.** `transfer_days`
     becomes a fulfilment setting, default 0. When 0, a pool take fulfils the same day as
     an own-location take.
- R-C. **Lightbox navigation batch - all four asks approved:**
  1. One obvious click from a grid cell to the line's own row in the lightbox (no
     expand-subtotal-then-hunt dance).
  2. Borrow-from-order: the donor SO named in the suggestion is clickable and the donor
     row is highlighted in the stock table ("Donor" badge, mirror of "This line").
  3. A search input on the lightbox tables - SO number, customer, agent.
  4. Borrow/Use incoming: the SPO document named in the suggestion is clickable and its
     row is highlighted in the location's incoming detail.

## Slices

### S1 - Incoming = SPO only (engine)

Backend only. Test-first.

- `supply_borrow_candidates_for`: candidate events are `SA_KIND_SPO` only (three
  `event.kind not in (SA_KIND_SPO, SA_KIND_PO)` gates at
  `project_supply_service.py:2564/2577/2601` tighten to SPO; the SPO-before-PO sort key at
  `:2648` loses its PO arm).
- `front_planning_engine.py`: the `kind == "po"` sentence branch in
  `supply_borrow_reason` (`:608`) and the PO wording contract comment die with it. R29's
  `issue + lead` arrival stays wherever the ASSIGNMENT still nets SPO cuts out of POs -
  the assignment keeps reading POs (netting, PO qty column, Stock Debt); only the ladder's
  step 3 stops OFFERING them.
- Measure on the prod copy while the tests are red: run the engine over the captain's
  76-unit batch, count units whose step-3 document was a PO, and record before/after
  category counts in the PR body (expected: those units move to pool or Buy).
- Tests: a unit covered only by a PO gets NO supply-borrow offer and falls through; a unit
  covered by an SPO is unchanged; no option/suggestion sentence anywhere contains a PO
  document; `assignments_for` still nets POs.

### S2 - transfer_days setting, default 0 (BE + one FE field)

- Migration: `transfer_days` int NOT NULL default 0 on the priority-policy table.
- `FULFILMENT_SETTINGS_DEFAULTS` gains `transfer_days: 0`; `fulfilment_settings()` and
  `save_fulfilment_priority` carry it (validate >= 0).
- `walk_line` takes `transfer_days` (default 0) and uses it at `:1144` in place of the
  `TRANSFER_DAYS` literal; the literal and R36's "+2 days with a transfer" comment go.
  Callers (`project_supply_service`, board service) pass the setting through.
- FE: the existing fulfilment-priority settings surface gains one numeric field
  "Transfer days between bins" with 0 visible as the default. No new page.
- Tests: pool option fulfil date == as_of when 0; == as_of + N when the policy says N;
  days-late column follows; settings round-trip asserts the field (response_model lesson).

### S3 - Lightbox navigation (FE first against the existing wire, then any BE gap)

All in `sorento_crm_frontend/app/(protected)/project-sales/fulfilment-planning/`
(`BoardCellBreakdownDialog`, `CellStockTable`, `StockDocumentsPanel`, grid cells in
`FulfilmentBoardMatrix`). Mockup `scm-planning-lightbox-mockup.html` (lavish session) is
the visual contract; captain annotates there.

1. **My line, one click.** (Revised on the mockup, 31 Aug.) The WHOLE grid cell is the
   click target - hover ring + pointer - and opening AT my line becomes the lightbox's
   default landing: own-location group pre-expanded, scrolled to the first "This line"
   row, row flash-highlighted. The toolbar's "My line" button re-runs the jump from
   anywhere inside.
2. **Donor jump.** Suggestion sentence: donor SO number renders as a link. Click =
   expand the holding location's S/O detail, scroll, highlight, "Donor" badge on the row
   (same component as "This line", different label/colour). Applies to BOTH donor shapes
   (captain, mockup round 4): the on-hand borrow's donor AND the order waiting on a
   borrowed SPO - "Borrow ... (SPO x) from SO397460" links and jumps to SO397460's row
   the same way; the sticky Donor button targets whichever the suggestion names.
3. **Search + sticky jump toolbar.** (Extended on the mockup, 31 Aug.) One STICKY toolbar
   at the top of the lightbox scroll: `ListSearchInput` (shared component, standing rule)
   filtering expanded detail rows by SO number, customer, agent (spinner until rows land,
   explicit empty state), beside three jump buttons - "My line", "Donor", and the SPO
   document - the latter two rendered only when the suggestion names one. Same search on
   the contributing-lines table.
4. **Incoming doc jump.** For a Use/Borrow-incoming suggestion the SPO number renders as
   a link -> expands that location's incoming detail, scrolls, highlights the SPO row,
   "This document" badge. (After S1 this is always an SPO.) The detail's running
   balance-after treats an SPO row as an ADDITION (+qty, green) in strict chronological
   order - an arrival helps only the rows dated after it (captain confirmed the read on
   the mockup, 31 Aug).
- Detail rows come from the existing expanded-row wire; if the wire cannot say which row
  is the donor/document (it carries donor_core_line_id / supply_key today - verify), the
  gap is a field on the existing response, not a new endpoint.
- **Design contract (captain, mockup round 3):** S3 follows `.claude/skills/apple-design`
  and PRINCIPLES' design mandates - sticky toolbar and row highlights use spring-feel,
  interruptible, reduced-motion-respecting transitions; scroll-to-row lands on the final
  geometry (verify end states, lesson 89); jump flashes fade, never persist as a second
  selection colour; 375px + 1280px both clean.
- Vitest for the four behaviours (DataGrid-in-jsdom mock per the standing lesson);
  agent-browser evidence run for the click-through journey.

## Order

S1 and S2 are independent of S3 and of each other; S3 waits on the mockup sign-off.
Suggested: mockup review -> S3 FE mock -> S1 -> S2 -> S3 wiring -> review.

## Out of scope

- Renaming the stock table's "PO qty" column (still useful context; not an offer).
- Any change to the assignment/netting or Stock Debt reads of purchase orders.
- SPO-into-purchase_orders direction (separate, unbuilt, needs its own plan).
