# UAC: warehouse entity + last SPO line per product

Plan: `PLAN-chatbot-warehouse-entity-and-last-in.md`. Pytest unless marked browser. Every
pytest seeds its own chain (CI's DB is empty): products, warehouses, spo_allocations with
the dates named.

- AC-1 Gate. With `domain = inventory` and entities `[product, warehouse]`, the gate's
  `compatible_entities` keeps both. With `domain = spo_allocation`, `ALLOWED` now has a row
  and `compatible_entities` keeps `product` + `warehouse` and drops e.g. `customer`.
- AC-2 Transformer. `entity_ids_transformer` (fetch) emits `warehouse_ids=[<uuid>]` for a
  resolved warehouse entity, alongside `product_ids`.
- AC-3 Exact warehouse code. Seed warehouses `BRW`, `BRW-IB`, `BRW-IR`. Resolving the
  tokens "brw", "BRW", "brw ib", "brwib", "brw-ib", "Brw_IB" yields exactly one match each:
  `BRW` for the first two, `BRW-IB` for the rest. "brw" never returns `BRW-IB` or `BRW-IR`.
  "brw xx" (no such code) is a miss.
- AC-4 Last SPO line, GR ignored. Seed product P with three spo_allocations: A
  (`expected_date` 2026-02-22, `receipt_status` fully_received), B (`expected_date`
  2026-08-30, `receipt_status` pending, not received), C (no `expected_date`, no
  `issue_date`, `created_at` 2026-08-21, fully_received, with an inbound shipment arrival
  2026-08-26). `last_receipt_rows(product_ids=[P])` returns B first with
  `date = 2026-08-30`, `date_label = "Expected"`; with `top_n = 3` the order is B, C
  (`date = 2026-08-21`, `date_label = "Recorded"`), A. The shipment arrival is never used
  as the key.
- AC-5 Issue-date fallback. A line with `expected_date` NULL and `issue_date` set uses
  `issue_date` with `date_label = "Issued"`.
- AC-6 One row per product. Products P1 and P2 each with two lines; `product_ids=[P1, P2]`,
  `top_n = 1` returns exactly two rows, one per product, each product's newest line, grouped
  by `product_code` order. `top_n = 2` returns four rows, two per product, newest first
  within each.
- AC-6b Unscoped call is bounded. Three products, one line each, no `product_ids`,
  `top_n = 2` returns exactly 2 rows, the two newest lines by the same key regardless of
  which product they belong to - never one row per product across the whole table.
- AC-7 Warehouse filter. Lines of P in `BRW` and `BRW-IB`; `warehouse_ids=[BRW-IB]` returns
  only the BRW-IB line even when the BRW line is newer.
- AC-8 Route. `GET /api/v1/procurement/spo-allocations/last-receipt?product_ids=..&warehouse_ids=..&top_n=..`
  returns the same rows through the API, `data[0].date_label` present, `empty` false.
- AC-9 Presenter (MCP). `_spo_last_receipt` renders the intro "Here is the last SPO line
  per product." and a "Quantity" field from `quantity`; a row with `quantity_received`
  also shows "Quantity Received". `date_label` is still the date field's label.
- AC-10 Browser (tester, agent-browser via sidebar, stack :3080/:8080 over
  `sorento_ai_automation_0907`). Chatbot Console, contact Jayson:
  - "last in for SRT62-GM to brw" answers one row for SRT62-GM whose warehouse is `BRW`
    (not `BRW-IB` / `BRW-IR`), dated by the SPO's expected date.
  - "stock for SRT62-GM in brw ib" answers stock at `BRW-IB` only.
  - "last in for srtwc286" answers one row per SRTWC286 family member (several products,
    one line each), not a single row.
  Trace check by SQL on `chatbot.turns.trace`: the fetch args carry `warehouse_ids` on the
  two warehouse asks.
