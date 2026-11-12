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
