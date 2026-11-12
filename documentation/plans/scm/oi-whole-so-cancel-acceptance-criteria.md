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
