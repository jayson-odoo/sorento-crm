# PLAN: packing list status recompute on input change (PACKING-LIST-RECALC)

Status: #2215 merged; follow-up #2218 in review (small fix track: about 300 lines, no migration, no RBAC)

## Problem
Prod (YMMU7738143): an SPO had no container number. The ref was fixed in AutoCount; the next
shipping-order push saved the container on the SPO and linked its allocations to the packing
list, but the packing list's stored line status and header status stayed stale until somebody
opened the packing list page, because `GET /procurement/packing-lists/{id}` was what recomputed
(`refresh_shipment_line_statuses`, and it committed inside the read).

Root cause: `ShippingOrderIngestService._write_row` links the container
(`shipping_order_rules.link_allocation_to_shipment`) but only the xlsx-supersede path records
the shipment in `shipment_ids_touched`, so the route's post-commit refresh hook had nothing to
refresh. One forgotten writer among about fifteen that each had to remember to call the refresh.

## Design
- One recompute, unchanged: `InboundShipmentService.refresh_shipment_line_statuses`
  (idempotent). It now writes an audit EVENT `packing_list.status_recalculated` (old/new header
  status, `reason` = trigger) when the header status moves.
- `app/services/scm/packing_list_recalc.py`: a Session listener. After flush it notes the
  containers whose inputs changed: `SPOAllocation` rows (insert, delete, or a change to a column
  the recompute reads; the old AND new `inbound_shipment_id`), `PickingLine` and `PickingHeader`
  (GRN) rows resolved to containers through their allocation and SPO number. After commit it
  queues one RQ job per container on the new fast queue `scm_recalc`, job id
  `pl-recalc-<shipment id>` (a write landing while it runs uses `...-rerun`), skipped while a
  job for that container is still waiting (burst de-dupe). Only the outermost commit
  dispatches; a savepoint release folds its notes into the parent level. Redis
  unreachable: recompute inline on a fresh session. A root rollback forgets the noted set.
- The packing list GET reads only. If the stored figures would change
  (`stored_figures_stale`), it queues the recompute instead of writing.
- Safety net: the relink + open-container sweep runs hourly instead of daily.
- Status may go back from Fully Received (existing `rollup_shipment_status` rule, unchanged).

No registry or config: one listener because the inputs have many writers today (evidence above).

## UAC
See `packing-list-recalc-acceptance-criteria.md`.

## Follow-up (#2218, after crew's adversarial review of #2215)
- Hand-run scripts (`scripts/*.py`) open `app.database.SessionLocal` without importing
  `app.main` / `worker.py`, so they never registered the listener. It is now registered at
  the bottom of `app/database.py`, where the session factory is built.
- The hourly sweep visits open containers PLUS every container whose inputs were written
  since the previous sweep (`changed_shipment_ids`; watermark in Redis key
  `pl-recalc:sweep-watermark`, 24h when absent, 10 min overlap). `spo_allocations`,
  `inbound_shipment_lines` and `picking_lines` gained an ORM-side `onupdate=func.now()` on
  `updated_at` (no DDL), which nothing stamped before. Raw-SQL `UPDATE`s in
  `scripts/fix_product_duplicates.py` and `scripts/dedupe_spo_number_format.py` now stamp
  `updated_at` (`stamp_sql`). Limit: a raw DELETE leaves no row to stamp; such a writer calls
  `packing_list_recalc.mark_stale`. `scripts/oneoff/dedupe_spo_standalone.py` (raw SQL
  throughout) already refreshes every shipment it touched itself at the end of its apply.
- The header's `shipment_status` / `company_id` are watched; the recompute's own write is
  excluded (`recomputing`), so it never queues itself.
