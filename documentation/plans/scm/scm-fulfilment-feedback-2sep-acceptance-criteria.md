# UAC: Fulfilment planning feedback batch, 2 Sep

Plan: `PLAN-scm-fulfilment-feedback-2sep.md`. Dates are relative to `as_of`; the six walks
below are the golden cases S2 adds. Pool = the asking bin's site pool (BRW for BRW-BB).

## Journey

A CS planner (Leena, Eric) uploads today's outstanding SO book, opens Fulfilment Planning
from the sidebar, filters to the order they are working (SO419370), and opens a product
cell. The lightbox already shows the quantity needed, the suggestion as pills ("BRW 3"),
the Stock tab with BRW's free stock and what BRW can spare, and the contributing lines with
their own pills. The one decision per line is accept, or amend (add a location such as
BRW, change a quantity, buy). Save decision answers on the row and survives leaving the
page; a colleague opening the same order sees it. When the batch is ready they press
Confirm once. Purchasing sees the buys on the reorder plan; the upload card counts rows
while the file runs and finishes in minutes. Nobody is asked for a percentage, a window,
or a rule: those live once on the Policies page.

## S1 policy fields

- AC-1.1 Policies page shows "Immediate window (days)" 30 and "Pool share (%)" 50 on a
  database that never set them; saving 45 / 40 round-trips through GET and reaches the engine
  on the next board build without a restart.
- AC-1.2 Out-of-range values (366 days, 101 %) are refused with a field message; 0 is valid
  for both (0 % = pool never gives a share, 0 days = nothing is immediate).

## S2 engine v8

- AC-2.1 **Immediate share, pile base.** Line 650 due in 10 days, pool free 900, five-pool
  net 900, own group 0: allowance 450, proposal = pool 450 + buy 200. Options: Use BRW stock
  450 (not whole), Use our locations 0, Buy 200. Sourced-from pills "BRW 450" "Buy 200".
- AC-2.2 **Small line takes whole from the pool.** SRTWB241 on SO419370, qty 3 due in 2
  days, BRW free 47 (allowance 23), MWH-BB 84: proposal = pool 3 whole. Never pool 1 + own 2.
- AC-2.3 **Beyond window, fits the allowance.** Line 100 due in 60 days, pool free 900:
  100 <= 450, proposal = pool 100 whole.
- AC-2.4 **Beyond window, exceeds the allowance.** Line 600 due in 60 days, pool free 900:
  600 > 450, pool gives nothing; own group 700 covers, proposal = own 600. Options row "Use
  BRW stock" reads 0 with the reason "600 is more than the 450 BRW can spare".
- AC-2.5 **Five-pool net bounds the share.** Line 30 due in 5 days, BRW own free 3,034
  (allowance 1,517), five-pool net 1: share = 1; proposal = pool 1 + remainder 29 walks
  (TPE-9204 on SO381895 line 74 shape). Never 1,517.
- AC-2.6 **Per-line walk, smallest first.** SO419208 CSK14A-NL, 14 Sep, lines 1305 and 135,
  on hand at BRW-BB 145 with the 4 Sep line 10 already taking 10: line 135 walks first and
  reads Own 135 at BRW-BB; line 1305 reads BRW allowance + Buy (pool per its own picture); the
  unit cell reads 1440 with both compositions summed. Stock tab running Available reads
  135, 0, then negative, in that order.
- AC-2.6b **Allowance visible (R-K).** SRTWCX8840-S-RL lightbox: BRW row reads On hand 102,
  Available 590 (as today), Can spare = min(590 x 50 %, five-pool net) as a new column after
  Available; the Suggestion card reads pills "BRW 1" and the sub-line "BRW can spare 295 of
  590 · due in 2 days". A pool row with 0 to spare reads 0, never blank.
- AC-2.7 Dealer hot-selling product with pool free 6,500 (WESERP10B): reads pool, not Buy.
- AC-2.8 Every option row still carries fulfil date and days late (R36); `ladder` on the
  board and the drawer is "v8".
- AC-2.9 SO407733, SO407735, SO414617 produce the same proposals as v7.1 (pool free 0).
- AC-2.10 `test_ladder_v7_borrow.py` step-order test rewritten for the v8 order; goldens
  re-blessed with the diff listed in the PR body (count of rows changed per step).

## S3 reserve add-location

- AC-3.1 Decision panel Reserve section has "Add location"; the dialog lists locations with
  free stock for the product, the site pool included, each with its free quantity; none with
  0 free.
- AC-3.2 Picking BRW seeds an editable row; Save then Confirm writes a reserve component at
  BRW; the Stock tab shows it under Taken at BRW.
- AC-3.3 Server refuses a reserve above on hand at that location (existing guard), the
  panel shows the field message and keeps the row.

## S3b sourced-from pills

- AC-3b.1 A composition of three parts in a 160 px column shows one pill and "+2"; the same
  cell at 420 px shows all three; dragging the column border reflows without a reload.
- AC-3b.2 Clicking "+2" or any pill opens a popover listing every part with kind, quantity,
  location and the option row it came from; Escape closes it; the row is not expanded by
  the click.
- AC-3b.3 The Contributing lines Sourced-from column and the Stock tab Taken cell use the
  same primitive (one component in `components/common`, vitest covers fit / overflow).
- AC-3b.4 Usable at 375 px: the cell shows one pill and "+N", the popover fits the viewport.

## S4 saved decisions

- AC-4.1 Save decision on a line: pill Suggested to Saved within the interaction, button
  shows a check for about 600 ms, toast "Line N saved · K to confirm".
- AC-4.2 Reload the page, or open the same board on another device: the line is still
  Saved with its composition and the saver's name.
- AC-4.3 Undo on a saved line deletes the draft; the pill returns to Suggested.
- AC-4.4 Confirm promotes every saved line to active in one write; the confirm summary
  counts saved lines; a line saved but then re-suggested by a new upload shows the
  "suggestion changed" state and is not silently confirmed.
- AC-4.5 A second planner sees the first planner's saved lines; saving over one replaces
  it and names the newer saver.

## S5 upload

- AC-5.1 The 22,111-row outstanding file completes in under 5 minutes on the dev machine
  (was 18 min and counting); the 82,257-row completed book is refused before enqueue with
  the message naming the history channel.
- AC-5.2 The activity card counts up during the run (at least every 1,000 rows), matching
  the outcomes page count.
- AC-5.3 Killing the worker mid-run leaves documents committed up to the last batch and
  the job marked failed with the row it reached; re-upload resumes without duplicates.
- AC-5.4 `pytest tests/scm/test_outstanding_import*.py` green; a new test asserts the
  query count for a 200-row apply stays under 60 (no per-row SELECT) and that no statement
  carries more than 1,000 bound parameters (the prod trace shipped 13,519 per row).

## S6 SPO duplicates

- AC-6.1 Prod count of open rows sharing `(spo_number, product, location, qty,
  expected_date)` across two source systems is recorded in the plan before build.
- AC-6.2 Re-uploading the same SPO through a second feed updates the existing open row
  instead of adding one; `on_order_v` for the product does not change.
- AC-6.3 "Suspected duplicates" lists the groups, bulk delete counts down before it runs,
  the incoming figure on the board drops by the deleted quantity.
