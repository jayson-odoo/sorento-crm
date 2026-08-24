# PLAN - Packing list container-number matching

Status: Done

## Problem

The external packing-list API (n8n → `POST /api/v1/external/packing-lists/`)
creates inbound shipments. Re-sends were matched only by `shipment_number` then
by the linked `attachment_id`. When n8n re-sends a packing list for a shipment
that has no shipment_number yet (or a newly-assigned one) it created a duplicate
inbound shipment even though the same physical container was already in transit.

Container number is the shipment's **secondary identifier**: a container carries
exactly one *not fully received* inbound shipment at a time. Once that shipment
is fully received the container is free to carry a new one.

Separately, the attachment-directories detail modal showed the raw shipment UUID
for a linked packing list whenever `shipment_number` was null - both in the
Linkages table and the Integration tab.

## Changes

### Backend

- `InboundShipmentService.create_shipment` (`app/services/procurement_service.py`):
  insert a container-number match step between the `shipment_number` and
  `attachment_id` matches. It is scoped to shipments whose status is **not**
  `fully_received`/`completed`, so a received shipment's container can be reused.
  On match it follows the existing update-in-place path, which already rewrites
  the header (including `attachment_id` from the n8n payload) and replaces lines.
- `ResourcesService` linked-packing-list builder (`app/services/resources_service.py`):
  both queries now select `shipping_container_number` and fall back to it
  (never the raw UUID) when `shipment_number` is null. This feeds the modal
  Linkages table and the Integration tab (via `upload_activity.py`'s `name`).

### Frontend

- `AttachmentDetailModal.tsx` packing-list picker: selected-label and option
  labels fall back to `shipping_container_number` before the id.

## Tests

- `tests/test_packing_list_container_match.py`:
  - container match updates a not-fully-received shipment in place (attachment
    replaced, lines replaced, shipment_number filled in);
  - a fully-received shipment's container does **not** match → new shipment;
  - `shipment_number` still takes precedence over container.
