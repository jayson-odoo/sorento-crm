# UAC: Reject on a confirmed board line

Plan: `PLAN-board-reject-on-confirmed-line.md`
Owner ruling: 22 Sep 2026, R3 (b); REWORKED 23 Sep 2026 (hand-test feedback, "we should
confirm the rejection") - see the plan's Design section for the current contract. AC-R*/
AC-F* (the row actions and the panel) are unchanged by the rework; AC-B* and AC-E1/AC-E4
below are not.

## Server, draft save (`PUT /api/v1/project-sales/fulfilment-planning/lines/{key}/draft`)

- AC-B1 `{ "verdict": "rejected", "reason": "<non-empty>" }` on a line an ACTIVE decision
  covers answers 200. The draft row holds `verdict: rejected` with that reason. NOTHING
  ELSE moves: the line is still named in the SAME active decision's `line_snapshots`
  afterwards (same revision id, no supersede), and its raised supply OI row is still
  `raised`. The save is STAGED, exactly like every other board decision - only Confirm
  actually withdraws the line.
- AC-B5 `{ "verdict": "rejected", "reason": "" }` (or missing) on a covered line answers
  422 `board_line_reject_reason_required`; nothing is written.
- AC-B6 Every verdict other than `amended` and `rejected` on a covered line still answers
  409 `board_line_already_confirmed` (unchanged).
- AC-B7 A rejected verdict on an UNCOVERED line behaves exactly as today (draft written,
  nothing else moves - unchanged by the rework, since it never touched a confirmation).
- AC-B8 A covered line inside an OPEN planning-change batch is treated as uncovered by the
  existing predicate: the reject writes the draft without touching any revision (unchanged).

## Server, Confirm (`POST /api/v1/project-sales/sales-orders/{pso_id}/confirm`)

Confirm is what actually withdraws a staged reject - `ConfirmSupplyBody.rejected_line_ids`,
the mirror `project_line_id`s of covered lines carrying a `rejected` draft.

- AC-B2 A press naming both `lines` (a composition for at least one OTHER line) and
  `rejected_line_ids` withdraws the named lines AND replaces/carries the rest in ONE fresh
  revision - `superseded_reason` on the revision it replaces reads "Line \<no\> rejected:
  \<reason\>" (joined with `; ` when more than one line is withdrawn), never
  `_write_decision`'s own "Reconfirmed by CS.". Every OTHER line the old revision covered
  that this press does not also touch is carried into the new revision with its
  allocations, claims and transfers unchanged. `rejected_count` on the response equals the
  number of ids withdrawn.
- AC-B3 A press naming `rejected_line_ids` ONLY (`lines` empty), where the withdrawn
  line(s) were the ONLY covered ones, retires the revision with no successor - the order
  has no active decision afterwards.
- AC-B4 The withdrawn line's raised supply OI row (`ORDER` / `ORDER_BACK` on the order's
  inquiry) is no longer `raised` after Confirm. **REWORDED, fix round, 23 Sep 2026**: its
  note carries the row's OWN BARE reason - "Taken out of the confirmation: \<reason\>" -
  on BOTH the path that carries the withdrawal through `confirm()`'s own
  `uncover_line_ids` (AC-B2's own mixed press) and the path that reaches `uncover_lines`
  directly (AC-B3's withdrawal-only press). The JOINED "Line \<no\> rejected: \<reason\>;
  ..." sentence, one clause per withdrawn line, is `superseded_reason`'s alone (AC-B2
  above) - never the row's own note, on either path.
- AC-B9 The withdrawn line's DRAFT is kept, never deleted by Confirm - only a line NAMED in
  `lines` has its draft deleted (the existing promote-and-delete rule), same as an ordinary
  uncovered rejection keeps its draft today.
- AC-B10 `rejected_line_ids` naming a line whose own draft is not a `rejected` one with a
  reason (a stale client) is refused 422 `board_line_reject_reason_required`; nothing is
  written.
- AC-B10b **NEW, fix round, 23 Sep 2026 (B1, review):** `rejected_line_ids` naming a line
  the ACTIVE decision does not (or no longer) COVER - a stale tab, or a line another
  mechanism (purchasing's own refusal, a planning-change apply) already dropped out of
  coverage since the reject was staged - is refused 422
  `board_line_withdrawal_not_covered`, "This line is not confirmed any more. Reload the
  board."; nothing is written, on both the mixed and the withdrawal-only path.
- AC-B11 A body naming NEITHER `lines` NOR `rejected_line_ids` is refused (the existing
  `supply_nothing_to_confirm` refusal, now read as "no lines and no withdrawals").
- AC-B12 `rejected_line_ids` alongside `batch_id` (a pending planning change) is refused
  422 - a batch apply has no shape for a withdrawal riding beside it.
- AC-B13 An outsider (module EDIT permission but not the project's own salesperson or an
  approved collaborator) is refused 403 by the SAME `_assert_can_act_on` check Confirm
  already runs, even when the press carries only a withdrawal.
- AC-B14 Undoability: a press that reaches `uncover_lines` directly (`lines` empty, only
  `rejected_line_ids`) mints an UNJOURNALLED revision, same as the purchasing-refusal path
  - not undoable. A press that carries the withdrawal through `confirm()`'s own
  `uncover_line_ids` (because `lines` was also non-empty) is journalled exactly as an
  ordinary reconfirm is - undoable.
- AC-B15 **NEW, fix round, 23 Sep 2026 (S4, review):** a covered line's staged reject on
  an order that ALSO carries a pending planning-change batch (AC-B12's own refusal, so it
  cannot ride along regardless of which line the batch's rows themselves name) is EXCLUDED
  from the board's "Confirm (N)" count - the X stays enabled and the reject stays staged,
  but the counter must never promise a withdrawal this press cannot carry out. The
  confirm-all press still runs the rest of the order normally and names the held-back
  line in the results panel ("Line N: rejection is staged; it commits after the pending
  change is applied.").

## Row actions (`BoardVerdictActions`, beside the pill)

- AC-R1 A covered line (`Confirmed` pill) shows the pencil (Change decision) AND the X.
  Accept does not render. (Replaces #1115 AC-B4.)
- AC-R2 The X opens the same reject popover as on a Suggested line: reason textarea,
  "system problem" checkbox, Reject button; Reject is disabled until a reason is typed.
- AC-R3 Popover Reject calls `onDecide(key, { verdict: 'rejected', reason,
  suspected_system_issue })`; the row's click does not toggle expansion. A failed
  `onDecide` keeps the popover open.
- AC-R4 Both views (List view and the grid cell breakdown dialog) show the same set on a
  covered line.

## Panel (`BoardLineDecisionPanel`)

- AC-F1 Covered line, locked: only Amend renders (unchanged).
- AC-F2 After Amend, reason empty: Reject is disabled with the title "Say why this line is
  being refused first."; Save is disabled with the "This line is already confirmed..."
  tooltip (R2 of #989 unchanged for Save).
- AC-F3 After Amend, reason typed: Reject is enabled; clicking it calls `onDecide` with
  `{ verdict: 'rejected', reason, suspected_system_issue }`.
- AC-F4 The Reject trigger element is the same DOM node before and after the reason is
  typed (no unmount on the enabled flip).

## Browser (agent-browser, via sidebar)

- AC-E1 REWORKED (23 Sep 2026): board for an order with two confirmed lines. Click the X
  beside line A's `Confirmed` pill, type a reason, Reject. Pill on A reads `Rejected`; pill
  on B unchanged - AND Order Inquiries STILL lists A's row as raised (staged, not yet
  withdrawn). Confirm button reads `Confirm (1)`. Press Confirm: A's row in Order Inquiries
  is no longer raised, pill on B stays `Confirmed`, and the toast names "1 withdrawn"
  alongside whatever else the press confirmed.
- AC-E2 Same through the panel: expand line B, Amend, type a reason, Reject. Same end state
  for B (staged; Confirm still owed to actually withdraw it).
- AC-E3 Reason left empty in either place: Reject stays disabled.
- AC-E4 Undo on line A BEFORE pressing Confirm (the list-view Undo icon, or the panel):
  A's draft is removed and its pill returns to `Confirmed`. Nothing moved server-side - no
  revision written, A's OI row still raised, Confirm button reflects one fewer line.
