# PLAN: CONFIRM-REMARK-FIX

Status: in review, PR #2116. Track: small fix track (no migration, no auth/RBAC change). Follow-up
to merged #2091 (`PLAN-confirm-preview-stale-2nov.md`, UAC
`confirm-preview-stale-2nov-acceptance-criteria.md`), from the crew re-check on #2091's last head
(SO394876 real Confirm, SO425045). Owner rule honoured: popup = email = Excel.

## Items and outcome

### F1 (prod bug): the SO Remark typed in the Confirm popup was blank in the queued email

Cause: a Confirm that answers a planning-change batch tells purchasing
(`planning_change_service._notify_purchasing`), and `NotificationService.create_with_channel_preferences`
commits. That root commit drained the handover email (the post-commit listener in
`register_order_inquiry_post_commit_dispatch`) before `confirm_all`'s `write_one` stamped the
planner's SO remark (`stamp_so_remark`). The older SO-remark tests had no active purchasing user,
so the notify returned early and never committed. The dry run and Simulate never commit, so they
printed it.

Fix: the batch notify is queued (`queue_purchasing_notification`, the order inquiry service's own
post-commit purchasing queue) and sent on a fresh session once the write commits; a rollback of
the transaction it was queued under drops it. The Confirm no longer commits mid-write.

### F2: the planner's own line remark printed in the popup, not in the email or Excel

Cause: a batch Confirm rebuilds each line from the batch row's stored composition;
`_validate_composition_shape` and `_to_confirm_line` dropped `ConfirmLine.remark`, so the frozen
line had no own remark and the email printed the generated words. Fix: both carry it. A plain
Confirm was already right.

### F3: two email dry runs per change

Cause: the guide's email dry run was keyed on `rawBoard.dataUpdatedAt`, which the save's cache
patch (`useLineDraftMutation`) moves as well as the board re-read after it. Fix: it keys on
`usePlanningBoardReadAt()`, which moves only when a board fetch answers (a query-cache success that
is not `manual`).

### Speed (owner saw slow previews; one dry run is about 3 s of real Confirm work)

- The guide's email dry run covers only the order on screen (`ConfirmGuideDialog.onPageChange`,
  `emailPreviewBody(body, psoId)`), once per board read per order; the Confirm step runs none (the
  press runs its own). Next on a later page now waits for that page's own dry run.
- At most one in flight: the run a newer one replaces is aborted (`AbortSignal` through the hook,
  the service and `apiFetch`); an abort toasts nothing.
- The preview (`confirm_many` with `preview`) takes `SET LOCAL lock_timeout = '5s'`, the bound
  Simulate takes; a lock wait answers "Another change to this order is being saved right now. Try
  again in a moment." Simulate itself is untouched (lane SIMULATE-CONFIRM-SPEED, #2115).

## Tests

- Backend, red first: `tests/scm/test_confirm_remark_fix.py` (F1 with an active `purchasing*`
  user, one email per press, F2 email = dry run = planner's words and frozen remark, preview lock
  timeout set and not on the real press, lock-wait message). The purchasing-notify suites now read
  the send through a spy that commits its session as the real one does
  (`test_planning_change_apply_notifies_purchasing.py`, `..._notify_survives_a_failed_sibling.py`).
- Vitest: `FulfilmentBoardPanel.confirmGuide.test.tsx` "CONFIRM-REMARK-FIX" (one dry run per save
  with a slow re-read, order on screen only and no re-run on Back, superseded run aborted); all
  three fail on main's sources.

## Open

- `cs_note` (the planner's "CS: ..." note on a Buy) is dropped by the same two functions as F2.
  Not in this lane; asked on the PR.
- Hand test: `laneboard/scripts/2116.md`.
