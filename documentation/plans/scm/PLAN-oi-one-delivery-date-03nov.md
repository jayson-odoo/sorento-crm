# PLAN: One delivery date, OI rows use the SO line delivery date (OI-ONE-DELIVERY-DATE)

Status: Phase 2 build green (5 lane suites + wide run, 4 Nov); fix round 1 = AC-D2 split grid date. D1 reworded: split emails keep base date as the was (pinned by test_line_splits_round3). Card answered 3 Nov 22:50. Track: full (L): data
migration, about 40 readers across backend and one frontend cell. Branch
`claude/oi-one-delivery-date-43wfua`, PR #2145 (crew lane OI-ONE-DELIVERY-DATE).

Card: `OI-ONE-DELIVERY-DATE-card.md` (every reader with file:line, dev data, Q1 to Q5).
UAC: `oi-one-delivery-date-acceptance-criteria.md`.

## Journey

Owner, 3 Nov: one delivery date, the SO line's. OI-2609-0588 CB55CR read 01/09 and 01/10/2026 while
Stock Debt showed SO397450 due 04/02 and 18/02/2027, and the reserve dialog repeated the OI dates.
Purchasing and CS must read the same date on the OI, in Stock Debt and in every email; a change shows
on the OI as Was / Now in the same lightbox the SO line uses.

## Answers

Q1 (a) the OI tallies with the SO line at once, confirmed or not. Q2 (a) backfill, sheet date kept as
Was, no emails. Q3 (a). Q4: print 01/01/2030 as it is (owner's words; he also wrote "4 a", flagged to
crew). Q5 (a). Extra: reuse the SO line's change lightbox (`BoardChangeTable`).

## Design

1. **One resolver, `app/services/oi_delivery_date.py`** (new, the only place the rule lives):
   - `line_date_sql(row_table)`: the SQL expression
     `COALESCE(core.required_date, mirror.delivery_date, row.delivery_date)` plus the two outer joins
     it needs (`projects.sales_order_lines` on `so_line_id`, `public.sales_order_lines` on
     `core_sales_order_line_id`), for list queries, sort, filters, month buckets and raw-SQL legs.
   - `resolve(db, rows) -> {row_id: OiDate(date, was)}`: one batched read for Python readers.
   - `was_of(told, previous, line_date)`: the Was rule from the UAC terms.
2. **The stored column keeps its job as the told date.** The confirm-time machinery
   (`_handover_settle_diff`, `_stamp_date_move`, `_settle_row_in_place`, undo restore) is unchanged:
   it diffs the told date against the new SO date and stamps it at confirm, which is what keeps the
   DELAY / ADVANCE email (AC-B2). Nothing else reads the column as "the delivery date".
3. **Readers swapped to the resolver** (card table): worklist projection / sort / filters / month
   tabs / matrix (`order_inquiry_worklist_service.py:844`, `:874`, `:935`, `:1471-1475`,
   `:1688-1693`, `:3366-3374`, `:3562-3572`, link suggestions `:1969-2047`, host changes
   `:2341-2381`); `project_order_inquiry_service.py` per-project list `:8387`, `serialize_rows`,
   `handover_item` `:4790` (the one source for email, preview and attachment), split view base date,
   link walk `:12029`, `:12503`, `:13377`, `:13991`; `oi_handover_resend.py:108`, `:243`;
   `order_inquiry_reserve_service.py:331`, `:464`; `project_supply_undo_service.py:984-1000`;
   `project_supply_service.py:635`, `:12348`; `scm/stock_debt_snapshot_service.py:202`;
   `planning_change_service.py:1632`, `:1686`, `:4151`; `scm/demand.py`,
   `scm/demand_breakdown_service.py`, `scm/summary_order_service.py`, `api/v1/scm/reorder_runs.py`,
   `scm/spo_conversion_service.py` (OI date legs only; book legs already read `required_date`).
   OI-EXPORT-SHARED (#2146) owns `_records`, `export_xlsx`, `_handover_sorted`, `_handover_sort_key`,
   `order_inquiry_export.py`: not edited here, their sort follows the fields.
4. **Sheet import** (`project_order_inquiry_import_service.py:2827`): `delivery_date` = the SO line
   date; `previous_delivery_date` = the sheet date when it differs. The line pick by sheet date is
   unchanged. The "Dates corrected" restatement (`rows_delivery_date_updated`) stops moving dates.
5. **Data migration** `oiod_0001_backfill` (no DDL on existing tables; one log table
   `projects.oi_delivery_date_backfill(row_id, old_delivery_date, old_previous_delivery_date)`):
   up = log, then update (AC-C3); down = restore from the log, drop the table. Chained onto main's
   head at build time (`./scripts/alembic-reparent.sh`).
6. **Frontend**: `DeliveryDateCell` (`orderInquiryWorklistColumns.tsx:819`) adds `BoardChangeTable`
   with an annotation built from `previous_delivery_date` (the Was) and `delivery_date` (Now),
   `kind` `delayed` / `advanced`; the Qty (i) dialog already reads the same two fields. Split view
   marks a part with no AutoCount line "planned". The upload dialog drops the "Dates corrected" tile.

## Tests (tester first, red)

Backend (pytest, Postgres, seeded chain: core SO + line, mirror, OI + rows):
- resolver: core first, mirror fallback, told-date fallback, 2030-01-01 printed as is, Was rule.
- worklist: value, server sort, month filter, from / to filter use the SO line date (AC-A1 to A3).
- reserve: dialog rows + merged email context carry the SO line date (AC-A4).
- handover: `handover_item`, resend preview and the Excel cells read the same date (AC-A5).
- pending change: SO date moved, no confirm: OI reads new date, Was = told (AC-B1); confirm still
  emails DELAY (AC-B2).
- sheet import writes the line date and keeps the sheet date as Was (AC-C1).
- migration up / down on seeded rows (AC-C3, C4); several rows on one line (AC-C5).
- stock debt snapshot freezes the SO line date (AC-A7).
Frontend (vitest): `DeliveryDateCell` shows the `BoardChangeTable` icon only with a Was; the lightbox
Was / Now Date row (AC-E1 to E3).

## Steps

1. UAC + plan (this file). 2. Red tests. 3. Resolver. 4. Reader swaps. 5. Sheet import. 6. Migration.
7. Frontend. 8. Reviewer + browser pass. 9. Hand-test script, crew-migration if needed.
