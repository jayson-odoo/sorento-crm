# PLAN: managing a sales-order change after planning, one engine

**Status:** Slices A, B and C built (C's Phase 1 and Phase 2 both); Slice E built. Same lane/scm-change-a-diff-parity, ONE PR
(#855) for all slices per the owner, 13 Sep 2026. Grilled with the owner across four rounds
on 12 and 13
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
| B. Delta seam | Own-hold carve-out, whole-unit top-up (S1) and pool-share-inside-the-window (S11) already existed, now guarded by tests; the real gap was AC-B2's Borrow - the ladder's `order_borrow` rung was proposed but never composed, confirmed or given an ORDER_BACK on the donor's own line | `planning_change_service.composition_from_proposal` (`_borrow_components_from_sources`, new), `_validate_composition_shape`, `_to_confirm_line`, `project_supply_service._borrow_shortfalls` (donor-line resolution) |
| C. Recompute-and-diff | `suggest()` and the rule table replaced by the diff of the re-run against the held composition; vocabulary Keep / Reduce / Release / Reallocate; Confirm / Amend only on the board; `BoardChangeTable` shows the composed suggestion | `planning_change_service.suggest`, `_build_row`, `apply`, `boardChangeAnnotations.ts`, `BoardChangeTable.tsx` |
| D. Reallocation | Freed PO / SPO quantity: unlink then re-deal through the linking engine with the hot-selling gate; freed reserve moves to the receiving decision (S3); pool-location row for the leftover; `redirected_to_pool` retired | `project_order_inquiry_service.unplace`, `auto_place_for_products`, `_classification` (hot-selling), a hold-move between `SOSupplyDecision`s |
| E. One signal (built) | `challenge_if_drifted` deleted; a drift is never flipped to `challenged` on its own again, on the sheet read, on confirm, or on reconciliation's non-relink branch - the change batch is the only signal. Its borrow-hold release carries into batch apply instead; a per-line drift check replaces the whole-decision flip inside the carry-forward | `project_supply_service.py` (`proposal_for`, `confirm`, `_carried_lines`/`_carry_snapshot_has_drifted`), `project_so_reconciliation_service.py` (`_persist`), `planning_change_service.py` (`_apply_one_order`) |

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
     (shared by `SalesOrderFormData`/create and `SalesOrderUpdate`, since AC-A4 needs an
     EDIT to accept 0); a `SalesOrderFormData.lines` `field_validator` (review round,
     R-S4) rejects a `qty_ordered <= 0` line on create instead, so a brand-new order still
     cannot open with a line that has nothing on it.
6. One manual-edit batch per save, `source_kind = so_manual_edit`, every changed row of that
   save in it - unchanged from before this slice.
7. Qty set to 0 is a cancellation that deliberately does not pass the removal guards
   (`is_authored`, other dependents, `OrderLinkClaim`): the line is kept, not deleted, so
   nothing dangles; the change row still raises. Line id is identity for every trigger. A
   re-keyed AutoCount line (new DtlKey, same product) reads `cancelled` + `added`, not one
   moved line; counted on the first ESB run after deploy.

## Slice B contract (captain, 13 September 2026, issue #857)

`tests/scm/test_planning_change_delta_seam.py` (the tester's own red-test pass, 10 cases)
found that AC-B1, AC-B3 and AC-B4's own-hold arithmetic already worked - the ladder's
`walk_line` already carves out an own hold as a Keep candidate (rule 1), a Buy line's top-up
already re-runs the whole unit and posts one row ("Was <old>") through the existing
settle-in-place seam (`ProjectSupplyService.confirm`'s `settle_in_place_line_ids`,
`ProjectOrderInquiryService.refresh_for_decision`), and pool-share partial cover is already
gated to the immediate window (`DEFAULT_IMMEDIATE_WINDOW_DAYS`) with whole-or-nothing outside
it (rule 10). Those are guarded by tests now, unchanged by this slice. **The only real gap
was AC-B2's Borrow:**

1. `app/services/planning_change_service.py`: `composition_from_proposal` used to hardcode
   `"borrow": []` on the stated (and false) belief that "the board never proposes a Borrow" -
   LADDER V7.1's `order_borrow` rung (step 2) already does, whole-unit, off a later donor's
   own committed stock (`BoardSource.donor_core_line_id`/`donor_so_number`/`donor_line_no`/
   `donor_required_date`). Comment removed; a new `_borrow_components_from_sources` builds
   the Borrow list off `proposal["sources"]` the same way `_reserve_components_from_sources`
   already builds Reserve, `source` always `ALLOC_SOURCE_OTHER_LOCATION` (every rung the
   board proposes a Borrow on today names a committed line or a moving document, never a
   cross-project claim). The donor identity fields had to be carried through TWO further
   places that would otherwise have silently dropped them - `_validate_composition_shape`
   (the PUT-time shape check, which used to keep only 5 of `ConfirmBorrowComponent`'s
   fields) and `_to_confirm_line` (apply's own composition -> `ConfirmLine` translation,
   which built `ConfirmBorrowComponent` without `donor_core_line_id` at all) - without both,
   `ProjectSupplyService._check_line`'s group-borrow branch and `_borrow_shortfalls`'s
   order-back both read `donor_core_line_id` as `None` and the Borrow would either refuse at
   Apply or raise nothing back to the donor.
2. `app/services/project_supply_service.py`: `_borrow_shortfalls`'s group-borrow order-back
   hung its `OrderInquiryRow` off the ASKING line (`entry["line"]`, literally the row
   variable from `checked`) for EVERY shortfall, including a NAMED donor
   (`donor_core_line_id` set) - AC-B2's own wording, "an ORDER_BACK row FOR THE DONOR",
   needs it on the donor's own project line instead. Fixed with one batch lookup
   (`ProjectSalesOrderLine.core_sales_order_line_id.in_(...)`) resolving the donor's mirror
   line before the loop; falls back to the asking line only for a donor core line with no
   project mirror (never adopted), the pre-existing shape for that edge case. The
   location-pile shortfall (no named donor line) is unaffected - it never had
   `donor_core_line_id` to resolve.
3. Verified through the EXISTING confirm mechanics end to end (apply -> `confirm()` ->
   `refresh_for_decision` -> `_borrow_shortfalls`), not a parallel path: the asking line's
   Buy row is cancelled, the donor's own line gets a live `ORDER_BACK` row for the full
   borrowed quantity, and `test_ladder_v7_supply_borrow.py` / `test_supply_group_borrow_carry.py`
   / `test_project_supply_borrow_row_ack.py` (the existing step-2/step-3 borrow suites) stay
   green - the donor-line resolution only changes WHICH line an already-correct row lands on.

**AC-B4, resolved (the tester's own `_hold_qty` fix, commit `2b769e294`; both tests pass,
`test_planning_change_delta_seam.py` is 10/10):** the earlier read of these two tests as a
backend bug was itself wrong - the helper, not the engine, was unscoped. Recorded here so the
reasoning travels with the code:

1. A superseded revision's `SOLineAllocation` rows are never deleted - they are an immutable
   ledger (`_carry_allocations`'s own docstring). The engine counts holds through `_hold_rows`
   (`project_supply_service.py`'s `_hold_query`), which scopes to `decision.state ==
   DECISION_ACTIVE OR decision_id IS NULL`; a superseded row simply stops counting, it does not
   need to disappear.
2. On a qty-up apply the OLD decision reads `challenged`, not `superseded`, only because
   `confirm()` calls `challenge_if_drifted` (which flips a stale active decision to
   `challenged`) before `_write_decision` supersedes it moments later. Either state is already
   outside `_hold_query`'s `DECISION_ACTIVE OR NULL` scope, so holds read right regardless of
   which of the two the old decision ends up carrying.
3. Slice E must carry `_release_supply_borrow_holds` (today called only from
   `challenge_if_drifted` at line ~3990 and `supersede_active` at line ~3906, never from
   `_write_decision`) into batch apply, or a step-3 supply-borrow placement made under an old
   decision stays pinned once that decision stops being active - the state flip alone frees the
   HOLD accounting but not the placement itself.
4. Slice B is also the first place a step-3 `supply_borrow` composition reaches `confirm()`
   through the planning-change apply path at all (a test the tester added alongside the AC-B4
   fix) - earlier borrow coverage only exercised step-2 `order_borrow` through this seam.


## Slice C contract (captain, 13 September 2026, issue #858)

The shapes the tester's red tests and the backend both build against. Written during Phase 1
(frontend against the fixture) so the board, the tests and the engine share ONE text.

### A. The row shape

`PlanningChangeRow` (BE model + `app/schemas/planning_change.py` + FE
`_shared/types/planningChange.types.ts`) gains a `suggestion` (BE column `suggestion_json`,
JSONB) and loses `suggested` / `why`:

```
suggestion = {
  "components": [
    {
      "action":    "keep" | "reduce" | "release" | "reallocate"   # on a HELD component
                 | "use_own" | "borrow" | "spo" | "buy",          # for NEW quantity
      "source":    "reserve" | "borrow" | "spo" | "buy" | "po" | "pool_share" | null,
      "qty_was":   string | null,
      "qty_now":   string,
      "location":  string | null,     # BRW-IB
      "document":  string | null,     # PO-A, SPO-77
      "target":    string | null,     # "dealer pool", "SO420103 ORDER 50", "pool"
      "item_code": string | null,     # product_changed: the NEW product
      "label":     string             # the sentence the board prints VERBATIM
    }
  ],
  "late_days":     number | null,     # the unit is kept but lands N days late (S12)
  "shortfall_qty": string | null      # nothing covers this much in time (S11)
}
```

`label` is composed SERVER-side and printed verbatim - "Keep 134", "Release 134, free at
BRW-IB", "Buy 134 for 20 Nov", "Reduce Buy 100 to 0", "Keep PO-A 100 of 134", "Reallocate
PO-A 34 to SO420103 ORDER 50", "Buy 234 (was 134)", "Keep 134, late by 12 days", "Short 34 by
20 Aug". Only the engine knows which rung covered what, against which document, for whose
order, so a second composition in TypeScript could only drift from it. Held components come
FIRST, in held order, then the new sourcing.

`composition` (`composition_json`) is PRE-FILLED at build from the re-run proposal, so Confirm
posts it unchanged and Amend edits it through the existing `BoardAmendDialog` / PUT
`rows/{row_id}`. `decision` is `null` | `confirm` | `amend` only. `proposal` stays (the re-run
itself, what the amend dialog opens on). `suggested` and `why` are removed from the FE type
and the API schema, and the backend stops writing them.

### B. Frontend behaviour (Phase 1, against the fixture)

`BoardChangeTable` renders Was / Now (qty, date, decision) as it does today, then ONE line per
`suggestion.components[].label`, then "Late by N days" when `late_days` is set and "Short N"
when `shortfall_qty` is set. A `cancelled` row still reads `Cancelled` in the Now column; a
`product_changed` row prints "Product changed, was <old item_code>" above its suggestion and
carries the new product's sourcing lines.

The words replan / retire / accept, and `keep` as a DECISION value, never render; the existing
tests that guard that keep their intent (their fixtures were rewritten, not their assertions'
purpose) - Keep / Reduce / Release / Reallocate DO render now, because they are the
suggestion's own words rather than the name of a reaction. Confirm is the existing pre-marked
`confirmMany` path and Amend the existing amend flow: no new control, no "accept" anywhere.
In `boardChangeAnnotations.ts`, `BoardChangeSide.decision` for the Now side reads the row's
pre-filled `composition` first, then the `proposal`, then the hold - never `suggested`;
`preMarkedKeys` is unchanged in intent.

### C. The fixture

`_shared/__mocks__/planningChanges.ts`: `pcb-1` and `pcb-0` rewritten to the new shape, `pcb-1`
carrying ONE ROW PER SCENARIO S1 to S12 with the exact suggestion lines the grill page gives
(S2: "Reduce Buy 100 to 0", "Keep PO-A 100 of 134", "Reallocate PO-A 34 to SO420103 ORDER 50";
S3, S4, S9, S10, S12 likewise), `decision` null / confirm / amend only.

### D. Backend (Phase 2)

1. `compose_suggestion(kind, held, proposal, facts)` replaces `suggest()`: it DIFFS the re-run
   against the hold rather than picking a verb off a rule table, and returns the shape in A.
2. `RESERVE_WINDOW_DAYS` and the within-window fact are retired from
   `planning_change_service.py` - the ladder's own step 0 decides whether a line that far out
   may hold stock (rule 2), and a second window constant in the change service could only
   disagree with it.
3. `apply` dispatches on `decision` + `composition`, and on `kind == cancelled`; no other kind
   carries a branch of its own any more.
4. Migration `515` adds `suggestion_json` and maps existing `decision` values:
   `accept` / `keep` -> `confirm`, `board` -> `null`.

### E. Slice C as built (13 September 2026), and what it cost elsewhere

1. **`compose_suggestion` is a pure diff, and the RE-RUN is asked for on every kind but
   `cancelled`.** `_build_row` used to walk the ladder only for a `replan` row; it now does
   it for every held line that still exists, because the suggestion IS that walk diffed
   against the hold. A cancelled line is skipped (there is nothing left to walk for) and
   its whole hold is released or reallocated.
2. **The walk is taken as it comes; THE LINE IS WRITTEN BEFORE THE BATCH IS BUILT.** Every
   trigger writes the line first and raises the change after (`_propagate_planning_change`
   runs after `_upsert_lines`; the delta-seam helper's own docstring states the same order),
   so the board's walk is already at the new state and the diff needs no correction. A first
   cut trimmed a stale walk to the row's new quantity; it was removed (captain's ruling, 13
   September) because the only callers that needed it were two tests that skipped the write,
   and machinery that exists for a fixture rather than a journey is machinery to delete.
3. **The `release` path is gone, not moved.** `_oi_demand_rows`' release branch, and with it
   `_release_inquiry_rows` / `_release_note` / `_has_unlinked_row` / `_confirm_payload_reduce`,
   were only ever reachable from a reaction verb. A delayed-past-the-window line is now
   Released-and-Bought as a COMPOSITION that CS confirms, and the confirm's own
   settle-in-place seam updates the line's inquiry row - so nothing moves a row to the pool
   location behind CS's back. Moving freed quantity is Slice D's, and it will need its own
   path (the target is a row or the dealer pool, not a location string).
4. **A batch no longer applies a row nobody decided.** `build_batch` writes `decision=None`
   for every row; Apply takes `confirm` / `amend` plus `kind == cancelled` (a line the book
   closed has nothing to decide). Every test that relied on the implicit `accept` has to
   say what it decides.
5. **`_notify_purchasing` on an order inquiry is now QUEUED, not sent inline**
   (`project_order_inquiry_service.py`). It calls
   `NotificationService.create_with_channel_preferences`, which COMMITS - forbidden inside
   a savepoint by that method's own docstring - and it runs inside the confirm, which the
   batch apply wraps in one. Before Slice C a batch apply never reached it (a release
   superseded instead of confirming); now CS confirming a delayed line raises a NEW inquiry
   and the commit released the savepoint, so a perfectly written revision came back as
   "This transaction is closed" whenever a purchasing-role user existed - i.e. on live. The
   payload is queued on `Session.info` and fired by the module's existing
   `after_commit` listener on a fresh session, the same pattern
   `_dispatch_changed_with_links` already uses beside it.
6. **The board's own Confirm** (`_confirm_a_planning_change`) dispatched on
   `row.suggested in ("release", "retire")`; it dispatches on `row.kind == "cancelled"` now.

### F. Slice C review round (13 September 2026)

1. **C1, the blocker - rule 7 was not reachable.** A pure delay cuts nothing from the Buy,
   so the placed-document arm never ran and a purchase order landing in October against a
   line moved to March composed `Keep`. THE RULE, now in `compose_suggestion`: a held
   document whose **arrival + `RESERVE_WINDOW_DAYS` falls before the new required date** is
   reallocated WHOLE (rule 6's target) and the line is bought again for its own date
   ("Buy 134 for 20 Nov"); the composition is that Buy. Inside the window the document is
   kept, unchanged. Keeping it beyond the window is an Amend, never the suggestion (the
   owner's own ruling on the grill page's open 4.2). The constant is IMPORTED from
   `project_so_delta_service`, the one place it is defined - rule 2 retired this service's
   own use of it for the size of a move, not the window itself.
2. **C2 - the notify queue is keyed by the savepoint that earned it.** Each queued
   "order inquiry raised" payload carries `tx_chain`: the transaction it was written under
   and every one above it. `after_soft_rollback` (which fires on a NESTED rollback too, and
   a batch apply gives each order its own savepoint) now discards only the items whose own
   ancestry contains the transaction that rolled back, instead of popping the queue. Two
   behaviours measured on the real session: a savepoint COMMIT already drains the queue
   (SQLAlchemy fires `after_commit` on a nested commit as well), so order 1 is normally
   notified before order 2 even runs; and an item still queued at an outer scope now
   survives an inner rollback.
3. **C3 - `scripts/recompute_planning_change_proposals.py` is a Slice C backfill now.** It
   filtered `suggested == "replan"` and had become a silent no-op. It recomputes
   `suggestion_json`, `composition_json` and the re-run for every PENDING row of an
   unapplied batch that nobody has decided yet (a confirmed or amended row keeps the
   composition a person chose). Idempotent; both callers of the compose seam go through one
   function (`compose_row_state`) so the script and `_build_row` cannot drift. Run on the
   lane database: 2 rows recomposed, second run 0 changed / 2 unchanged. It is the DoD
   backfill for the new column - a row raised before the deploy otherwise shows a Was / Now
   table with no suggestion under it and a Confirm with nothing to post.
4. **C4 / C5 / C6, the wording.** The shortfall is said LAST, after every rung that could
   cover part of the unit, and names the Buy it came off ("Short 84 by 20 Aug (was Buy
   134)"). A `product_changed` row carries the item code in every sentence ("Release 134 A,
   free at BRW-IB", "Buy 134 B for 4 Sep"); every other kind stays code-free. Lateness is
   said once: `late_days` is the fact the board prints "Late by N days" from, so the
   sentence stays "Keep 134".
5. **C7 and the nits.** `_confirm_payload` deleted (no caller since the rule table went),
   the unreachable `accept` dropped from two decision tuples, `_reallocation_target`'s dead
   ORDER BACK arm removed, two unused locals dropped, and the prose naming a deleted
   function corrected. `PLANNING_CHANGE_REACTION_*` stays: `tests/test_project_so_unpublish
   .py` still writes `suggested=PLANNING_CHANGE_REACTION_KEEP` when it builds a row.

## Slice E contract (captain, 13 September 2026, issue #860, AC-E1/AC-E2; AC-X1, issue #854)

1. `challenge_if_drifted` (`project_supply_service.py`) loses every caller and is deleted
   outright, not left dead: `proposal_for` no longer challenges an active decision on the
   sheet read, `confirm` no longer challenges it on its way to `_write_decision`, and
   `project_so_reconciliation_service.py`'s `_persist` non-relink branch no longer calls it
   either (the relink branch's `supersede_for_material_change` is untouched - AC-C06 stays,
   only the SECOND signal a re-mapping never needed goes). A drift against a confirmed
   revision's frozen snapshot is never a signal of its own again; the change batch a re-run
   or manual edit raises is the only thing that supersedes an active revision now.
   `_release_supply_borrow_holds` stays a standalone method (`supersede_for_material_change`
   still calls it on a relink), and the legacy `DECISION_CHALLENGED` constant and
   `challenged_reason` serialisation stay for rows a pre-Slice-E confirm already left in that
   state.
2. Retiring the whole-decision flip uncovered a real per-line gap it had been covering for:
   `_carried_lines` carries every previously-covered, unnamed line into a fresh confirmation
   verbatim, and used to rely on `challenge_if_drifted` having already flipped the WHOLE
   decision to `challenged` (so `active_decision()` read `None` and nothing was left to
   carry) whenever any one covered line's facts had moved. With that flip gone, a line whose
   frozen link, open quantity or required date has since drifted would otherwise be carried
   on a stale snapshot. `_carry_snapshot_has_drifted` reads the same three facts `challenge_
   if_drifted` used to compare, per line, so only the drifted line goes back to undecided -
   the lines a confirmation DOES name still commit exactly as before.
3. The borrow-hold release `challenge_if_drifted` used to perform as a side effect moves to
   batch apply: `_apply_one_order` (`planning_change_service.py`), immediately before the
   order's own `confirm()` call, retires the previous active revision's step-3 supply-borrow
   placements on every line THIS BATCH has a row for (`ProjectOrderInquiryService.
   retire_supply_borrow_rows(pso_id, reason=f"Planning change {batch.id}", line_ids=list(
   by_line_id.keys()))`). `confirm()`'s own retirement of a re-decided line's old placement
   (`_retire_supply_borrows`) only reaches a line that is actually CHECKED (named in the
   payload, or carried) - a line this batch UNCOVERS or RETIRES is neither, so without this
   call its old placement would keep a document pinned to a revision that no longer covers
   it. A composition that still carries the same document is re-placed by `confirm()`
   moments later at the new quantity (one live link, never two); one that drops it leaves
   nothing pinned.
4. AC-X1 (issue #854): `_purchasing_user_ids` (`project_order_inquiry_service.py`) matches
   every role slug STARTING WITH `purchasing` (`UserRole.slug.like("purchasing%")`) rather
   than the single literal slug, so `purchasing_manager` and `purchasing_executive` are
   notified alongside `purchasing` itself; a role that merely contains the word elsewhere in
   its slug is not matched (prefix, not substring).

**Two pre-existing tests reported, not touched (captain's own instruction - no test edits;
these predate this slice and are not among the tester's rewrites):**

- `tests/test_so_supply_confirmation.py::test_a_reconciliation_link_change_supersedes_the_
  active_decision` is the OLDER AC-C06 test (`STAGE1C-scm-front-planning-promising.md`, a
  different, earlier plan) that this slice's own `test_reconciliation_without_a_relink_
  leaves_the_decision_active` (`tests/scm/test_one_signal.py`, AC-E1c) directly supersedes:
  its scenario is a quantity drift on the SAME core line, no relink, and its assertion
  (`state in ("superseded", "challenged")`) accepted the retired `challenged` outcome as one
  of two valid branches. Under AC-E1 ("no decision is set to `challenged`... the change batch
  is the only signal") that branch cannot fire and the scenario never reaches `supersede_
  for_material_change` either (nothing relinked), so the decision now correctly reads
  `active` - the exact behaviour AC-E1c pins. Measured directly: fails today with `active`
  where it asserts `superseded`/`challenged`.
- `tests/test_planning_changes.py::test_apply_returns_a_dropped_bystander_in_returned_to_
  review` and `::test_apply_of_an_already_challenged_revision_still_reports_its_bystanders`
  are fix-cluster tests from 20 August 2026 built entirely around `challenge_if_drifted`'s
  side effects inside `confirm()` (one calls `supply.challenge_if_drifted(order)` directly
  and asserts the row it leaves `challenged`; the other relies on `confirm()`'s internal
  call to it superseding a sibling line mid-request). Both fail now - one with
  `AttributeError: 'ProjectSupplyService' object has no attribute 'challenge_if_drifted'`,
  confirming the method the retired flip removed is exactly what they exercise - and neither
  can pass again without the mechanism AC-E2 explicitly retires.

## Slice D contract (captain, 13 September 2026, issue #859) and what was built

**The rule (6, 7, 10):** a `reallocate` component is not a word, it is an instruction. At
apply of a confirmed row - AFTER the confirm, because the confirm is what frees the
quantity by settling the line's own inquiry row down to what the line still needs - every
`reallocate` in `suggestion_json` is carried out.

### A. Freed document quantity (AC-D1, D2, D3)

In rule 6's own order, per component:

1. **Dealer hot-selling -> the dealer pool.** A POOL-LOCATION row: a new `OrderInquiryRow`
   in the same `OrderInquiry`, `so_line_id` NULL, verb ORDER, `stock_location` = the line's
   pool warehouse code, qty = the freed quantity, note `Reallocated from <SO> line <n>`,
   linked to the same document for that quantity through `place_on_po_allocations`. Retail
   wins over a waiting project row (the grill page's decided 3.1).
2. **Else the linking engine's priority.** `_waiting_rows` = raised or partly-linked ORDER
   rows for the product with unlinked quantity, company-wide, ranked by `_rank_raised_rows`
   (the one priority policy). The first takes what it needs, gains the link and the note
   `Found: <document> <qty>`; its order's decision is NOT touched and no revision is written
   for it - its board reads the new state next time it opens (decided 3.2).
3. **Else the pool-location row** as in 1, where the reorder engine counts it as cover.

**The hot-selling verdict and the ranking are read LIVE at apply**, not off the row: a batch
may sit for days, and where a quantity goes is decided by what is selling, and who is
waiting, when it actually moves. The words the board showed name the same walk
(`_reallocation_target` and the apply share `_waiting_rows`), so they can only differ when
the world itself has.

**A line THIS batch is re-deciding is never a candidate.** Its rows are in flux the same
apply, and handing it a quantity the next line of the loop cancels is two answers to one
question.

**The SPO half is not built.** Only an ORDER BACK row may carry an SPO allocation
(`place_on_po_allocations`'s own rule), so a pool-location ORDER row cannot hold one. A
freed SPO share is logged and left where it is for a person. THE TRIGGER for building it:
the first batch that frees SPO quantity in anger.

### B. The reserve (AC-D4, S3)

A `reallocate` whose source is `reserve`: a `SOLineAllocation` on the RECEIVING mirror line,
at the warehouse the giver held it in, `decision_id` = the receiving order's active decision
(or NULL), `confirmed_at` now, reason `Reallocated from <SO A> line <n>`. Its ORDER row is
cancelled (or reduced when only partly covered) with `Found: reserve <qty> from <SO A>`, and
its decision's `line_snapshots` are NOT rewritten - that board reads live holds.

The receiving line's `order` allocation is DELETED for the covered quantity: it holds
nothing, it is a statement that a quantity still needs buying, and it has stopped being
true. Every stock allocation on that line is untouched.

**Compose side.** `_reserve_rival` is what the ladder cannot see: `_proposal_for` walks the
board with this line's own hold carved out, so free stock reads as available and the re-run
proposes the same reserve again, while another order's earlier, unlinked row waits for it.
When there is such a row, the re-run is rewritten as a whole-unit Buy at the new date (rule
1: what is left of the stock cannot cover the unit) and the suggestion reads Reallocate +
Release + Buy. With no such row it still reads Keep (S9). **The simplification, named:** the
rewrite says Buy, because the ladder was walked once against stock the rival had not yet
claimed and has no "reserve minus this claim" input to be asked again with - so a rung that
could have covered the whole unit (the grill page's S3 ends on SPO-77) is not knowable from
here. THE TRIGGER for building that input: the first case where a whole-unit SPO or Borrow
could have covered the line and the board offered a Buy.

### C. What was retired (AC-D5)

`_apply_placed_redirect` is deleted and nothing writes `redirected_to_pool` (the column and
its readers stay for the rows already carrying it). The `placed_redirect_qty` field
`_apply_placed_offset` used to leave on a proposal fed that function alone and is retired
with it - a second answer to "where does this go" is exactly what rule 6 replaced. The
`PLANNING_CHANGE_REACTION_*` constants went too, once their last writer (a test fixture)
did.

### D. Words only (AC-D6)

Every target, note and label carries an SO number, a document number or a warehouse code.
No id reaches a sentence: `_row_target_words` resolves a receiving row to `<SO> ORDER <qty>`,
and the pool row says `Reallocated from <SO> line <n>`.

### E. Slice D review round (13 September 2026), D1 to D7

**D1. A reallocation that cannot be carried out fails the order, and the pool row carries
the product.** `_execute_reallocations` no longer swallows anything. A refusal propagates,
so the apply's per-order savepoint rolls back: the order is named in `failed_orders`, each of
its rows reads `applied_state = failed` with the message, and every row the attempt wrote
(the pool-location row above all) rolls back with it. The failure it existed to hide was
real: `_pool_row_for` addressed the row by the change row's `item_code` (whatever the book
called the item), `place_on_po_allocations` resolves a row with no sales-order line through
`products.product_code`, and the mismatch refused with `order_inquiry_no_product` - leaving
an unlinked raised ORDER row at the pool, which reads as NEW demand, while the freed purchase
order quantity sat unclaimed and the apply reported success. The pool row now carries the
PRODUCT'S own code, read from the line, and is born company-stamped and acknowledged the way
`_raise_borrow_shortfalls` raises the donor's order-back.

**D2. Freed quantity on a line nobody decided moves too, and it is composed, not
improvised.** The seam chosen is the COMPOSE side: when the line holds nothing (`held` has no
buy) but has a placed quantity larger than the fresh proposal's Buy, the suggestion emits the
`reallocate` component for the difference, and apply executes it through rule 6's three
routes exactly like any other. The alternative (executing from the links the confirm's
refresh is about to drop) was rejected because it would move quantity the board never said
would move: every reallocation must be a named instruction the reader saw before confirming.

**The freed quantity is dealt PER PURCHASE-ORDER LINE.** One sales-order line's placed
quantity routinely sits on several purchase-order lines (the G2 cascade splits a 432 across a
300 and a 132), and each of those has only its own quantity to give;
`place_on_po_allocations` refuses the whole amount against the first with
`order_inquiry_po_line_short`, and nothing moves. `_document_links_by_row` therefore keeps
`planning row id -> [{po_line_id, document, qty}]` in link order, read BEFORE the confirm
trims it, and `_take_document_shares` draws the freed amount off those lines in turn. The
destination is still ONE row - a receiving waiting row, or one pool-location row for the
whole leftover - with as many links underneath it as the quantity came off. The words name
the documents actually used, joined with "and", never an id.

**D3. The moved reserve does not belong to the receiving decision.** `_move_reserve` writes
the receiving `SOLineAllocation` with `decision_id = None`: it is a hold that survives the
next decision rather than a line of one, the same as any hold the engine's `_hold_query`
predicate counts. The receiving order's ACTIVE decision has its `line_snapshots` settled for
that line (the component becomes `reserve <qty>` where it read `buy <qty>`), so the carry
keeps the reserve rather than re-proposing the buy it no longer needs.

**D4. `exclude_line_ids` is threaded into apply.** The lines this same batch is re-deciding
are not candidates to receive what it frees - otherwise a reallocation hands quantity to a
line that is about to be uncovered in the next breath.

**D5. What actually happened is recorded in words.** Every executed target lands in the
row's `result_json` under `reallocated`, because a later read of the live world can pick a
different row than the one that received it - the record is what the row says it did, not
what a re-query would guess.

**D6. The receiving row's state is refreshed after it is reduced**, through the service's own
`refresh_link_state`, so a row whose unlinked remainder reaches zero reads `placed` instead of
staying `partly_linked`.

**D7. A freed SPO share is unallocated, never re-dealt.** Only an ORDER BACK row may carry an
SPO allocation (`place_on_po_allocations`'s own rule), so there is no waiting ORDER row and no
pool-location row that could receive one: there is nowhere to re-deal it TO. The suggestion
therefore reads "Release SPO <n> <qty>, unallocated for purchasing", apply removes the
allocation link so the incoming list shows the share unallocated, and `result_json` records
that. NEVER RECORD AN INSTRUCTION NOT CARRIED OUT is the rule this serves, and it is why the
old "Reallocate SPO" wording is gone.

**Left alone, named.** `_purchasing_user_ids` has no company filter. It is pre-existing, it
predates this lane, and widening it here would change who gets notified on an unrelated
journey: it needs its own change with its own evidence.
