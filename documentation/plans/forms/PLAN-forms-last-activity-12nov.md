# PLAN: Last activity column, sortable, on every form list (FORMS-LAST-ACTIVITY)

Status: Build (answers relayed 12 Nov; tests first). Track: M, lead pattern (tester -> coder ->
reviewer). Migration additive; backfill sized once crew's dev counts arrive.

Owner ask (12 Nov): a "Last activity" column on every form list so the records with the newest
activity sort to the top. Card: `forms-last-activity-behaviour-card.md`. UAC:
`forms-last-activity-acceptance-criteria.md`.

## Design (simplest thing that works)

One stored column per form table, `last_activity_at`, stamped where the History rows are already
written. No new log, no live aggregation over `audit_logs` on list loads.

1. Migration `fla_0001_last_activity_at` (id <= 32 chars): `ADD COLUMN IF NOT EXISTS
   last_activity_at timestamp NULL` + index on the 7 tables; backfill per table with one UPDATE
   from `max(audit_logs.changed_at)` over person actor rows rooted on the record, greatest with
   newest non-system form comment, coalesce `created_at`. Down drops index + column.
2. Stamp in `app/services/audit_service.py`: one helper `_stamp_last_activity(conn, rows)` called
   after every audit row insert path (after-flush rows `:970`, `log_audit` `:246`, bulk DML
   `_write_bulk_rows` `:1176`). It picks rows whose `actor_type` is a person (`user`, `contact`,
   `public_link`) and whose root (or entity) type is in a 7-entry map entity_type -> table, and
   runs one Core `UPDATE <table> SET last_activity_at = clock_timestamp() WHERE id IN (...)` per
   table. Core on the connection: no ORM flush, so no audit recursion. Best-effort like the rest
   of capture: wrapped in the same savepoint, never raises into the business write.
3. New record: the helper also stamps the form's OWN CREATE row whatever the actor (entity is the
   form itself, not a child line), so a system-created form starts at its create time (U2) while
   later system updates and system child rows still do not move it (U4).
4. Comments: `form_comment_service.add_staff_comment` (`:532`) and `add_contact_comment`
   (`:558`) stamp the form through the same helper's table map (not system messages).
5. Each list service adds `last_activity_at` to its sort map, `last_activity_from/to` filters,
   default sort desc with `created_at desc, id` tie-break; row schemas add the field.
   Sort maps: complaints `complaints_service.py:510-531`, PR/SF `procurement_service.py:9466-9490`,
   price tags `price_tag_request_service.py:2899-2910`, samples `sample_request_service.py:1272`,
   NPA `new_product_application_service.py:1402`, stock inquiry `procurement_service.py:5681-5704`,
   workflow `workflow_forms_service.py:629` + list-query resource `workflow_form_submissions`.
6. FE: each list adds the column (copy `StockInquiriesList.tsx:319-336` minus the "Revised"
   branch), default `SortingState` `[{id:'last_activity_at',desc:true}]`, a Last activity
   `DateRangePicker` in Filters (pattern `scm/sales-orders/components/SalesOrdersGrid.tsx:1124`),
   types + services pass the params via `buildDataGridParams`.

## Standing rules that apply

Server-side sort (holds on page 2); one line per row; Columns hide/show/reorder; filters combine;
filters/sort in the address bar (where the list already does this); dates via the shared
formatter, `dd/mm/yyyy, h:mm am/pm`; shared date picker; no internal ids; History unchanged;
375 + 1280 px.

## Assistant coverage

No new list route or record action: the existing list routes gain a sort key and two filters.
n/a for DoD 6-8 (registry entries for these lists, where present, gain nothing).

## Guide

Update each form list's user guide page under `documentation/user-guides/` with the Last
activity column, default order and filter.
