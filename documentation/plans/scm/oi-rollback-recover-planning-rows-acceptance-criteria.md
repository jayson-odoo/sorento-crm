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
- **AC-RB-2** Two deliveries with the SAME quantity (the CB2807-DIY shape; on prod each delivery
  is its own sales order line of the same item, the test also holds them on ONE line): each
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
  note that `_settle_row_in_place` writes. Its `ack_state` is `changed`, which is what a confirm
  leaves on an acknowledged row it restates (the importer raises rows acknowledged). The row then
  takes AutoCount's links for the line exactly as any freshly raised row does (R1).
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

## Shapes found on the full 18 Sep copy (ruling R7, R8, 20 Sep 2026; slice S5)

Measured: of 12,285 live sheet rows, 13 share their line with a row planning made. 10 are the
used rows above. The other 3:

| Line | Sheet row | Planning's row on the same line | Decision |
| --- | --- | --- | --- |
| TPE-9204 (a) | restated 280 @ 2027-04-01, was 182 @ 2026-09-01 | DELAY notice 280 @ 2027-04-01, `Was 2026-09-01` | buy 280 |
| TPE-9204 (b) | plain 176 @ 2026-12-01 | DELAY notice 219 @ 2027-05-04, `Was 2026-12-01` | buy 219 |
| SRTWC8605-SC-RL | plain 182 @ 2026-03-01 | top-up ORDER 38 @ 2027-01-04, `supply_decision_id` set | buy 220 (182 + 38) |

- **AC-RB-24** (R7) A notice row never stands for the line's own row: "this line already carries
  an order inquiry" counts only a live row whose verb is ORDER or ORDER BACK (the same two verbs
  `_settle_row_in_place` settles). A line whose only live row is a DELAY notice is raised on,
  and AC-RB-11 applies to it (the TPE-9204 (a) shape comes back 280, was 182).
- **AC-RB-25** (R7) The notice row itself is never altered, re-raised or cancelled by the upload.
- **AC-RB-26** (R8) Top-up shape: the line's live ORDER rows all carry a `supply_decision_id` of
  the ACTIVE decision, and the sheet row's quantity PLUS those rows' quantities EQUALS the
  decision's `buy_qty` for the line: the sheet row is raised PLAIN (182 beside the 38), never
  restated, and takes AutoCount's links as any raised row does.
- **AC-RB-27** (R8) Same line, the sum does NOT equal the decision's `buy_qty`: nothing is raised
  and the upload report names the sheet row (its own outcome code), as AC-RB-3 does.
- **AC-RB-28** A line whose live ORDER row carries no `supply_decision_id` of the active decision
  (a row raised on the board before the migration, the original D2 case) is still left alone:
  `already_raised`, exactly as today.
- **AC-RB-29** Rollback also keeps a stamped row whose LINE carries a live row planning made
  (a row with `supply_decision_id`, a `Replaces N used` row, or a notice row), trait named
  `planning_row_on_line` in the kept listing, so a later rollback never makes these shapes.
- **AC-RB-30** A second upload after AC-RB-24 and AC-RB-26 changes nothing on those lines.

Known difference from the 18 Sep state, accepted unless the owner rules otherwise: TPE-9204 (b)
read PLAIN 176 @ 2026-12-01 beside its DELAY notice (the confirm told purchasing of the delay but
never restated the row). Under AC-RB-24 + AC-RB-11 it comes back 219 @ 2027-05-04, was 176 @
2026-12-01, which is what the active decision says. The rehearsal (AC-RB-22) lists it by name.

## Review round (reviewer + security-reviewer, 20 Sep 2026; slice S6)

- **AC-RB-31** (blocker B1) The links on a rebuilt used row never total more than the row's own
  quantity: the received-link move is capped at the row's quantity MINUS what the upload's own
  book pairing already linked onto it. Fixture: received allocation 400, fresh row holds 182 of
  it, used row 182: after the upload `sum(link.qty)` on the used row is 182, not 364.
- **AC-RB-32** Two or more sheet rows landing on ONE line in one upload, the line covered by an
  active decision: none is settled (AC-RB-11 does not fire), all are raised plain as today, the
  same refusal `_settle_row_in_place` makes for two live rows. Two or more sheet rows on a top-up
  line: AC-RB-26 does not fire, they read `already_raised`.
- **AC-RB-33** A second upload reports `already_raised`, and no other code, for the row rebuilt
  by AC-RB-11, by AC-RB-24 and by AC-RB-26. The mismatch codes never fire on a line whose live
  stamped row already equals this sheet row on (quantity, date) or on (previous quantity,
  previous date). Only a row this sheet raised (its note carries the stamp) counts for that
  test: a board-made top-up row of the same quantity and date never swallows a genuine top-up
  (plan buy 76, top-up 38, sheet 38 on the same date: the sheet row is raised plain, AC-RB-26).
- **AC-RB-34** A decision snapshot with no `required_date` proposes no date change: quantity
  equal to the sheet raises PLAIN; quantity different settles the quantity and keeps the sheet's
  date.
- **AC-RB-35** (R7 refined) The line's own row means a live ORDER, ORDER BACK or RESERVE AND
  ORDER row, the buy verbs used everywhere else; a line whose only live row is RESERVE AND ORDER
  reads `already_raised`, and the top-up sum counts it.
- **AC-RB-36** A used row (`redirected_to_pool`) is never counted in the top-up sum.
- **AC-RB-37** A malformed snapshot entry (unreadable `buy_qty` or `required_date`, or a
  `buy_qty` that is not a finite number, `NaN` / `Infinity`) never aborts
  the upload: that sheet row is raised plain and every other row is processed.
- **AC-RB-38** `changed_at` on a row rebuilt by AC-RB-11 is the decision's `confirmed_at`.
- **AC-RB-39** The rollback's more-than-one-company refusal is evaluated over EVERY stamped row,
  kept ones included, before any kept row is listed; without `--all-companies` no kept row of a
  second company is printed or returned (the per-company row count line the script has always
  printed before refusing stays).
- **AC-RB-40** The rollback reads the stamped rows and their line siblings ONCE, under a row
  lock (`FOR UPDATE` on the order inquiry rows), and derives kept and removable from that one
  read, so planning cannot put a trait on a row between the read and the DELETE. Links, claims and
  rows always address the SAME set: a row the rollback spares keeps every link and its claim
  (re-review N1: a trait set between the read and the deletes, simulated in the test, leaves the
  row AND its links). The DELETE still repeats the row's own three traits as predicates. A
  planning row that lands on the LINE after the read is outside this guard, and the script says so.
- **AC-RB-41** The upload preview's "already carries an order inquiry" warning counts
  `no_used_delivery_match` and `top_up_sum_mismatch` rows on their own line of text.

## The whole journey

- **AC-RB-21** `[T]` One test walks step 2 to step 4 of the journey on the fixture above: upload,
  confirm a plan that produces one used + fresh pair and one restated row, DELETE those rows the
  way the old rollback did (the prod state today), run the new rollback, upload again. The used
  row, the restated row, the fresh row and every link read exactly as they did before the
  deletion, and the all-from-stock row is plain.
- **AC-RB-22** `[E2E]` Rehearsal before the PR is marked ready, on the 18 Sep 19:00 prod copy
  `sorento_ai_automation_0918_1900` (owner, 20 Sep: no fresh backup needed), inside ONE
  transaction that is rolled back, so the copy is never written: delete every stamped row the old
  way, run `follow_book` over SO314592 to SO314595 (prod's state today), run the new rollback,
  upload the 2026 book. The 22 rows match `~/Desktop/oi-compare/recovery_0918_rows.json` on
  quantity, date, Was/Now, greyed, and which document sits on which row; the 3 rows of AC-RB-24
  to 27 land as stated. Landings are counted by KIND (used, restated, plain, reported), never as
  one "landed" total. Evidence recorded in the PR description. What the copy cannot show (prod
  drift since 18 Sep 19:00) is covered on prod by the rollback dry run and `compare.py`.
- **AC-RB-23** `[T]` Every existing test in `test_oi_sheet_line_pick_month_po.py`,
  `test_oi_sheet_pairing_repair.py`, `test_oi_sheet_date_follow_sheet.py` and the inquiry test
  family stays green unchanged.
