# PLAN: supplier as a bot entity + open POs / outstanding by supplier (SUPPLIER-ASK)

Status: in review (owner-given design, SIZE S; red-first, kill test, reviewer + security-reviewer). Carries two
data-only migrations (`sask_0001_supplier_kind`, `sask_0002_span_supplier`), so not the small fix track.

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

## As built

- PO placed: `supplier_ids` on `purchase_order_service` (rows, summary, unshipped SPO query), the
  `/procurement/purchase-orders/placed` route and the MCP tool `crm_procurement_po_placed_list`. Under a
  `contact_id` without the `purchase_orders.supplier` reveal the route answers 403 (security review).
- Kind: `contracts.ENTITY_HINTS` + `supplier`; `contracts.supplier_visible` = staff profile + the
  `purchase_orders.supplier` reveal; `chatbot_entity_kinds` row and `supplier: optional_filter` on the
  purchase_order domain's narrowing (migration `sask_0001_supplier_kind`), so several suppliers for one word
  ask "Which one do you mean?" through the existing roster (`turn/narrow.decide`), never an unfiltered list.
- Gate/fetch: `purchase_order` admits `supplier`; `supplier` -> `supplier_ids`, refused again in
  `fetch.entity_ids_transformer` without the reveal (the `RESTRICTED_SORT_KEYS` precedent).
- Resolve: supplier tokens and resolver rows are dropped for anyone `supplier_visible` refuses.
- Route: an order/sales verdict naming a supplier and no customer-side party becomes
  `purchase_order` / `check_po` (its `asks` too) right after the access check (`engine`, the dealer-cost
  swap's precedent), decided by the entity kind, never a word.
- Span pass: `lookup_lists._supplier_rows` (name + code) only for office staff holding the supplier reveal;
  `list_resolver.SPAN_TYPES` gains `supplier`. Floors borrowed from the customer list, not yet measured.
- Prompts, UNLABELLED (migration `sask_0002_span_supplier`): a span version (production text + the meaning
  paragraph it lacked + a supplier type line + a pinyin sentence for company names in Chinese characters) and a
  span-pass parser version (span marker kept, one supplier line after it) that records its span version
  (`config_json.span_prompt_version_id`). A console dry run pinning that parser runs that span prompt too
  (`engine._span_override`); a live turn never does.

## Owner steps to promote (after the chatbot eval)

1. Prompts page: move `production` on `chatbot_span_extractor` to the SUPPLIER-ASK version.
2. Prompts page: move `production` on `chatbot_semantic_parser` to the SUPPLIER-ASK version.

## Open

- Measure the supplier meaning floor (both embedders) on real supplier names; the sandbox's OpenAI
  route answered 429, so no live cosine was taken here.
