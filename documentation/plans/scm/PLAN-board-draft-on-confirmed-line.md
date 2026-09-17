# PLAN: planning board refuses a plain Save or Reject on an already-confirmed line, and catches up after a lost Confirm

Status: building (owner go 17 Sep 2026, "backend needs to be more strict")
Domain: scm / fulfilment planning board
Branch: `fix/board-draft-on-confirmed-line` (worktree `sorento_crm-board-draft-covered`, test DB `sorento_sodl_ci`)
UAC: `board-draft-on-confirmed-line-acceptance-criteria.md`

## Evidence (prod, SO314595, 17 Sep 2026)

Rev 1 confirmed at 02:11:43 for lines 1,3,4,5,7 to 14. Snapshots carried the right `core_line_id`s and the confirm deleted the drafts in its own transaction. A network outage at that instant lost the response, so the tab kept reading Saved. Between 03:10 and 03:24 the same user re-saved lines 3 to 14 from the expanded-row panel: nine drafts with verdict `approved`, two `rejected` with reason "local", all on lines the active decision already covered.

On screen: pill read `Saved` / `Rejected` on eleven confirmed lines, header read `0 to confirm · 0 rejected`, Confirm (0) disabled. Line 1, which nobody re-saved, read `Confirmed`.

## Cause

Three readers, two rules.

- `FulfilmentBoardService._attach_drafts` stamps a draft on a row whether or not `row.decision` covers it.
- `BoardDecisionPill` reads the local draft ahead of `covered`, so any draft prints `Saved` or `Rejected`.
- `confirmSummaryFor` (`_shared/lib/fulfilmentBoard.ts`) skips a covered line unless the draft verdict is `amended`, so an `approved` or `rejected` draft on a confirmed line never reaches the header or Confirm.
- `canQuickSave` already refuses a quick save on a covered line ("there is nothing to approve on a line an active decision already confirms"). `BoardLineDecisionPanel.save` / `reject` and the server's `save_draft` do not apply that rule.
- `useConfirmManyMutation` invalidates the board only on success, and `confirmAll` swallows the error, so a Confirm whose response was lost leaves the tab reading the pre-confirm state until a manual reload.

## Rulings (captain, 17 Sep 2026)

R1. **On a covered line the only draft the server accepts is an amendment.** `save_draft` refuses any other verdict with 409 `board_line_already_confirmed`, message "This line is already confirmed. Amend it to change the decision, or undo the confirmation." Covered = an ACTIVE `SOSupplyDecision` on the mirror order (`ProjectSalesOrder.so_id == core_line.sales_order_id`) whose `line_snapshots[].core_line_id` equals the core line. A superseded decision does not count. **A line named by a PENDING planning-change row (`planning_change_rows.applied_state` not applied) is exempt** (review round 1, B1): the batch board already shows such a line as uncovered so the planner can approve the batch's proposal, and that approval is a real change against the frozen decision, so the server states the same exemption once rather than the client rewriting verdicts. Order-inquiry cover (`inquiry_decided`) is out of scope: no evidence, and the panel already shows no Save for a line with no composition.
R2. **The panel says so before the round trip.** On a covered line, Save is disabled while the draft matches the frozen composition (the `approving` branch), and Reject is disabled, both carrying the sentence above in a Tooltip on a wrapper span (review round 1, S1: a `title` on a disabled button never shows, the Button primitive sets `pointer-events: none`). A change to the suspected-system-issue tick alone counts as a change. On a covered line Save always posts `amended`, never `approved`. An amendment that differs still saves.
R3. **A failed or lost Confirm refetches the board.** `useConfirmManyMutation` invalidates the board and fulfilment-planning queries on error as well as success. On every board read the panel drops a local draft whose contribution is now `covered` and carries no server draft, unless that key has a save or delete in flight, so the pill reads `Confirmed` once the server's state arrives.
R4. `confirmLinesFor`'s "approval on a covered line is posted" branch is left as is. R1 guarantees such a draft can no longer be saved, so the branch is unreachable from a stored draft; removing it is a separate tidy-up.

## Slices

One lane, one PR.

1. Backend: `project_line_draft_service.save_draft` gate (R1) + tests in `tests/test_fulfilment_line_draft_route.py`.
2. Frontend: `BoardLineDecisionPanel` disabled states (R2), `useConfirmManyMutation.onError` (R3), `FulfilmentBoardPanel` covered-line local-draft drop (R3) + vitest in the three existing spec files.
3. Review (reviewer, security-reviewer light: no auth surface changes) + agent-browser evidence on a lane stack.

No migration. No new table, flag, or setting.

## Out of scope

Undo of a whole confirmation (PR #985), rejected-on-covered as a carried verdict (would need a revision semantics decision), inquiry-covered lines.
