# PLAN - Packing list region (West / East Malaysia)

Status: planned, awaiting owner answers on CARD-region-packing-list-2oct.md + mock v1. Track: L / standard
(migration, contact access). Lane REGION-PACKING-LIST, branch `crew/region-packing-list`, one PR.
UAC: `region-packing-list-acceptance-criteria.md`. Paths under `sorento_crm_backend/app/` unless shown.

## Schema (one additive Alembic revision)
- `inbound_shipments.region` varchar(8) NOT NULL server_default 'west', CHECK in ('west','east'). Backfill = default.
- `respond_contacts.regions` text[] NOT NULL server_default '{west}', CHECK non-empty and subset of {west,east}.
- `attachments.region` varchar(8) NULL (set only for a Packing List upload; read by external create).

## Backend
1. Models + schemas: `InboundShipment.region` (`models/procurement.py:128`), `InboundShipmentBase/Update` + responses
   (`schemas/procurement.py:351-465`), `PackingListHeader.region` optional (`schemas/external/procurement.py:19`),
   `RespondContact.regions` (`models/access.py:278` area), `Attachment.region`.
2. Writes: external create (`api/v1/external/packing_lists.py:112`) region = payload or attachment or west;
   staff list filter `region` (`api/v1/procurement/packing_lists.py:224`); attachment create form field `region`
   (`api/v1/resources/attachments.py:730`); proforma convert keeps the default.
3. Contact: `ContactChatbotUpdate.regions` (`api/v1/user_management/contacts.py:279`), returned by
   `contact_service.py:688` and `RespondContactResponse` (`schemas/user.py:70`).
4. Read rule: `ContactEtaRules.regions` (`services/eta_policy.py:50`), read in `rules_for_contact`; `UNRESOLVED` = west.
   `visible_regions(rules)` = {west,east} if east held else {west}.
5. Filter in SQL: `IncomingStockService(db, regions=None)`; `_region_filter(regions)` ANDed beside every
   `_not_draft_shipment_filter()` (`services/incoming_stock_service.py:204,448,570,625,790,931,1044`);
   `earliest_packing_list_shipment(db, ids, regions=None)`. Routes (`api/v1/incoming_stock.py`) build the
   service with `_Contact.regions` (None when no contact). Stock ask passes `contact_rules` regions
   (`services/inventory_service.py:1629`).
6. ACCESS-MODEL: `effective_access()` can read `respond_contacts.regions` as a contact fact; no tree change.

## Frontend
- `AttachmentUploadDialog.tsx`: Region SearchableSelect when the selected type code is `packing_list`; sends `region`.
- `PackingListsList.tsx`: Region column (Badge) + filter; `PackingListForm.tsx` + `PackingListDetailsTab.tsx`: Region field;
  `packingList.types.ts` + `packingListService.ts`.
- `ContactChatbotSection.tsx` + `contactChatbotService.ts`: Regions SearchableMultiSelect, at least one.

## Tests (red first, `test(red):` commit alone)
- `tests/test_packing_list_region.py`: AC-RPL-1,3,4,5,6 (defaults, external precedence, 422, filter).
- `tests/test_incoming_region_filter.py`: AC-RPL-9..13,15 over the five routes + stock ask, totals/paging.
- `tests/test_contact_regions.py`: AC-RPL-7,8 incl. response_model field assertion.
- vitest: upload dialog region (shown only for Packing List, sent), contact Regions save, list column.

## Migration check + hand test
Idempotent SQL at `crew/state/migrations/REGION-PACKING-LIST.sql`; applied and counted on a private clone of the dev
copy before the hand test. Security review (contact data scoping) + reviewer + browser 1280/375.
