# PLAN: An ORDER inquiry row is owed until it is linked, whatever AutoCount says about the line (23 Sep 2026)

Status: BUILT 23 Sep 2026, review round 2; fix round 29 Sep 2026 (R3 = A recorded, reopen
script removed, main merged, migration 527 re-parented onto `merge_29sep_batch7`,
browser AC-OU-12 run). Feature track (one demand fragment across the view, the plan SELECT
and the worklist ORM twin, a view migration).
UAC: `oi-order-rows-uncapped-acceptance-criteria.md`.
Lane: worktree `../sorento_crm-oi-order-uncapped`, branch `fix/oi-order-rows-uncapped` off
`origin/main` 7c2c8e342 (alembic head `oirs_0002_reserve_round2`). Tests on `sorento_buc_ci`
via `SORENTO_ENV_FILE=.env.ci-tests` (export `DATABASE_URL` too for `tests/scm/`).

## 1. Journey

SO421985: CS raised three ORDER rows of 493 on 18 Sep (OI-2609-0027, To Buy, nothing linked).
On 21 Sep the AutoCount pull marked all three lines delivered 493/493 and closed the order.
Start Plan (Demand = Project) no longer lists SO421985 and the plan buys nothing for it,
while the OI detail still reads Remaining 493. The owner (23 Sep): "this is delivered
already and we want to replenish, I don't mind order back or order, as long as it needs to
order". A raised ORDER row is buy demand until purchasing links it, full stop.

## 2. Measured facts (origin/main 7c2c8e342, DB `sorento_ai_automation_0921`)

- `demand._OWED_SQL` / `_OWED_FORM_SQL` (`demand.py:435-460`) cap an ORDER row at the core
  line's outstanding (`_LINE_OUTSTANDING_SQL`, owner ruling 14 Sep, SO368872 / SRTWC286-SH:
  row 314 vs 12 outstanding bought 302 the customer already had). Since #1114 (22 Sep) the
  ORDER_BACK branch is uncapped. Both fragments feed `COMMITTED_V_SQL` (frozen in
  `alembic/versions/525_committed_v_orderback.py`), `horizon_committed_select_sql`, the
  needed-date SQL and `/reorder-runs/candidate-orders`. Worklist twin
  `order_inquiry_worklist_service._CAPPED_QTY` (`:403`). The OI detail's Remaining is NOT
  capped (header lines serializer), so the two screens disagree on SO421985 today.
- SO421985 on the copy: three ORDER rows, `raised`, `awaiting`, linked 0, lines delivered
  493/493 `closed`, SO `closed`. Owed today 0 on every reader but the OI detail.
- Rows in that shape (raised or partly linked, ORDER/ORDER_BACK, line delivered, not
  cancelled, unlinked qty > 0): 14 rows, 1,666 units.
- Importer history close (`_close_history`, AC-S1-29): a row uploaded against a line that is
  already not open demand (`line_status != open` or `purchasing_status = covered` or qty 0)
  is stamped `actioned` on upload, ORDER_BACK exempt since #1114. Importer-closed ORDER rows
  with unlinked qty > 0 on delivered, not-cancelled lines: 1,488 rows, 133,847 units (the
  whole Jan to Dec book); with delivery date on or after 1 Sep 2026: 168 rows, 9,221 units.

## 3. Rulings

- R1 (owner, 23 Sep 2026): an ORDER row is owed `qty - linked - bundled` in full, never
  capped by the line's outstanding, exactly like ORDER_BACK. The 14 Sep cap is retired for
  every verb. Known consequence: the SO368872 shape buys the row quantity again.
- R2 (owner, 23 Sep, implied by R1): the importer keeps closing rows on CANCELLED lines only.
  A row uploaded against a delivered line is raised like any other (history close narrows
  from "not open demand" to "line cancelled").
- R3 (owner, 29 Sep 2026): A, reopen NONE. Rows the importer closed on delivered lines
  before this lane stay `actioned`; nothing is reopened automatically or by script in prod.
  The options were A: none; B: delivery date on or after 1 Sep 2026 (168 rows, 9,221 units
  on the 21 Sep copy); C: another date. With A the bounded reopen script this plan carried
  as S4 has no consumer, so it is removed with its tests rather than shipped as an unused
  tool; CS re-raises any such row by uploading it again (R2 makes a delivered line a raise
  candidate).

## 4. Slices

- S1 Owed math: `_OWED_SQL` = `GREATEST(oir.qty - COALESCE(lk.linked, 0) - oir.bundled_qty,
  0)`; `_OWED_FORM_SQL` = `GREATEST(oir.qty - COALESCE(flk.linked, 0) - oir.bundled_qty, 0)`
  (the `csol.id IS NULL` branch and the ORDER_BACK branch collapse into the one formula).
  `_LINE_OUTSTANDING_SQL` stays for any other reader that still needs it (grep before
  deleting). Worklist `_CAPPED_QTY` = `OrderInquiryRow.qty` (rename to `_ROW_QTY` if nothing
  else reads the old name). Doc comments: R1, 23 Sep, the 14 Sep cap retired, SO421985.
- S2 Migration `527_committed_v_uncapped` (id <= 32 chars): `CREATE OR REPLACE VIEW
  scm.committed_v` with the new frozen body `_AS_OF_527`, 525's body frozen beside it for
  the downgrade; `down_revision` = current single head; drift guard in
  `tests/scm/test_committed_v_migration_chain.py` registers 527.
- S3 Importer, what shipped (review round 2, R2 turned out to reach deeper than the candidate
  test alone): `_pick_lines_by_date_order`'s own candidate gate widens from `line_status ==
  "open"` to `line_status != "cancelled"` - a closed/delivered line is a raise CANDIDATE again,
  not merely a line `_close_history` used to be trusted to close afterwards - so a sheet row
  against a delivered line now raises directly instead of being refused `order_fully_delivered`
  before it ever reaches `raise_row`. With that gate widened, `_close_history` is dead (a
  cancelled line never reaches `raise_row` at all, so nothing raised is ever a candidate to
  close) and is deleted outright, along with its call site, the `history` list, and
  `_is_open_demand` (zero remaining callers). Nothing closes on upload any more. R4 (captain,
  23 Sep 2026): open lines keep PAIRING PRIORITY over closed ones, ABSOLUTE - admitting a
  closed line as a candidate must never let it outrank a pre-existing open line, whatever
  the date order or how many rows already sit on it, so both `_line_pick_key` and the
  per-row `_rank` closure sort OPEN before CLOSED as their own dominant tier, ahead of
  free/room/last-resort; a row reaches a closed line only once the item's own candidate set
  on that order holds no open line at all.
- S4 Reopen script: DROPPED (R3 = A, 29 Sep 2026). Review rounds 1 to 3 shipped it as
  `scripts/reopen_delivered_order_rows.py --delivery-from <date>` with its own tests; the
  29 Sep fix round removed both. The PR's earlier commits hold it if a later ruling ever
  wants a bounded reopen (measured scope then: option B was 168 rows / 9,221 units).
- S5 Picker / plan / board: nothing to change; they read the fragments.

## 5. Test list (tester first)

- View + plan SELECT: ORDER row qty 493, line delivered 493/493 closed -> project_qty 493 at
  the line's warehouse (was 0). ORDER row on an open line with 12 outstanding, row 314 ->
  314 (was 12). Linked 100 + bundled 10 of 493 -> 383.
- Worklist Remaining: same 493 on the delivered line.
- Candidate orders: an SO whose only rows are ORDER on delivered lines is listed with
  rows_total 3 (SO421985 shape).
- Importer: ORDER row uploaded against a delivered `closed` line -> raised (candidate gate
  widened, AC-OU-7); against a `cancelled` line -> refused with its existing reason code,
  no row created, nothing history-closed (`_close_history` retired, AC-OU-8); ORDER_BACK
  unchanged. Open lines keep pairing priority over closed ones (R4, captain, 23 Sep 2026).
- Migration 527 drift guard + in-place round trip (clone the 525 test).
- Reopen script: retired with S4 (R3 = A, 29 Sep 2026); its test file went with it.
- Existing AC-OB-5 (`test_ac_ob_5_...stays_capped_at_zero`) is now WRONG by ruling: rewrite
  it to expect the row quantity and cite R1.

## 6. Out of scope

Green "took from stock" rows (next lane, on #1120's reserve link); the OI detail Remaining
(already uncapped, now agrees).
