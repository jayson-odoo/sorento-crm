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
  Available 590 (as today), Available for Project = min(590 x 50 %, five-pool net) as a new
  column after Available, on every site pool row and on the site pool subtotal; the
  Suggestion card reads pills "BRW 1" and nothing else. A pool row with 0 to give reads 0,
  never blank. Expanding BRW (site pool section) shows the ledger with the running column
  headed Available for Project = floor(Balance after x 50 %) capped by the five-pool net:
  On hand 102 reads 51, after the first 1-unit dealer SO 50, after the 510 SPO 295 (the
  last row equals the summary row's Available for Project). Expanding a GROUP section still
  reads Balance after, unchanged.
- AC-2.6c **Expanded ledger Total is the signed net (D9).** On a group or site pool reading,
  the ledger's Quantity totals the signed net of the rows listed (on hand and SPO plus, S/O
  and holds minus) and equals the section's own Available; on a single-bin reading it totals
  the S/O rows as before. SRTWB241 site pool ledger: 49 + 586 + 20 + 113 + 4 - 1 = 771.
- AC-2.7 Dealer hot-selling product with pool free 6,500 (WESERP10B): reads pool, not Buy.
- AC-2.8 Every option row still carries fulfil date and days late (R36); `ladder` on the
  board and the drawer is "v8".
- AC-2.9 SO407733, SO407735, SO414617 produce the same proposals as v7.1 (pool free 0).
- AC-2.10 `test_ladder_v7_borrow.py` step-order test rewritten for the v8 order; goldens
  re-blessed with the diff listed in the PR body (count of rows changed per step).
- AC-2.12 **Another group's free pile is capped by that group's own book (R-M) [BE][T].**
  Two goldens in `tests/scm/front_planning_golden.py`, from the production cell (SO419417,
  SRTWT7443, 3 Sep 2026):
  - AC-2.12a **the lending group is short.** BB line 4 due 5 Oct at BRW-BB, own group offer
    0, pool share 0 (BRW has nothing to spare), the IB group holding 2,237 against 2,684 of
    open demand so its book is -447 (or -191 counting the assignment's own incoming), and a
    later IB order lendable: the proposal is BORROW 4 from that later order (or Buy where
    step 2's own rules refuse it), NEVER "Reserve 4 @ BRW-IB". The `use` options row reads
    0 with "IB group is 447 short on its own book, nothing to spare".
  - AC-2.12b **the lending group's book is whole.** The same cell with IB owing only 1,708
    against 2,237: the take stands, and the component's sentence states the PILE and the
    date it was measured on - "BRW-IB has 529 free outside the BB group at 5 Oct 2026, none
    of it owed to a later IB order" - beside a Reserve of 4. The `use` row reads 4, whole,
    chosen, labelled "Use IB group stock".
  - Board side [BE]: `use_candidates_for` on an oversold other group returns NO row for
    that group's bins at all - a bin with nothing to offer is omitted, the same way every
    other exhausted candidate is - and names the group in the shorts map, which is what the
    `use` option row prints; where the book is whole it returns the measured pile (529).
  - AC-2.12c **one book, spent once across the whole walk (review fix, 3 Sep).** The cap is
    a statement about the GROUP, so a board spends it once: the lending group's spare book
    is seeded into the walk's own offer ledger and drawn down by what each unit composed, so
    two units whose dates bring DIFFERENT bins of that group into view (one seeing the
    floor, the next an arrival) share one budget instead of each being handed the whole of
    it. Confirm carries the same bound through `_CapacityLedger` under the group's own key,
    so a second line of one confirmation reserving at another bin of a group already lent to
    its budget is refused with "<bin> now has 0 free for this line, and N was asked for".
  - Pill [FE]: the Suggestion card and the summary cards read an other-group source as
    "Use IB group stock" (water: "Use incoming from IB group"), and an own-group source as
    "Use own location", unchanged.

## S3 reserve add-location

- AC-3.1 Decision panel Reserve section has "Add location"; the dialog lists locations with
  free stock for the product, the site pool included, each with its free quantity; none with
  0 free.
- AC-3.2 Picking BRW seeds an editable row; Save then Confirm writes a reserve component at
  BRW; the Stock tab shows it under Taken at BRW.
- AC-3.3 Server refuses a reserve above on hand at that location (existing guard), the
  panel shows the field message and keeps the row.
- AC-3.4 (D7, captain 3 Sep) Editing a reserve quantity moves the Buy remainder; Buy is
  derived, never typed, unless the line is bought whole.

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

- AC-4.1 Save decision on a line: pill Suggested to Saved within the interaction, the button
  shows a check and STAYS "Saved" (disabled) until the line is edited again, toast "Line N
  saved · K to confirm". A line opened on somebody's existing saved draft reads Saved too.
  (Amended 3 Sep, D4: it used to revert after about 600 ms, which read as the save undoing
  itself - "shows saved then jumps back".)
- AC-4.2 Reload the page, or open the same board on another device: the line is still
  Saved with its composition; the pill reads "Saved" only, the saver's name is in the popover.
- AC-4.3 Undo on a saved line deletes the draft; the pill returns to Suggested.
- AC-4.4 Confirm promotes every saved line to active in one write; the confirm summary
  counts saved lines; a line saved but then re-suggested by a new upload shows the
  "suggestion changed" state and is not silently confirmed.
- AC-4.5 A second planner sees the first planner's saved lines; saving over one replaces
  it (popover names the newer saver).
- AC-4.6 (D10, captain 3 Sep) The sales order page's Lines tab shows a saved (unconfirmed)
  decision as Decided `<composition>` with a Saved pill and Decision "Saved" naming the
  saver, until Confirm replaces it with Rev N. An approval with no typed composition prints
  Decided "-" beside the Saved pill - there is nothing to state beyond the pill itself.
- AC-4.7 (D14, captain 3 Sep) Quick save as suggested and per-line Undo: (a) in the list
  view, ticking N selectable rows (not already confirmed, not already saved) and pressing
  "Save as suggested (N)" saves each ticked row with the engine's own composition - the same
  object an untouched Save on that row would post - and every one of those rows now reads
  Saved with the saver's own stamp; (b) in a cell's breakdown dialog, the SAME composition is
  what "Approve selected" writes (D11: an approval carries the suggestion, so approving in
  bulk and saving as suggested were one verb, and the dialog has one button for it), a row
  already saved is not selectable there either ("Already saved. Undo it before saving it
  again."), and a header-level "Save all suggested" saves every still-selectable line in the
  cell with no selection needed, skipping a confirmed line and a line already saved; (c) Undo
  on one saved row (list or dialog) returns that row alone to Suggested and deletes its
  server draft, with no confirmation dialog - it is reversible with another quick save - and
  every other row's own state is untouched.
- AC-4.8 (D15, captain 3 Sep) One-click save without opening a row, on every surface, and a
  board-wide button: (a) the list's Verdict column carries a save icon beside the pill on
  every row a quick save could touch (not covered, not unplannable, not already drafted) -
  pressing it saves that ONE line with the engine's own composition and toasts "Line N saved
  · K to confirm", the same as today's Save-inside-the-row; the icon and the per-line Undo
  never both show, since a drafted row is never quick-save-eligible; (b) a grid cell carries
  its own small icon in its own corner, a save (posts every eligible line in the cell in one
  press) when the cell holds at least one eligible line, or an Undo (posts every drafted line
  in the cell) when it holds only drafted ones and nothing left to save - neither icon opens
  the cell underneath it; (c) the board's action bar carries a "Save all suggested (N)"
  button, left of the gear, where N is every quick-save-eligible line the board is CURRENTLY
  SHOWING (product search and the decision-strip filter narrow it, a day-window scroll does
  not hide a line from the count on the other views) - pressing it saves all N with one toast
  ("N lines saved · M to confirm"), disabled at zero, no confirmation dialog since Undo all
  reverses it; (d) every bulk quick save on this screen - the list's own "Save as suggested
  (N)", the dialog's "Approve selected" and "Save all suggested", the cell icon and the
  board-wide button - posts through the same quiet-bulk path and toasts EXACTLY ONCE for the
  whole press, closing the D14 rough edge where a bulk quick save toasted once per line.
- AC-4.9 (D16, captain 3 Sep) Saving or undoing a draft decision never refetches the board and
  never shows a skeleton: the pill flips Suggested/Saved in place off a cache patch, every other
  card on screen keeps its own object identity (no re-render, no flicker), and the rows never
  drop out from under the reader. Confirm still refetches the board (its write changes what the
  engine can offer every OTHER order) - its rows dim in place while the fresh read lands, never
  blank to a skeleton, since the previous board is kept on screen for the round trip.

## S5 upload

- AC-5.1 The 22,111-row outstanding file completes in under 5 minutes on the dev machine
  (was 18 min and counting); the 82,257-row completed book (every row delivered) completes
  in under 10 minutes on the SO channel and settles its lines; the PO channel accepts a
  completed book the same way.
- AC-5.2 The activity card counts up during the run (at least every 1,000 rows), matching
  the outcomes page count.
- AC-5.3 Killing the worker mid-run leaves documents committed up to the last batch and
  the job marked failed with the row it reached; re-upload resumes without duplicates.
- AC-5.4 `pytest tests/scm/test_outstanding_import*.py` green; a new test asserts the
  query count for a 200-row apply stays under 100 (no per-row SELECT) and that no SELECT
  carries more than 1,000 bound parameters (the prod trace shipped 13,519 per row). 100, not
  a literal 60: company-scope resolution costs a handful more statements depending on which
  fixture warmed it up earlier in the same pytest session against the shared local
  database - `test_query_count_does_not_scale_with_row_count` (40 rows vs 200 rows, same
  shape) is the precise regression guard the absolute ceiling only backs up (review round
  1, S4). The 1,000-parameter ceiling is scoped to SELECTs: SQLAlchemy's `insertmanyvalues`
  legitimately coalesces a batch's own new-line INSERTs into one multi-row statement with
  one parameter per column per row, bounded by `_DOCUMENT_BATCH` rather than by the file's
  row count, and that is not the shape the prod trace measured (a SELECT's `NOT IN` exclude
  list growing with every row already processed).

## S6

Dropped 2 Sep (R-I). No criteria.
