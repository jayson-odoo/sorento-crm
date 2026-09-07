# PLAN: DO list product-code search, delivered-status backfill, MCP incoming/summary feedback (7 Sep 2026)

Status: REVIEWED x2, PR #711, promote runbook pending
Branch: `fix/do-search-and-mcp-feedback-7sep` (one lane, one PR)
UAC: `do-search-and-mcp-feedback-7sep-acceptance-criteria.md`

Five owner comments from 7 Sep 2026, each a small repair. No new abstraction, no new table.

## 1. Delivery Orders list: search box matches product code

Today `OrderService.list_orders(query=...)` (order_service.py ~576-617) unions order ids over
order_number / debtor_name / debtor_code / legacy transporter text / Customer name+code /
Transporter code+name. It never touches order lines. Product search exists only as the separate
`product_query` param (advanced Filters).

Change: add a fourth id-set to the same union:
`Order.id` where `Order.lines.any(OrderLine.product.has(Product.product_code.ilike(term)))`.
Product code only (the ask). The Filters panel quick-search shares this code path
(list_query_search_service passes `query=req.quick_search`), so it benefits with no FE change.
No frontend edit.

## 2. "Is there a reconciler?" - no. Backfill instead.

Measured on the prod copy (7 Sep): 4,833 orders carry `actual_delivery_date` under status
`NEW`; 0 under any other non-delivered status; all 4,833 have `order_date`; all were written by
the Excel tracking import (checker/transporter/delivery_days populated) on 4 Jun, 13-14 Jul,
19 May. The master-sheet pass used to reset status to NEW unconditionally; the guard
(`already_delivered`, commit 9c3acb004, 5 Aug) stopped new damage but heals nothing.
No scheduler, listener or import step derives status from the date. `update_order` never does.

Change: one-off script `sorento_crm_backend/scripts/backfill_delivered_status.py`.
Rule: `order_status = NEW AND actual_delivery_date IS NOT NULL AND deleted_at IS NULL`
-> `order_status = DELIVERED` (status_code lookup, case-insensitive). Dry-run by default,
`--apply` to write, prints count before/after. Only NEW is touched: CANCELLED/PENDING etc. with
a date are not the reported defect and stay as they are. Prod run needs the owner's go.
No permanent reconciler: the writer that caused it is already fixed.

What the owner is saying go to: the 4,833 rows move to status code DELIVERED, whose display
name on prod is `Picked Up / In Transit` - the same label the 18,585 rows the tracking import
already set carry today. They leave the outstanding bucket in every list, summary and chatbot
answer (DELIVERED is the canonical "delivered" predicate everywhere it is checked). Embedding
rows keep whatever status they last carried in their vector metadata - that is inert: the
resolver joins back to the live `orders` table for status, so a stale embedded status is never
read.

## 3. `crm_incoming_stock_list` render: drop the Shipment line

`_incoming_list` in `sorento_crm_mcp/sorento_crm_mcp/presenters.py` (~590) emits
`("shipment_number", "Shipment", ...)`, the auto-generated packing-list number (PL-2609-002),
meaningless to a customer. Remove that one tuple. Raw payload key `shipment_number` stays
(the AI assistant and `_incoming_shipments` read it). `_incoming_by_product` already omits it.
Tests asserting `fields["Shipment"]` on the list tool flip to asserting absence.

## 4. `crm_order_management_orders_list` summary card: add DO date

`stamp_order_summary` (order_service.py ~129-347) aggregates per product and per
(customer, product) with COUNT/SUM plus `delivered_from`/`delivered_to` (delivered subset).
Add `order_date_from` / `order_date_to` = MIN/MAX(`Order.order_date`) over ALL DOs in the row
(not the delivered subset), on both `products[]` and `groups[]`, emitted only when non-null.
Presenter: `_summary_item` adds field key `order_date`, label `DO Date`, rendered through the
existing `_sl_between` (single date or `from - to`), placed right after `order_count`. Omitted
when the backend did not send it (old fixtures keep passing). Catalog description gains one
clause naming the DO date span.

## 5. Chatbot: a checkpoint ask returns every earlier checkpoint too

`output_structurer` (app/services/chatbot/lanes/business/fetch.py ~955-993) projects the
incoming render envelope's `fields[]` to IDENTITY_KEYS + ALWAYS_KEPT_KEYS + the literal
`requested_attributes` (or everything under the `__all__` sentinel). Asking `gatepass_date`
returns only gatepass.

Change: module tuple `CLEARANCE_CHECKPOINT_ORDER` in fetch.py, in the order the admin-editable
`statuses` rows (entity_type `inbound_shipment`, by `sort_order`) hold on prod today:
`loading_date, etc_date, etd_date, estimated_arrival_date, eta_delay_date, inspection_date,
approval_date, gatepass_date, warehouse_arrival_date, informed_collection_date, collection_date`.
After `keep_keys` is built and when not `timeline`: for each requested key found in the tuple,
add every key up to and including it. Only `keep_keys` grows; `req_attrs` (echoed back, carried
forward, and driving the "not recorded yet" / denial notes) is untouched, so implicit earlier
checkpoints are shown when recorded and silent when not. Non-sequence keys (liner_code, consignee,
...) never expand. Hardcoded, not read from `statuses`: `output_structurer` is a pure function
with no session, and the parser prompt already hardcodes the same vocabulary.

## 6. A bare container ask is a timeline, not an ETA-only answer

Live turn f07632b6-d56d-4036-944c-8200462caac3: "incoming TIIU6323920" parses to
`requested_attributes: []` with entity `{"raw": "TIIU6323920", "hint": "inbound_shipment",
"confident": true}` - no attribute named, but a specific container IS named. Code rule
(`fetch._names_a_shipment`, `fetch.output_structurer`): when `requested_attributes` is empty
AND the RESOLVED entity list (`ctx["entities"]`) carries `entity_type == "inbound_shipment"`,
treat the turn as a timeline ask, exactly as the `__all__` sentinel does - every recorded
checkpoint comes out, chronologically. When the gate ran empty (no resolved entity list at
all), fall back to the parser's own raw `hint` on `semantic_input.entities` instead. A bare
PRODUCT ask (`entity_type`/`hint` == `"product"`) is explicitly NOT widened: identity + the
always-kept ETA only. An EXPLICIT attribute ask (`requested_attributes` non-empty) always
takes the backward-expansion path (§5 above), never this one - the bare-container rule only
fires on an empty ask.

Prompt side: the WORKED EXAMPLES paragraph in `chatbot_parser_prompt.py` (both the FULL and
SLIM constants) now names this case directly - "incoming TIIU6323920" / "TIIU6323920" /
"container status of X" -> `["__all__"]` - alongside the existing warehouse-arrival and
bare-ETA examples, and a fourth: an EXPLICIT ETA ask about a container ("when does container
X arrive" / "ETA of X") still resolves to `["estimated_arrival_date"]` alone, so the model
does not have to infer that boundary from the other three. See §9 for the migration that
publishes this text.

## 7. `crm_incoming_stock_shipments` collapses to the list tool, narrowly

Evidence turn 147d6888-d313-4612-a32f-364cec119ec4: "incoming TIIU6323920" picked
`crm_incoming_stock_shipments` (similarity 0.4675) over `crm_incoming_stock_list` (0.4537).
The shipments tool's header carries no clearance checkpoints and no `field_access` block, so
the container timeline (§6) can never render from it - `apply_field_access`
(`app/api/v1/incoming_stock.py` `/list`) is the only place clearance gating is wired, and the
n8n spine this engine replaced called only the list tool.

The collapse lives at the CRM-policy seam, `app/services/chatbot/lanes/business/services.py`'s
`_tool_search`, right after its existing read-only filter (the docstring there already names
this seam as the place for CRM-specific rules, so `fetch.tool_filter` stays a byte-for-byte
ported node with nothing CRM-specific grafted onto it). Narrowed to ONE tool:
`crm_incoming_stock_shipments` renames to `crm_incoming_stock_list` in the candidate list
(keeping its similarity, recording `collapsed_from`); `crm_incoming_stock_by_product` is left
alone - it renders batch numbers and the catalog routes product asks to it on purpose, so it
is a real answer, not a stand-in for the list. Implemented as a rename in place rather than an
appended row: when both the shipments and list tools are candidates in the same turn, the
collapsed name never appears twice - whichever has the higher similarity wins under the list
name.

## 8. An out-of-enum `domain_hint` never zeroes the tool search

Evidence turn b5b19cec-dccc-4eda-b766-1aeb1362957b: the parser tagged `domain_hint:
"purchasing"` for "IBWB248什么时候会到仓库？" - "purchasing" is a TEAM name (see ROUTING in the
prompt), not one of the domains the prompt itself declares. `EmbeddingReadService.
search_tool_chunks`'s `source_id LIKE '%purchasing%'` filter matched nothing (every incoming
tool's `source_id` is `implemented::crm_incoming_stock_*`), so the domain-scoped search came
back empty and the turn ended `not_found`.

Fixed at the source rather than papered over with a retry: `output_exchange.py`, right beside
the existing coercion of the literal string `"null"` to real `None`, a `domain_hint` that is
not a member of `contracts.DOMAIN_HINTS` (the closed enum the prompt's own `domain_hint = ONE
of: ...` line declares, already present in `contracts.py` for this exact purpose but not yet
consumed anywhere) is coerced to `None`. `fetch.select_tool` no longer retries with
`domain=None` on a zero-candidate domain-filtered search - by the time it runs, `domain` is
already trustworthy, so a retry would only ever be a no-op or paper over a genuinely narrow
domain search that legitimately found nothing.

## 9. Parser prompt: warehouse-arrival cues + worked examples, migration 487

"IBWB248什么时候会到仓库？" / "when will IBWB248 arrive at the warehouse" / "bila IBWB248 sampai
gudang" all parsed to `requested_attributes: ["estimated_arrival_date"]` instead of
`["warehouse_arrival_date"]`: the vocabulary line for `warehouse_arrival_date` carried no cue
at all, so `estimated_arrival_date` (which owned the bare word "arrival") matched instead. Both
`SEMANTIC_PARSER_PROMPT` (FULL) and `SEMANTIC_PARSER_PROMPT_SLIM` now give
`warehouse_arrival_date` its own warehouse/CJK/Malay cue, narrow `estimated_arrival_date` to
port-ETA phrasing, and carry the WORKED EXAMPLES paragraph from §6 (measured 8/8 on the v5
text against the owner's tested phrasings, local runs 7 Sep 2026).

This is CONTENT, not a mechanical transform of the live n8n text (unlike the two edits
`test_parser_prompt_is_live.py` already pins - the leading `=` drop and the date-expression
swap) - it is new prompt text the owner asked for, so it cannot come out of the live file by
derivation. Migration `alembic/versions/487_chatbot_warehouse_cue.py` publishes BOTH the FULL
and SLIM corrected texts as NEW, UNLABELLED `chatbot_semantic_parser` versions (same
immutable-versions-plus-movable-labels split as migration 475) - nothing changes on prod until
the label moves. `downgrade()` excludes any version a label already points at from its delete
(`AIPromptLabel.version_id` is `ondelete=CASCADE`, so deleting a labelled version would
silently take the label row with it).

**RUNBOOK:** after this PR deploys, the owner moves the `production` label onto the new FULL
version in System Management > AI assistant > Prompts. Nothing changes on prod before that -
the fallback and the currently-labelled version are untouched by this migration.

## Out of scope
`orderService.ts` hand-built URLSearchParams (pre-existing, unrelated). `_incoming_shipments`
Shipment line (dormant tool, shipment IS its identity). Auto-advancing status on manual
`actual_delivery_date` edits.

## Verification
pytest: tests/test_order_list_summary.py, tests/test_incoming_list.py, new search test,
tests/chatbot/test_s6b_fetch_lane.py, new backfill test. MCP: sorento_crm_mcp/tests.
No FE change, so no browser run for the search; curl the list route with `query=<code>`.

§6-9 (review pass): tests/chatbot/test_s6b_fetch_lane.py (bare-container timeline, hint
fallback, the narrowed shipments collapse), tests/chatbot/test_parser_warehouse_arrival_cue.py
and tests/chatbot/test_parser_prompt_is_live.py (prompt content + reproducibility),
tests/test_chatbot_warehouse_cue_migration.py (publish idempotency + the label-safe
downgrade), tests/chatbot/test_output_exchange_unit.py (the domain_hint enum guard).
tests/chatbot/test_replay.py must stay green throughout (D8 byte-for-byte grading).
