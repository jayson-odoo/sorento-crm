# UAC: OI-SPLIT-VIEW (split follow-ups after #1749)

Status: APPROVED for build (owner, Lavish 21:54: mock v3 OK, Q4 = (a), plus the gear items of section D, recorded as
mock v4). v2 note 21:44: the chip goes in its own column. Card:
`oi-split-view-behaviour-card.md`. Mock: `documentation/mockups/OI-SPLIT-VIEW/index.html`.
Rulings: Q1 (a), Q2 (a) (crew, ask a14412763); Q3 (b) and Q5 = (i) popup per line (owner + crew
ruling a14761180); Q4 (a) (owner, 21:54).

Words: the **applied plan** of a line is the `split_plan` stamp on the newest decision of its order
that names the line (`_recorded_split_plans`, `project_line_split_service.py:1021`). A line is
**split-edited** when it has saved splits and `split_plan_key(saved splits)`
(`project_order_inquiry_service.py:237`) differs from its applied plan (none counts as different).

Examples use the owner's SO417636 as stored on the dev DB (revision 3): line 480 = 14 @ 20/09/2026
own, 236 @ 20/11/2026 New line, 167 @ 20/11/2026 New line (AutoCount 417 @ 20/10/2026, now 14 @
20/09/2026); line 752 = 37 @ 20/11/2026 own, 467 @ 02/01/2027 New line, AutoCount extra 145 (504
@ 20/12/2026, now 649 @ 02/01/2027); line 608 has no splits (192 -> 632, ORDER 440).

## A. Planning board: saved split edits are confirmed

- A1 **One function.** One backend function answers "split-edited" for a line. The board row, the
  Confirm, Simulate confirm and the split popup (B) all read it; nothing else recomputes it.
- A2 **Counted on the board.** The board payload marks each split-edited line (a flag on the
  line's board row). The browser adds those lines to "N to confirm" and "Confirm (N)", once per line:
  a line that also has a pending AutoCount change or a staged verdict counts once.
  - Saving 480 with 167 @ 20/11/2029 (rest unchanged) gives "1 to confirm" and Confirm (1).
  - A remark-only edit (236 "SITE HOLD") counts 0. Editing 167 back to 20/11/2026 counts 0.
  - A first split saved on a confirmed unsplit line (608: 600 @ 20/11/2026 own + 32 @ 20/12/2026 New
    line) counts 1 (Q1 a).
  - A line delivered in full never counts.
- A3 **Listed on the board.** While split edits wait, the board shows one line under its action bar
  "Split edits to confirm: line 480 CSK14B", AutoCount line numbers, comma-separated items for
  several lines; it lists exactly the lines the count includes (lead, build: the result card exists only after a Confirm, so the line sits under the
  bar; the mock's "(167 now 20/11/2029)" suffix is dropped because the board read carries no before
  values; the View splits popup shows "was").
- A4 **Confirm acts on every split-edited line of the order.** Pressing Confirm (N) confirms the
  order even when nothing else on it changed, and the server applies every split-edited line of that
  order (A1), whether or not the browser named it. The engine path is #1749's AC-G15: purchasing's
  rows move with their links, one email row and one Excel row per changed split, no CANCEL from
  splits, no second ORDER. The new decision's stamp equals the saved plan, so the next board load
  counts 0 for it.
  - E2: after the 167 edit, Confirm moves OI row 167 to 20/11/2029 (link kept); the email has
    exactly one row for 167 with NEW DATE 20/11/2029 and REMARK starting DELAY; the Excel reads 167 @
    20/11/2029; 14 and 236 rows are unchanged and are not in the email.
  - A qty edit 236 -> 200 + new 36 @ 20/01/2030 (total 417) writes rows 200 and 36, each linked for
    its own qty, both in the email and the Excel; the 236 is gone; no CANCEL row anywhere.
  - A second Confirm right after sends nothing and writes no rows (AC-G13).
- A5 **Simulate confirm** (admin) shows the same rows and email as A4 for the same board state.
- A6 **Save guard unchanged** (Q2 a). Moving a confirmed split onto another SO line still answers 422
  "Line <n>: a confirmed split cannot move to another line." and stores nothing (#1749 AC-G19).
- A9 **A line with a pending AutoCount change goes the AutoCount way** (reviewer round 1, lead). Such a
  line is never split-edited (A1 skips it): the board already counts it for its AutoCount change, and its
  Confirm (batch or not) behaves exactly as on main, email and worklist included (e.g. 608 plan 600 + 32
  applied, AutoCount 632 -> 700, the 32's date edited: the batch Confirm emails what main emails, 600
  REMAIN and 68 ORDER 68 included). A Confirm that names only OTHER lines never fails because of such a
  line (main answers 200, so must this). Known older gap, not this lane: on main that batch Confirm does
  not move the edited 32 row either (follow-up ticket).
- A11 **A held-back line stays held back** (reviewer round 2). When the server holds back a named line
  whose breakdown it refuses (e.g. 608 "components add up to 532 and the line is open for 632"), that
  line is not confirmed, not emailed and not in `lines_confirmed`, even if it is split-edited; it is in
  `lines_held_back` only, its OI rows stay as they were and its plan is not stamped (so it stays
  split-edited). This goes past main: on main a held-back line whose saved split plan still acts got a
  new ORDER row and an email line (3e2666c5e3: "632 ADVANCE, ORDER 600"); fixed here in
  `_kept_split_needs` (d8438ef1af). A Confirm of OTHER lines leaves a line's applied split plan alone:
  no row change and no email for it (main collapsed 608's applied 600 + 32 rows into one 632 row and
  emailed "632 ORDER 32"). Exception, unchanged from main and out of scope: an unnamed split-edited line
  whose confirmed Buy no longer adds up with no pending AutoCount change (qty_ordered drift outside an
  AutoCount batch) is held back from the decision, but its rows get main's carried-line treatment
  (cancelled, "CANCEL ALL"); follow-up ticket with the other older gaps. A split-edited line the press did not name is added BEFORE the
  hold-back runs, so the hold-back can drop it like any named line; a Confirm of the order's other lines
  never answers 422 because of it.
- A10 **The pre-confirm list cannot leave a split-edited line out.** Its row shows no untick box: the
  server applies every split-edited line of an order it confirms.
- A8 **Whole-Buy lines only** (known limit carried from #1749: the split plan logic covers lines the
  active decision buys whole). A line partly served from stock is never flagged split-edited.
- A7 **Never stuck.** If the Confirm fails, the board shows the server's message, the count stays,
  and nothing is half-applied (the order's Confirm is one transaction, as today).

## B. "Split N" + (i) popup on the SO and OI Lines tabs

- B1 **Its own Split column.** On the Sales Order page > Lines tab and on the Order Inquiry page >
  Lines tab, a column headed "Split" sits right after Product (owner, mock v2 note: "i don't want to
  jumble up the product column"). For a line with saved splits it shows "Split N" (N = its split
  rows; the AutoCount extra row is not counted) and an (i) icon button labelled "Show the splits of
  line <n>"; for a line without splits it is empty. The Product cell shows the product only (the OI
  page's "Split N" moves out of it). The Columns menu lists "Split" and turns it on or off like any
  other column, saved per user like the others. Nothing opens by default (Q3 b). The OI chevron keeps
  what it shows today.
- B2 **The popup** (a Dialog the size of the Email Outbox body view). Title "Line <n> <item>:
  split"; under it the SO number and, when the line has an OI row, "<OI number> line <n>". Then the
  plan status (B3), the line's purchasing State (and PO on the OI page), and one grid:
  Qty | Delivery date | Change | Sits on | Remark, one row per split in the saved order, then the
  AutoCount extra row when there is one, then a total row "<sum>" with "AutoCount <base qty> @
  <base date>, now <now qty> @ <now date>". Change is the email's REMARK word from
  `remark_for_row` (ADVANCE / REMAIN / DELAY / CANCEL BALANCE / ORDER n); Sits on reads "line <n>"
  (AutoCount number), "New line (not in AutoCount yet)" or "line <n> (AutoCount extra)".
  - 480: rows 14 / 20/09/2026 / ADVANCE / line 480; 236 / 20/11/2026 / DELAY / New line; 167 /
    20/11/2026 / DELAY / New line; total 417.
  - 752: rows 37 / 20/11/2026 / ADVANCE / line 752; 467 / 02/01/2027 / DELAY / New line; 145 /
    02/01/2027 / ORDER 145 / line 752 (AutoCount extra); total 649.
- B3 **Plan status**, one per line: "Confirmed" with "revision <r>, <dd/mm/yyyy>" when the saved
  plan equals the applied plan; "Saved, not confirmed" when the line is split-edited (A1, the same
  membership the board flag reads) and also when a whole-Buy line with a pending AutoCount change (A9)
  has a saved plan that differs from its applied plan (lead ruling, reviewer round 2: e.g. 608's 32 moved
  to 20/01/2027 while AutoCount 632 -> 700 waits; its rows are highlighted as in B4, and the board
  counts the line once, for its AutoCount change); a partly-from-stock line right after its Confirm
  reads "Confirmed", nothing highlighted. Precedence: "AutoCount changed" over "Saved, not confirmed"
  over "Confirmed";
  "AutoCount changed" when the plan is stale (`split_state` stale).
- B4 **What changed, only when exact.** In "Saved, not confirmed", a split row whose
  (qty, date, sits on, cancel) is not in the applied plan is highlighted. When the saved plan and
  the applied plan differ by exactly one row removed and one row added, the added row also shows
  "was <qty>" or "was <date>" (the removed row's values). Otherwise no "was" is shown. Never a
  guess.
- B5a **Grids are the shared DataGrid** (PRINCIPLES hard-fail: no hand-rolled table). The line popup is
  one DataGrid of the split rows with the total under it as a line of text ("Total 417 · AutoCount 417 @
  20/10/2026, now 14 @ 20/09/2026"); the whole-order popup is one section per split line (a heading
  "Line 480 CSK14B" with its status badge and the AutoCount text) holding that line's DataGrid.
- B5 **Same data, same component.** Both pages get the popup's data from one backend read (the same
  function feeds the OI rows and the SO lines) and render one shared component. Opening the popup
  makes no extra request beyond the page's own read.
- B6 **Q4 (a) (owner, 21:54).** A split sitting on another SO line is listed in its own line's
  popup with Sits on "line <n>"; the landing line shows only its own splits.
- B7a **Split column sorts by split count** (the chip's N, extra row not counted).
- B7 **Access.** The SO page shows splits to anyone who can open that sales order (scoped by its
  company, as the page's lines are); no new permission. An SO with no project order shows no chip.
- B8 **Layout.** Unclipped at 1280 and 375; at 375 the popup fills the width and keeps Qty, Date and
  Change in view, with Sits on as a small line under Change. Escape and Close return focus to the
  (i) button.

## D. Gear items (owner, Lavish 21:54)

- D1 **View splits, whole order.** A gear item "View splits" opens one popup (the same Dialog as B2)
  listing every split line of the order:
  - Planning board gear: one "View splits <SO number>" per order on the board, beside that order's
    other per-order items (like "Undo <SO number> confirm (rev n)").
  - Sales Order page gear ("Sales order options"): "View splits".
  - Order Inquiry page gear ("Order inquiry options"): "View splits", for the inquiry's lines.
  The popup's title is "<SO number>: splits" (on the OI page "<OI number>: splits", with the SO
  number under it), then "<n> split lines" ("1 split line" for one), then one grid: Qty | Delivery date | Change | Sits on |
  Remark, with a group row per split line (in line number order) reading "Line <n> <item>", its plan
  status badge (B3) and "AutoCount <base> @ <date>, now <now> @ <date>", followed by that line's
  rows exactly as in B2 (incl. the AutoCount extra row and B4's highlight and "was").
  SO417636: group "Line 480 CSK14B" with 14 / 236 / 167, then "Line 752 CSK14B" with 37 / 467 / 145.
  With no split line the popup shows the heading "No split lines" and the hint "Every line ships as
  AutoCount has it.". Escape and Close return focus to the gear button.
- D2 **Split delivery moves to the board gear.** The planning board gear gets "Split delivery <SO
  number>" per order (only for planners who may split today); it opens the same split sheet
  (`LineSplitDialog`) for that order. The Decide dropdown no longer lists "Split delivery..."
  (`BoardDecideControl.tsx:572-581`). The cell breakdown's Split delivery button
  (`BoardCellBreakdownDialog.tsx:1019`) and the AutoCount change table's (`BoardChangeTable.tsx:136`)
  stay.

## C. Out of scope

- AC-G19 (moving a confirmed split onto another line) stays deferred (Q2 a).
- Purchasing state per split row (needs a stored OI-row-to-split link, a migration; Q5).
- The "Confirmed: line 560 ..." text on the board card keeps its current numbers.
