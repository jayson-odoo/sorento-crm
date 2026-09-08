# PLAN: warehouse as a chatbot entity, and "last in" as the last SPO line per product

Status: PLANNED (8 Sep 2026). Owner rulings the same day, verbatim: "it is actually the
bare code, so it should be exact match ... brw ib, brwib should map to brw-ib, but when we
say brw, it means brw, not the rest"; "last in should be per product, if we resolve to
entire family then return the latest receipt for each of the product"; "last in doesn't
relate to GR actually, it is purely last SPO ... based on the delivery date column at the
SPO"; "ignore GR entirely, i am okay with the gate allowed, yes expected date, yes one row
per product".
UAC: `chatbot-warehouse-entity-and-last-in-acceptance-criteria.md`.

## Measured (local prod copy `sorento_ai_automation_0907`, 8 Sep 2026)

- The parser already extracts a warehouse: console turn d2bce92f "last in for srtwc286 to
  brw" parsed `{raw: "brw", hint: "warehouse"}`. The resolver has a warehouse type
  (`entity_resolver.py`: `_probe_warehouse`, `_prefix_probe_warehouse`,
  `_and_probe_warehouse`). Both tools accept `warehouse_ids`
  (`crm_inventory_stock_balance_list`, `crm_procurement_spo_allocations_last_receipt_list`,
  and `last_receipt_rows(warehouse_ids=...)`).
- The entity is dropped in the middle: `gate.ALLOWED["inventory"]` is
  `[product, category, brand]` (warehouse filtered out), `spo_allocation` has no `ALLOWED`
  row (passes through unscoped, so the entity survives the gate), and
  `fetch.TYPE_TO_PARAM` has no `warehouse` key, so no `warehouse_ids` is ever sent. Result:
  "to brw" returned the identical answer.
- 19 warehouses start with `BRW` (`BRW`, `BRW-IB`, `BRW-IR`, `BRW-HP`, ... 5 inactive). A
  prefix match would fan "brw" out to all of them; the owner ruled exact code.
- "Last in" today (`spo_last_receipt_service.last_receipt_rows`): filter
  `receipt_status = 'fully_received'`, order `coalesce(inbound_shipments.warehouse_arrival_date,
  actual_arrival_date) DESC NULLS LAST, spo_allocations.created_at DESC`, `limit top_n`
  across ALL products. 74,432 of 76,340 fully-received lines (97.5%) have no shipment date,
  so a dated line always outranks a dateless one regardless of recency (SRTWC286-SH-UF:
  SPO-202608-0086 "Arrived 2026-08-18" beat three lines recorded 2026-08-27). Ties on the
  same date fall to the recorded timestamp, which is not a business order.
- `spo_allocations.expected_date` is the SPO line's promised delivery date (model comment:
  "the line's promised arrival"; rung 1 of the fulfilment ladder already compares against
  it). Filled on 74,825 of 77,260 lines (97%), same fill as `issue_date`. The 3% without
  either (e.g. SPO-2026/08-0101, SRT62-GM, recorded 2026-08-21, shipment arrival
  2026-08-26) are the same lines that carry a shipment date.

## Contract after this plan

### Warehouse entity

1. `gate.ALLOWED["inventory"]` gains `"warehouse"`. A new row
   `"spo_allocation": ["product", "warehouse", "category", "brand"]` replaces the
   unscoped pass-through (the owner accepted the gate matrix). `purchase_order` stays as is.
   This row carries no `ALLOWS_EMPTY` entry, so a bare "last in" with no product now fails
   the gate instead of passing through unscoped - with one-row-per-product semantics (item
   4 below), a bare "last in" with no product asks for one instead of fanning out.
2. `fetch.TYPE_TO_PARAM["warehouse"] = "warehouse_ids"`.
3. Warehouse resolution is EXACT CODE after normalisation: casefold and strip every
   non-alphanumeric character on both sides, so "brw ib", "brwib", "BRW-IB" all resolve to
   `BRW-IB` and nothing else; "brw" resolves to `BRW` only, never to `BRW-*`. No prefix or
   fuzzy fan-out for this type (the product-style `_prefix_probe_warehouse` /
   `_and_probe_warehouse` behaviour is not used for a warehouse token). A token that
   matches no warehouse code exactly is a miss, handled by the existing miss path (no new
   picker). Inactive warehouses still resolve (a customer may ask about stock that sits in
   one); the tool decides what to show.

### Last in

4. `last_receipt_rows` (and the `/last-receipt` route + MCP tool description) change
   meaning to "the last SPO line per product":
   - No `receipt_status` filter. GR is ignored entirely.
   - Ordering key per line: `expected_date`, falling back to `issue_date`, then
     `created_at::date` for the 3% with neither. `date_label` names which:
     "Expected" / "Issued" / "Recorded". The shipment arrival columns are no longer read
     here (they belong to the incoming domain).
   - ONE row per product: for each product in `product_ids` (or every product when none
     given), the top `top_n` lines by that key, newest first. `top_n` therefore means
     "lines per product", default 1. Rows are grouped product by product, products in
     `product_code` order.
   - `warehouse_ids` filters lines to those warehouses before the per-product pick.
   - Ties on the same date: `created_at DESC` stays as the deterministic tiebreak, stated
     in the docstring as a tiebreak and nothing more.
5. Presenter `_spo_last_receipt` and its intro line ("Here is the last receipt I found.")
   are reworded for the new meaning: intro "Here is the last SPO line per product." and the
   quantity field reads the ordered quantity (`quantity` on the allocation, not
   `quantity_received`); keep `quantity_received` as a second field only when it is
   non-null so a received line still says so. The catalogue `ToolSpec` description for the
   tool says the same. `restricted_fields`, `related_tools`, `domain` on the spec are
   unchanged.

Out of scope: any new picker, the `incoming` domain's warehouse handling, the parser
prompt, the AI assistant.

## Work

Backend + MCP presenter, one lane, test-first.

- `app/services/chatbot/lanes/business/gate.py` (`ALLOWED`), `lanes/business/fetch.py`
  (`TYPE_TO_PARAM`), `app/services/entity_resolver.py` (warehouse probes: exact
  normalised code), `app/services/spo_last_receipt_service.py`,
  `app/api/v1/procurement/spo_allocations.py` (docstring + query descriptions),
  `sorento_crm_mcp/sorento_crm_mcp/catalog.py` (tool description),
  `sorento_crm_mcp/sorento_crm_mcp/presenters.py` (`_spo_last_receipt`, intro).
- Tests: `tests/test_spo_last_receipt.py` rewritten for the new contract;
  `tests/chatbot/test_domain_spec.py` or a new `tests/chatbot/test_warehouse_entity.py`
  for the gate + transformer; resolver tests for the exact-code rule; MCP presenter test
  for the reworded render. See the UAC.
