# PLAN: packing list status recompute on input change (PACKING-LIST-RECALC)

Status: built, in review (small fix track: no migration, no RBAC, no new ingest surface)

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
  `pl-recalc-<shipment id>`, skipped while that job is still waiting (burst de-dupe). Redis
  unreachable: recompute inline on a fresh session. A root rollback forgets the noted set.
- The packing list GET reads only. If the stored figures would change
  (`stored_figures_stale`), it queues the recompute instead of writing.
- Safety net: the relink + open-container sweep runs hourly instead of daily.
- Status may go back from Fully Received (existing `rollup_shipment_status` rule, unchanged).

No registry or config: one listener because the inputs have many writers today (evidence above).

## UAC
See `packing-list-recalc-acceptance-criteria.md`.
