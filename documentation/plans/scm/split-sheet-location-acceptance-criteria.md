# UAC: Detect an SO line location change (SPLIT-SHEET-LOCATION)

Plan: `PLAN-split-sheet-location-06nov.md`. Owner answers 7 Nov 2026 (Q1 to Q5).

- **AC-1** An AutoCount push (or manual SO edit) that moves only an SO line's location raises
  one `location_changed` change row for a held or inquired line, carrying the old and new
  location. Test: `tests/scm/test_so_line_location_change.py`,
  `test_a_location_move_on_a_held_line_raises_one_location_changed_row`.
- **AC-2** A move riding with a qty or date change is one row of that kind, carrying the
  location too (Q2). Test: `test_so_line_location_change.py`.
- **AC-3** Any move counts, within the pool or not (Q4). Test: every case above moves within
  one pool.
- **AC-4** A later push replacing the pending row keeps the planned location as "from"; a move
  back to the planned location with nothing else changed leaves no row. Test:
  `test_planning_change_batch_kind_parity.py` (B1 / S1 / S2 cases).
- **AC-5** The board change lightbox shows a Location Was/Now row; the history labels the kind
  "Location changed". Test: `boardChangeAnnotations.test.ts`.
- **AC-6** Purchasing hears of the move only via the board Confirm: the line's REMARK reads
  "NEW LOCATION (was <old>)", after any qty / date words (LOCATION / NEW LOCATION per AC-9); a line with acting splits says it once on its first plan row. On a line's FIRST
  Confirm (no earlier decision) the move is read against where purchasing's live order sits,
  read before the Confirm writes; every existing first-Confirm wording (CHANGED, take-backs, a
  mixed decision in full, the planner's remark) stays and the move follows it; with nothing
  else to say it is the move alone. Order Inquiry rows and links are not cancelled or
  re-ordered (Q3); a still-raised row follows the line's location as it already did. Tests: `tests/test_so_line_location_change_email.py`,
  `tests/scm/test_split_line_location_move.py`.
- **AC-7** Review split: a line with no move reads its AutoCount location, as the board, with the
  planned `stock_location` only as a fallback; a moved line reads per AC-9. Test:
  `test_so_line_location_change_email.py`.
- **AC-8** No backfill: lines moved before this ships are not flagged (Q1).
- **AC-9** (owner change request, 9 Nov 2026) In the Confirm Review split, the purchasing email table
  (HTML and text) and its Excel attachment, LOCATION prints the line's previous location and NEW
  LOCATION, right after it, the new one; filled only on a moved line, blank otherwise; the column
  shows only when some line moved. At 375px both columns show. Tests:
  `tests/test_so_line_location_change_columns.py` (email body, text part, Excel, migration
  downgrade), `test_so_line_location_change_email.py` (`was.location` on each told path, split
  read `was_location`), `tests/scm/test_split_line_location_move.py`,
  `_shared/components/locationChangeTally.test.tsx`.
