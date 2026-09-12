# PLAN: managing a sales-order change after planning, one engine

**Status:** AGREED, pre-code, 13 September 2026. Grilled with the owner across four rounds on
12 and 13 September 2026; the agreed page is versioned at
`documentation/plans/scm/mockups/so-change-management-grill-v4.html` (twelve worked
scenarios). This plan is the contract; the UAC is
`scm-change-management-one-engine-acceptance-criteria.md`. Supersedes the suggestion
vocabulary and rule table of `PLAN-so-book-diff-replanning.md` (keep / release / replan /
reduce / retire and the "accept" step), which stays as history.

Prerequisites already shipped on `lane/main-so-changes-12sep` (PR pending): the gate (a
change is raised only for a held or inquired line), the board picking up a pending batch on
its own, the list pill, and the savepoint fix on apply.

## The problem

A sales order changes after CS has planned it. Today the reaction is uneven: an upload or an
ESB push raises qty / date / closed / added changes, a manual edit raises qty and date only
(never a removed line, a new line, a product swap, or qty-to-zero as closed); a qty increase
promises "delta only" but re-walks the whole line and drops the hold; a product swap falls
apart into closed plus added with the added half dropped; a placed PO or SPO is redirected to
the pool whole or left with a note; a removal is refused when an inquiry row exists; and every
edit fires two signals (a change batch and the lazy `challenged` flip). Measured on the 10 Sep
live copy and confirmed on the grill page, section 1 of v1.

## The rules (agreed)

1. **One engine, whole unit.** A planning unit (order, product, location, date) is covered by
   ONE ladder step or by a Buy: pool share (only inside the immediate window, may cover part),
   Use own, Borrow (an ORDER_BACK row for the donor), SPO, Buy. Never half stock and half
   bought. Existing rule R10 / R33 in `front_planning_engine.walk_line`.
2. **Step 0 stands.** A line due beyond the reserve window or beyond purchasing's
   reorder-coverage date is a single Buy; no stock is reserved for it. The "60 days" is this
   window, not a change-specific knob. `RESERVE_WINDOW_DAYS` in `planning_change_service.py`
   and the size-of-move test are retired.
3. **A change is a re-run at the new state, diffed against what is held.** The diff is the
   suggestion: per held component Keep / Reduce / Release / Reallocate, plus new sourcing for
   uncovered quantity. CS decides Confirm or Amend on the fulfilment board. There is no
   "replan" suggestion and no "accept" step.
4. **A top-up joins the held source.** Qty up on a Buy line tops up the same Buy and the same
   inquiry row ("Was 134"). Qty up on a Use own line takes more stock if the group has it,
   else the whole unit moves to the next step that covers all of it.
5. **Every trigger, every kind.** Manual edit, SO book upload, AutoCount ingest all build the
   same before / after line diff and raise the same kinds: qty up, qty down, date advanced,
   date delayed, line cancelled or removed, line added, product changed. Product changed is a
   kind of its own, keyed on line identity, shown as one row "Product changed, was X".
   Removal is never refused because an inquiry row exists.
6. **Reallocation candidates are inquiry rows.** Freed stock and freed PO / SPO quantity go,
   in order: dealer pool if the product is dealer hot-selling; else raised or partly linked
   ORDER rows with unlinked quantity, through the existing linking engine's priority
   (`auto_place_for_products`, `_rank_raised_rows`); else a pool-location row. Project lines
   without an inquiry row are not candidates. The receiving order's CS is not asked; their
   row shows "Found" and their board reads the new state next time.
7. **Never hold stock for a far date.** A big delay past the reserve window releases the
   reserve and reallocates a placed PO or SPO; the line is bought again nearer its date.
   Keep is an Amend, not the suggestion.
8. **Show it short.** When an advanced line cannot be covered in time even after pool share
   and Borrow, the board shows the shortfall and the remainder stays a Buy; CS decides. A
   unit kept late (S12) is shown as late, never silently kept.
9. **One signal.** The `challenged` flip (`challenge_if_drifted`) is retired from sheet read,
   confirm and reconcile. A change always arrives as a batch with a suggestion.
10. **Order Inquiry is where the outcome lands.** Keep = note (DELAY / ADVANCE "Was ..."),
    Reduce = row qty down in place, Release = row cancelled (RELEASE / CANCEL_BALANCE), a
    Borrow = ORDER_BACK row for the donor, Reallocate = link moved to the receiving row or a
    pool-location row. Nothing writes to a supplier.

## Scenarios

S1 to S12 on the versioned grill page are the specification by example; the UAC cites them.

## Slices (each its own lane and PR, in this order)

| Slice | What | Main files |
|---|---|---|
| A. Diff parity | Manual edit builds the same before / after diff as ESB (`outstanding_diff`), including removed, added, product changed (new kind), qty-to-zero as cancelled; removal no longer refused on an inquiry row | `sales_order_service._propagate_planning_change`, `_upsert_lines`, `outstanding_diff` identity by line id, `planning_change_service._map_kind` |
| B. Delta seam | The engine can be asked for a unit whose held components are Keep candidates; whole-unit top-up (S1); pool share partial only inside the immediate window (S11) | `project_supply_service.demand_facts` / `compose_lines` (`exclude_line_ids` today un-nets a hold; the seam keeps it as a candidate), `planning_change_service._proposal_for` |
| C. Recompute-and-diff | `suggest()` and the rule table replaced by the diff of the re-run against the held composition; vocabulary Keep / Reduce / Release / Reallocate; Confirm / Amend only on the board; `BoardChangeTable` shows the composed suggestion | `planning_change_service.suggest`, `_build_row`, `apply`, `boardChangeAnnotations.ts`, `BoardChangeTable.tsx` |
| D. Reallocation | Freed PO / SPO quantity: unlink then re-deal through the linking engine with the hot-selling gate; freed reserve moves to the receiving decision (S3); pool-location row for the leftover; `redirected_to_pool` retired | `project_order_inquiry_service.unplace`, `auto_place_for_products`, `_classification` (hot-selling), a hold-move between `SOSupplyDecision`s |
| E. One signal | `challenge_if_drifted` removed from `proposal_for`, `confirm`, reconcile; "Needs CS review" retired from the sheet | `project_supply_service.py:3910-3992, 1037, 4126`, `project_so_reconciliation_service.py:562` |

Slice A first because every later slice needs all kinds to arrive. B before C because C's
suggestion text is only honest once the delta run exists. D last among the engine slices
because it moves state between decisions. E is independent and small; it can ride any lane.

## Not doing

- No supplier-facing action (no PO or SPO amendment, no supplier task state).
- No polling of the board; a change shows on the next open.
- No new "changed" column on lists; the pill in the SO number cell is the precedent.
- Partial delivery after a change, a line moved to another SO (`CHANGE_SO`), a supplier
  cancelling an SPO: later lanes.

## Verification

Per slice: red pytest from the UAC first, then green; vitest for the board vocabulary; a
browser run on a lane against the prod copy with the twelve scenarios seeded on SO419772.
