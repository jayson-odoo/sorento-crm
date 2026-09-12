# UAC: "last purchase cost" per product per location, gated per contact

Plan: `PLAN-chatbot-last-purchase-cost.md`.

## Service and route

- AC-1 Latest line per location. Product P with lines at warehouse W1 (issue dates 1 Aug,
  1 Sep) and W2 (15 Aug): `last_cost_rows(db, product_ids=[P])` returns exactly two rows,
  W1's from the 1 Sep PO and W2's from the 15 Aug PO.
- AC-2 No-warehouse bucket. A cost line with `warehouse_id` NULL answers its own row with
  `row["warehouse"] is None`; it never displaces a warehouse row and no warehouse row
  displaces it.
- AC-3 Cancelled excluded. A newer line with `line_status = 'cancelled'`, and a newer line
  on a PO with `status = 'cancelled'`, are both skipped; the answer is the newest non
  cancelled line.
- AC-4 No cost, no answer. A line with `unit_cost` NULL is never picked, even when it is
  the newest.
- AC-5 Ordering. Two lines on the same `(product, warehouse)`: the one whose PO
  `issue_date` is later answers; on the same date the later `created_at` answers.
- AC-6 Per-unit discount. qty 19, unit_cost 110.00, discount 1254.00, line_total 836.00
  answers `unit_cost == 110.0`, `discount_per_unit == 66.0`,
  `unit_cost_after_discount == 44.0`.
- AC-7 Discount absent. discount 0 or NULL answers `discount_per_unit is None` and
  `unit_cost_after_discount == unit_cost`.
- AC-8 No line_total. `line_total` NULL answers `unit_cost_after_discount == unit_cost`
  and `discount_per_unit is None`.
- AC-9 Currency. `row["currency"]` is the line's `currency`.
- AC-10 Warehouse filter narrows before the pick. `warehouse_ids=[W2]` on AC-1's data
  returns only the W2 row.
- AC-11 Family, all members. Three products named in `product_ids` with `top_n=1` return
  three rows (one per member per location); `top_n=2` returns up to two per
  `(product, warehouse)`, never two overall.
- AC-12 Unscoped cap. No `product_ids`, `top_n=2` returns exactly two rows, newest first,
  across every product.
- AC-13 Company scope. Under a session scoped to company A, a cost line owned by company B
  on the same product never answers, on both branches.
- AC-14 Route. `GET /api/v1/procurement/purchase-orders/last-cost?product_ids=P` returns
  `{data, pagination, empty}` with the AC-1 rows; `top_n=0` and `top_n=51` are 422; the
  route is reachable with `X-API-Key`.

## Permission

- AC-15 Key exists. `GET field-reveal-keys` lists `purchase_orders.cost` with label
  "Last purchase cost"; the Contacts > Access > Field reveals card shows it unticked for a
  contact with no row.
- AC-16 Default hidden, whole domain. A contact WITHOUT the key asking "last purchase cost
  for M218" gets the `access_denied` canned reply for the purchasing team; no MCP tool is
  called; the trace carries `{"skipped": "not_granted", "needs": "purchase_orders.cost"}`.
- AC-17 Granted. The same contact WITH the key gets the answer; the reply contains
  "Cost / unit" and "Cost after discount / unit" and no UUID.
- AC-18 Belt and braces. `output_structurer` with a granted set lacking
  `purchase_orders.cost` drops `unit_cost`, `discount_per_unit` and
  `unit_cost_after_discount` from the envelope; with it, keeps them.
- AC-19 Catalogue pin. `FIELD_REVEAL_KEYS` equals the union of every
  `ToolSpec.restricted_fields` pair (existing test stays green with the new pair).

## Presenter and catalogue

- AC-20 Order. For a row carrying every field, `_po_last_cost` renders EXACTLY, in this
  order: `PO Number`, `Product Code`, `PO Quantity`, `PO Date`, `Cost / unit`,
  `Discount / unit`, `Cost after discount / unit`, `Warehouse`. Asserted as an exact list.
- AC-21 If any. A row with `discount_per_unit` None renders no `Discount / unit` line; a
  row with `warehouse` None renders no `Warehouse` line; nothing renders with an empty
  value.
- AC-22 Money format. `Cost / unit` renders `CNY 110.00`; `Discount / unit` renders
  `CNY 66.00`; `Cost after discount / unit` renders `CNY 44.00`.
- AC-23 Restricted keys. The envelope's `restricted_fields` maps `unit_cost`,
  `discount_per_unit` and `unit_cost_after_discount` to `purchase_orders.cost`.
- AC-24 Catalogue description names the row order, says the three money figures are per
  unit and derived from the line amount, and says the answer is restricted to a contact
  holding `purchase_orders.cost`.

## Chatbot routing

- AC-25 Parser. Under the new prompt version, "last purchase cost for M218", "what did we
  pay for M218", "上次采购价 M218", "harga belian terakhir M218" emit
  `domain_hint purchase_cost` / `intent_hint check_po_cost`; "how much do we sell M218
  for" does not.
- AC-26 Domain table. `test_domain_spec.py` is green: `purchase_cost` has one intent, one
  tool, unique switch words, and `CHATBOT_READ_ONLY_TOOLS` includes
  `crm_procurement_po_last_cost_list`.
- AC-27 Gate. A `purchase_cost` ask with a product resolves and calls the tool with
  `product_ids`; with a warehouse named, `warehouse_ids` is passed too; with no entity, the
  gate asks for a product (no `ALLOWS_EMPTY` row).
- AC-28 top_n passthrough. "last 3 purchase cost for M218" passes `top_n=3` directly (tool
  is in `TOP_N_DIRECT_TOOLS`), not `limit`.
- AC-29 Prompt publish. Migration 513 adds one new unlabelled version per body, is
  idempotent on re-run, and moves no label.

## Last-in family (pin, D5)

- AC-30 `last_receipt_rows(db, product_ids=[A, B, C], top_n=1)` returns one row per member
  (three rows); `top_n=2` returns up to two per member, never two overall.

## Live (agent-browser / console, per `documentation/agents/chatbot-verification.md`)

- AC-31 Lane backend + MCP up on the prod copy: the MCP tool called for M218 renders
  `PO Number: PO-2026/09-0013`, `Cost / unit: CNY 110.00`, `Discount / unit: CNY 66.00`,
  `Cost after discount / unit: CNY 44.00`, `Warehouse: BRW-SMC`.
- AC-32 Console case: default contact -> access denied; granted contact -> the AC-31 answer;
  SRTWC8517 -> one row per family member per location.
