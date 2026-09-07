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
