# PLAN: Reject on a confirmed board line takes the line out of the confirmation and rejects it, in one step

Status: planned (22 Sep 2026). Track: small fix.
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

## Rulings (owner, 22 Sep 2026)

- R3 (b): Reject on a confirmed line = take the line out of the confirmation AND record the
  rejection, in one step, reason required. Not (a) "use Undo first", not (c) a carried
  rejected verdict over the frozen composition.

## Design (one seam)

`save_draft`, the guard that refuses today, becomes the seam that does the work:

```
if verdict == "rejected" and covered:
    uncover_lines(order, [core_line.id], actor_user_id=actor, reason=<reason>)
    # line is uncovered now; fall through to the ordinary draft upsert
elif verdict != "amended" and covered:
    409 board_line_already_confirmed   # unchanged for every other verdict
```

- `reason` is required for the rejected verdict on a covered line (422
  `board_line_reject_reason_required` when blank), and it is the sentence stamped on the
  superseded revision (`superseded_reason`), so the audit reads why the line left.
- The mirror `ProjectSalesOrder` is the one `_covered_by_active_decision` already joins
  (`ProjectSalesOrder.so_id == core_line.sales_order_id`); the coder lifts that lookup
  rather than a second query.
- After the call the line is uncovered, its draft is `rejected`, and the board's next read
  shows the `Rejected` pill exactly as an uncovered rejection does. Confirm treats it as it
  treats any rejected uncovered line today (no new path).
- A covered line inside an OPEN planning-change batch is not "covered" by the existing
  predicate, so it already rejects today; untouched.

FE, two places, same verdict:

1. **Row, beside the pill** (`BoardVerdictActions.tsx`, #1115): flips R3 / AC-B4 of
   `PLAN-board-verdict-actions-chips.md`. A covered line (`Confirmed`) now shows the pencil
   (Change decision) AND the X. The X opens the SAME reject popover (reason textarea,
   "system problem" checkbox, Reject button) the Suggested / Change proposed states use;
   submit calls `onDecide(key, { verdict: 'rejected', reason, suspected_system_issue })`
   exactly as AC-B8. No new component. Owner, 22 Sep: "beside confirmed now no button".
2. **Panel** (`BoardLineDecisionPanel`): on a covered line, once unlocked (Amend pressed),
   Reject follows the uncovered branch's own rule - enabled when `reason.trim()` is
   non-empty, with the same "Say why this line is being refused first." title when empty.
   The `CONFIRMED_LINE_TITLE` tooltip stays on Save (R2 of #989 still holds for Save: a
   plain re-save of the frozen composition is still refused). The wrapped-`span` trigger
   structure stays (it was built so the button never remounts mid-click); only `disabled`
   gets its expression.

Both paths hit the one server seam above.

## Not in scope

- Undoing a whole confirmation (PR #985, `undo_last_confirm`) - a different action.
- Reversing this rejection through the undo journal: an uncover revision is unjournalled
  today; the way back is to decide the line again and Confirm.
- Rejecting a line whose OI row purchasing already actioned - `uncover_lines` retires
  raised rows only, as it does for the purchasing-refusal path; anything past raised is
  the OI page's own concern.

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

## Verification

Browser (agent-browser, via sidebar): board with one confirmed line, expand, Amend, type a
reason, Reject. Pill reads `Rejected`, the line's OI row is gone from the order's Order
Inquiry, the order's other confirmed lines keep their pills. Confirm afterwards succeeds.

## Guide

`documentation/user-guides/supply-chain/` board guide: the sentence that says a confirmed
line can only be amended gains "or rejected with a reason, which takes it out of the
confirmation".
