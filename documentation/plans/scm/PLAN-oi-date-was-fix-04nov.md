# PLAN: OI date change, restore pending DELAY/ADVANCE emails + Was column in OI export

Status: in progress (small fix track: data migration with no DDL on a live table + one export column; no auth/RBAC change)

Lane: OI-DATE-WAS-FIX. Follows OI-ONE-DELIVERY-DATE (#2145, `PLAN-oi-one-delivery-date-03nov.md`).

## Owner rule

The OI date follows the SO line date. When AutoCount moves an SO line date earlier or later,
purchasing is told through the OI with Was (old) and Now (new), in the email AND the Excel.

## Gap A: backfill swallowed pending DELAY/ADVANCE emails

`alembic/versions/oiod_0001_backfill.py` moved `delivery_date` to the SO line date on every
live row that differed, including rows whose SO line has a `delayed`/`advanced` planning change
still waiting for CS Confirm. At Confirm every path then sees no move:

- `_stamp_date_move` filters `row.delivery_date != new_date` (`project_order_inquiry_service.py`).
- `handover_moves(previous_qty, previous_date, need, required_date)` compares the row's date.
- `planning_change_service.py` suppresses the notice when a buy row already carries `to_date`.

So purchasing got no DELAY/ADVANCE email for those lines.

Fix: data migration `oiod_0002_pending_restore`. For rows logged in
`projects.oi_delivery_date_backfill` whose SO line has a PENDING `delayed`/`advanced` planning
change, set `delivery_date` back to the logged `old_delivery_date` and `previous_delivery_date`
back to the logged `old_previous_delivery_date`. Every changed row is logged first in
`projects.oi_delivery_date_pending_restore` so the downgrade reverses exactly. No email at
migration time; the next Confirm emails as normal.

## Gap B: Was column in the OI Excel exports

Both the OI list-page export (`order_inquiry_worklist_service.py` `EXPORT_HEADINGS`/`_records`)
and the per-project download print only DELIVERY DATE. Add `WAS DELIVERY DATE` as the LAST
column, from `previous_delivery_date`, blank when the row has no move. Same shared exporter,
dd/mm/yyyy.

## Tests (red first)

- Migration: pending delayed row restored + logged; row without pending change untouched;
  row not in the backfill log untouched; downgrade reverses.
- Export: last heading is `WAS DELIVERY DATE`; moved row shows dd/mm/yyyy Was; unmoved row blank.
