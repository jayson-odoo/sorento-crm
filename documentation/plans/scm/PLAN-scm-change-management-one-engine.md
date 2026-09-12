# PLAN: managing a sales-order change after planning, one engine

**Status:** Slices A, B and C built (C's Phase 1 and Phase 2 both). Same lane/scm-change-a-diff-parity, ONE PR
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
2. **A stale walk is fitted to the line's own new quantity** (`_fit_to_new_quantity`). The
   board walks the LIVE line, and production writes the line before it raises the change -
   but a caller that diffs before it writes (two of the red tests do) came back sized to
   the old quantity, and diffing against that offers to keep a Buy for stock the customer
   no longer wants. Which rungs were chosen stays the engine's answer; only the size is the
   line's. A walk sized to NEITHER quantity is left alone: that is a partially delivered
   line.
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
