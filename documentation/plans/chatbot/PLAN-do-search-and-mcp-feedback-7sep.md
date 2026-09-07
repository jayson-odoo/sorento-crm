# PLAN: DO list product-code search, delivered-status backfill, MCP incoming/summary feedback (7 Sep 2026)

Status: PR #711 OPEN, browser-verified 7 Sep
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

## Out of scope
`orderService.ts` hand-built URLSearchParams (pre-existing, unrelated). `_incoming_shipments`
Shipment line (dormant tool, shipment IS its identity). Auto-advancing status on manual
`actual_delivery_date` edits.

## Verification
pytest: tests/test_order_list_summary.py, tests/test_incoming_list.py, new search test,
tests/chatbot/test_s6b_fetch_lane.py, new backfill test. MCP: sorento_crm_mcp/tests.
No FE change, so no browser run for the search; curl the list route with `query=<code>`.
