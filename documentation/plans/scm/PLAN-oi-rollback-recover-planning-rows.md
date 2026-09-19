# PLAN - order inquiry: recover the rows planning had worked on, and stop a rollback taking them again

Status: APPROVED by owner 20 Sep 2026, full `/feature` pipeline, backend only. Lane
`fix/oi-sheet-rebuild-from-planning`. UAC written; tickets next.
UAC: `oi-rollback-recover-planning-rows-acceptance-criteria.md` (AC-RB-1 to AC-RB-23).

## 0. What was measured

19 Sep 2026 the owner rolled the book `JAN - DEC 2026 ORDERabc.xlsx` back and re-uploaded it four
times while the line-pick fixes (#1026, #1027, #1035, #1036) landed. `scripts/rollback_oi_sheet_upload.py`
deletes EVERY row carrying the sheet's stamp, whatever planning has since done to it.

Read off the last backup before any rollback (`sorento_ai_automation_0918_1900`, prod 18 Sep 19:00),
the stamped, non-cancelled rows planning had touched: **22 rows on 4 sales orders** (SO314592 to
SO314595), all from the 2026 book, none from the 2027 book. Exported with their links to
`~/Desktop/oi-compare/recovery_0918_rows.json`.

- **10 "used" rows** (`redirected_to_pool = true`, greyed on the worklist). A replan on a line
  whose supply was already RECEIVED keeps the old row as the record of the received goods and
  raises a fresh row beside it (`Replaces 182 used; SPO-... received`,
  `project_order_inquiry_service._write`, AC-OH-40 to 42). The used row is the sheet's own row,
  so the rollback deleted it and its link. The re-upload found the line already carrying the
  fresh row and skipped it (D2). `follow_book` (#1033) then linked the fresh row to the received
  shipping order, which is what prod shows now (SO314593: 220 @ 01/03/2027, via SPO, received).
- **12 rows a confirm had restated IN PLACE** (`changed_at` set, Was/Now on the row, stamp kept).
  The rollback deleted them, the re-upload raised the sheet's figures again (SO314593 /
  SRTWCX8605-S-RL-PJ: 182 @ 01/06/2026, no Was, where it read 280 @ 01/03/2027, was 182). The
  board says Confirmed already, so nothing fires again.

The book is PURCHASING's; the planning board is customer service's (CS).

19 Sep 2026 was a Saturday; nothing suggests CS worked rows between the 18 Sep backup and the
first rollback, but section 3 re-checks that on prod before writing.

## 1. Owner rulings (19 Sep 2026)

- **R1** AutoCount's link is the only source of a link (the sheet's PO never links).
- **R2** Received goods belong to the greyed "used" row only. The fresh `Replaces ... used` row
  never carries the received shipping order.
- **R3** Recover the used rows and the Was/Now rows, and make the protection general: any row
  with these traits, not only SO314593.

Grill, 20 Sep 2026 (each measured on the 0918 copy first):

- **R4** A line planned "all from stock" (the active decision's `buy_qty` is 0) that the sheet
  still lists comes back as a PLAIN row. Measured: 6 such lines (C-FHSS24, CB231SS-NL, CB4702,
  CSA150, CSH2072, SRT2403-RG) carried a plain, untouched sheet row before the rollback, so 2.1(b)
  must skip a buy-0 line or it would stamp a false Was/Now on them.
- **R5** The `follow_book` guard in 2.2 is test-first: AC-RB-9 is written before any change to
  `follow_book`, and a guard is built only if it goes red (#1033 already never displaces a row of
  the same SO line).
- **R6** A sheet row becomes a used row only on an EXACT quantity AND date match with a fresh
  row's `previous_qty` / `previous_delivery_date`; otherwise no used row is guessed and the upload
  report names the row. Measured: 10 of 10 match exactly, and CB2807-DIY and CSH2072 each carry
  two used deliveries of the SAME quantity on one line, which only the date tells apart.
- Must-not-change, measured: TPE-9204 and SRTWC8605-SC-RL carry an untouched sheet row beside a
  second live row under an active decision that differs from the sheet. 2.1(b)'s "the line
  carries no live row" condition is what keeps them untouched (AC-RB-15).

## 2. Design - rebuild from the LIVE planning decisions (owner, 19 Sep: no recovery from an old copy)

Checked against the pre-rollback copy that everything lost is derivable from data that is still
live, 22 of 22:

- A restated row's NOW is the ACTIVE `so_supply_decisions.line_snapshots` entry for its line
  (`project_line_id` = the row's `so_line_id`; `buy_qty`, `required_date`): 12 of 12 exact. Its WAS
  is the sheet's own figure, which is what the re-uploaded row carries today.
- A used row's quantity and date are the live `Replaces N used` sibling's own `previous_qty` and
  `previous_delivery_date`: 10 of 10 exact, and they are the sheet's figures for that delivery.
  Its documents are named in the sibling's note and are AutoCount's own for the line; today they
  sit as links on the sibling, put there by `follow_book` after the used row was deleted.

So the recovery is a RULE, not a data patch, and it runs on the live database:

**2.1 The sheet row meets an active planning decision (importer, general).** When a sheet row
lands on a line that an ACTIVE supply decision covers:
- (a) the line's live row is a `Replaces N used` row with no used sibling, and the sheet row's
  quantity and date are EXACTLY that row's `previous_qty` / `previous_delivery_date` (R6): the
  sheet row is raised as the USED row (`redirected_to_pool = true`, greyed), not skipped as
  already raised. No exact match: no used row, and the upload report names the sheet row.
- (b) the line carries no live row and the decision's `buy_qty` / `required_date` differ from the
  sheet's: the row is raised already settled, NOW from the decision, WAS from the sheet,
  `supply_decision_id` and `changed_at` from the decision, the same fields
  `_settle_row_in_place` writes. A decision whose `buy_qty` is 0 for the line is skipped by
  this rule: the sheet row is raised plain, as today (R4).

**2.2 Received goods sit on the used row only (R2, general).** When a used row exists on a line,
its `Replaces N used` sibling holds no link to a RECEIVED allocation: raising the used row in
2.1(a) moves those links (and their claims, through the one link writer) from the sibling to the
used row, up to the used row's quantity, and `follow_book` never offers a received allocation to
a replacement row whose line has a used row.

**2.3 Rollback guard (prevents a repeat).** `rollback_oi_sheet_upload.rows_of` keeps a stamped
row planning has worked on (`redirected_to_pool`, or `changed_at` set, or `supply_decision_id`
set), and counts and names every kept row in the dry run and the apply output.

**Recovery on prod = deploy, then roll back and re-upload the 2026 book once.** No script, no old
copy. The 22 rows come back by 2.1 and 2.2; 2.3 keeps them through any later rollback.
`~/Desktop/oi-compare/recovery_0918_rows.json` stays only as the ANSWER KEY: after the re-upload
the 22 rows on prod must match it (quantity, Was/Now, greyed, which document sits on which row).

## 3. Order of work

1. Grill + UAC (done 20 Sep), then tickets.
2. Tester red tests: 2.1(a) used row raised greyed from a `Replaces N used` line; 2.1(b) row raised
   settled from the active decision; 2.2 received links move to the used row and follow_book leaves
   them there; 2.3 rollback keeps and names the three traits; a second re-upload changes nothing.
3. Coder; one reviewer.
4. Before prod: run the rebuilt importer on a copy restored from a CURRENT prod backup and diff the
   22 rows against the answer key.
5. Owner on prod: deploy, rollback dry run + apply, re-upload, then `compare.py` for SO314592 to
   SO314595.

## 4. Not in scope

- The Raised at history icon not showing on prod (suspected column width, 190 px does not fit
  `17/09/2026, 11:25 am` plus the icon). Separate FE small fix.
- Sales order detail header: Plan action, Edit into the gear menu. Separate FE small fix.
