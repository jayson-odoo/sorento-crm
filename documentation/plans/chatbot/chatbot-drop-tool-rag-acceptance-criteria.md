# UAC: drop the tool RAG from the chatbot business lane

Plan: `PLAN-chatbot-drop-tool-rag.md`. Every criterion is a pytest unless marked browser.

- AC-1 Deterministic pick. For every `DOMAIN_SPEC` key with a non-empty `tools` tuple,
  `select_tool(domain)` returns exactly one candidate named `tools[0]`. Pinned per domain
  against the measured historic pick: inventory -> `crm_inventory_stock_balance_list`,
  incoming -> `crm_incoming_stock_list`, master_products -> `crm_master_products_list`,
  order -> `crm_order_management_orders_list`, product_attachment ->
  `crm_master_product_attachments_list`, promotion -> `crm_marketing_promotions_list`,
  resource_attachment -> `crm_resource_attachments_list`, spo_allocation ->
  `crm_procurement_spo_allocations_last_receipt_list`, forms ->
  `crm_forms_management_forms_list`, purchase_order -> `crm_procurement_po_placed_list`,
  portal_link -> `crm_portal_link_get`.
- AC-2 No embedding, no registry. A business turn in the `spo_allocation` domain, run
  against a database with NO `embedding_chunks` row and NO `mcp_tools` row for the tool,
  still calls `crm_procurement_spo_allocations_last_receipt_list` on the `mcp_call` seam.
  The test asserts no call reaches `EmbeddingReadService` (the class is monkeypatched to
  raise). This is the production failure of 8 Sep 2026 reproduced and closed.
- AC-3 Trace. `_tool_pick` on the picked item carries `chosen = tools[0]`,
  `rejected = []`, `count = 1`, `source = "domain_spec"`. The trace step the drawer
  reads is otherwise unchanged in shape.
- AC-4 Outcome parity. `domain = None`, a domain outside `DOMAIN_SPEC`, and a domain
  with an empty `tools` tuple (`goods_receive`, `ideate`) all end `outcome = "not_found"`
  with the existing "no MCP tool matched this question" fragment.
- AC-5 Egress guard intact. `tests/chatbot/test_tool_pool_is_read_only.py` and the
  `ensure_read_only` tests pass unchanged.
- AC-6 Seams gone. `FetchServices` has no `embed` or `tool_search` field;
  `EmbeddingReadService` has no `search_tool_chunks`; `collapse_tool_rows`,
  `_collapse_incoming_shipments`, `drop_by_product_without_product` no longer exist. A
  grep for each name across `sorento_crm_backend/app` returns nothing.
- AC-7 Suite. `pytest tests/chatbot -q` green on a Postgres DB migrated to head (this
  lane uses `sorento_ai_automation_0907`), including `test_replay.py`.
- AC-8 Browser (tester, agent-browser, via sidebar). Chatbot Console, contact Jayson,
  message "last in for SRT62-gm" on the local stack over `sorento_ai_automation_0907`:
  the reply lists the most recent fully-received allocation for SRT62-GM (10 rows exist,
  all `fully_received`), and the turn's trace shows `source: domain_spec`. If the local
  parser has no LLM key the tester reports that as the blocker rather than skipping AC-8.
