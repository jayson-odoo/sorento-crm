# UAC: DO search, delivered backfill, MCP incoming/summary feedback (7 Sep 2026)

## AC1 DO list search by product code
- AC1.1 `GET /api/v1/order-management/orders?query=SRTWC8518-SH` returns every DO with at least one line whose product_code contains the term (case-insensitive), and none without.
- AC1.2 Existing matches (order number, debtor name/code, customer, transporter) still match.
- AC1.3 `POST /api/v1/list-query/search` resource `orders` with `quick_search=<code>` returns the same set.
- AC1.4 Company scope still applies to product-matched rows.

## AC2 Delivered-status backfill
- AC2.1 `python scripts/backfill_delivered_status.py` (no flag) prints the candidate count and writes nothing.
- AC2.2 `--apply` sets status DELIVERED on rows with status NEW and a non-null actual_delivery_date; re-running reports 0.
- AC2.3 Rows with status CANCELLED/PENDING/other and a date are untouched. Soft-deleted rows untouched.
- AC2.4 Prod run only after owner go.

## AC3 Incoming list render drops Shipment
- AC3.1 `crm_incoming_stock_list` with view=render: no field labelled Shipment / key shipment_number on any item.
- AC3.2 Raw (non-render) payload still carries `shipment_number`.
- AC3.3 Container, ETA, Incoming Quantity, allocations, clearance dates unchanged.

## AC4 Summary card DO date
- AC4.1 With include_summary=true, every `summary.groups[]` and `summary.products[]` row carries `order_date_from` and `order_date_to` (ISO date) when any DO in the row has an order_date; both absent otherwise.
- AC4.2 The span covers ALL DOs in the row, delivered or not.
- AC4.3 Render card lists `{"key":"order_date","label":"DO Date","value":"21/07/2026"}` for one date; for a span both dates render joined by the presenter's existing range separator (the same one `delivered_between` already uses), directly after the DOs field; omitted when the backend sent none.
- AC4.4 Existing summary tests and the recorded qs6 envelopes still pass.

## AC5 Checkpoint ask expands backwards
- AC5.1 requested_attributes ["gatepass_date"] keeps loading, ETC, ETD, ETA, ETA delay, inspection, approval, gatepass fields (those present in the envelope) and drops warehouse arrival, informed collection, collection.
- AC5.2 ["warehouse_arrival_date"] keeps everything through warehouse arrival.
- AC5.3 ["__all__"] behaviour unchanged (everything kept).
- AC5.4 ["liner_code"] keeps liner_code plus identity + ETA only; no checkpoint expansion.
- AC5.5 `requested_attributes` echoed in the output is still the original list (not the expanded one); "not recorded yet" notes only for the asked key.
- AC5.6 Product / order domain envelopes are untouched.

## AC6 A bare container ask returns every recorded date, chronologically
- AC6.1 `requested_attributes: []` with a resolved entity `entity_type == "inbound_shipment"` (or, when the gate ran empty, the parser's own raw `hint == "inbound_shipment"`) returns every recorded checkpoint in `CLEARANCE_CHECKPOINT_ORDER`, identical to the `["__all__"]` sentinel.
- AC6.2 The same bare ask with the resolved/hinted entity as `"product"` returns identity + ETA only - never widened.
- AC6.3 An explicit `requested_attributes` (non-empty) with an `inbound_shipment` entity still takes the backward-expansion path (AC5), never the full-timeline path - the bare-container rule only fires when the ask itself is empty.
- AC6.4 The echoed `requested_attributes` stays `[]` (untouched) on a widened bare-container turn.

## AC7 `crm_incoming_stock_shipments` renders through the list tool
- AC7.1 A candidate list containing `crm_incoming_stock_shipments` as the argmax winner is renamed to `crm_incoming_stock_list` before `tool_filter` ever sees it, same similarity, with `collapsed_from` recorded on the candidate.
- AC7.2 `crm_incoming_stock_by_product` is never renamed or touched by the collapse.
- AC7.3 When both `crm_incoming_stock_shipments` and `crm_incoming_stock_list` are candidates in the same turn, the collapsed name appears exactly once - the higher-similarity candidate wins under the list name.
- AC7.4 The collapse lives in `services._tool_search` (the CRM-policy seam), not in `fetch.tool_filter`, which is left a byte-for-byte ported node.

## AC8 An out-of-enum domain_hint never zeroes the search
- AC8.1 `domain_hint: "purchasing"` (a team name, not a declared domain) is coerced to `null` in `output_exchange.py`, before it ever reaches `select_tool`.
- AC8.2 `domain_hint: "incoming"` (a declared domain) is passed through unchanged.
- AC8.3 The literal string `"null"` is still coerced to real `null` (pre-existing behaviour, unaffected).
- AC8.4 `select_tool` no longer retries `tool_search` with `domain=None` on a zero-candidate domain-filtered search - one call per turn.
- AC8.5 Every member of `contracts.DOMAIN_HINTS` is a substring the parser prompt itself declares (guards enum drift both ways).

## AC9 Parser prompt cues + worked examples (migration 487)
- AC9.1 "when will X arrive at the warehouse" / its zh/ms phrasings parse to `requested_attributes: ["warehouse_arrival_date"]` in both the FULL and SLIM prompt constants (evidence: 8/8 local runs against the v5 text, owner-tested phrasings, 7 Sep 2026).
- AC9.2 "when is X arriving" (product named, no warehouse/checkpoint) still parses to `[]` (the ETA default) in both prompts.
- AC9.3 "incoming TIIU6323920" / a bare container/shipment ask with no checkpoint named parses to `["__all__"]` in both prompts; an explicit ETA ask about a container ("ETA of X") parses to `["estimated_arrival_date"]` alone.
- AC9.4 Migration `487_chatbot_warehouse_cue` publishes BOTH the FULL and SLIM corrected texts as new, UNLABELLED `chatbot_semantic_parser` versions; the `production` label is untouched by `upgrade()`.
- AC9.5 `downgrade()` excludes any version a label currently points at from its delete - promoting `production` onto the new FULL version and then downgrading leaves the label pointing at that version, and only deletes the still-unlabelled SLIM version.
- AC9.6 Promoting is a manual, separate action: the owner moves the `production` label in System Management > AI assistant > Prompts after deploy. Nothing changes on prod before that.
