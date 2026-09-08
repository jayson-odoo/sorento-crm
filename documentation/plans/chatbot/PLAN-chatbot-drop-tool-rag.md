# PLAN: drop the tool RAG from the chatbot business lane

Status: IMPLEMENTED, AC-8 browser check pending (8 Sep 2026, branch
`feat/chatbot-drop-tool-rag`). Owner ruling the same day: "actually i just need 1 for each ... we can drop
the rag from chatbot lane".
UAC: `chatbot-drop-tool-rag-acceptance-criteria.md`.

## Why (measured, not argued)

The business lane picks ONE tool per turn (`fetch.tool_filter` takes the single top hit).
Today that pick is made by embedding the customer's message, running a pgvector search
over `embedding_chunks` (`source_type = 'mcp_tool'`) narrowed to the domain, and taking
the highest cosine similarity. The candidate set it searches is already a literal in the
backend: `contracts.DOMAIN_SPEC[domain].tools`.

Tools per domain (main @ 9a49921c9): master_products 4, promotion 3, incoming 3,
resource_attachment 3, product_attachment 2, inventory 2, order 2, and ONE each for
forms, portal_link, spo_allocation, purchase_order. Median 2.

Measured over every turn in the 7 Sep prod copy (`sorento_ai_automation_0907`,
`chatbot.turns.trace` `_tool_pick.chosen`, 740 turns), the pick was the domain's
FIRST-LISTED tool on every turn. Not one variant (`orders_by_product_list`,
`incoming_stock_by_product`, `incoming_stock_shipments`, `brands_list`,
`product_categories_list`, `units_of_measure_list`, `promotion_attachments_list`,
`promotion_products_list`, `resource_attachments_catalogue`,
`resource_attachments_current_stock_list`, `warehouses_list`, `certificates_list`) was
ever chosen. The vector search is deciding a question that has one answer.

What it costs: one embedding API call per business turn, and a runtime dependency on the
whole registry-plus-chunk seeding chain (`mcp_tools` rows, `embedding_chunks`,
`chatbot_domain`, the seeder script). That chain cannot run in the deployed backend image
(the MCP catalogue is not in it - PR #748's finding), so production's tool RAG has been
frozen since 2 June 2026 and every tool added since (`spo_allocations_last_receipt_list`,
`po_placed_list`) is unreachable: "last in for SRT62-GM" answered "no spo_allocation
matched these" with 10 fully-received allocations in the table. Selecting from
`DOMAIN_SPEC` directly makes that failure class impossible rather than monitored.

The RAG stays where it earns its keep: the in-app AI assistant (free text over 100+ tools,
no domain enum) is untouched by this plan.

## Contract after this plan

`fetch.select_tool(domain)` returns `[{"name": DOMAIN_SPEC[domain].tools[0], "similarity": 1.0}]`
when `domain` is a `DOMAIN_SPEC` key with a non-empty `tools` tuple, else `[]`. No
embedding, no DB read, no network. The FIRST entry of each domain's `tools` tuple is now
a contract: it is the tool the lane calls. The remaining entries stay where they are -
they are allow-list members for the probes and the cross-domain rung
(`CHATBOT_READ_ONLY_TOOLS` is derived from `DOMAIN_CLAIMED_TOOLS`), not candidates.

`tool_filter` (ported node, graded against 38 captures) is NOT modified. It receives the
one candidate and emits `_tool_pick = {chosen, rejected: [], count: 1, has_product}` plus
a new `source: "domain_spec"` set by the caller, so the trace still says how the tool was
chosen.

Outcomes: an unknown domain, or a domain with an empty `tools` tuple (`goods_receive`,
`ideate`), reaches `tool_filter` with `[]` and ends `not_found` with the same "no MCP tool
matched this question" fragment (H11), exactly as a zero-row search did.

**A NULL domain is a narrowing, not parity, and it is deliberate.** `search_tool_chunks`
ran an UNFILTERED search when `domain` was null (its `else: rows = _run([])` branch), so
such a turn used to come back with whatever tool was nearest in the whole pool;
`select_tool(None)` returns `[]` and the turn ends `not_found`. Measured on
`sorento_ai_automation_0907`: of 994 `business_query` turns, 0 reached the fetch step with
a null or missing `domain_hint`, so the change has no measured effect. It is also the
right direction: a tool chosen by cosine distance with no domain to answer from was never
a defensible answer.

## Work

1. `lanes/business/fetch.py`: replace `select_tool`'s body (embed + `services.tool_search`)
   with the `DOMAIN_SPEC` read. Delete `collapse_tool_rows` and `_rag_message`'s only
   consumer if nothing else uses it. `TOP_N_DIRECT_TOOLS`, `tool_filter`, `call_tool`,
   `ensure_read_only`, `CHATBOT_READ_ONLY_TOOLS` stay.
2. `lanes/business/__init__.py` (~line 322): call the new signature; set
   `_tool_pick.source`. `drop_by_product_without_product` can no longer see a by-product
   tool (it was only ever the second candidate): delete it and its call, and convert
   `tests/chatbot/test_pick_customer_only_order_ask.py` into the assertion that the
   `order` domain picks `crm_order_management_orders_list`.
3. `lanes/business/services.py`: remove the `embed` and `tool_search` seams from
   `FetchServices` and `production_services`, `_embed`, `_tool_search`,
   `_collapse_incoming_shipments`, and the node-mapping rows in the module docstring.
   `_mcp_call` stays.
4. `app/services/embedding_service.py`: delete `EmbeddingReadService.search_tool_chunks`
   (its only caller was the seam above) and
   `tests/chatbot/test_tool_search_domain_filter.py`.
5. Leave `mcp_tools.chatbot_domain`, its sync stamping and `mcp_tool_domains.py` in
   place this lane. Nothing reads the column after step 4; dropping it is a migration on
   a column production never populated, so it is a follow-up with its own trigger
   (next migration that touches `mcp_tools`).
6. Docstrings that describe the RAG pick (`fetch.py` header, `select_tool`,
   `call_tool`'s H58 paragraph, `contracts.py` lines ~55-65 and ~239, `access.py`
   `chatbot_domain` comment) are rewritten to describe the `DOMAIN_SPEC` pick. No dashes
   of the em/en variety anywhere.
7. Tests, test-first (Phase 2): see the UAC. Existing fixtures that construct
   `FetchServices(embed=..., tool_search=..., mcp_call=...)` in
   `tests/chatbot/test_s6b_fetch_lane.py`, `test_s6c_engine_paths.py`,
   `test_s6_s7_integration.py`, `test_dry_run_isolation.py`, `test_foundre_rung_end_to_end.py`,
   `test_trace_add.py`, `test_trace_persistence.py`, `test_replay.py`,
   `test_pass4_item2_last_month_keeps_customer_scope.py`,
   `test_pass5_item1_photo_attachment_alias.py`,
   `test_parser_growth_r1_reachability.py` are updated to the two-seam bundle. Where a
   test asserted a similarity-driven pick, it now asserts the `DOMAIN_SPEC` pick.

Out of scope: the AI assistant's RAG, the seeder script, the sync at startup, the MCP
catalogue's presence in the backend image (separate lane), the parser prompt.

## What landed, and where the code differed from the plan

Five corrections, made while implementing and recorded here because the plan is the
contract:

1. **Step 3 names the wrong builder.** `production_services` builds `ResolveGateServices`;
   the `FetchServices` builder is `fetch_services(db)`, and that is the one now returning
   `FetchServices(mcp_call=_mcp_call(db))`. It still takes its session, unused, so the
   engine's call site reads like every other lane's.
2. **`rag_query_params` goes too** (review, 8 Sep 2026). Step 1 names
   `collapse_tool_rows` only, and the first cut kept the other `sub-get-rag` body on the
   grounds that 38 captures grade it. That is an unjustified asymmetry: both are
   REPLAY-only bodies of a sub nothing calls now, so both are deleted.
3. **`sub-get-rag`'s 76 captures are no longer graded.** With neither port left,
   `test_replay.RUNNERS` loses both entries, `_corpus.NODE_SLUGS` loses both slugs, and
   the two nodes drop out of `PORTED_NODES` and out of `COVERAGE.md` (regenerated;
   `sub-get-rag-live` now renders as `(none ported)`, with its scan still on record). The
   fixture files stay on disk, with a comment at each site saying why. Nothing else about
   the replay changes: the vendored gate is green.
4. **A zero-tool turn is no longer reachable end to end**, which is the point of the
   change but does move two engine-level tests. Every domain that can pass the gate has a
   tool, so `tests/chatbot/test_s6c_engine_paths.py::TestH11ZeroToolsIsAnOutcomeEndToEnd`
   and `test_s6_s7_integration.py`'s matrix now drive the same customer-facing `not_found`
   through a tool that answers EMPTY. H11's actual zero-tool arm is graded directly on
   `run_fetch` (UAC AC-4). One assertion moved with it: the shadow cell's stage is `routed`
   rather than `looked_up`, because `looked_up` is what the engine records when the shadow
   lane ERRORED and the zero-tool pick was that error.
5. **`mcp_tools.chatbot_domain` keeps the column and loses its prose.** Step 5 leaves the
   column, the stamping and `mcp_tool_domains.py` in place; their comments all described
   `search_tool_chunks` as the reader, so each now says the column is written and unread,
   and names the same trigger for the drop.
