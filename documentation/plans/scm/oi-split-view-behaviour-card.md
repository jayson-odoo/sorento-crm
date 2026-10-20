# Behaviour card: OI-SPLIT-VIEW (split follow-ups after #1749)

Owner 19 Oct ~20:30 MYT (verbatim): "I am okay for 1749, can merge, you have a follow up PR to make
the split delivery at this level [planning board] and it should be based on those that are saved
only, not all the lines, and I need this split detail visible at the sales order level at the line
meaning I can visualize the split from the sales order perspective, as well as the OI perspective
at line level".

Data: dev DB `sorento_cagent_stack`, SO417636 (pso bc94d914), board revision 3 confirmed
19/10/2026 20:32 MYT. Line numbers are AutoCount's (480 / 608 / 752).

## Today (cited)

- Board "N to confirm" / "Confirm (N)" is counted in the browser only: `confirmSummaryFor`
  (`_shared/lib/fulfilmentBoard.ts:861`) over the board's contributions; it never looks at splits.
  Confirm posts only the lines the browser names (`fulfilment_planning.py:1447`, `:446`).
- The engine already knows an edited applied plan (AC-G15): `_later_change_lines`
  (`project_order_inquiry_service.py:6028-6040`) compares the saved plan's `split_plan_key`
  (`:237`, qty + date + line it sits on + cancel, never remark) with the stamp the last Confirm
  wrote on the decision. It runs only for a line with a pending AutoCount change, so a split-only
  edit on a quiet line is never posted and never acts: Confirm (0) in screenshot 712.
- SO page Lines tab is the core sales order (`scm/sales-orders/[id]/components/SalesOrderDetail.tsx:2167`,
  GET `/scm/sales-orders/{id}`, `sales_orders.py:183`): no split fields, no row expand. Splits are
  keyed by the project order (`projects.sales_orders.so_id` -> core SO, `project_so.py:472`).
- OI page Lines tab already has a read-only split grid behind the row chevron (Qty, Date, Change,
  Sits on, Remark; `orderInquiryHeaderLinesColumns.tsx:241-345`), closed by default, so only the
  "Split 3" chip shows (screenshot 714).
- The split read (`LineSplitService.read`, `project_line_split_service.py:714`) already returns every
  word the email uses (ADVANCE / REMAIN / DELAY / CANCEL BALANCE / ORDER n).

## Rules (proposed)

1. **Board counts saved split edits.** A line counts in "N to confirm" and "Confirm (N)" when its
   saved split plan differs from the plan the last Confirm applied to it (same compare as
   `split_plan_key`: qty, date, line it sits on, cancel row). A remark-only edit does not count.
   Editing back to the confirmed values drops it from the count. A line that also has a pending
   AutoCount change counts once.
2. **One function decides "edited".** One backend function answers "this line's saved plan differs
   from its last applied plan"; the board count, Confirm, Simulate confirm, the email and the Excel
   all use it, so the count can never show 1 while Confirm sends nothing (or the reverse).
3. **Confirm sends only the change.** Confirm (N) moves purchasing's OI rows of that line only
   (links and ack kept), and the email and Excel carry one row per changed split (CHANGE DATE /
   CHANGE QUANTITY, REMARK word). Unchanged splits and other lines send nothing. No CANCEL from
   splits; only an explicit Cancel row on the sheet is a CANCEL BALANCE (as in #1749).
4. **Save guard stays.** After a Confirm, a split still cannot move onto another SO line (#1749
   AC-G19 deferred, Save answers "Line <n>: a confirmed split cannot move to another line.").
5. **SO page shows the split behind (i).** A split SO line carries the "Split N" chip and an (i)
   button; (i) opens one popup (like the email view) with the line's split rows: Qty, Delivery date, REMARK word, Sits on (own line / line n / New line;
   the OI line the split rides on), Remark, plus the AutoCount extra row ("ORDER 145") so the rows
   add up to the line's qty, and one status for the plan: Confirmed / Saved, not confirmed /
   AutoCount changed.
6. **OI page: the same (i) and popup.** The OI Lines tab gets the same (i) next to "Split N" and the
   same popup; the chevron keeps what it shows today. State and PO stay on the line (no per-row
   guess).
7. **Same component both pages.** One read-only split grid, fed by the one split read, on the SO
   page and the OI page; no second copy of the words.

## Real examples (SO417636, dev DB)

| # | Line | Stored now | What happens |
|---|------|-----------|--------------|
| E1 | 480 CSK14B, AutoCount 417 @ 20/10/2026 -> 14 @ 20/09/2026 | 14 @ 20/09/2026 own (ADVANCE), 236 @ 20/11/2026 New line (DELAY), 167 @ 20/11/2026 New line (DELAY); rev 3 stamp = saved plan | Board Confirm (0), correct. SO and OI pages: chip "Split 3", three rows, status Confirmed. OI rows 14 / 236 / 167, all To Buy. |
| E2 | 480, owner fixes 167's date to 20/11/2029, Save | plan differs from rev 3 stamp | Board "1 to confirm", Confirm (1). Confirm: OI row 167 moves to 20/11/2029 (links kept), email + Excel one row 167, 20/11/2026 -> 20/11/2029, DELAY. 14 and 236 send nothing. Status Saved, not confirmed until then. |
| E3 | 752 CSK14B, AutoCount 504 @ 20/12/2026 -> 649 @ 02/01/2027 | 37 @ 20/11/2026 own (ADVANCE), 467 @ 02/01/2027 New line (DELAY), AutoCount extra 145 (ORDER 145) | Board Confirm (0). SO page line 752: chip "Split 2", rows 37 / 467 / 145 ORDER 145 (sum 649). |
| E4 | 480, remark "site not ready" typed on 236, Save | stamp ignores remark | Board stays Confirm (0); the remark shows on the SO and OI split rows. |
| E5 | 608 CSK14B, 192 -> 632, no splits, ORDER 440 confirmed | no split rows | No chip, no rows on either page; board unchanged. |

## Edge cases

- Line delivered in full: read-only, never counted (as in #1749).
- A plan applied before #1749's stamp existed counts once as edited (dev data only; production has
  no splits yet).
- Board Undo of the order's Confirm: the line goes back to pending as today; nothing new here.
- A split line on an order with no project order (core SO only): no split rows; nothing breaks.
- 375 px: split rows stack under the line inside the same horizontal scroller as the Lines grid.

## Questions (at most 5, each with a recommendation)

Q1. **Which edits count on the board?** (a) any saved plan that differs from the last applied one,
including a first split added to a line that was confirmed unsplit (608 above); (b) only lines that
already had a confirmed split plan. **Rec (a)**: one rule, and adding a split to a confirmed line
is the same "saved, not confirmed" change.

Q2. **#1749's deferred AC-G19 (moving a confirmed split onto ANOTHER line).** (a) stays deferred:
Save keeps refusing it; this lane confirms edits on the line's own and New-line rows (qty, date,
add or drop a row); (b) build it here (the engine re-plan across lines failed review 6 times in
#1749; makes this lane L). **Rec (a)**.

Q3. **SO page: split rows open or closed?** (a) open under the line by default (like the email and
Excel: one row per split, stacked downward), chevron to close; (b) closed, chevron to open (like
the OI page today). **Rec (a)**: you asked to see the split, and closed is what hid it on the OI
page.

Q4. **Where does a split that sits on another line show** (possible before the first Confirm, e.g.
480's 14 dropped onto 608)? (a) under its own line, Sits on "line 608"; (b) under line 608, as
the split sheet does. **Rec (a)**: the SO and OI pages answer "how was this line split", and the
OI page already lists splits under their own line.

Q5. **Purchasing state per split row** (To Buy / On PO + PO number). (a) show it per split row:
needs a stored link from each OI row to its split (a migration; today the engine matches a split to
its OI row by qty + date only, `project_order_inquiry_service.py:6175`, which breaks once rows merge
or a date moves); (b) keep State and PO on the line as today, and each split row says which OI line
it rides on (Sits on line 480 = OI-2609-0578 line 480; a New-line split rides on its own line).
**Rec (b)**: no migration, no guessed match; the line's State and PO stay exact.

## Answers

- Crew on ask a14412763 (19 Oct): Q1 (a), the owner's own words ("based on those that are saved
  only, not all the lines"); Q2 (a), AC-G19 stays deferred, the Save guard keeps refusing, the lane
  stays M. Q3, Q4, Q5 went to the owner with the recommendations; mock v1 (`v1.html`) was built on them.
- Owner 19 Oct ~21:05: Q3 (b) hide by default ("informational fatigue"); Q5 no database change,
  split on each OI row if exact, else an (i) button per line, else a header gear popup. Per-row is not
  exact (engine pairs split and OI row by qty + date, `project_order_inquiry_service.py:6189`; line
  752's own OI row is 182 = split 37 + extra 145). Crew ruling a14761180: pick (2), "Split N" chip + (i)
  on the line on both the OI and SO Lines tabs, one popup like the email view. Q4 still with the
  owner; mock v2 (`v2.html`) is built on Q4 (a) and marks it open.
- Owner on mock v2 (Lavish 21:44): "this one can put in an individual column? i don't want to jumble
  up the product column". Mock v3 (`index.html`): own "Split" column (chip + (i)) after Product on
  both grids, on/off in Columns; the Product cell stays clean.

## Build notes (for the plan, not for the owner)

- One function `split_plan_edited(line)` = saved `split_plan_key` != newest recorded stamp
  (`_recorded_split_plans`, `project_line_split_service.py:1021`). The board row gets a
  `split_edited` flag from it (`BoardContribution`, `schemas/project_board.py:574`); the browser
  adds those lines to its count (`confirmSummaryFor`, `fulfilmentBoard.ts:861`, once per line).
- A covered line is not postable from the browser today (`lineFor`, `fulfilmentBoard.ts:532`), so
  the server's Confirm (and Simulate) adds the order's `split_plan_edited` lines itself, and the
  AC-G15 compare (`project_order_inquiry_service.py:6028-6040`) runs for them without a pending
  AutoCount change. The browser still calls Confirm for an order whose only change is a split edit.
- SO page: the split rows ride on the core SO read (`SalesOrderService._line_inquiries`,
  `services/scm/sales_order_service.py:~651-720`, core line -> mirror line), filled by the same split
  read the OI page uses (`splits_for_lines`, `project_order_inquiry_service.py:7703`), plus the
  plan status and the extra row from `LineSplitService.read`.
- OI page: `LineSplitsList` (`orderInquiryHeaderLinesColumns.tsx:333`) moves to `_shared` and is
  reused on the SO page; split lines start expanded.
