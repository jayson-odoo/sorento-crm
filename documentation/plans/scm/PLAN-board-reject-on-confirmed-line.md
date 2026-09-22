# PLAN: Reject on a confirmed board line is staged, and Confirm commits the withdrawal

Status: implemented, awaiting review (23 Sep 2026 rework). Track: small fix.
UAC: `board-reject-on-confirmed-line-acceptance-criteria.md`
Domain: scm / fulfilment planning board
Supersedes in part: `PLAN-board-draft-on-confirmed-line.md` R1 and R2 (PR #989), whose
"Out of scope: rejected-on-covered as a carried verdict" this plan now decides; and
`PLAN-board-verdict-actions-chips.md` R3 / AC-B4 (PR #1115, merged 22 Sep), "Confirmed line
gets Change decision only".

## Why

Owner, 22 Sep 2026, relaying user feedback: on a line the board already confirmed, the
planner presses Amend and then wants to Reject, and cannot. Users are right - it is
refused on purpose today. PR #989 (R1/R2) made a covered line accept ONLY an `amended`
draft: the server 409s any other verdict and the panel hard-disables Reject with the
sentence "This line is already confirmed. Amend it to change the decision, or undo the
confirmation." The plan that shipped it deferred "rejected on a covered line" pending a
revision-semantics decision. That decision is now taken (R3 below).

## Measured facts (primary checkout, `origin/main` 2280975f9, 22 Sep 2026)

| fact | where |
| --- | --- |
| Server guard: any verdict but `amended` on a covered line -> 409 `board_line_already_confirmed` | `app/services/project_line_draft_service.py:247-255` (`save_draft`) |
| Covered = an ACTIVE `SOSupplyDecision` on the mirror order whose `line_snapshots[].core_line_id` names the line, unless in an open planning-change batch | `project_line_draft_service.py:406-430` (`_covered_by_active_decision`) |
| FE: Amend only flips `locked`; Reject on a covered line is `disabled` with no expression, wrapped in a Tooltip carrying `CONFIRMED_LINE_TITLE` | `BoardLineDecisionPanel.tsx:134-136,897-906,959-984` |
| FE `reject()` posts `{ verdict: 'rejected', reason, suspected_system_issue }` through `onDecide` -> `useLineDraftMutation().save` -> `PUT /project-sales/fulfilment-planning/lines/{key}/draft` | `BoardLineDecisionPanel.tsx:457-464`, `useFulfilmentPlanning.ts:476-523`, `fulfilmentPlanningService.ts:621-637` |
| The list-view Undo icon beside the pill removes the DRAFT (`onDecide(key, null)`), it does not undo a confirmation | `FulfilmentBoardListView.tsx:594-609` |
| The un-decide seam that already exists: `ProjectSupplyService.uncover_lines(order, line_ids, actor_user_id=, reason=)` takes named lines OUT of the active revision, retires their supply/borrow OI rows, and leaves every other covered line verbatim; retires the whole revision when nothing else is covered | `app/services/project_supply_service.py:6908-6980` |
| `uncover_lines` is already the answer when purchasing refuses an OI row | `project_order_inquiry_service.py:5358` |
| Tests pinning today's refusal | BE `tests/test_fulfilment_line_draft_route.py:1059` (AC-B2); FE `BoardLineDecisionPanel.test.tsx:1086-1100` (AC-F1) |
| A revision minted by `uncover_lines` is not in the undo journal (`undo_last_confirm` does not reverse it) | `app/services/project_supply_undo_service.py:12` |
| **(fix round, 22 Sep 2026)** `uncover_lines`' WHOLE-REVISION branch (`covered - wanted` empty, i.e. the rejected line is the ONLY one covered) never ran `confirm()`/`refresh_for_decision`, so its `_retire_uncovered_rows` call - the thing that actually cancels a dropped line's still-raised `IV_ORDER`/`IV_ORDER_BACK` row - never fired either; `supersede_for_material_change`'s own `_release_supply_borrow_holds` only releases step-3 PLACEMENT rows (`covered_by` set), not a plain raised Buy. Confirmed empirically: a single-line order confirmed as Buy, then `uncover_lines`'d, left its `IV_ORDER` row `raised`. The owner's exact case ("one confirmed Buy line, reject it") hits precisely this branch. | `project_supply_service.py:6975-6976` (the bare `supersede_for_material_change` call, before the fix) |

## Rulings (owner, 22 Sep 2026; superseded in part 23 Sep 2026)

- R3 (b), ORIGINAL: Reject on a confirmed line = take the line out of the confirmation AND
  record the rejection, in one step, reason required, AT SAVE TIME. Not (a) "use Undo
  first", not (c) a carried rejected verdict over the frozen composition.
- R3 (b), REWORKED (owner ruling 23 Sep 2026, after hand-testing the shipped version):
  "we should confirm the rejection." The ORIGINAL R3(b) wrote the withdrawal the instant
  the reason was typed and Reject pressed - a CLICK, not a confirmation - which is out of
  step with every other board decision (Amend, Approve) staying a DRAFT until Confirm is
  pressed. Reject on a covered line is now STAGED the same way: the draft alone at save
  time, reason still required so there is something to stamp with later, and Confirm is
  what actually takes the line out - naming it in the new `ConfirmSupplyBody
  .rejected_line_ids`. (a) and (c) are still not the shape: Undo-first is still not
  required, and the frozen composition is still not carried as a rejected verdict - it is
  DROPPED from the confirmation, exactly as the original ruling said, just one press later.

## Design (rework, 23 Sep 2026): the draft is staged; Confirm carries the withdrawal

**Save (`save_draft`, `PUT .../lines/{key}/draft`)** - draft ONLY, no seam to a confirmation
any more:

```
if verdict == "rejected" and covered:
    reason required (422 board_line_reject_reason_required when blank)
    # falls through to the ordinary draft upsert - nothing else moves
elif verdict != "amended" and covered:
    409 board_line_already_confirmed   # unchanged for every other verdict
```

No `uncover_lines` call, no `coverage_for`, no per-project `_assert_can_act_on` on this
route (Confirm already has its own) - all three existed only to support the write this
rework takes back out. `_active_coverage` is asked only "is this line covered at all",
never for the order/snapshot it also returns.

**Confirm (`POST .../sales-orders/{pso_id}/confirm`)** is the write. `ConfirmSupplyBody`
gains `rejected_line_ids: List[str]` - the mirror `project_line_id`s of covered lines
carrying a staged `rejected` draft. The route (`_confirm_with_possible_rejects`, the one
seam both `confirm_supply` and `confirm_all`'s `write_one` share):

1. Refuses 422 if `batch_id` and `rejected_line_ids` are BOTH given - a pending planning
   change has no shape for a withdrawal riding beside it.
2. Reads the REASON off each named line's own staged draft (`_reasons_for_rejected_lines`),
   never off the request body, which carries none - refuses 422
   `board_line_reject_reason_required` when an id names no covered line, no draft, or a
   draft that is not `rejected` with a reason (defends a stale client). Builds the ONE
   sentence every withdrawn line's note and the revision's `superseded_reason` are stamped
   with: `"Line <no> rejected: <reason>"`, joined with `; ` when more than one line is
   named - the exact shape `uncover_lines`' own whole-revision branch already used for a
   single line (fix round, 22 Sep 2026), now built from the staged draft instead of the
   click's own body.
3. `lines` non-empty (a composition for at least one OTHER line, whether or not any is
   withdrawn): `service.confirm(order, payload, actor_user_id=, uncover_line_ids=
   rejected_line_ids)` - the EXISTING two-line branch (`PLAN-so-book-diff-replanning.md`
   section 10), unchanged. `_write_decision`'s own "Reconfirmed by CS." stamp is corrected
   to the joined sentence afterwards (`_restamp_superseded_reason`, the same post-hoc
   correction `uncover_lines` already makes for its own covered-wanted-nonempty branch).
   Journalled - undoable, exactly as an ordinary reconfirm is.
4. `lines` empty, `rejected_line_ids` non-empty: `service.uncover_lines(order,
   rejected_line_ids, actor_user_id=, reason=<joined sentence>)` directly - the SAME method
   the draft-save used to call at click time, now called by Confirm instead, one press
   later. Its own two branches are UNCHANGED by this rework: some other covered line
   survives (a fresh revision, ordinary carry-forward retirement) or none does (the
   whole-revision branch, `retire_rows_for_dropped_lines`, the fix-round-3 fix below - still
   the thing that actually cancels a plain raised `IV_ORDER`/`IV_ORDER_BACK` row). NOT
   wrapped in `UndoJournal` - `uncover_lines` mints an unjournalled revision, the existing,
   deliberate invariant `project_supply_undo_service.py`'s own module docstring states -
   not undoable, same as the purchasing-refusal path that also calls it.
5. Neither: the existing `supply_nothing_to_confirm` 422 (now reads "no lines and no
   withdrawals").
6. A withdrawn line's DRAFT is kept, never deleted - only a line NAMED in `lines` has its
   draft promoted-and-deleted, the existing rule.
7. Response gains `rejected_count` (`ConfirmResult`, and the per-order twin on
   `ConfirmManyOrderResult`) - the FE toast's "M withdrawn".

FE, two places, same verdict, UNCHANGED by this rework - they only ever wrote the draft,
never called `uncover_lines` themselves, so nothing about them assumed the old click-time
seam:

1. **Row, beside the pill** (`BoardVerdictActions.tsx`, #1115): a covered line (`Confirmed`)
   shows the pencil (Change decision) AND the X. The X opens the SAME reject popover (reason
   textarea, "system problem" checkbox, Reject button) the Suggested / Change proposed
   states use; submit calls `onDecide(key, { verdict: 'rejected', reason,
   suspected_system_issue })`. No new component.
2. **Panel** (`BoardLineDecisionPanel`): on a covered line, once unlocked (Amend pressed),
   Reject follows the uncovered branch's own rule - enabled when `reason.trim()` is
   non-empty. The `CONFIRMED_LINE_TITLE` tooltip stays on Save.

What DID change on the FE (`_shared/lib/fulfilmentBoard.ts`,
`fulfilment-planning/components/FulfilmentBoardPanel.tsx`,
`_shared/hooks/useFulfilmentPlanning.ts`):

- `rejectedCoveredLineIdsFor(contributions, salesOrderId, draft)` (new): the covered lines a
  `rejected` draft is staged on, for one order - `ConfirmSupplyBody.rejected_line_ids`'
  own builder, the withdrawal twin of `confirmLinesFor`.
- `plannedLineCount`/`confirmSummaryFor`: a covered rejected line now counts in `toConfirm`
  (Confirm has something to DO with it: withdraw it) AS WELL AS in `rejected` - it used to
  count as neither, back when a covered line's own rejection was refused outright and
  "carried rather than rejected" was the only sane reading.
- `FulfilmentBoardPanel`'s `wantedOrders`/order-building loop: an order with a covered
  rejected line is now IN the Confirm-all batch, and its request carries
  `rejected_line_ids` (guarded to `[]` when the order also carries a pending planning-change
  `batch_id`, matching the server's own refusal of that combination). An UNCOVERED rejected
  line still has nothing active to withdraw and stays excluded, as before.
- The post-confirm toast appends `· M withdrawn` when `M > 0` (`rejected_count` summed
  across the order results), same shape as the existing `kept`/`left out` clauses.
- `useLineDraftMutation`'s save REVERTED to a plain cache patch, invalidating nothing - the
  S3 lift (fix round 3, 22 Sep 2026) existed only to keep the reject-on-covered save's own
  wider effects visible, and that write no longer has any. `confirmationInvalidationKeys()`
  (born as a hotfix for a circular-import crash the S3 lift's module-level const hit on the
  order-inquiries page) is removed with it - `useConfirmManyMutation`'s `onSuccess` is back
  to its own plain `invalidateQueries` calls. The IMPORT CYCLE itself
  (`useFulfilmentPlanning.ts` <-> `useOrderInquiry.ts`, `ORDER_INQUIRY_*_KEY` one way,
  `PLANNING_BOARD_KEY` the other) is UNCHANGED and UNFIXED - recorded here as a trigger for
  a later cleanup lane, not addressed in this one.

## Not in scope

- Undoing a whole confirmation (PR #985, `undo_last_confirm`) - a different action.
- Reversing an UNJOURNALLED withdrawal (Confirm with `lines` empty, only
  `rejected_line_ids`) through the undo journal - the way back is to decide the line again
  and Confirm. A withdrawal that rode alongside a real composition (`lines` non-empty) IS
  journalled and IS undoable, same as any other reconfirm (AC-B14).
- Rejecting a line whose OI row purchasing already actioned - `uncover_lines` retires
  raised rows only, as it does for the purchasing-refusal path; anything past raised is
  the OI page's own concern.
- A withdrawal riding alongside a pending planning-change batch - refused outright (422),
  not attempted; `_confirm_a_planning_change`'s own apply has no shape for it.
- Fixing the `useFulfilmentPlanning.ts` / `useOrderInquiry.ts` circular import the hotfix
  worked around - named above as a trigger for a later cleanup lane.

## Tests

pytest, `tests/test_fulfilment_line_draft_route.py` (flip AC-B2, add):

- Red 1: PUT `{verdict: "rejected", reason: "wrong site"}` on a covered line -> 200; the
  line's `core_line_id` is no longer in any ACTIVE decision's `line_snapshots`; the draft
  row holds `verdict: rejected`; the superseded revision carries
  `superseded_reason == "wrong site"`.
- Red 2: same order, two covered lines, reject one -> the other stays covered, with its
  allocations untouched (`uncover_lines`' own rule, asserted at this seam).
- Red 3: PUT `{verdict: "rejected", reason: ""}` on a covered line -> 422, nothing
  uncovered, no draft written.
- Red 4: PUT `{verdict: "approved"}` on a covered line -> still 409 (the other verdicts are
  unchanged).
- Red 5: the covered line's raised supply OI row is retired by the reject (state not
  `raised` afterwards).
- Red 11 (fix round, 22 Sep 2026): the OWNER's own case - a SINGLE covered line (nothing
  else covered), confirmed as Buy, rejected -> its raised `IV_ORDER` row is no longer
  `raised` (`test_rejecting_the_only_covered_line_retires_its_raised_order_row`), and the
  same for a Buy CS marked "Order back" (`IV_ORDER_BACK`, no `covered_by` document -
  `test_rejecting_the_only_covered_line_retires_its_raised_order_back_row`). Fixed in
  `ProjectOrderInquiryService._retire_uncovered_rows`'s new `only_line_ids` mode (widens the
  verb set to `IV_ORDER_BACK`, drops the "diff against a successor decision" filter since
  the whole-revision branch writes no successor, and explicitly SKIPS a row purchasing has
  already rejected - `ack_state == ACK_REJECTED` - because `reject_row`/`reject_rows`
  reaches this same seam through `_uncover_rejected_lines`, and cancelling `row.state` there
  dropped the row out of the ack-summary's `rejected` facet, caught live by
  `test_the_summary_ack_facet_carries_all_four_keys_by_name`
  (`tests/test_order_inquiry_handshake_edges.py`) failing once the first cut of this fix
  landed).

vitest, `BoardVerdictActions.test.tsx` (flip AC-B4 of #1115, add):

- Red 9: covered line -> pencil AND X render; Accept does not.
- Red 10: X opens the popover; Reject with a typed reason calls `onDecide` with
  `{ verdict: 'rejected', reason, suspected_system_issue }`; a failed `onDecide` keeps the
  popover open (AC-B8 rule reused).

vitest, `BoardLineDecisionPanel.test.tsx` (flip AC-F1, add):

- Red 6: covered line, Amend pressed, reason empty -> Reject disabled, title "Say why this
  line is being refused first."; Save still disabled with `CONFIRMED_LINE_TITLE`.
- Red 7: type a reason -> Reject enabled; click -> `onDecide` called with
  `{ verdict: 'rejected', reason, suspected_system_issue }`.
- Red 8: before Amend (locked) nothing changes: only the Amend button renders.

**Fix round 3 (review), 23 Sep 2026:**

- B1: `_retire_uncovered_rows`' `only_line_ids` mode was missing the
  `supply_decision_id == decision.id` predicate the ordinary branch carries, so a
  book-change reaction row on the SAME line (no `supply_decision_id`) was cancelled
  alongside the decision's own row -
  `test_rejecting_a_covered_line_does_not_retire_a_book_change_row_on_the_same_line`.
- B2 (kill-test gap): every test up to this round was a one-line-one-row order, so nothing
  pinned `so_line_id.in_(only_line_ids)` itself with a second line's row in play - line 2's
  row carries the SAME decision id as line 1's, so only the line filter (not the decision-id
  predicate) excludes it -
  `test_rejecting_the_only_covered_line_leaves_a_sibling_lines_live_row_alone`.
- S1: `save_draft` ignored `uncover_lines`' own return value; `False` (nothing left to
  uncover) now raises a 409 `board_line_confirmation_moved` (nit, review: its own code and
  sentence, not `board_line_already_confirmed`'s "...reject it with a reason..." - the
  caller just did) rather than falling through to a 200 that wrote a `rejected` draft over
  a still-covered line -
  `test_a_reason_given_reject_that_uncovers_nothing_is_refused_not_silently_written`.
- S2: `save_line_draft` now runs `_assert_can_act_on` (Confirm's own per-project check)
  when the verdict is `rejected` AND the line is covered - the branch that reaches
  `uncover_lines` - via the new read-only `project_line_draft_service.coverage_for`; an
  uncovered line's rejection keeps needing only the module permission -
  `test_a_reject_on_a_covered_line_needs_the_projects_own_edit_rights`,
  `test_a_reject_on_an_uncovered_line_still_needs_only_the_module_permission`.
- S3 (FE): `useLineDraftMutation`'s save patches the cache as before, but when the saved
  verdict is `rejected` and the contribution WAS covered, it also invalidates the board
  query and the same key family `useConfirmManyMutation` invalidates (lifted to a shared
  const, `CONFIRMATION_INVALIDATION_KEYS`) - a reject that uncovers a line changes the
  same surfaces a Confirm does, just smaller.
- S4: the three retirement tests and the handshake-edges skip guard now assert the exact
  `state` (`INQUIRY_CANCELLED`, never a bare `!= raised`) and the exact `note`; the
  `only_line_ids` mode's own note is now `"Taken out of the confirmation: <reason>"`
  rather than a bare reason fragment, matching the "Superseded by revision N" shape the
  ordinary branch already writes.
- AC-B8 (open planning-change batch) note: no dedicated reject test was added for it this
  round - it is guarded INDIRECTLY by the existing `approved`-verdict batch tests
  (`test_a_pending_planning_change_in_an_open_batch_exempts_the_line` and its siblings),
  because the batch exemption sits in `_active_coverage` itself, upstream of the verdict
  branch `save_draft` takes once coverage is known: a line the predicate reads as
  uncovered takes ANY verdict, `rejected` included, through the plain save path those
  tests already pin.
- AC-B5's "or missing" half (the reason key absent, not merely blank) had no test of its
  own until this round - `test_a_rejection_with_the_reason_key_entirely_missing_is_also_refused`.

**Rework, 23 Sep 2026 (owner ruling, "we should confirm the rejection"), all in
`tests/test_fulfilment_line_draft_route.py` unless named otherwise:**

- Red 1/3/4 keep their SHAPE but move to the DRAFT save: covered+rejected now answers 200
  with the draft written and NOTHING else moved (same active decision id, `superseded_reason
  is None`, the OI row still `raised`) -
  `test_a_rejection_with_a_reason_on_a_confirmed_line_is_staged_not_written` (replaces the
  old `..._uncovers_it_and_records_the_rejection`); the two 422 reason tests are unchanged
  in substance. Red 4 (`test_an_approval_on_a_confirmed_line_still_refuses_with_409`) is
  untouched - `approved` was never part of this rework.
- Red 2/5/11 and fix-round-3's B1/B2 move to being reached through CONFIRM
  (`ConfirmSupplyBody.rejected_line_ids`) instead of the draft PUT - same underlying
  mechanism (`uncover_lines`, `_retire_uncovered_rows`'s `only_line_ids` mode), same
  assertions, new caller: `test_rejecting_one_covered_line_leaves_a_sibling_lines_
  allocation_untouched`, `test_rejecting_a_covered_line_retires_its_raised_order_row`
  (now also asserts `superseded_reason == "Line 10 rejected: wrong site"`),
  `test_rejecting_the_only_covered_line_retires_its_raised_order_row`/`..._order_back_row`
  (note text now carries the "Line \<no\> rejected: " prefix, since the reason is read off
  the staged draft and formatted by the route rather than passed bare),
  `test_rejecting_a_covered_line_does_not_retire_a_book_change_row_on_the_same_line`,
  `test_rejecting_the_only_covered_line_leaves_a_sibling_lines_live_row_alone`.
- S1 (the no-op-uncover 409 test) DROPPED - `save_draft` no longer calls `uncover_lines` at
  all, so there is nothing for it to ignore the return value of.
- S2 (the two `_assert_can_act_on`-on-draft-save tests) DROPPED - the check moved to
  Confirm, which already ran it; see AC-B13 above instead.
- New CONFIRM tests (same file, reusing its fixtures rather than
  `test_so_supply_confirmation.py`'s - a deviation from the brief that asked for the latter,
  made for fixture reuse; noted here so a later reader is not surprised by the location):
  `test_confirming_a_new_composition_alongside_a_staged_reject_withdraws_both` (AC-B2, the
  `lines` non-empty branch, `rejected_count == 1`), `test_confirming_with_only_a_rejection_
  and_nothing_else_covered_leaves_no_active_decision` (AC-B3, the whole-revision branch
  through the route), `test_rejected_line_ids_naming_a_line_whose_draft_is_not_rejected_is_
  refused` (AC-B10), `test_confirming_with_neither_lines_nor_rejections_is_still_refused`
  (AC-B11), `test_an_outsider_confirming_only_a_rejection_is_still_refused_with_403`
  (AC-B13).
- vitest: `useFulfilmentPlanning.test.tsx`'s two S3 tests reworded to pin the REVERTED
  behaviour (plain cache patch, nothing invalidated, covered or not).
  `fulfilmentBoard.test.ts`'s `confirmSummaryFor` test that used to pin "carried rather than
  rejected" on a covered reject is flipped to "BOTH rejected and something this press
  confirms", plus three new `rejectedCoveredLineIdsFor` tests.
  `FulfilmentBoardListView.test.tsx` gains one test pinning Undo on a covered rejected row
  (AC-E4): `onDecide(key, null)`, same as any other Undo, and the pill reads `Confirmed`
  again afterwards (`verdictOf`'s existing `covered && !decision` rule, no code change).

## Verification

Browser (agent-browser, via sidebar), REWORKED for the staged/Confirm-carries shape: board
with one confirmed line, expand, Amend, type a reason, Reject. Pill reads `Rejected`; the
line's OI row is STILL on the order's Order Inquiry (staged, not yet withdrawn); Confirm
button reads `Confirm (1)`. Press Confirm: the OI row is now gone, the toast names "1
withdrawn", the order's other confirmed lines keep their pills.

## Guide

`documentation/user-guides/supply-chain/` board guide: the sentence that says a confirmed
line can only be amended gains "or rejected with a reason - Reject stages the withdrawal,
and Confirm is what actually takes the line out and tells purchasing".
