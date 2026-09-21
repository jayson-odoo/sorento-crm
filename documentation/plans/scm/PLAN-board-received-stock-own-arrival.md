# PLAN - Fulfilment board: received goods are stock, bought-for-this-line first

Status: in progress, Phase 2 tester-first (started 21 Sep 2026 evening); lane `feat/board-received-stock-own-arrival`, worktree `sorento_crm-own-arrival` off origin/main cc6c09f19, private DB `sorento_buc_ci`. Rulings taken 21 Sep 2026 (lavish alignment page, owner "ok go").
Domain: SCM, fulfilment planning board + planning-change engine + order inquiries + OI sheet importer.
UAC: `board-received-stock-own-arrival-acceptance-criteria.md`.
Evidence: prod dump 21 Sep 03:49 UTC restored as `sorento_ai_automation_0921`; SO372176 / MHS1025.

## The problem, measured (SO372176, 21 Sep 2026)

Confirm on `/project-sales/fulfilment-planning?orders=SO372176` fails with
`SO372176 line 2: 38 of SPO-2026/01-0138 has no purchase-order line to re-deal`
(`planning_change_reallocation_no_document`, `app/services/planning_change_service.py:3258`).

Facts on the prod copy:

- 10 open SO lines / 530 pcs (Oct 2026 to Dec 2027). PO 202510-S0101 has six MHS1025 lines bought
  for L1 to L6 (`purchase_order_lines.from_so_line_ref` = the line's `sales_order_lines.source_ref`),
  39 + 5 x 40 = 239, all closed and fully received via SPO-2026/01-0138 allocations
  (`spo_allocations.po_line_id` NULL, `from_po_number` set, `receipt_status = fully_received`).
  BRW-BB on hand 231, reserved 0. 202607-S0080's 70 line for L7 is cancelled on the PO.
- Batch `9afcae64` was composed 15 Sep 03:21 and froze "L2 holds 40 on SPO-2026/01-0138". The
  20 Sep rollback + re-upload of the two order books rebuilt the OI rows: L1, L2, L7 got none, three
  2027-book rows (40 Jan, 40 Feb, 40 Mar) were dropped, and the 2026 book's 70 @ Oct 2026 was paired
  to L11 (120 @ Dec 2027) instead of L2 (20 @ Oct 2026). The owner's 21 Sep 02:59 confirm applied L3
  and linked L3 to L6 (40 each) onto the received allocations; L1, L2, L7 batch rows stayed pending
  with 15 Sep facts.
- The ladder's own trail for L2 (`planning_change_rows.proposal_json.trail`): step 1 "BRW: 37 on
  hand, this line takes 18"; step 2 "The BB group nets -1375, so there is nothing left for this
  line". The board has no notion that 239 of the BRW-BB pile was bought for this order: nothing on
  the board reads `from_so_line_ref` (verified by grep across `project_fulfilment_board_service.py`,
  `project_supply_service.py`, `scm/front_planning_engine.py`).
- A received document has zero link capacity at Order Inquiries
  (`project_order_inquiry_service.py:5992`, `ordered - received - linked`), so purchasing cannot link
  a raised row to the 239 today; only the board's confirm path re-linked them.

Three defects:

- **D1** compose counts every link (SPO allocation included) as "placed on a document"
  (`_placed_links` :1442-1499, readers :390 :521 :670 :1993), so the undecided-line path emits
  "Reallocate SPO-2026/01-0138 38 to pool"; apply (`_document_links_by_row` :2917-2966) re-deals only
  `po_line_id` links and can never execute it. The ladder also counts the same landed units as pool.
- **D2** a pending batch row is applied against its compose-time facts; when the placement is gone,
  apply raises for the whole order (:3258-3266) instead of recording "nothing to move".
- **D3** the importer paired sheet rows to lines product -> location -> remaining qty with a
  five-pass line pick (`project_order_inquiry_import_service.py:583-635`, `:836-931`, `:946-1019`)
  and skipped rows whose matched line already carried a row (`_already_raised` :1021-1074,
  `raisable` :263-266). Result: 8 sheet rows became 5 DB rows, one on the wrong line.

## Rulings (owner, 21 Sep 2026, lavish page `.lavish/so372176-fulfilment-alignment.html`)

- **R1** A link to a received document = stock in hand for this line. OI row and board show
  Received. The board never composes a Reallocate for it and never counts those units as free pool a
  second time.
- **R2** Path picker at replan: own landed stock (received on PO lines bought for this line, capped
  by on hand at the location, net of what the order already delivered) covers the link -> RETAIN the
  row (still linked, Was/Now note, board Received, no new row). Otherwise today's rule: mark used,
  raise a fresh row.
- **R3** Parked. Minimum only: Confirm never fails the whole order over a placement that no longer
  exists; it records "nothing to move" for that component. A batch row whose SO line is closed is
  dropped at apply. No recompose.
- **R4** Sheet row to SO line pairing by date order: sheet rows sorted by delivery date onto open
  lines sorted by required date, one each; a second sheet row on the same line lands as a second row
  on that line. One OI row per sheet row, never dropped. Closed and cancelled lines take none.
- **R5** Fix lane first, one SCM lane, tester-first; deploy; then confirm SO372176 on prod.
- **R6** Received goods are plain stock. CS covers a line from stock on the board (Reserve).
  Purchasing never links a received document at OI. Existing received links stay as history.
- **R7** Own-arrival credit. Before the group net, the board credits a line with what landed FOR it
  (tier 1: received PO lines whose `from_so_line_ref` is this line's `source_ref`), then the rest of
  the same sales order's landed stock (tier 2), then the group pile as today. Credited quantity
  composes as Reserve ("Received, own arrival"), is never a Buy and never marks a row used. CS
  amending it to Buy is refused: "N landed for this line on PO ...".
- **R8** Closed by R2: no date rule; when other orders consume the stock, on hand falls below the
  link and Path A fires by itself.
- **R9** (owner, 21 Sep evening, after the S4 reconciliation measured the collision) A sheet row
  for a sales order with no open line (fully delivered or all cancelled) lands nowhere: the import
  refuses it with its own reason `order_fully_delivered` (not `no_line_for_item`, which stays for
  a genuine item mismatch), the order is not adopted, the row is listed under `line_not_found`.
  The old D8 history row on the closed line is not written.
- **R10** (owner, 21 Sep late, after the AC-S4-5 replay showed L2 never paired) Line quantity
  does not gate the date-order pairing. A sheet row lands on the line its date order gives it even
  when its qty exceeds that line's ordered qty; the difference is the ordinary "Was {qty} on
  {date}" note. `qty_exceeds_ordered` remains only for a row larger than the order's total open
  quantity. On SO372176 this puts OCT26/70 on L2 (20 @ Oct 2026), not L11.
- Board vs OI split (owner): the board does not consider incoming; incoming is purchasing's decision
  at Order Inquiries. R7 reads RECEIVED quantity only; open-PO shifting at OI is untouched, and a
  delayed line still reaches OI as a fresh row (Path A) or a retained row with Was/Now (Path B).

## Slices (Phase 2 order; each slice = tester red first, then coder green)

### S0 Measure the importer before touching it
Replay the 20 Sep import of both books against `sorento_ai_automation_0921` in preview/dry-run
(no writes) for SO372176 and record per sheet row: which pass matched, which line, and for the three
2027 rows why `raisable` was false. Output: a table in this plan. Decides whether S4 is a ranking
change or a skip-rule change.

**Measured 21 Sep 2026**, replaying `preview()` (`_preview_plan` -> `_plan` + `_pair`,
`project_order_inquiry_import_service.py:2627-2648`) against `sorento_ai_automation_0921`, one
call per book, for every sheet row naming SO372176. Verified read-only first: every
`db.commit()/flush()/add()` in the file sits at or after line 2864 (the write path's
`raise_order_inquiry` and its call sites), strictly after `preview`/`_preview_plan`/`_plan`/
`_pair`/`pair_needs` (lines 1855-2649), which touch only `db.query(...)`. The run itself still
opened its own session and rolled it back in `finally` regardless. Script:
`/Users/tehjayson/.claude/jobs/77a4318c/tmp/measure_so372176_import.py`. Run:

```
cd /Users/tehjayson/Documents/foundryx/sorento_crm-own-arrival/sorento_crm_backend
SORENTO_ENV_FILE=/Users/tehjayson/.claude/jobs/77a4318c/tmp/env.0921 \
  /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend/venv/bin/python \
  /Users/tehjayson/.claude/jobs/77a4318c/tmp/measure_so372176_import.py
```

Every blocking OI row found below carries `created_at = 2026-09-20 03:19:03` (the 2026 book's own
upload) or `2026-09-20 03:22:36` (the 2027 book's own upload, three seconds later) - i.e. every
block on these nine rows was already in place by the END of the 20 Sep import itself, none of it
from the owner's 21 Sep 02:59 confirm (which only touches L3/L6/L9/L10, none of the lines below).
Today's `preview()` therefore reproduces the exact 20 Sep outcome for these rows (nothing about
them changed between 20 and 21 Sep).

| Book | Sheet row | Product | Delivery date | Qty | Pass matched | Paired SO line (No. + required date + qty) | Raisable | Reason |
|---|---|---|---|---|---|---|---|---|
| 2026 book | OCT 26 row 154 | MHS1025 | 2026-10-01 | 70 | 5 fallback rank | L11 (req 2027-12-30, qty 120) | No | `already_raised` - blocked by `oi_row e59974d8` (created 20 Sep 03:19:03, same import, note "Was 70 on 2026-10-01") |
| 2026 book | SEPT OCT 26 row 821 | MHS1025 | 2026-10-01 | 70 | (none - duplicate) | - | No | `duplicate` - restates the OCT 26/row 154 instruction across tabs (D7/R5 key: same SO+item+qty+date+location); never reaches the line pick |
| 2026 book | NOV 26 row 179 | MHS1025 | 2026-11-01 | 40 | 5 fallback rank | L8 (req 2027-08-30, qty 40) | No | `already_raised` - blocked by `oi_row ae786503` (created 20 Sep 03:19:03, same import, note "Was 40 on 2026-11-01") |
| 2026 book | DEC 26 row 279 | MHS1025 | 2026-12-01 | 30 | 4 same month | L3 (req 2026-12-30, qty 50) | No | `already_raised` - blocked by `oi_row 02ee2cb4` (created 20 Sep 03:19:03, same import, note "Was 30 on 2026-12-01"; only its *state* changed later via the 21 Sep `decision_confirm`) |
| 2026 book | DEC 26 row 280 | MHS1025 | 2026-12-01 | 40 | 5 fallback rank | L4 (req 2027-02-28, qty 50) | No | `already_raised` - blocked by `oi_row 86de9932` (created 20 Sep 03:19:03, same import, note "Was 40 on 2026-12-01") |
| 2027 book | JAN 27 row 49 | MHS1025 | 2027-01-01 | 40 | 5 fallback rank | L8 (req 2027-08-30, qty 40) | No | `top_up_sum_mismatch=True` - L8 carries an ACTIVE decision (buy_qty 40) and one live ORDER row (`ae786503`, qty 40, itself the 2026 book's NOV 26 row above); 40 (this row) + 40 (L8's own) = 80 != 40, and no sibling row already states this row's Now/Was, so AC-RB-27 reports it rather than silently skipping. Root block is `ae786503`, created 20 Sep 03:19:03 - a cross-book collision inside the SAME 20 Sep session (2026 book ran first) |
| 2027 book | FEB 27 row 3 | MHS1025 | 2027-02-01 | 40 | 4 same month | L4 (req 2027-02-28, qty 50) | No | `top_up_sum_mismatch=True` - L4's decision buy_qty is 50, its own live row (`86de9932`, qty 50) already equals it; 40 + 50 = 90 != 50. Root block `86de9932` created 20 Sep 03:19:03 (2026 book's DEC 26/row 280, landed on L4 via fallback rank instead of its own month) |
| 2027 book | MAR 27 row 3 | MHS1025 | 2027-03-01 | 40 | 5 fallback rank | L3 (req 2026-12-30, qty 50) | No | `top_up_sum_mismatch=True` - L3's decision buy_qty is 50, its own live row (`02ee2cb4`, qty 50) already equals it; 40 + 50 = 90 != 50. Root block `02ee2cb4` created 20 Sep 03:19:03 (2026 book's DEC 26/row 279, landed on L3 via same-month) |
| 2027 book | APR 27 row 186 | MHS1025 | 2027-04-01 | 30 | 4 same month | L5 (req 2027-04-30, qty 50) | No | `already_raised` - blocked by `oi_row 112a1b5e` (created 20 Sep 03:22:36), which IS this same sheet row's own successful 20 Sep raise (note "Was 30 on 2027-04-01"). Not a drop - shown for contrast with the three above |

Conclusion: **both**, and R4 already says so. The five-pass pick (`_match_in_passes`
:946-1019, `_run_pass` :836-931, `_rank_for*`/`_narrow_*` :510-822) is a RANKING defect on its
own terms - OCT 26's 70 (delivery 2026-10-01) lands on L11 (required 2027-12-30) and DEC 26's 40
(delivery 2026-12-01) lands on L4 (required 2027-02-28) via fallback rank, both off by more than a
year, because the fallback has no notion of "closest date" once the narrower passes 1-4 (exact
date, month+citation, citation alone, same month) find nothing - it falls through to whatever
`_rank_for` ranks first among the order's OTHER open lines. That mis-pairing is what left L8/L4/L3
"already raised" by the WRONG sheet row (a 2026-book row) before the 2027 book's genuinely-dated
JAN/FEB/MAR rows for those same months ever got a turn at them, three seconds later in the same
session. Separately, `_already_raised` (:1021-1078) and its `_resolve_recovery_matches`
top-up refinement (:1271-1358, `top_up_sum_mismatch` :258, `_top_up_status` :1147-1177) are a
SKIP-RULE defect: once two sheet rows do land on one line, the second is dropped/reported rather
than raised as a second row on that line, which is exactly what R4 ("a second sheet row on the
same line lands as a second row on that line") replaces. Fixing only the ranking (closest-date
assignment) would still collide when two real deliveries genuinely share one open line across two
books; fixing only the skip rule would still send JAN/FEB/MAR to the wrong lines' history. S4 needs
both halves of R4.

### S1 Apply never fails over a vanished placement (D2, R3 minimum)
`planning_change_service.py::_redeal_document` :3258-3266: when `available <= 0` for a
non-cancelled row, append `"{document}: nothing to move, the placement this suggestion named is no
longer on the line"` to `released` (same list `_execute_reallocations` :3675 writes to
`result_json["released_documents"]`) and return. Keep the 409 for `0 < available < freed`.
`_apply_one_order` (:4169+): a live batch row whose core line `line_status` is `closed` or
`cancelled` and whose kind is not `cancelled` is marked superseded ("the sales-order line is closed")
and skipped, so L1's stale qty_down row stops blocking.

### S2 Compose never re-deals a received document (D1, R1)
`_placed_links` :1442 returns `qty` (unchanged, for arrival/late maths), plus `po_qty` = open
purchase-order-line quantity still reallocatable (link qty on `po_line_id` links whose line is not
fully received per `_received_documents_for`'s test, `project_order_inquiry_service.py:1750-1753`)
and `received_qty` = link qty on received PO lines + all SPO allocation links judged received
(negation of `scm/spo_supply.open_incoming_clauses`). Readers :390, :521, :670, :1993 use `po_qty`.
`received_qty` composes a `keep` component labelled "Received {document} {qty}" so the board row says
so; never a reallocate.

### S3 Own-arrival credit and the path picker (R7, R2, R6)
- New helper in `project_supply_service.py` beside `use_candidates_for` (:2547):
  `_own_arrival_credit_for(fact)` = sum of `purchase_order_lines.qty_received` where
  `from_so_line_ref == this line's source_ref` (tier 1), then where `from_so_line_ref IN (source_ref
  of the other lines of the same sales order)` (tier 2), each capped by `LocationNet.on_hand` at the
  line's location (`scm/group_netting.py:82`) net of what the order already delivered (closed lines'
  `qty_ordered`) and of credit already granted to earlier lines of the same order in this walk.
  Accumulated into `mine` ahead of ordinary own-group candidates so `_draw_group`
  (`scm/front_planning_engine.py:1387-1440`) draws it first as `RESERVE` on `RUNG_GROUP_TAKE`.
- Trail: a `why` addendum via `_group_take_why` (`project_fulfilment_board_service.py:3818`):
  "N landed for this line on PO {po_number}, taken first."
- Composition: a Reserve born from the credit carries `source: own_arrival`; `set_row_decision` /
  amend refuses a Buy over it with `planning_change_buy_over_own_arrival`:
  "{N} landed for this line on PO {po_number}; nothing to buy for it".
- Path picker: `project_order_inquiry_service.py:1636` (the S2 decline rule of
  `PLAN-oi-replan-received-links.md`): before marking used, compute the same credit for the row's
  line; if credit >= the row's linked quantity, return `None` (settle in place, links kept, Was/Now
  note as any other settle). Otherwise today's path.
- The ladder must not count credited units again as free pool: subtract granted credit from the
  location's free figure for the rest of the walk (the same ledger `_own_pool_floor` reads).

### S4 Importer pairing by date order, never drop (D3, R4)
Shape depends on S0. Expected: (a) the line pick for a sales order becomes: open lines (not closed,
not cancelled) sorted by `required_date`, sheet rows of both books sorted by `delivery_date`, paired
one to one in order; a sheet row beyond the last open line lands on the last open line as a second
row; (b) `_already_raised` no longer makes a sheet row unraisable when the line's existing row came
from a different book or the same restated instruction: the existing row is restated in place
(follow-book, Was/Now), a genuinely new instruction is raised as a second row. Cancelled/closed core
lines are never candidates (drop the pass-5 fallback onto them).

**AFTER (fix round, HEAD c6e3c77c1, AC-S4-5)**, 21 Sep 2026. The 21 Sep first pass above
(HEAD 7ba28c778) was preview-only and flagged its own methodology gap (Deviation 3): two
independent `preview()` dry-runs against one unchanged snapshot cannot see book 1's picks when
book 2 previews, so it could not reproduce a real sequential upload. Since then R10 landed (line
qty no longer gates the date-order pairing) and the five-pass fallback was deleted (HEAD
6c9b05636). This re-run closes that gap by calling the REAL write path -
`svc.apply()`, the same function `app.tasks.import_tasks._run_scm_upload_job` calls - for each
book in turn, inside one still-uncommitted session, so book 2's plan genuinely sees book 1's
raised rows the way a live sequential upload would, without ever committing to disk.

Verified before running that this is safe: `apply()` takes the caller's own session and never
opens one of its own (grepped the whole service file for `SessionLocal(`, `Queue(`, `enqueue`,
`.delay(`, `notification_service`, `send_email`, `send_notification`, `rq.` - zero hits); it never
calls `db.commit()` (its own docstring: "One transaction, owned by the caller"), only `db.flush()`
and one `begin_nested()` SAVEPOINT inside `ProjectSOAdoptionService._insert_record` (undone by the
outer rollback same as everything else); and `outcome=None` makes `apply()` build
`ImportOutcome(None, persist=False)` itself, which `import_outcome.py` confirms never buffers or
writes an `import_job_rows` row on any session once `persist` is False. Nothing to stub - no RQ
job, no email, no notification sits anywhere on this path. Script:
`/Users/tehjayson/.claude/jobs/77a4318c/tmp/measure_so372176_import_after2.py`. Run:

```
cd /Users/tehjayson/Documents/foundryx/sorento_crm-own-arrival/sorento_crm_backend
SORENTO_ENV_FILE=/Users/tehjayson/.claude/jobs/77a4318c/tmp/env.0921 \
  /Users/tehjayson/Documents/foundryx/sorento_crm/sorento_crm_backend/venv/bin/python \
  /Users/tehjayson/.claude/jobs/77a4318c/tmp/measure_so372176_import_after2.py
```

One rolled-back session. Step 1 deletes SO372176's own 8 `order_inquiry_rows` (uncommitted;
`order_inquiry_links` cascade). PASS 1 previews then APPLIES the 2026 book, then previews then
APPLIES the 2027 book, against that clean state, both in the same open transaction. PASS 2, before
rollback, re-uploads (preview + apply) both books again over PASS 1's own applied state, to show
what a restate looks like. The whole session is rolled back in `finally`; a fresh second session
then re-counted `order_inquiry_rows` for SO372176 and got 8, identical to the pre-run count - the
delete and every apply never persisted.

PASS 1 - clean sequential import (delete, then 2026 book applied, then 2027 book applied against
that now-flushed state):

| Line | Line required date / qty | Row qty / date | Note |
|---|---|---|---|
| L2 | 2026-10-01 / 20 | 70 / 2026-10-01 | Migrated ... 2026 book.xlsx; **Was 20 on 2026-10-01**; Linked to SPO-2026/01-0138 |
| L3 | 2026-12-30 / 50 | 50 / 2026-12-30 | Migrated ... 2026 book.xlsx; Was 40 on 2026-11-01; Linked to SPO-2026/01-0138 |
| L4 | 2027-02-28 / 50 | 50 / 2027-02-28 | Migrated ... 2026 book.xlsx; Was 30 on 2026-12-01; Linked to SPO-2026/01-0138 |
| L5 | 2027-04-30 / 50 | 50 / 2027-04-30 | Migrated ... 2026 book.xlsx; Was 40 on 2026-12-01; Linked to SPO-2026/01-0138 |
| L6 | 2027-06-01 / 50 | 50 / 2027-06-01 | Migrated ... 2027 book.xlsx; Was 40 on 2027-01-01; Linked to SPO-2026/01-0138 |
| L7 | 2027-06-30 / 50 | 40 / 2027-02-01 | Migrated ... 2027 book.xlsx |
| L8 | 2027-08-30 / 40 | 40 / 2027-08-30 | Migrated ... 2027 book.xlsx; Was 40 on 2027-03-01 |
| L9 | 2027-10-30 / 50 | 50 / 2027-10-30 | Migrated ... 2027 book.xlsx; Was 30 on 2027-04-01 |

8 rows, L2..L9, exactly as the UAC states, with OCT26/70 on L2 carrying the R10 "Was 20 on
2026-10-01" note (row qty 70 exceeds L2's own 20).

PASS 2 - re-upload of both books over PASS 1's applied state (before rollback, same session):

| Line | Line required date / qty | Row qty / date | Note (abridged) |
|---|---|---|---|
| L2 | 2026-10-01 / 20 | 70 / 2026-10-01 | unchanged, restated in place (`already_raised`) |
| L3 | 2026-12-30 / 50 | 50 / 2026-12-30 | unchanged, restated in place |
| L4 | 2027-02-28 / 50 | 50 / 2027-02-28 | unchanged, restated in place |
| L5 | 2027-04-30 / 50 | 50 / 2027-04-30 | unchanged, restated in place |
| L6 | 2027-06-01 / 50 | 50 / 2027-06-01 | unchanged, restated in place |
| L7 | 2027-06-30 / 50 | 40 / 2027-02-01 | unchanged, restated in place |
| L8 | 2027-08-30 / 40 | 40 / 2027-08-30 | unchanged, restated in place |
| L9 | 2027-10-30 / 50 | 50 / 2027-10-30 | unchanged, restated in place |
| L11 | 2027-12-30 / 120 | 40 / 2026-12-01 | **new**, "2026 book.xlsx" only |
| L11 | 2027-12-30 / 120 | 30 / 2026-12-01 | **new**, second row on the same line |
| L10 | 2027-11-30 / 50 | 50 / 2027-11-30 | **new**, "2026 book.xlsx"; Was 40 on 2026-11-01 |

11 rows after PASS 2, not 8: three new rows land on L10/L11, lines PASS 1 never touched.

Comparison with UAC AC-S4-5 ("8 rows on L2..L9 by date") and 3 deviations:

1. **PASS 1 matches exactly.** Calling the real write path sequentially (book 1 applied before
   book 2 previews) resolves the earlier preview-only run's Deviation 2/3 collisions entirely: 8
   rows, one per open line L2..L9 in date order, none dropped, and OCT26/70 lands on L2 with the
   R10 "Was 20 on 2026-10-01" note exactly as the UAC describes. The 21 Sep first pass's L2-unused
   / L3-L6-collision findings were an artifact of previewing both books dry against one unchanged
   snapshot, not a defect in S4's pairing itself.
2. **New finding, only visible on the real apply path:** 6 of the 8 PASS 1 rows (L3, L4, L5, L6,
   L8, L9) have their qty/date SETTLED to an ACTIVE `so_supply_decisions` row's own buy_qty and
   required_date (`_apply_settle_recovery`, AC-RB-11, `project_order_inquiry_import_service.py:
   2807-2833`) rather than keeping the sheet's own literal ask - the sheet's figures survive only
   in the row's "Was ..." note. This is pre-existing, documented behaviour (2.1(b)), not something
   S4 changed; the earlier preview-only script could never see it because `preview()` never calls
   `apply()`'s post-raise settle step.
3. **PASS 2 is not a clean restate-in-place.** Because settle (#2) moved 6 of 8 rows' own
   qty/date away from what the sheet literally states, PASS 2's `already_raised` match (keyed off
   the sheet row against the row's OWN current qty/date) no longer recognises those sheet rows as
   already raised on re-upload, so 3 "new" instructions land on lines L10/L11 that PASS 1 never
   used - the count grows from 8 to 11, not restate-in-place at 8. This is a consequence of the
   settle mechanism in #2 interacting with a re-upload, not a defect S4 introduced; out of scope
   for AC-S4-5 (which is about the clean-import count, matched by PASS 1) but worth a follow-up
   ruling before a live re-upload of an already-decided line is relied on to restate cleanly.

### S5 Board and OI read the credit (FE)
Board line shows the `Received N (own arrival)` chip where the composition carries
`source: own_arrival`, next to the existing received-link chip; OI worklist row shows Received for a
retained (Path B) row exactly as it shows a received link today. No new screens.

## Out of scope
- Recompose of stale batch rows (R3 parked).
- Inventory reservation (`quantity_reserved`) for landed goods.
- Purchasing linking a raised row to a received document (R6: no).

### Follow-ups (reviewer, round-5, 22 Sep)
- `_restated_existing` consumed-row tracking - the AC-S4-8 restate-recovery seam flagged by the
  reviewer as worth its own guard rather than being folded into this lane.
- Confirm-time credit judged against the line's live proposal sources instead of a re-derivation:
  `_check_line`'s own-arrival recheck (`own_arrival_credit_for` ->
  `_own_arrival_credit_components`) recomputes the credit from scratch rather than reading what
  the board's own frozen `proposal_json["sources"]` already state for the line - S-3, a
  payload-order divergence the reviewer measured but did not force red this round (AC-S3-16 fixes
  the reserve-window gate the re-derivation was missing; the re-derivation itself staying a
  second, independent read of the same facts rather than a read of the proposal is the open
  question this follow-up names).
- Picker vs board window verdict: the replan path picker's minimal `_LineFacts` carries no
  `required_date`, so it never applies the reserve-window gate the board and confirm now apply
  (AC-S3-16); a line outside the window can be settled in place by the picker while the board buys
  it; needs an owner ruling on whether landed-for-this-line stock is window-gated at all.
- Confirm-time window verdict reads today while compose reads `as_of`: a line exactly one day past
  the window at compose can cross into it at confirm (one-day-wide, closed by the
  live-proposal-sources follow-up).

## Verification on SO372176 (after deploy, owner)
Confirm on the board succeeds; L2 to L6 read Received (20, 40+10, 40+10, 40+10, 40+10), nothing to
buy for them; L1's row is gone; L7 offers Buy/stock; a re-upload of both books yields 8 OI rows
paired L2..L9 by date with Was/Now notes; no row is grey.
