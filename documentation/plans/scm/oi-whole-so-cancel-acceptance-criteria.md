# OI-WHOLE-SO-CANCEL acceptance criteria

Card: `oi-whole-so-cancel-behaviour-card.md`. Plan: `PLAN-oi-whole-so-cancel-12nov.md`.
AC-WC-5/6 depend on owner Q1; they are written for the recommended answer (b) and are revised if the owner
picks (a).

- AC-WC-1 An AutoCount SO push that cancels the WHOLE header of an SO whose line carries a live
  (non-cancelled) OI row raises one planning-change `cancelled` row per such line, for CS on the board.
- AC-WC-2 An AutoCount SO push that removes the SO's LAST open line (other lines already cancelled or none)
  raises the same `cancelled` row for that line.
- AC-WC-3 An AutoCount SO delete (`DELETE` ingest; the SO has dependents, so it is cancelled, not removed)
  of such an SO raises the same `cancelled` row per line.
- AC-WC-4 CS Confirm (`planning_change_service.apply`) of that batch cancels the OI rows (one
  `OI_ROW_CANCELLED` audit each) and is the ONE purchasing handover email, every line a CANCEL.
- AC-WC-5 The push / delete itself sends purchasing nothing (no `order_inquiry_handover`, no
  `order_inquiry_changed_with_links`).
- AC-WC-6 (Q1 b) After the push / delete, the OI row keeps its state and ack (not acknowledged by the system)
  until CS's Confirm; the core line reads `cancelled`.
- AC-WC-7 Guards (unchanged behaviour): a re-push of an already cancelled SO raises no second row; an SO
  with no live OI row and no held decision raises nothing; a push that keeps open lines behaves exactly as
  today (one line removed still raises its row, a qty change still raises its row).
- AC-WC-8 (Q4) A header cancelled by one push and reopened by a later push before CS decides supersedes
  the pending `cancelled` row: CS has nothing to do, and an apply cancels no OI row and sends no CANCEL.

## Owner / crew answers (12 Nov)

- Q1: with the owner (crew rec (b)). The sync-time auto-done sits behind one named branch so either answer
  is a one-line change; AC-WC-6 is written for (b).
- Q2 (a): plain cancel item, no auto-pairing, no new UI.
- Q3 (a): read-only SQL list in `oi-whole-so-cancel-affected-rows.sql`; crew runs it on the dev prod-copy.
- Q4 as recommended (AC-WC-8). Q5: a hard delete has no OI rows; delete and header cancel are treated the same.
- AC-WC-7b (review, 12 Nov) A record of the push that FAILS (rolled back in its savepoint) raises no
  `cancelled` row: the scope is only the SOs this push actually wrote.

## v2 (owner rule 12 Nov ~12:45; crew decisions on card v2 Q1-Q5 (a))

Rule: the OI shows the SO's current values everywhere; any SO change since CS's last Confirm shows as the
change with status "Waiting for CS"; CS Confirm clears it and sends purchasing the email. One rule for date,
qty, line removed, whole-SO cancel, SO delete. The 30 Oct auto-done at sync is superseded.

- AC-V2-1 A whole-header cancel and an SO delete leave the OI rows' state and ack unchanged at sync
  (`WHOLE_SO_CANCEL_AUTO_DONE_AT_SYNC = False`; AC-WC-6 is no longer xfail;
  `test_fp_email_one_trigger_a_line_dropped_by_a_header_cancel_push_is_still_flagged` now asserts the row
  is NOT acknowledged).
- AC-V2-2 (Q1 a) An OI row is "waiting for CS" exactly while its SO line has a pending planning-change row in
  an unapplied batch (`planning_change_rows.project_line_id = order_inquiry_rows.so_line_id`). Derived, no
  column. The OI worklist row carries `waiting_for_cs: true|false`; it turns false after CS Confirm applies the
  batch, and after a change back that supersedes the pending row (AC-WC-8).
- AC-V2-3 (Q2 a) Purchasing cannot acknowledge a waiting row: `acknowledge_rows` refuses it (409, message
  "Waiting for CS to confirm the sales order change"); the select-all scope press skips it; the system's own
  auto-confirm does not acknowledge it either; `ack=to_confirm` does not list it (it is not purchasing's to
  confirm yet). It is still listed under every other filter, with its status.
- AC-V2-4 (Q3 a) OI Qty is the SO line's current qty (ordered less cancelled and returned) with
  "Was <confirmed qty>" (the stored row qty) when they differ, for a line with one live OI row. Multi-row
  lines: see open question below.
- AC-V2-5 Status text on the OI screen: "Waiting for CS" while AC-V2-2 holds; "SO cancelled" when the SO header is
  cancelled (header cancel or SO delete); "Line cancelled" (today's text) for any other cancelled line.
- AC-V2-6 (Q4 a) The OI Lines Excel and the per-project OI export show the same values as the screen: current
  date and qty, WAS DATE / WAS QTY, and a STATUS column with the AC-V2-5 text (else today's acknowledgement
  label). The handover email Excel is unchanged.
- AC-V2-7 The last open line removed raises a board item (AC-WC-2, built).
- AC-V2-8 Nothing is emailed at sync for any change type; CS Confirm sends the one email (AC-WC-4/5, built).
- AC-V2-4b (crew, Q3 multi-row (a)) A line with more than one live OI row keeps each row's confirmed qty in OI
  Qty; the SO Qty column shows the line's new qty with "Was <old>" (`so_line_qty` / `previous_so_line_qty`);
  the rows read "Waiting for CS" until CS's Confirm re-splits. No spreading rule.
