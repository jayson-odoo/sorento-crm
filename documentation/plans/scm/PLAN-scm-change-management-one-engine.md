# PLAN: managing a sales-order change after planning, one engine

**Status:** Slice A in progress on lane/scm-change-a-diff-parity; ONE PR (#855) for all
slices per the owner, 13 Sep 2026. Grilled with the owner across four rounds on 12 and 13
September 2026; the agreed page is versioned at
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

## Slice A contract (captain, 13 September 2026, after reading `outstanding_diff.py`,
`planning_change_service.py`, `sales_order_service.py`)

Recorded here because these shapes are the ones the tester's red tests assume, and the plan
is the source of truth once code diverges from the table above:

1. `app/models/planning_change.py`: `PLANNING_CHANGE_KIND_CLOSED` renamed
   `PLANNING_CHANGE_KIND_CANCELLED = "cancelled"` (every reference updated, `suggest()`
   included); `PLANNING_CHANGE_KIND_PRODUCT_CHANGED = "product_changed"` added.
   `app/schemas/planning_change.py` `PlanningChangeKind` Literal = delayed, advanced, qty_up,
   qty_down, cancelled, added, product_changed. `PlanningChangeFromTo` gains `item_code`.
   FE mirror: `planningChange.types.ts`, the `__mocks__/planningChanges.ts` fixture,
   `boardChangeAnnotations.ts` (`row.kind === 'closed'` -> `'cancelled'`).
2. Migration `514_planning_change_kind_cancelled` (revision id shortened to
   `514_plan_change_kind_cancelled`, <=32 chars), down_revision
   `513_planning_gate_backfill`: data-only rename `kind='closed'` -> `kind='cancelled'` on
   `projects.planning_change_rows`, reversible, idempotent, Core-built against the mapped
   table (513's own Reviewer S2 reason).
3. `app/services/scm/outstanding_diff.py`: `Line.line_id: Optional[str] = None`. `diff_lines`
   pairs a before/after sharing the same `line_id` FIRST (pass 0), ahead of the
   `(doc, item, location)` + date-order fallback, which only lines with NO `line_id` ever
   reach; a `line_id` line unmatched by that pass closes/adds directly rather than entering
   the fallback (this is what keeps two differently-identified same-looking lines from
   zipping into a false `unchanged`). New `PRODUCT_CHANGED` kind: a `line_id` pair whose
   item_code differs and whose after is not settled; after settled (qty 0) is `CLOSED` even
   with a different item_code; before-only is `CLOSED`; after-only is `ADDED`. `CLOSED`
   keeps the value `"closed"` inside this module - only the wire row kind renames. `diff_lines`
   also gained a keyword-only `scope_documents` override: a manual edit removing every line
   off one order leaves the after side empty, and the scope `diff_lines` derives from an
   empty incoming list would read the whole order as untouched rather than wholly closed.
4. `app/services/planning_change_service.py`: `_map_kind` CLOSED -> `"cancelled"`,
   PRODUCT_CHANGED -> `"product_changed"`; `suggest()`'s own dispatch renamed the same way,
   plus a `product_changed` branch. `_from_to` puts `item_code` (old/new) into
   `from_json`/`to_json`; the row's own `item_code`/`product_name` are already the NEW
   product because `Change.item_code` is built from the after side. Gate in `_build_row`
   unchanged for every other kind; an `added` change (no mirror line) is raised when the
   ORDER has at least one held or inquiry line, asked once per order group
   (`_order_has_held_or_inquiry`, only queried when the group actually carries an `added`).
5. `app/services/scm/sales_order_service.py`:
   - `_upsert_lines` returns a `_LineUpsertResult` (`matched` / `removed` / `added`) instead
     of a bare list, capturing the OLD item_code/location on a matched line (needed for a
     product swap's "before" side) and the freshly-inserted line objects. `has_dependents`
     drops `OrderInquiryRow` (four EXISTS, not five); a NEW `has_inquiry` check plus
     `ProjectSupplyService.frozen_lines_of(active_decision)` decide, PER REMOVED LINE, held
     or inquired -> the CORE line is set `line_status = CANCELLED` (never deleted, mirror
     line and inquiry row both survive) instead of being pruned/deleted. **Deviation from
     the plan's first cut:** the held-or-inquiry check runs BEFORE `has_dependents`, not
     after - confirming a decision (even a pure Buy) always writes the line its own
     `SOLineAllocation` row, so a held line always has a "dependent" in the four-table
     sense, and checking that first would 409 the exact removal rule 5 requires to be
     accepted. `is_authored` and the `OrderLinkClaim` 409 are untouched.
   - `_propagate_planning_change` builds `outstanding_diff.Line` before/after pairs keyed by
     the CORE line id (`line_id`) from `_LineUpsertResult` and calls `diff_lines` (with
     `scope_documents=(so.so_number,)`, see point 3) instead of hand-classifying - one call
     covers matched (qty/date/product), removed (`CLOSED`) and added (`ADDED`) lines
     uniformly. The manual-edit batch stamping (`source_kind = so_manual_edit`) and the
     best-effort try/except are unchanged.
   - `app/schemas/scm_orders.py`: `SalesOrderLineInput.qty_ordered` loosened `gt=0` -> `ge=0`
     (shared by `SalesOrderFormData`/create and `SalesOrderUpdate`; no test asks create to
     stay positive, so the validator was not split by operation).
6. One manual-edit batch per save, `source_kind = so_manual_edit`, every changed row of that
   save in it - unchanged from before this slice.
