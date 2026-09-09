# PLAN: warehouse as a chatbot entity, and "last in" as the last SPO line per product

Status: IMPLEMENTED, AC-10 verified in the browser 8 Sep 2026 (branch feat/chatbot-warehouse-entity-last-in).
Owner rulings the same day, verbatim: "it is actually the
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
   - No `receipt_status` filter. GR never decides WHICH line answers.
   - Ordering key per line (`spo_date`): `expected_date`, falling back to `issue_date`,
     then `created_at::date` for the 3% with neither. `spo_date_source` names which:
     "expected" / "issued" / "recorded". The shipment arrival columns are no longer read
     here (they belong to the incoming domain).
   - ONE row per product **when `product_ids` is given**: for each named product, the top
     `top_n` lines by that key, newest first. `top_n` therefore means "lines per product",
     default 1. Rows are grouped product by product, products in `product_code` order.
   - With NO `product_ids` the call is UNSCOPED and `top_n` is instead a plain cap over
     the same ordering across every product (follow-up ruling, 8 Sep 2026). One row per
     product across the whole table would be thousands of rows, and the tool is reachable
     directly by the AI assistant rather than only behind a resolved product, so an
     unscoped call costs exactly `top_n` rows.
   - `warehouse_ids` filters lines to those warehouses before the per-product pick.
   - Ties on the same date: `created_at DESC` stays as the deterministic tiebreak, stated
     in the docstring as a tiebreak and nothing more.
   - A RETIRED line never answers (#753, merged 8 Sep 2026): both branches apply
     `spo_supply.visible_line_clauses()` before the window, so the line this tool calls
     "the last SPO line" is one the SPO document itself still shows. The shared predicate
     is reused rather than restated as `retired_at IS NULL`, which would be stricter than
     every other listing and would hide a retired line carrying a receipt - #753 keeps
     that one visible on purpose (R2: stock physically arrived against it, and this is the
     one question that is about receipts).
5. Presenter `_spo_last_receipt` and its intro line ("Here is the last receipt I found.")
   are reworded for the new meaning: intro "Here is the last SPO line per product."

### The rendered row (owner ruling, 8 Sep 2026, against the screenshot)

GR never decides which line answers, but it IS reported on the line that did - so the
row reads, in this order and no other:

    SPO Number, Product Code, SPO Quantity, GR Quantity (if any), SPO Date,
    GR Date (if any), Warehouse

Amended 9 Sep 2026 (`PLAN-chatbot-last-in-container-number.md`): `Container Number (if
any)` sits directly after `SPO Number`.

- SPO Number stays first: it is the identity line, the same string the item title carries.
  The owner's list starts after it.
- `spo_quantity` = `allocated_quantity`. `gr_quantity` = `quantity_received`, **None when
  zero**: the column defaults to 0 and is never null, and the zero rows are exactly the
  open lines this rework exists to surface, so a non-null test would print
  "GR Quantity: 0" on every one of them.
- `SPO Date` is labelled `SPO Date (recorded)` when `spo_date_source` is `"recorded"`, so
  the 3% that fell back to `created_at` stay honest.
- `gr_date` is `picking_headers.picking_date` reached through
  `picking_lines.spo_allocation_id`, `picking_status = 'approved'` only. Measured on the
  0907 copy: 987 of 987 approved headers carry a `picking_date`; 2,043 allocations have
  approved GRN lines and NONE has more than one approved header, so `max(picking_date)`
  per allocation is the whole rule - taken as ONE grouped join, never a per-row lookup,
  and company-scoped by hand on both picking tables for the same `.subquery()` reason as
  the allocation predicate. 74,300 allocations carry `quantity_received > 0` with no
  approved GRN row (the ESB-stated path): they show a GR quantity and no GR date, which
  is what "if any" means.
- Service keys renamed to match: `spo_quantity`, `gr_quantity`, `spo_date`,
  `spo_date_source`, `gr_date`. `quantity`, `quantity_received`, `date` and `date_label`
  are gone. Grepped before renaming: no chatbot renderer reads this tool's row keys -
  `fetch.IDENTITY_KEYS` projection is gated on `result_type == "incoming_stock"` (or a
  `field_vocabulary`, which only the incoming envelope carries) and this tool's
  `result_type` is `spo_last_receipt`. The `Company` line was dropped from the presenter
  with them: the service has never emitted `company_name`, so it has never rendered.
- The catalogue `ToolSpec` description, the `/last-receipt` route docstring and
  `mcp_tool_capability_service`'s intent line all name the six fields in this order and
  the GR Date source. `restricted_fields`, `related_tools`, `domain` on the spec are
  unchanged.

### Resolver: the warehouse AND probe is all or nothing

Added 8 Sep 2026, after the AC-10 browser run measured the defect this section fixes.

**The defect.** "last in for SRT62-GM to brw" parsed
`[{raw: "SRT62-GM", hint: product}, {raw: "brw", hint: warehouse}]`, and the fetch args
came back with `warehouse_ids: [<BRW uuid>]` and NO `product_ids` - the gate's
`compatible_entities` held only the warehouse. Same on "stock for SRT62-GM in brw ib" and
"last in for srtwc286 to brw ib". Without a warehouse token in the message everything
resolved.

**The cause, in two layers.** `resolve_gate.resolve_entity_body` sends `match_mode: "and"`
with every entity's token and every entity's hint, and
`entity_resolver._build_token_type_map` has been a deprecated no-op since positional
pairing was removed, so in `resolve_references_intersection` every AND probe receives
EVERY token. `_and_probe_product` therefore returns nothing the moment one token ("brw")
has no `product_code` hit. That has always been true, and it has always been harmless,
because a zero intersection makes `_resolve_input` degrade the whole call to OR-mode under
the caller's whitelist ("AND-mode produced zero intersection; switched to OR-mode under the
whitelist so per-token fallback can apply only to unresolved tokens"), and the OR pass
resolves each token separately. **Item 3 of this plan broke that.** Making
`_and_probe_warehouse` exact-code PER TOKEN meant it answered "brw" with BRW even beside a
product code, the intersection came back non-empty with the warehouse alone, the degrade
never ran, and the product was lost.

**The rule.** `_and_probe_warehouse` is ALL OR NOTHING across its tokens, like every other
AND probe: it answers only when EVERY token is itself a warehouse code. Exact-code
resolution per token (item 3) is unchanged for a single-token call and for a call whose
tokens are all warehouse codes; what is restored is the AND contract, "rows matching EVERY
token". A product beside a warehouse then produces a zero intersection, the existing
degrade fires, and both resolve.

**Why not one resolver call per hint group.** The obvious alternative - have the chatbot
lane issue one AND call per hint group and merge the responses, which is what the
resolver's own docstring tells callers who need 1:1 pairing to do - was measured against
the local prod copy `sorento_ai_automation_0907` before being rejected:

- 166 of the last 1760 turns are multi-hint AND. **161 of them already ride the OR
  degrade**, and only 5 do not: exactly the `(product, warehouse)` turns this section is
  about. So the per-hint-group split would change 161 turns to fix 5.
- Replaying each of the 166 as per-hint-group calls, **76 come back with a MIXED response
  shape** (one group AND-shaped with an `intersection`, another OR-shaped with
  `resolutions`), 70 of them in `product_attachment`. `gate.py`'s REQUIRE_SPECIFIC block
  prefers `resolutions` when both are present, so on those turns `exact_entities` would be
  built from the OR group alone and `compatible_entities = exact_entities` would DROP the
  product - reintroducing the exact bug the B1 attachment-subject-gate exists to catch.
- A further 71 turns that are OR-shaped today (`customer` + `product`, 64 of them) would
  become AND-shaped and lose the per-token `resolutions` the did-you-mean and
  customer-picker lanes read.
- The all-or-nothing probe touches one function, changes 5 turns, and leaves the vendored
  and full-corpus replay corpora byte-identical.

The trigger for revisiting this: a hint pair where BOTH types have a per-token AND probe,
so the intersection is non-empty and wrong rather than empty. `warehouse` is the only such
probe today; the day a second one lands, the degrade stops being a sufficient answer and
the per-hint-group split (with a merge that keeps ONE response shape) is the next design.

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

### Review round (8 Sep 2026)

- `spo_last_receipt_service`'s per-product branch ANDs the company predicate in by hand.
  `.subquery()` loses the session listener's `with_loader_criteria` and the outer query
  names only `Product` / `Warehouse`, so nothing else scoped the LINES: under a Mocha scope
  it returned a Sorento-owned line on a Mocha product. Precedent and reason:
  `order_service._order_summary`.
- `answer._SCOPE_WORD` gains `"spo_allocation": "SPO line"`, and the scoping ask offers a
  date range only for a domain whose own tool takes one - derived from
  `DOMAIN_SPEC[domain].tools` and `fetch.DATE_PARAMS`, the two declarations that already
  answer the question, rather than a third list.
- `DOMAIN_BLOCKED_HINTS["resource_attachment"]` gains `"warehouse"`, beside `brand` and
  `category` and for the same reason plus one: `warehouse_ids` is a `NARROWING_PARAM`, so a
  warehouse token also SATISFIES `ENTITY_FILTER_REQUIRED_TOOLS` for
  `crm_resource_attachments_list`, a tool with no warehouse parameter. Warehouse codes read
  like ordinary words (HOLD, DISPLAY, REPAIR).
- `tests/chatbot/divergences.py` registers the matrix-echo divergence the new `ALLOWED`
  rows create. `gate_debug.allowed_lookup` is the gate's read-only echo of `ALLOWED`, so
  every capture taken before this plan lists one type fewer; the entry is FIELD-scoped to
  that one key across the five places the exit item spreads it, and everything else about
  those 135 vendored captures is still graded. Measured: with the `inventory` row reverted
  all 135 pass, so the echo is the only thing the matrix change moves.
