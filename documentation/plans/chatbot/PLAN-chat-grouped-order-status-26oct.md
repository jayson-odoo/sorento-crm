# PLAN: CHAT-GROUPED-ORDER-STATUS - grouped delivery-order list crashed the chat turn

Status: in progress, fix committed, PR next (small fix track, crew lane CHAT-GROUPED-ORDER-STATUS, branch
`crew/chat-grouped-order-status`). No migration, no auth/RBAC change, no prompt change.

UAC: `chat-grouped-order-status-26oct-acceptance-criteria.md` (this folder).

## Bug

Prod turn 9465ad23 (26 Oct 2026 10:00 MYT, prod sha 0accc5caa9, still on main caa4e7be68): a
delivery-order check grouped by customer failed at the "Looked up" step with
`TypeError: unhashable type: 'dict'`; the contact read the generic "Sorry, I ran into a problem".

## Diagnosis (verified against the code)

1. `GET /order-management/orders` with `group_by` builds `groups` from the jsonable DO rows
   (`sorento_crm_backend/app/api/v1/order_management/orders.py:631-643`, SO-outstanding leg
   `:561-562`), so every group row carries the raw `order_status` object
   `{"id", "status_code", "status_name"}` and every UUID the flat rows carry.
2. The MCP sanitizer slims ONLY the top-level `data` rows:
   `sorento_crm_mcp/sorento_crm_mcp/server.py:865-874` `_slim_orders_list_response`
   (`_slim_orders_list_row` at `:813` turns `order_status` into its name). `groups[i].rows` pass
   through untouched. Same top-level-only walk in `_strip_row_company_ids` (`server.py:1335-1358`),
   so group rows also keep `company_id`.
3. The presenter renders each group's rows through the same row builder
   (`sorento_crm_mcp/sorento_crm_mcp/presenters.py:2124-2141`, DO row builder `:456`
   `("order_status", "Status", o.get("order_status"))`), so a grouped answer's Status field value
   is the dict.
4. The business lane takes the grouped items as the answer rows
   (`sorento_crm_backend/app/services/chatbot/lanes/business/fetch.py:4115-4121` `answers`,
   `_rendered_answers` at `:1746`), `turn_runtime.py:6087-6088` turns them into figures,
   and compose dedupes them with a set keyed by `_row_key`
   (`sorento_crm_backend/app/services/chatbot/turn/compose.py:148-149`, set membership at `:593`):
   a tuple holding a dict is unhashable.

Earlier occurrence (turn ad7eb847, 15 Oct, "SEP 2026"): UNVERIFIED. Plausible - the compose
dedupe has been there since 0a335146ec (22 Sep) and the grouped route since 9a49921c92 (8 Sep),
so any grouped DO answer since then hits it; the turn's verdict is not stored, so it cannot be
confirmed from the repo.

## Other sanitizers checked (brief: same top-level-only pattern with `groups`)

Only these backend routes emit `groups` of rows: orders list (`orders.py:562`, `:643`) and PO
placed (`purchase_orders.py:194`). The PO placed tool has no MCP row slim at all, so its group
rows are the same shape as its flat rows. `_slim_grn_response`, `_slim_rows` (projects,
quotations) and `_slim_promotion_products_response` are top-level-only too, but their routes emit
no `groups`, so nothing to fix there today.

## Fix

1. MCP `server.py`: `_slim_orders_list_response` also maps `_slim_orders_list_row` over every
   `groups[i]["rows"]`; `_strip_row_company_ids` walks the same group rows. A grouped answer's
   rows are then the same shape as the flat list (Status is text, no UUIDs).
2. Backend `compose.py::_row_key`: a dict/list field value becomes a stable string
   (`json.dumps(sort_keys=True, default=str)`), so no answer row shape can crash a turn. Dedupe
   semantics otherwise unchanged.

## Tests (red first)

- `sorento_crm_mcp/tests/test_orders_sanitizer.py`: a grouped orders list response has text
  `order_status` and no `id` / `company_id` in group rows.
- `sorento_crm_backend/tests/chatbot/test_chat_grouped_order_status.py`: a real turn
  (`engine.run_turn`, parser verdict stubbed, MCP double = real sanitizer + presenter) for a
  check_order grouped by customer whose route body carries a dict `order_status` in its group rows:
  turn completes, reply prints the group with Status as text. Plus a unit test that `_row_key`
  hashes a dict value.

## Track

Small fix: diff well under 300 lines, no migration, no auth change, no new ingest surface. One
reviewer, no browser pass (no screen changed).
