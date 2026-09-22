# PLAN: ORDER BACK rows are owed in full, never closed by the borrowing line's delivery (22 Sep 2026)

Status: BUILT 22 Sep 2026, review in progress; browser pass AC-OB-17 queued (no slot). Feature track (one demand seam across the
view, the plan SELECT, the worklist ORM twin and the importer, plus a view migration and a
one-off backfill script; too wide for the small fix track).
UAC: `oi-order-back-not-capped-acceptance-criteria.md`.
Lane: worktree `../sorento_crm-order-back-owed`, branch `fix/oi-order-back-owed` off
`origin/main` 1417ce36b. Tests on `sorento_ci` via `SORENTO_ENV_FILE=.env.ci-tests`. No
stack slot yet (both slots taken); browser pass queued.

## 1. Journey

SO417310 line 16 (MKT5529SS-DIY, 3 pcs, BRW-BB) was delivered from stock BORROWED off another
order. CS writes the row on the Order Inquiry sheet as ORDER BACK: buy 3 to fill the hole the
borrow left at BRW-BB. Purchasing uploads the sheet, opens Start Plan with Demand = Project,
and SO417310 must be in the Orders list and the plan must buy 3 for BRW-BB. Today the upload
stamps the row `actioned` in the same second it raises it, the picker hides the order, and
the plan buys nothing, because the borrowing line reads delivered 3/3.

## 2. Measured facts (origin/main 1417ce36b, DB `sorento_ai_automation_0921`)

- SO417310 / MKT5529SS-DIY inquiry row `bee581f3`: verb `ORDER`, state `actioned`,
  `actioned_at` == `order_inquiries.raised_at` (2026-09-20 11:19:23), `actioned_by` = the
  uploader. Core line 16: qty_ordered 3, qty_delivered 3, `closed`. Owed = 0.
- The sheet reader (`app/services/project_order_inquiry_reader.py:69,303`) flags
  `order_back` ONLY when the Delivery date cell matches `\bORDER\s+BACK\b`. The remark
  column is read into `remark` and never consulted for the verb. This row's date cell held a
  date, so it was stored as `ORDER`.
- `demand._OWED_SQL` (`demand.py:435`) and `_OWED_FORM_SQL` (`:446`) cap the owed quantity
  at the CORE LINE's outstanding (`_LINE_OUTSTANDING_SQL`, owner ruling 14 Sep, SO368872 /
  SRTWC286-SH). Both fragments are interpolated into `COMMITTED_V_SQL` (the view body, frozen
  in migration `512_committed_v_redirect_exclude.py`), into `horizon_committed_select_sql`
  (the plan), into the needed-date SQL and into `/reorder-runs/candidate-orders` (the Start
  Plan picker). The worklist's ORM twin is
  `order_inquiry_worklist_service._CAPPED_QTY` (`:403`, `least(qty, _LINE_OUTSTANDING)`).
- The importer's `_close_history` (`project_order_inquiry_import_service.py:2812`, called
  at `:3223` for every raised row where `not _is_open_demand(match.core_line)`) stamps
  `actioned` regardless of verb.
- `IV_ORDER_BACK`'s own doctrine (`models/project_so.py:795-811`): "a shortfall against
  something already ordered or already shipped", the quantity belongs to the DONOR location
  named by the row's `stock_location`, and it "is still demand until it is linked"
  (`demand.py:514`). A delivered borrowing line is the normal case for an order back, so the
  cap and the history close swallow every one.
- Re-uploading the sheet after the fix does NOT repair existing rows: `_restates` dedupes
  on (SO, item, qty, date, location) and skips them as `ALREADY_RAISED`.

## 3. Rulings (owner, 22 Sep 2026)

- R1: "order back" in the REMARK cell also makes the row ORDER_BACK, not only the Delivery
  date cell. Date cell keeps its date when it holds one.
- R2: An ORDER_BACK row is owed `qty - linked - bundled` in full. The borrowing line's
  outstanding never caps it. ORDER rows keep the 14 Sep cap unchanged.
- R3: The importer never history-closes an ORDER_BACK row. An ORDER row on a delivered line
  is still closed as today (AC-S1-29 stands for ORDER).
- R4: Backfill: a one-off script re-reads the uploaded sheet(s), and every existing ORDER row
  the IMPORTER closed (`actioned_at == raised_at`) whose sheet row now reads ORDER BACK is
  flipped to `ORDER_BACK` / `raised` with `actioned_by/at` cleared. A row a person marked
  actioned (any other `actioned_at`) is never touched. Owner runs it on prod.
- R5 (interim, owner needs it now): the same flip for SO417310 / MKT5529SS-DIY runs as a
  hand SQL on prod before this lane ships. Until the cap fix deploys the row reads Raised /
  ORDER BACK with Remaining 0 and the picker still hides it; the SQL is a data repair, not a
  workaround.

## 4. Slices

- S1 Reader: `order_back = ORDER BACK in delivery-date cell OR in remark cell`.
  `delivery_date` stays `_as_date(cell)` (date when the cell is a date, None when it is the
  words). One function, no new field.
- S2 Owed math: `_OWED_SQL` and `_OWED_FORM_SQL` become
  `GREATEST((CASE WHEN oir.verb = 'ORDER_BACK' THEN oir.qty ELSE LEAST(oir.qty, <outstanding>) END)
  - linked - bundled, 0)` (form twin keeps its `csol.id IS NULL` branch). Worklist
  `_CAPPED_QTY` gets the same `case(verb == IV_ORDER_BACK, qty)` branch. New migration
  `525_committed_v_order_back_uncapped.py` re-creates `scm.committed_v` with the new frozen
  body (same columns, `CREATE OR REPLACE`), 512's body frozen beside it for the downgrade,
  `test_committed_v_migration_chain.py` drift guard updated.
- S3 Importer: `_close_history` candidates exclude `entry.verb == IV_ORDER_BACK` (the check
  at `:3177` becomes `if entry.verb != IV_ORDER_BACK and not _is_open_demand(...)`).
- S4 Backfill script `sorento_crm_backend/scripts/backfill_order_back_rows.py <xlsx>...`:
  reads each book with the reader, matches `order_back` rows to existing inquiry rows on
  (so_number, item_code, qty, delivery_date, stock_location), applies R4, prints the flips,
  `--apply` to commit (dry run by default).
- S5 Picker: nothing to change; `/reorder-runs/candidate-orders` reuses the constants, so
  the SO appears once S2 lands. Covered by a test, not code.

## 5. Test list (tester writes these red first)

- Reader: remark "order back" (any case, extra spaces) -> `order_back=True`, delivery_date
  kept; date cell "ORDER BACK" still True; neither -> False.
- Committed view: ORDER_BACK row qty 3 on a line delivered 3/3 -> `project_qty` 3 at the
  DONOR warehouse; ORDER row on the same line -> 0 (cap unchanged, SO368872 case stays).
- Plan SELECT (`horizon_committed_select_sql`): same pair.
- Worklist Remaining: ORDER_BACK row on a delivered line -> 3.
- Importer: sheet row ORDER BACK (remark) against a delivered line -> stored ORDER_BACK,
  state `raised`, `actioned_at` NULL; ORDER row on the same line -> still `actioned`.
- Candidate orders: ORDER_BACK-only SO on a delivered line is listed with rows_total 1.
- Backfill: importer-closed ORDER row whose sheet row reads ORDER BACK flips; a person-marked
  actioned row (actioned_at != raised_at) does not; dry run writes nothing.
- Migration chain drift guard passes with the new body.

## 6. Out of scope

Board `confirmed_unplaced_buy_rows` warehouse attribution for ORDER_BACK (already handled
via `stock_location`), the OI detail page wording for a system close (separate ask), re-upload
dedupe rules.
