# PLAN: supplier as a bot entity + open POs / outstanding by supplier (SUPPLIER-ASK)

Status: in progress (small fix track, owner-given design; red-first, kill test, reviewer)

## Journey
Staff asks the Chatbot Console "the outstanding for <supplier>" (any language, typos) or "POs for
<supplier>" and gets the open purchase orders not yet received (outstanding PO qty) for that
supplier. Dealers never see suppliers.

## Design (owner, 1 Nov 2026)
1. `supplier` becomes an entity kind (contracts ENTITY_HINTS, seeded kind row, parser kind list),
   resolved through the existing shared resolver probe (`_probe_supplier`), semantic, no word lists.
2. The purchase_order domain accepts the supplier kind (gate + fetch kind->filter map) and the
   PO placed endpoint / service / MCP tool gain a `supplier_id` filter.
3. "outstanding for supplier X" lands on the PO placed list filtered by supplier (open, not yet
   received), staff-only, same permission gates as today.

## Tests (red first on main)
- owner's exact message, an English supplier name, a supplier code, a typo.
- PO placed service/endpoint filter by supplier_id.

## UAC
See `supplier-ask-acceptance-criteria.md`.
