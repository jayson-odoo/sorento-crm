# PLAN - order inquiry sheet: line pick by exact date, then same month, then the sheet's PO

Status: IN PROGRESS (owner go 19 Sep 2026). Lane `fix/oi-sheet-line-pick-month-po`, worktree `sorento_crm-oi-line-pick`.
UAC: `oi-sheet-line-pick-month-po-acceptance-criteria.md`

## 0. What was measured

Owner cross-check, prod, 19 Sep 2026, SO324265 / BT012-CR. The 2026 book states six deliveries;
the live database holds five order inquiry rows for the item, one of them on the 2025-12-01 line
the 2026 book never names. Two 2026 lines carry no row.

Cause, read off `origin/main` (`project_order_inquiry_import_service.py`), not reproduced locally
(no current prod copy on the Mini; `sorento_ai_automation` is 8 Aug and has no `projects` schema):

1. AutoCount's line dates moved after the book was written. Sheet 02-02 / 03-02 / 04-01 against
   book lines 04-02 / 05-01 / 05-02. Only three of six sheet dates equal a line's
   `required_date`.
2. `_match_row` filters on item, location and quantity; the date is a rank term (`_rank_for`). A
   row with no exact-date line ties on "the book bought for it" (`_bought_refs` holds
   `(ref, product)`, no PO number, and all seven lines are bought) and falls to the EARLIEST
   date: the 2025-12-01 line, bought by 202508-S0012, a PO the sheet never cites.
3. `_match_row` charges the file ledger only when the landed line is not already raised (review
   finding 9, 14 Sep). On a re-upload the 2025 line is raised, so every undated-match row lands
   on it again, is counted `rows_already_raised`, and the lines behind it are never reached.
4. `_plan` matches in ONE pass in file order, so an early row with no exact-date line can take a
   line that a later row names exactly.
5. `_restates` docstring says `_plan` lends a duplicate's citation to the row it restates. It
   does not on main: the duplicate is marked and dropped. In the monthly book the MAY and JUNE
   tabs leave the PO blank and the MAY JUNE roll-up carries it, so the first statement has no PO.

The same date pattern (12-01, 01-02, 04-02, 05-02, 05-04, 06-01) repeats on every item of
SO324265 in the owner's AutoCount dump. Book-wide size is NOT measured; measure on the next prod
copy before sizing the prod repair (section 4).

## 1. Owner rulings (19 Sep 2026)

- **R1** AutoCount's dates are correct and are what live carries. The sheet row must find its line
  anyway.
- **R2** The sheet's PO may pick the LINE: "the sheet has 4 linked to 00049 and our system also
  has 4 linked to 00049, so they should be matching". This narrows the 15 Sep ruling ("ignore
  the sheet remark at all"): the sheet's PO still PAIRS nothing, the link stays the book's own.
- **R3** Same month before PO order: 04-01 lands on 04-02; 02-02 and 03-02 then take 05-01 and
  05-02.
- **R4** (19 Sep, prod C-FH14): the sheet's PO outranks the month when they disagree; pass order
  is exact, month and PO, PO, month, fallback.
- **R5** (19 Sep, prod CB1178A-SS-NEW): a restatement is only ever across tabs; two identical
  rows inside one tab are two separate instructions, and a later tab restates them by position.
  The single-sheet variant (`Order Inquiry Form.xlsx`) has no second tab at all, so restatement
  dedup never applies there - every row of that file is its own instruction, pinned by
  `test_single_sheet_variant_never_dedupes_a_repeat`.
- **R6** (19 Sep, prod CB2805A-DIY): inside every pass an equal-quantity line is tried before a
  bigger one.

## 2. Design

One seam: the match loop in `_plan` plus `_rank_for`. No new table, no setting, no new module.

**Passes instead of one loop.** `_plan` keeps building `plan.matches` in file order and keeps the
`stated` duplicate check exactly as is. The rows that reach `_match_row` today are then matched
in FIVE passes over the same `taken` ledger; a row matched in a pass is out of the later ones
(R4, prod C-FH14, 19 Sep 2026, added the month/PO split - the original four-pass design let the
month alone decide ahead of a row's own citation, which stole a month-mate's line from the row
that actually cited it):

1. **Exact date**: candidates narrowed to lines whose `required_date` is the row's date.
2. **Same month AND the sheet's PO**: candidates narrowed to lines in the row's year and month
   WHOSE book PO is also a PO the row cites. Tie-break inside: live before cancelled, then
   nearest date, then today's terms.
3. **Sheet PO alone**: candidates narrowed to lines whose book PO is a PO the row cites, whatever
   their month. Rows are taken in delivery-date order so the earliest row gets the earliest free
   line.
4. **Same month alone**: candidates narrowed to lines in the row's year and month, no citation
   filter - catches a row that cites nothing, or whose citation named no free line anywhere
   (passes 2 and 3 already tried every candidate that could possibly satisfy the citation, so a
   candidate reaching this pass can never still tie on it; the citation tie-break term this pass
   shares with pass 2 is therefore dead here and was dropped, review round 2, 19 Sep 2026).
5. **Fallback**: today's `_rank_for`, unchanged, for whatever is left.

Inside every pass the existing filters (item, location, quantity against the ledger) and the
existing rank terms (live before cancelled, open, earliest, oldest, id) still apply, so D1 and
determinism are kept. A failure reason is reported only after pass 5, and it is still the first
filter that refused the row.

**Book PO per line.** `_bought_rows` already loads the `PurchaseOrderLine` and `SPOAllocation`
rows that name each line. Add one map beside `_bought_refs`: `(ref, product) -> {document
numbers}` (PO number through `purchase_order_id`, SPO number off the allocation). One extra
query at most (PO numbers by id). Nothing new is read per row.

**Ledger.** Charge `taken` for every landed row, already raised or not. This reverses review
finding 9 (14 Sep) on purpose: the first upload charges the line, so the re-upload must too or
the two runs land differently (cause 3). Finding 9's worry, a later row reading
`qty_exceeds_ordered` for quantity nobody used, now only happens when the sheet states more
deliveries than the order has lines, which is a true report. One more consequence, found in
review (S1): a row bumped off a full already-raised line that still fits ANOTHER free line of
the order is RAISED there by the fallback pass, where the old re-upload skipped it silently.
That is exactly where a first upload of the same sheet puts it, so it is kept and tested
(`test_ac_lp_12_bumped_row_takes_the_next_free_line`). Name both in the PR for the reviewer.

**Lending.** In the `stated` branch of `_plan`: when the duplicate carries `po_numbers` and the
first statement carries none, copy them onto the first statement's row (`dataclasses.replace`).
Needs `stated` to map key -> match instead of being a set. Fix the `_restates` docstring to say
what the code does.

R5 (19 Sep 2026, prod CB1178A-SS-NEW) narrowed "the first statement" further: `stated` maps key
-> the LIST of instructions that key has stated so far (one per tab-position it reached, not one
per key), paired with a `(sheet, key)` counter, because a restatement is only ever ACROSS tabs -
two identical rows inside ONE tab are two separate instructions, not one restated. A later tab's
n-th row of a key restates the n-th instruction (position-matched), and lending targets that same
position rather than always the first.

## 3. Test list (tester writes these red first, Postgres, own seeded chain)

`tests/test_oi_sheet_line_pick_month_po.py`, one fixture builder for the UAC table:
AC-LP-1 to AC-LP-13. Then run the whole inquiry import family before push (lesson 18 Sep: a
confirm-seam change went red in four untouched files): `tests/test_*order_inquiry*import*`,
`test_*oi_sheet*`. Two later small-fix slices, coder-owned tests both times (R4, R5): AC-LP-14
(the sheet's PO outranks the month) and AC-LP-15 (a restatement is only ever across tabs).

Expected to change: any existing test that asserts finding 9's no-charge behaviour. Rewrite it to
AC-LP-12, do not delete it.

## 4. Rollout

1. Lane on its own branch off main AFTER `lane/oi-follow-book-chain` (#1022 to #1024) merges, or
   as a slice on it if the owner prefers: both edit this importer file.
2. Backend only. No migration, no FE, no worker task change (the import task calls `apply`; the
   worker still needs a restart on deploy as always).
3. After deploy the owner runs rollback + re-upload of the book on prod, as after #918. D2 stands:
   nothing here moves a row an earlier upload misplaced.
4. Before step 3, measure on a fresh prod copy: preview the book and count rows whose landed line
   changes against the current rows. That number is the size of the repair.

## 5. Trigger for more machinery

A global best-assignment (minimum total date distance per item) is NOT built. Build it only if
the measurement in 4.4 shows rows still landing on a line outside their PO group after these
passes.
