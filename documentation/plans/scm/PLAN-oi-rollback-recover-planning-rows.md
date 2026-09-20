# PLAN - order inquiry: recover the rows planning had worked on, and stop a rollback taking them again

Status: APPROVED by owner 20 Sep 2026, full `/feature` pipeline, backend only. Lane
`fix/oi-sheet-rebuild-from-planning`. UAC written; tickets next.
UAC: `oi-rollback-recover-planning-rows-acceptance-criteria.md` (AC-RB-1 to AC-RB-41).

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

Second measurement, 20 Sep (the whole 0918 copy, 12,285 live sheet rows; 13 share a line with a
row planning made, 10 of them the used rows):

- **R7** A notice row (DELAY and the other non-buy verbs) never stands for the line's own row:
  "already raised" counts only live ORDER / ORDER BACK rows. Measured: TPE-9204's restated row and
  a plain TPE-9204 row each sit beside a DELAY notice, which today reads as already raised.
- **R8** Top-up shape (SRTWC8605-SC-RL: sheet 182 beside a decision's top-up 38, buy 220): the
  sheet row comes back PLAIN when its quantity plus the active decision's own live ORDER rows on
  the line equals the decision's `buy_qty`; otherwise reported, nothing guessed. The rollback also
  keeps a stamped row whose line carries a row planning made. UAC AC-RB-24 to AC-RB-30, slice S5.

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

## 3.1 Seams (read off origin/main 1316bcd77, 20 Sep)

- Importer `app/services/project_order_inquiry_import_service.py`: `_already_raised` (988) returns
  only a SET of core line ids with any non-cancelled row, used rows included, and never loads the
  rows. `_run_pass` sets `match.already_raised` (901). `apply` skips `ALREADY_RAISED` at 2718-2801,
  else `_Raiser.raise_row` (2529) then links through `service._write_link`. 2.1(a) and 2.1(b) both
  sit at this one branch: 2.1(a) inside `already_raised`, 2.1(b) just before `raise_row`.
- A `Replaces N used` row: written in `project_order_inquiry_service.py` ~1104-1185; recognised by
  `previous_qty` / `previous_delivery_date` set, `redirected_to_pool` false, note starting
  `Replaces`.
- Snapshot entry: `line_snapshots[]` from `project_supply_service._snapshot` (6517); keys
  `project_line_id` (= the row's `so_line_id`, the mirror line), `core_line_id`, `buy_qty`,
  `required_date`. Active decision per order: `ProjectSupplyService.active_decision(pso_id)` (1082).
- Settle fields: `_settle_row_in_place` (`project_order_inquiry_service.py` 1383): `qty`,
  `delivery_date`, `supply_decision_id`, note `; Was {qty} on {date}`, `previous_qty`,
  `previous_delivery_date`, `changed_at`, `ack_state = changed`.
- Links: `_write_link` (6808) is the one writer; `_remove_links` frees; received test is
  `_received_documents_for` (1664). `_linkable_row_clauses` (2007) never offers a used row, so the
  move to the used row calls `_write_link` directly, as the importer's history path already does.
- `follow_book_for_rows` (2056) / `_displace_other_line_holders` (2391): a holder on the SAME core
  line is protected (AC-FB-6), which is why AC-RB-9 may pass with no new code.
- Rollback `scripts/rollback_oi_sheet_upload.py`: `rows_of` (100), `_remove` (150), `main` summary
  (253-308).
- New report code for AC-RB-3 in `app/services/import_outcome_codes.py`, constant + `LABELS` entry,
  riding on the existing skip outcome.

## 3.2 Captain's test list (tester writes these RED, before any implementation)

New file `tests/test_oi_sheet_rebuild_from_planning.py`, on the `World` / `world()` harness of
`tests/test_project_order_inquiry_import_migration.py` with `_apply`, `_rollback`, `_uploaded`,
`_rows_of` as `tests/test_oi_sheet_pairing_repair.py` defines them. CI's database is empty: every
test seeds its own order, lines, PO / SPO chain, fresh row and decision. A `Replaces N used` row and
an active decision are seeded DIRECTLY (rows + a `line_snapshots` dict in `_snapshot`'s real
shape), because that is prod's state today; only AC-RB-21 drives the real confirm.

| AC | test name | asserts, in words |
| --- | --- | --- |
| RB-1 | `test_sheet_row_beside_replaces_row_is_raised_used` | one new row, `redirected_to_pool` true, qty 182, date 2026-06-01, note starts with the file stamp; outcome is not `already_raised` |
| RB-2 | `test_two_same_qty_deliveries_pair_by_date` (parametrized over both file orders) | two used rows, each date pairs with the fresh row whose `previous_delivery_date` it equals |
| RB-3 | `test_no_exact_match_raises_nothing_and_is_reported` (parametrized: qty off, date off) | row count on the line unchanged; outcome carries the new code and names item, qty, date, SO |
| RB-4 | `test_second_upload_leaves_used_pair_alone` | second apply raises 0; every column of both rows equal before and after |
| RB-5 | `test_rebuilt_used_row_is_outside_demand` | the read the existing used-row tests assert on (find it in `test_oi_one_header.py` / `test_order_inquiry_draft_links.py`) treats the rebuilt row as it treats a confirm-made used row |
| RB-6 | `test_received_link_moves_from_fresh_row_to_used_row` | after apply: used row holds the received SPO link + its claim; fresh row holds none; claim count unchanged |
| RB-7 | `test_received_link_move_is_capped_at_used_qty` | link 200 received, used row 182: used row holds 182, fresh row keeps 18 |
| RB-8 | `test_open_link_on_fresh_row_never_moves` | open PO link stays on the fresh row untouched |
| RB-9 | `test_follow_book_leaves_received_link_on_used_row` | after RB-6 state, `follow_book_for_rows` over the line: link still on the used row, none on the fresh row. MAY BE GREEN ALREADY once RB-6 is green: report which |
| RB-10 | `test_rebuilt_links_are_autocounts_not_the_sheets` | sheet row cites a different PO than the book: no link to the sheet's PO anywhere |
| RB-11 | `test_row_on_decided_line_is_raised_settled` | qty 280, date 2027-03-01, previous 182 / 2026-06-01, `supply_decision_id`, `changed_at` set, `ack_state` changed, note has the stamp and `Was 182 on 2026-06-01`; book link written |
| RB-12 | `test_decision_equal_to_sheet_raises_plain` | no previous_*, no changed_at |
| RB-13 | `test_buy_zero_decision_raises_plain` | qty 36 as the sheet states, no previous_*, not used |
| RB-14 | `test_superseded_decision_is_ignored` + `test_order_without_decision_unchanged` | plain row in both |
| RB-15 | `test_line_with_live_row_is_never_restated` | live plain row + active differing decision: `already_raised`, row unchanged |
| RB-16 | `test_second_upload_leaves_settled_row_alone` | every column equal before and after |
| RB-17 | `test_rollback_keeps_planning_rows` (parametrized over the three traits) | row, links, claims all present after apply |
| RB-18 | `test_rollback_still_deletes_plain_rows` | as today |
| RB-19 | `test_rollback_names_kept_rows` | dry run and apply output: kept count, and per kept row SO, item, qty, date, trait; removed count excludes them |
| RB-20 | `test_rollback_then_reupload_changes_nothing_kept` | no duplicate, no column change |
| RB-21 | `test_journey_upload_confirm_old_delete_rollback_reupload` | snapshot of used, fresh, restated, plain rows + links before the old-style delete equals the snapshot after rollback + re-upload (ids and timestamps aside) |

Each test must fail for the RIGHT reason (an assertion on behaviour, or the missing outcome code),
never an import error or a fixture typo. AC-RB-22 and AC-RB-23 are captain-run, not tester files.

## 3.3 Review round, 20 Sep (slice S6, UAC AC-RB-31 to AC-RB-41)

Reviewer NOT READY (1 blocker), security-reviewer NEEDS WORK (1 high). Both reproduced their
findings; kill tests on AC-RB-6/7/9, 13, 24, 29 all went red, so the suite guards its ACs. Taken:
B1 over-link on the used row; two sheet rows on one decided line each settled to the full buy
(0 lines on the 0918 copy, reachable under the new line pick); false `top_up_sum_mismatch` on
every later upload; snapshot without `required_date`; RESERVE AND ORDER is a buy verb; used rows
out of the top-up sum; tolerant snapshot parse; `changed_at` from the decision; rollback single
read + self-guarding DELETE + company refusal over kept rows; nits (dead `KEPT_TRAITS`, `AC-R-19`
typos, `_top_up_status` docstring, preview warning line).

Not taken, with the evidence: a stale top-level `buy_qty` after `_replace_buy_with_reserve`
(545 of 545 active snapshots on the copy have `buy_qty` equal to their `kind = buy` components;
trigger to revisit: the rehearsal or prod shows one that differs); loading columns instead of
entities in `_already_raised` (about 12.7k rows; worker memory is read off the rehearsal).

## 4. Not in scope

- The Raised at history icon not showing on prod (suspected column width, 190 px does not fit
  `17/09/2026, 11:25 am` plus the icon). Separate FE small fix.
- Sales order detail header: Plan action, Edit into the gear menu. Separate FE small fix.
