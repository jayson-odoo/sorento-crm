# UAC - order inquiry sheet: a re-upload rebuilds the rows planning worked on; a rollback keeps them

Plan: `PLAN-oi-rollback-recover-planning-rows.md`. Owner rulings 19 Sep 2026 (R1 to R3) and
20 Sep 2026 (R4 to R6) in the plan, section 1. Backend only: no screen changes, so no `[FE]`,
`[UX]` or browser AC. Every AC is `[BE]` unless tagged.

## Journey

1. **Purchasing** keeps the order inquiry book (the Excel sheet). **Customer service** plans
   supply on the Fulfilment Planning board. Both describe the same sales order lines.
2. An operator uploads the book. Each sheet row raises one order inquiry row on its sales order
   line. No decision is asked of the operator beyond choosing the file.
3. Customer service confirms a plan on the board. Planning then works on the sheet's rows in two
   ways, with no one touching the sheet:
   - a line whose supply was already RECEIVED keeps the sheet's row as the greyed "used" row
     holding the received goods, and gets a fresh row beside it (`Replaces 182 used; ...`);
   - any other line has its row restated in place (Was = the sheet's figure, Now = the plan's).
4. Later an importer fix ships, and the operator rolls the upload back and uploads the same book
   again. **The operator makes no extra decision and runs no extra tool.** What they hold at the
   end: every row planning had worked on reads exactly as it did before the rollback (greyed used
   rows with their received documents, restated rows with Was/Now), and every other row is raised
   fresh by the fixed importer.
5. What everyone else is told automatically: the rollback's output names every row it kept and
   why; the upload report names every sheet row that stood beside a planning decision and could
   not be paired, so purchasing and customer service know which lines to look at.

Fixture shape, measured on prod copy `sorento_ai_automation_0918_1900` (SO314593):

| Line | Sheet row (purchasing) | Fresh row planning raised | Fresh row remembers | Received document |
| --- | --- | --- | --- | --- |
| CB2807-DIY | 182 @ 2026-06-01 | 220 @ 2027-03-01 | `previous` 182 @ 2026-06-01 | SPO-2026/08-0104 |
| CB2807-DIY (same line) | 182 @ 2026-09-01 | 280 @ 2027-04-01 | `previous` 182 @ 2026-09-01 | SPO-2026/04-0058 |
| SRTWCX8605-S-RL-PJ restated line | 182 @ 2026-06-01 | none (restated in place) | decision: buy 280, required 2027-03-01 | none |
| CSA150 all-from-stock line | 36 @ 2026-12-28 | none | decision: buy 0, reserve 36 | none |

## Used rows (plan 2.1(a), rulings R2, R6)

- **AC-RB-1** Given a line whose only live row is a `Replaces N used` row with `previous_qty` 182
  and `previous_delivery_date` 2026-06-01, and no used row, when the book is uploaded with a row
  182 @ 2026-06-01 for that line, then that sheet row is RAISED (not skipped as already raised)
  with `redirected_to_pool = true`, the sheet's quantity and date, and the file's stamp.
- **AC-RB-2** Two deliveries on ONE line with the SAME quantity (the CB2807-DIY shape): each
  sheet row becomes the used row of the fresh row that remembers its exact quantity AND date;
  neither is paired by quantity alone, and swapping the sheet rows' order in the file changes
  nothing.
- **AC-RB-3** (R6) A sheet row on such a line whose quantity or date equals no fresh row's
  `previous_qty` / `previous_delivery_date` raises NO used row and no other row, and the upload
  report names it with its own outcome code (item, quantity, date, sales order).
- **AC-RB-4** A line that already carries the used row (same quantity and date,
  `redirected_to_pool = true`) is left alone: a second upload of the same book raises nothing on
  it and changes no field of either row.
- **AC-RB-5** The used row raised in AC-RB-1 takes no part in demand: it is excluded wherever a
  used row written by a replan is excluded today (asserted through the same worklist read the
  existing used-row tests use, not a new one).

## Received goods sit on the used row only (plan 2.2, rulings R1, R2, R5)

- **AC-RB-6** Given the fresh `Replaces N used` row holds a link to a RECEIVED allocation (what
  `follow_book` wrote on prod after the used row was deleted), when AC-RB-1 raises the used row,
  then that link and its claim sit on the USED row afterwards and the fresh row holds no link to
  a received allocation. The move goes through the one link writer; no link row is written by
  hand.
- **AC-RB-7** The move is bounded by the used row's quantity: a received link larger than the
  used row's quantity moves only that quantity, and the rest stays where it was.
- **AC-RB-8** A link on the fresh row to an allocation that is NOT received (an open PO raised
  for the 220) never moves.
- **AC-RB-9** (R5, test first) With the used row present, running `follow_book` over the line
  leaves the received link on the used row and offers it to no `Replaces N used` row. This test
  is written before any `follow_book` change; a guard is built only if it fails.
- **AC-RB-10** (R1) No link in any AC above comes from the sheet's own PO column: every link on
  a rebuilt row is one AutoCount's book names for the line.

## Restated rows (plan 2.1(b), ruling R4)

- **AC-RB-11** Given a line with NO live order inquiry row, covered by an ACTIVE supply decision
  whose snapshot for the line is buy 280, required 2027-03-01, when the book is uploaded with
  182 @ 2026-06-01 for that line, then ONE row is raised already settled: quantity 280, delivery
  date 2027-03-01, `previous_qty` 182, `previous_delivery_date` 2026-06-01, `changed_at` and
  `supply_decision_id` from the decision, the file's stamp kept, and the same Was fragment in the
  note that `_settle_row_in_place` writes.
- **AC-RB-12** Decision equals the sheet (same quantity and date): the row is raised plain, no
  Was, no `changed_at`.
- **AC-RB-13** (R4) Decision buy quantity 0 for the line (all from stock, the CSA150 shape): the
  sheet row is raised PLAIN, exactly as the importer raises it today. No Was/Now, not greyed.
- **AC-RB-14** A SUPERSEDED decision is never read: only the active one for the sales order
  counts. A sales order with no decision at all behaves exactly as today.
- **AC-RB-15** (must not change, prod TPE-9204 and SRTWC8605-SC-RL) A line that already carries
  a live row is never restated by the importer, whatever the active decision says: the sheet row
  follows today's rules (already raised, or AC-RB-1 to 3 when the live row is `Replaces N used`).
- **AC-RB-16** A second upload of the same book changes no field of a row raised by AC-RB-11
  (its Now is not pulled back to the sheet's figure).

## Rollback guard (plan 2.3)

- **AC-RB-17** `rollback_oi_sheet_upload` keeps a stamped row that planning has worked on, each
  trait on its own: `redirected_to_pool = true`; `changed_at` set; `supply_decision_id` set.
  The row, its links and its claims are all still there after `--apply`.
- **AC-RB-18** A stamped row with none of the three traits is deleted exactly as today, links
  and claims included.
- **AC-RB-19** The dry run and the `--apply` output both state how many rows were kept and name
  each one (sales order, item, quantity, date, which trait kept it). The deleted count excludes
  them.
- **AC-RB-20** Rollback then re-upload, with kept rows on the lines: the kept rows are not
  duplicated and not altered (AC-RB-4 and AC-RB-16 hold across a rollback).

## The whole journey

- **AC-RB-21** `[T]` One test walks step 2 to step 4 of the journey on the fixture above: upload,
  confirm a plan that produces one used + fresh pair and one restated row, DELETE those rows the
  way the old rollback did (the prod state today), run the new rollback, upload again. The used
  row, the restated row, the fresh row and every link read exactly as they did before the
  deletion, and the all-from-stock row is plain.
- **AC-RB-22** `[E2E]` Rehearsal before the PR is marked ready: on a copy restored from a CURRENT
  prod backup, rollback + upload of the 2026 book; the 22 rows on SO314592 to SO314595 match
  `~/Desktop/oi-compare/recovery_0918_rows.json` on quantity, date, Was/Now, greyed, and which
  document sits on which row. Landings are counted by KIND (used, restated, plain, reported),
  never as one "landed" total. Evidence recorded in the PR description.
- **AC-RB-23** `[T]` Every existing test in `test_oi_sheet_line_pick_month_po.py`,
  `test_oi_sheet_pairing_repair.py`, `test_oi_sheet_date_follow_sheet.py` and the inquiry test
  family stays green unchanged.
