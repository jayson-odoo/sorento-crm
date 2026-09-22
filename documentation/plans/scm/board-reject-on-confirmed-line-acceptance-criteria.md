# UAC: Reject on a confirmed board line

Plan: `PLAN-board-reject-on-confirmed-line.md`
Owner ruling: 22 Sep 2026, R3 (b)

## Server (`PUT /api/v1/project-sales/fulfilment-planning/lines/{key}/draft`)

- AC-B1 `{ "verdict": "rejected", "reason": "<non-empty>" }` on a line an ACTIVE decision
  covers answers 200. Afterwards no ACTIVE decision's `line_snapshots` names the line, and
  the line's draft row holds `verdict: rejected` with that reason.
- AC-B2 The revision the line left is superseded with `superseded_reason` equal to the
  reason given. Every OTHER line that revision covered is covered by the new revision with
  its allocations, claims and transfers unchanged.
- AC-B3 When the rejected line was the ONLY covered line, the revision is retired and the
  order has no active decision (the `supersede_for_material_change` branch).
- AC-B4 The line's raised supply OI row (`ORDER` / `ORDER_BACK` on the order's inquiry) is
  no longer `raised` after the reject.
- AC-B5 `{ "verdict": "rejected", "reason": "" }` (or missing) on a covered line answers
  422 `board_line_reject_reason_required`; nothing is uncovered and no draft is written.
- AC-B6 Every verdict other than `amended` and `rejected` on a covered line still answers
  409 `board_line_already_confirmed` (unchanged).
- AC-B7 A rejected verdict on an UNCOVERED line behaves exactly as today (no uncover call,
  draft written).
- AC-B8 A covered line inside an OPEN planning-change batch is treated as uncovered by the
  existing predicate: the reject writes the draft without touching any revision (unchanged).

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

- AC-E1 Board for an order with two confirmed lines. Click the X beside line A's
  `Confirmed` pill, type a reason, Reject. Pill on A reads `Rejected`; pill on B unchanged.
  Order Inquiries for the order no longer lists A's row as raised. Confirm on the board
  still succeeds afterwards and reports "1 rejected".
- AC-E2 Same through the panel: expand line B, Amend, type a reason, Reject. Same end state
  for B.
- AC-E3 Reason left empty in either place: Reject stays disabled.
