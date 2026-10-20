# CARD: OI-LINE-SPLIT round 3: refer back after Confirm, lump sums, split rows in the email (18 Oct)

Status: filed as a behaviour card to crew. No code until the answers come back. A masked mock follows.
Lane: OI-LINE-SPLIT, PR #1749 (head 6c4b3c0524).
Owner hand test 18 Oct 20:15 / 20:2x (verbatim in the crew relay):
- "in autocount the 192 change to 632 as lump sum, but the 632 comes from part of 417, part of 504 ...
  when i view again ... the new qty is gone ... quite confusing if i want to refer back"
- "with the split in place ... we supposed to show the split in the email as well ... the remark we also
  can take from the sheet remark? ... we preload the remark there first just like the email show
  remark? then when the user change, it is reflected in the email also"

## What the code does today (facts, file:line)

Backend paths are under `sorento_crm_backend/app/services/`: LSS = `project_line_split_service.py`, OI =
`project_order_inquiry_service.py`, SUP = `project_supply_service.py`, PCS = `planning_change_service.py`,
WL = `order_inquiry_worklist_service.py`.

- F1 **NEW QTY / NEW DATE show only while an AutoCount change is pending** (LSS:480-486, UAC AC-A2b).
  After Confirm applies the change, nothing is pending, the NEW cells go blank, and an unsplit line reads
  its current figures (LSS:135-159). 608 then reads QTY 632, and the 192 it came from is shown nowhere.
- F2 **A split line is "applied" only if the splits on the line itself equal AutoCount's open qty**
  (LSS:163-186). Otherwise it is "stale": it re-bases to AutoCount's current figures and shows "AutoCount
  changed". On SO417636, 752 has 37 on itself against AutoCount's 649, so it is stale: 37 + 467 = 504
  against 649 shows "145 left".
- F3 **The Confirm email prints one row per split only when the line is "honoured"**: either every split
  sits on its own line, or a split moved onto another line of this Confirm whose qty went up (OI:4447-4466,
  moves at OI:5742-5750). A split on "New line" (`sits_on` empty) is never honoured. The line prints as one
  row, and the unlinked rest is the netting's CANCEL (OI:4441-4443, 4461-4463). That is why the queued
  email read 480 "ADVANCE, CANCEL 403": his 236 and 167 sat on New line, not on 608. Even an honoured
  line never prints an "ORDER (new qty)" row (OI:4506-4543), which is a gap against AC-D1.
- F4 **A split's own remark reaches the email only on honoured split rows** (OI:4612 `word, remark`).
  It reaches the worklist Excel at WL:3512. Excel expands per split only for splits sitting ON the row's
  line, and only when they add up to its QTY (WL:3438, LSS:850). Every other email REMARK is generated:
  `handover_remark` OI:599-663, saved lines OI:4712-4786.
- F5 **Refer-back data exists**:
  - Every Confirm writes a new `SOSupplyDecision` with per-line snapshots, never overwritten (SUP:7307-7320;
    before is read at SUP:5601-5604, now at SUP:5646-5650).
  - The OI row keeps `previous_qty` / `previous_delivery_date`, overwritten by the next change (OI:2560-2581).
  - AutoCount's before/after per batch stays in `planning_change_rows` after apply (PCS:3689-3706).
- F6 **The 167 dated 20/01/2026 was saved before Confirm.** The shared `DatePicker` commits every keystroke
  that parses as a full DD/MM/YYYY and then reformats the input (`components/ui/date-picker.tsx:84-92`,
  :80-82). Deleting one "1" of "20/11/2026" commits 20 Jan 2026 mid-edit. The exact keys he pressed are
  UNVERIFIED.
- F7 **The email he opened was never sent.** It is outbox row 3adfde93: sent_at empty, 0 attempts,
  cancelled 12:19:41Z. He saw the stored body on System Management > Email Outbox.

## Real cases (dev DB, read-only)

| SO / item | AutoCount change | Today's sheet after Confirm | Under the rules below |
|---|---|---|---|
| SO417636 CSK14B (owner's) | 480 417 -> 14 (20/10 -> 20/09/2026); 608 192 -> 632 (same date); 752 504 -> 649 (20/12/2026 -> 02/01/2027). Owner's Excel: 608's 632 = own 192 + 236 and 167 from 480 + 37 from 752. | NEW cells blank; 608 shows 632 with no source; 752 stale with "145 left". Email: 480 "ADVANCE, CANCEL 403". | QTY 417 / 192 / 504 -> NEW 14 / 632 / 649 kept, tagged "Confirmed 18/10/2026". 608 shows "632 = 192 own + 236 + 167 (line 480) + 37 (line 752)". Email rows per split under 480 and 752. |
| SO345263 CB2805A-DIY | line 9 486 -> 474, line 10 546 -> 558, same date 01/10/2026 (12 moved; pending) | Pending: NEW 474 / 558 shown | Line 10 shows "558 = 546 own + 12 not linked yet" until staff drags 12 from line 9 onto line 10. Then "+12 from line 9", and the email says "line 9: 12 -> line 10", not CANCEL 12 + ORDER 12. |
| SO422492 CB6409 | line 240 224 -> 202; lines 1520 (+20) and 1770 (+2) added (applied) | 202, 20, 2 as current figures, no trace of 224 | 240: 224 -> 202 kept as "Confirmed"; 1520 and 1770: 0 -> 20 and 0 -> 2. Make-up: "20 not linked yet" until staff links it to line 240. |
| SO424910 SRTSP124 | line 16 76 -> 2; 8 lines added = 74 (4 + 7 x 10, monthly to 05/06/2027; pending) | Pending: 76 -> 2 and 8 added lines | Each added line shows "10 not linked yet". Staff drags line 16's pieces onto them, and the email prints line 16's split rows (2 here + 4 -> line 32 + 10 -> line 48 ...). |

Data question for the owner (no design choice): **752 went 504 -> 649 in AutoCount (+145)**, but his Excel
plans 37 + 467 = 504. Where does the extra 145 come from?

## Proposed rules

- R1 **Refer back.** After Confirm, the sheet keeps showing the change that Confirm applied, until the next
  AutoCount change arrives:
  - QTY / DELIVERY DATE = what the OI said before that Confirm (the superseded decision's snapshot).
  - NEW QTY / NEW DATE = what it says now, blank when unchanged (`handover_moves`).
  - The line is tagged "Confirmed <date>".
  - While a newer change is pending, QTY / DELIVERY DATE = the last confirmed figures and NEW = AutoCount's
    pending ones (today's view).
  - Source: decision snapshots (F5). No new table.
- R2 **Lump-sum make-up.** A line whose AutoCount qty went up shows its make-up under QTY: "632 = 192 own
  + 236 (line 480) + 167 (line 480) + 37 (line 752)", built only from splits staff dropped on it (Q3a: no
  auto-link). What the links do not explain reads in amber, e.g. "440 not linked yet". A split sitting on
  a line may keep its own typed date (the 167 @ 20/11/2029 on 608).
- R3 **Where a split goes, visible on its row.** Each split row shows a read-only destination: "this line",
  "-> line 608", "new line", or "cancel". It is a label, not the removed AUTOCOUNT LINE select; moving is
  still drag only.
- R4 **The email and Excel print the plan.** A line with acting splits prints one row per split under the
  SO line, like his Excel:
  - QTY = the line's qty, DELIVERY = the line's date (both shown once), NEW QTY = split qty, NEW DATE =
    split date, REMARK = the split's remark (R5).
  - A split linked to another line reads "-> line 608" in REMARK.
  - A rest not on any line prints its own explicit row (Q4).
  - Excel follows the same rows (WL:3423-3459).
- R5 **One REMARK.** Each split row's (and each line's) REMARK cell is pre-filled with the remark the email
  would print for it (ADVANCE, DELAY, ORDER 440, CANCEL 403, -> line 608). Staff can edit it, and the
  email and Excel print the sheet's value (owner rule "OI email one function").
- R6 **Date entry** (small fix): a typed date commits on leaving the cell or on Enter, never mid-typing. A
  calendar pick commits at once.

## Edge cases

- Two Confirms in a row: refer back shows the last one only. Earlier ones stay in the decision history.
- AutoCount cancels a line: it shows "cancelled" with its last confirmed figures. Its splits fall back to
  their own line (AC-C2).
- A line AutoCount added (base 0): QTY 0 -> NEW its qty; make-up "N not linked yet" until linked.
- A split linked to a line whose qty did NOT go up: no move (OI:5742-5750). The make-up shows it as planned
  but not in AutoCount, in amber.
- Staff edited a REMARK, then changed qty or date: the staff text stays. An untouched remark re-generates.
- Delivered in full: read-only as today, no make-up.

## Questions (each with a recommendation)

1. **Refer back after Confirm.**
   (a) R1: keep the confirmed change (before -> after) visible with "Confirmed <date>" until the next
   AutoCount change.
   (b) Today's view plus a per-line history popover.
   (c) A "Show last confirmed change" toggle.
   **Rec (a):** it is the view he asked for, from data that already exists (F5).
2. **Lump sums.**
   (a) R2: show the make-up from staff links plus an amber "N not linked yet"; staff drags the pieces.
   (b) Also pre-suggest sources: the same item's lines that went down in the same change (staff still
   confirms).
   **Rec (a):** keeps Q3a (staff links only); (b) can come later if linking is slow.
3. **Destination label on split rows.**
   (a) R3: read-only "this line / -> line 608 / new line / cancel" on each row.
   (b) No label (today).
   **Rec (a):** his 236/167 went to New line unseen and the email said CANCEL 403.
4. **What a split on "new line" tells purchasing.**
   (a) ORDER on a new line (CS adds it in AutoCount later); the email prints an ORDER row.
   (b) CANCEL unless linked to a line (today, F3), printed as its own explicit "CANCEL N" row.
   **Rec (b) plus R3:** the qty is not in AutoCount, so ordering it would buy stock no SO line holds. The
   row and the label make it visible before Confirm.
5. **REMARK pre-fill.**
   (a) R5: the generated text shows live until staff edits it; then staff text wins and the email and
   Excel print it.
   (b) Generate at Save and freeze it.
   **Rec (a):** the remark stays right while qty or date are still being edited.

## Owner answers (18 Oct evening, via crew; verbatim parts quoted)

- Q1 **(a)**. After Confirm, keep the confirmed change: QTY / DELIVERY DATE before, NEW QTY / NEW DATE after.
  A single "Confirmed <date>" may sit in the sheet's header line, NOT on each line (see Q2's no-labels rule).
- Q2 **No equations, no labels**: "whenever i see long equation + + +, again i get confused when i see too
  many label, the position of the value should be self explanatory". Where a lump sum came from is shown
  only by the POSITION of values in the existing columns. The mock shows two layouts:
  - A, "under the line it came from", like his Excel.
  - B, "under the line it landed on", where the moved row's own Line cell names its origin.
  R2's equation and "not linked yet" text are dropped.
- Q3 **(b)**: no per-row destination labels (same reason). R3 is dropped.
- Q4 "it is not really cancel 403 right, the 403 just go to other places?". Rule: **split rows NEVER net into
  a CANCEL.**
  - A split left on "new line" is a delivery of that qty at its own date. It is its own row in the sheet,
    the email and the Excel, with a pill by date (ADVANCE / DELAY / REMAIN).
  - The netting that turns an unlinked split rest into "CANCEL N" (OI:4441-4463, `_tell_splits`) stops doing
    that for split rows.
  - CANCEL appears only where the user explicitly cancels: the "Cancel this qty" drop / Cancel target makes
    an `is_cancel` split (`lineSplitModel.ts:183`, `:462`). The email word for it is "CANCEL BALANCE"
    (LSS:70-73).
  - Unchanged: AutoCount cancelling a whole line still prints "CANCEL ALL" (OI:622/661), and a line that is
    NOT split prints its AutoCount reduction as today.
- Q5 **(a)**: REMARK pre-filled live with the generated text until staff edits it. Staff text wins, and the
  email and Excel print the sheet's value.
- Data: "the extra 145 is really extra qty". AutoCount added new qty to 752, shown as a NEW QTY increase,
  not as a move. Arithmetic flag for the owner:
  - If the 37 moved from 752 to 608 (608's 632 = 192 + 236 + 167 + 37), then 752's 649 = 467 + **182**.
  - The 145 in the email is 649 - 504, without taking the 37 out.
  - The mock shows 182 and asks him to confirm.
- Approved small fix (crew, S): a typed date commits on leaving the cell or on Enter, not mid-typing
  (`components/ui/date-picker.tsx:84-92`). Red-first in the build round.
