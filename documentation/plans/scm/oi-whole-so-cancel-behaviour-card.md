# OI-WHOLE-SO-CANCEL behaviour card v1 (12 Nov 2026)

Case (prod copy, 12 Nov): OI-2610-0154 / SO428043. On 3 Nov AutoCount issued SO429214 for the same line;
16 min later the sync pushed SO428043 with the WHOLE HEADER cancelled (no Cancel SO document). Every OI row
on SO428043 went done at sync, no board item was raised, purchasing was never told, and SO429214 was never
planned, so the order fell out of purchasing's Outstanding.

## What each AutoCount event does today (SO line with a live OI row)

| # | AutoCount event | OI row at sync | OI screen shows | Board item | Purchasing gets |
|---|---|---|---|---|---|
| 1 | One line deleted, other lines remain | stays live, not done (`document_ingest_service.py:1747`) | "Line cancelled" at once | yes (`ingest.py:539-575`) | CANCEL ALL on CS Confirm (`planning_change_service.py:4915-4942` -> `:4122-4180`) |
| 1b | Same, but it was the SO's LAST open line | stays live | "Line cancelled" | **no** (same hole as 4) | **nothing** |
| 2 | Per-line cancelled status | not possible: AutoCount sends no per-line status (`canonical_documents.py:72-130`, `document_ingest_service.py:2182`) | - | - | - |
| 3 | Cancel SO document | stays live | board "Transfer to Cancel SO" (`autocount_cancel_ingest_service.py:849-877`) | yes | CANCEL on CS Confirm (`project_supply_service.py:1358-1481`); partial = qty change -> CHANGED |
| 4 | Whole header cancelled | **done at sync** (`document_ingest_service.py:2182` -> `:1747-1757` -> `:1805`; `project_order_inquiry_service.py:1296-1340`) | "Completed" | **no**: the diff scope is derived from lines still open (`ingest.py:553`, `outstanding_diff.py:259-263`) | **nothing, ever** |
| 5 | SO deleted (has OI rows, so it is cancelled, not removed) | **done at sync** (`deletion_service.py:600-630`) | "Completed" | **no** (no planning-change hook on the delete path) | **nothing, ever** |
| 6 | Qty / date change | row unchanged; screen shows new values live with "Was" | new values | yes | CHANGED / DELAY / ADVANCE on CS Confirm |

Kept in sync live on screen (read, never stored): delivery date (`oi_delivery_date.py:1-12`,
`order_inquiry_worklist_service.py:849,898`), SO qty (`:940`), "Line cancelled" (`:634-636`), location when the
row has none (`:844`). Stored, changed only by CS Confirm or the done flag: ordered qty, verb, date last told,
status / Done.

Scope of this lane: rows 4, 5 and 1b.

## Proposed rules (pending Q1)

1. The SO push hands the planning diff every SO it wrote as its scope (`scope_documents`, the parameter
   `outstanding_diff.diff_lines` already has for this exact case), so a wholly cancelled SO, or one whose last
   open line was removed, reads as every line `cancelled` and raises the board item. Board gate unchanged
   (`planning_change_service.build_batch`: a held line or a non-cancelled OI row).
2. The AutoCount SO delete raises the same board item (same before lines, empty after, same build_batch call).
3. CS Confirm on that item runs the existing path: OI rows cancelled, CANCEL ALL on the handover email. No new
   email path; nothing is emailed without CS.
4. (Q1 b) A whole-header cancel and an SO delete no longer mark the rows done at sync; the rows stay live
   (screen shows "Line cancelled") until CS confirms, exactly like row 1 today.

## Questions

1. **OPEN owner question.** For a whole-SO cancel / SO delete: (a) keep the 30 Oct auto-done at sync (OI reads
   "Completed" before purchasing is told; the board item still raises and CS Confirm still sends CANCEL ALL), or
   (b) keep the row live until CS decides on the board, like a removed line (FP-EMAIL-ONE-TRIGGER Q1 (a), 6 Nov).
   Rec **(b)**: the 6 Nov one-trigger rule and the 11 Oct model ("OI changes only through CS decisions confirmed
   in Fulfilment Planning") both say the row waits for CS; with (a) the OI says Completed while purchasing may
   still be buying for it. The 30 Oct "no purchasing intervention" still holds: purchasing acts only after CS
   Confirm, on the CANCEL line.
2. **How a re-issue is shown to CS.** (a) The old SO's board item reads as a plain cancel; CS plans the new SO on
   the board as any new order, and confirms the old cancel. Purchasing gets CANCEL ALL (old SO) and ORDER (new
   SO) from CS's two Confirms. No auto-pairing. (b) Also add a "Re-issued as" SO picker on the cancelled item so
   the old rows close with a note naming the new SO, and the CANCEL email line carries it. Rec **(a)** for this
   lane: it closes the hole with no new screen; (b) is new UI (needs a mock) and pairing by customer + item
   would be automatic joining, which the standing rules forbid, so it must be a person's pick. (b) can follow as
   `OI-WHOLE-SO-CANCEL B`.
3. **Rows already auto-done by this hole since 30 Oct** (OI-2610-0154 and any others). (a) This lane ships a
   read-only SQL list (cancelled / deleted SO, OI rows done by NULL, no board item) for CS to work through
   manually; (b) a one-off script that raises the missing board items (dry run default). Rec **(a)**: few rows,
   and CS has to decide each one anyway (cancel or re-issue).
4. **AutoCount reopens the header before CS decides** (cancel undone). Rec: the next push's diff reads the lines
   back as live and the pending cancelled item is superseded the same way a deleted-then-re-added line is today
   (`document_ingest_service.py:1820`); CS sees nothing to do. UNVERIFIED; a red test decides, and the card is
   re-filed if it does not hold.
5. **SO delete of an SO with no dependents** is a hard delete; it has no OI rows, so nothing changes there. Not
   a question unless you want SO deletes treated differently from header cancels anywhere on screen (rec: no,
   both read "Line cancelled" and the same board item).
