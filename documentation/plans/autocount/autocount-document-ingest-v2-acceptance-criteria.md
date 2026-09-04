# UAC: AutoCount document ingest, contract v2 (xlsx-import parity)

**Status:** APPROVED 2026-09-05 (grilled via Lavish, all decisions as recommended). Requested by the
foundryx-shared-service session: `foundryx-shared-service/documentation/plans/sprint-5/02-autocount-document-mapping-sorento-addendum.md`
(branch `sprint-5/autocount-document-mapping`). Plan: `PLAN-autocount-document-ingest-v2.md`
alongside. Baseline contract: `PLAN-autocount-cross-repo-contract.md` section 3 (A3).

**Classification:** CORE. The `/external/ingest` surface and the `public.sales_orders`,
`public.purchase_orders`, `public.spo_allocations` tables it writes are base platform. The
SCM-module hooks it calls after a write (plan exceptions, order-link claims, CRM-raised PO
supersede) already exist behind the SCM module and are called, not built.

## Journey

**Actor:** the buyer / fulfilment planner (the captain) who opens the SCM plan on Monday
morning. Today they first export the SO book and the PO/SPO book from AutoCount, upload each
through `SCM -> Reorder -> Upload order book`, read the preview, confirm, and wait for the
job. The goal of v2 is that this step disappears: the ESB reads AutoCount's database and
pushes the same documents, and the plan the captain opens is the one the upload would have
produced.

**Where they arrive from:** the SCM sidebar, exactly as today. No new screen. The ESB is a
machine actor with no screen; its "screen" is the per-record verdict it gets back.

**What the system already knows:** every master the documents point at (products, warehouses,
suppliers, customers, agents) has either been pushed by the ESB with an integration reference,
or exists from the xlsx era with a code and no reference, or does not exist at all. The push
carries all three ways of naming a master (ref, code, name) so the system can decide, and the
captain is never asked to pre-create a supplier or an agent the book names.

**Steps, and the one decision at each:**

1. The ESB pushes a batch of sales orders (and separately purchase orders, shipping orders).
   Decision: none for a human. Per record the system answers created / updated / failed /
   retryable, plus warnings.
2. A master named only by code or name is resolved; a supplier, agent or customer the system
   does not hold is created minimally (exactly as the upload does). A product or warehouse the
   system does not hold is never invented: the record is `retryable` and names the code.
3. A sales order whose demand class cannot be decided lands anyway and is flagged
   (`warnings: ["unclassified_demand"]`), instead of blocking the whole batch. Decision for the
   captain: none here. The existing agent-classification screen is where the class gets set,
   and the next push re-runs the ladder.
4. The captain opens the plan. Committed demand, on-order supply, SO/PO dedication, plan
   exceptions and superseded CRM-raised POs read the same as they would after an upload.
5. A document AutoCount deleted is removed (or cancelled in place if something still points at
   it) on the ESB's deletion call, so the plan never carries a phantom order.

**What they hold at the end:** a plan built from AutoCount's own data, with no upload step,
and a list of records the ESB could not land (retryable, with the missing code named).

**What other stakeholders are told automatically:** nothing new. The ESB gets the verdicts;
the existing upload drawer is not involved. (No notification surface is added in v2.)

## Scope rules

- Every new payload key is OPTIONAL. A v1 payload (no new keys) ingests byte-for-byte as
  today. `extra="forbid"` stays.
- No FE work. Phase 1 (frontend mock) is NOT APPLICABLE and is recorded as such in the PR.
- Nothing here changes the xlsx upload path's behaviour.

## Group V0 - Contract version + verdict warnings (`tests/test_ingest_contract_v2.py`)

- **AC-V0-1 [BE]** Given a valid external principal, when it calls
  `GET /api/v1/external/contract`, then it receives `200 {"version": 2, "entities": [...]}`
  listing every ingestable entity. An unauthenticated call is 401.
- **AC-V0-2 [BE]** Given a v1 sales-order record (only the fields in the A3 contract), when it
  is ingested, then the outcome, the written columns and the read-back are identical to
  today's (pinned by a golden test over `test_ingest_documents` fixtures), with two stated
  v2 deviations: a bad `warehouse_ref` lands with a NULL FK (AC-V1-7b) and a `partial` sales
  order is stored `open` (AC-V5-3, D6a).
- **AC-V0-3 [BE]** The per-record verdict gains an optional `warnings: [str]` key, omitted when
  empty (same rule as `errors`).

## Group V1 - Code and name fallbacks, back-create (`tests/test_ingest_documents_v2_resolution.py`)

- **AC-V1-1 [BE]** Given a sales order carrying `customer_ref` that resolves, when `customer_code`
  is also sent, then the ref wins and the code is written to `sales_orders.debtor_code`.
- **AC-V1-2 [BE]** Given a sales order carrying no `customer_ref` but a `customer_code` that
  matches `customers.customer_code` (upper/trim) in the anchor company, then `customer_id` is
  linked to that row and `debtor_code` is written.
- **AC-V1-3 [BE]** Given `customer_code` + `customer_name` that match no customer, then a
  customer is created (`customer_code`, `customer_name`, `customer_type='company'`,
  `is_active=true`, no market segment), linked, and reported with
  `warnings: ["customer_created"]`. If `customer_ref` was ALSO sent, the new row is registered
  in `integration_references` under it, so the next push resolves by ref.
- **AC-V1-4 [BE]** Given `customer_code` with no `customer_name`, then no customer is created;
  `debtor_code` is still written and the record lands (`warnings: ["customer_unresolved"]`).
- **AC-V1-5 [BE]** Given a purchase order with `supplier_code` / `supplier_name` and no resolving
  `supplier_ref`, then resolution is ref, then code (upper/trim), then cleaned name
  (`_clean_supplier_name`, the `(RMB)` suffix stripped), then back-create via
  `back_create_supplier` (slug code when only a name is known), linked, registered under
  `supplier_ref` when one was sent, `warnings: ["supplier_created"]`.
- **AC-V1-6 [BE]** Given a sales order with `agent_code` and no resolving `sales_agent_ref`, then
  the agent is resolved by `sales_agent_service.normalize_code` and created via
  `resolve_or_create` when absent (shared row, `source='import'`), linked, registered under
  `sales_agent_ref` when one was sent, `warnings: ["agent_created"]`.
- **AC-V1-7 [BE]** Given a line with `product_code` and no resolving `product_ref`, then the
  product is resolved by `products.product_code` (upper/trim) in the anchor company. A miss is
  `retryable` with `errors: {"lines.N.product_code": "not found: <code>"}`. Products are never
  created. `warehouse_code` resolves against `warehouses.warehouse_code` the same way, but a
  miss follows AC-V1-7b, not retryable.
- **AC-V1-7b [BE]** Given a line whose `warehouse_ref` / `warehouse_code` was SENT and
  resolves to nothing, then the line lands with `warehouse_id = NULL` (and, on shipping
  orders, `location_code` = the sent code) and the record carries
  `warnings: ["warehouse_unresolved"]`. This replaces the v1 `retryable` outcome for a bad
  `warehouse_ref` (plan D10, v2 deviation).
- **AC-V1-8 [BE]** Given a ref that resolves into another company, then the record is `failed`
  exactly as today (A1 rule); a code is never consulted across companies.
- **AC-V1-9 [BE]** Given a purchase order (or shipping order) with no `currency` on the header
  or a line, then `CNY` is written (`DEFAULT_PO_CURRENCY`). A stated currency is written as sent.
- **AC-V1-10 [BE]** Given a dry run, then no supplier, agent or customer is created and the
  verdict still reports what WOULD be created (`warnings` present, outcome as it would be).

## Group V2 - Demand classification on sales-order ingest (`tests/test_ingest_documents_v2_demand.py`)

- **AC-V2-1 [BE]** Given a sales order whose stored `order_type` already classifies it, then
  `demand_class` is written from it and the payload's `order_type` does not overwrite the stored
  `order_type` (fill-only).
- **AC-V2-2 [BE]** Given a header with no `order_type`, a payload `order_type` that classifies,
  then `order_type` is filled and `demand_class` derived from it.
- **AC-V2-3 [BE]** Given neither, an agent with `demand_class`, then that class is written.
- **AC-V2-4 [BE]** Given none of those, a customer (via `customer_id` or `debtor_code`) with a
  `market_segment_code`, then the class is derived from the segment (`demand_class.class_of`).
- **AC-V2-5 [BE]** Given nothing classifies, then the record still lands (`created`/`updated`),
  `demand_class` stays as it was (NULL on create), and the verdict carries
  `warnings: ["unclassified_demand"]`.
- **AC-V2-6 [BE]** A stored `demand_class` is never downgraded or blanked by a later push that
  cannot classify.
- **AC-V2-7 [BE]** `demand_class` is not accepted in the payload (`extra="forbid"` rejects it).

## Group V3 - Shipping orders (`tests/test_ingest_shipping_orders.py`)

- **AC-V3-1 [BE]** `POST /api/v1/external/ingest/shipping_orders` accepts `CanonicalShippingOrder`
  (see plan section 3) under `scm.shipping_orders.edit`; read-back under
  `POST /external/read/shipping_orders` (`.view`); deletions under `.delete`. The four slugs exist
  and are swept to every role holding the matching `scm.purchase_orders.*` slug.
- **AC-V3-2 [BE]** Given a shipping order with N lines, when ingested, then N `spo_allocations`
  rows exist for `(company, spo_number)` with `source_system='autocount'`, `source_ref` = the
  line's DtlKey, `source_doc_ref` = the header's DocKey, `spo_line_number` assigned 1..N in payload
  order (continuing after the highest existing number on re-push), `allocated_quantity`,
  `quantity_received`, `receipt_status` (`pending` | `fully_received`), `line_status`
  (`open` | `closed`), `product_id`, `warehouse_id` (nullable), `location_code`, `supplier_id`,
  `issue_date`, `expected_date`, `unit_cost`, `currency`.
- **AC-V3-3 [BE]** Given a re-push with a changed quantity on an existing DtlKey, then the same
  row (same id, same `spo_line_number`) is updated. A line absent from the payload is
  `line_status='closed'` in place (never deleted): GRN lines and order-link claims point at
  these rows.
- **AC-V3-4 [BE]** Given rows the xlsx upload created for the same `spo_number`
  (`source_system='scm_upload'`, no `source_ref`), when the first push arrives, then they are
  adopted: matched to payload lines by `(product_id, upper(location_code))` in
  `spo_line_number` order, given the DtlKey and `source_system='autocount'`; unmatched ones are
  closed in place. Header adoption is by `spo_number` within the company.
- **AC-V3-5 [BE]** Given a `purchase_orders` record whose `po_number` is an `SPO-` family number
  (`po_listing_reader.doc_family`), then the record is `failed`
  (`errors: {"po_number": "shipping order; push under shipping_orders"}`), nothing written.
- **AC-V3-6 [BE]** Read-back returns the canonical shape (status word, refs where the master
  carries one, lines with `entity_id`).
- **AC-V3-7 [BE]** Deletions: unreferenced rows are hard-deleted and unlinked; referenced rows
  are `line_status='closed'` with verdict `deactivated`. (`spo_allocations` has no `cancelled`
  status; `closed` is what every reader already excludes.)
- **AC-V3-8 [BE]** `status` on the header is accepted for vocabulary validation but derived per
  line as today (`allocated_quantity - quantity_received`); `cancelled` closes every line.

## Group V4 - SO to PO dedication (`tests/test_ingest_documents_v2_links.py`)

- **AC-V4-1 [BE]** Given a purchase-order line (or shipping-order line) with
  `from_so_numbers: ["SO1", "SO2"]`, when ingested, then one `scm.order_link_claim` row per
  (so_number, po_number, item_code) exists with `source='autocount'`, and `order_link_service.resolve`
  has run for those SO numbers. `item_code` is the resolved product's `product_code`.
- **AC-V4-2 [BE]** Re-push is idempotent: the claim is found, not duplicated; a claim another
  source created is left as is.
- **AC-V4-3 [BE]** The `ck_scm_order_link_claim_source` check constraint admits `autocount`
  (migration, 458 pattern).
- **AC-V4-4 [BE]** Dry run writes no claim.

## Group V5 - Post-write hooks and committed demand (`tests/test_ingest_documents_v2_hooks.py`)

- **AC-V5-1 [BE]** After a non-dry sales-order batch, `plan_exception_service.snapshot` before and
  `generate_batch` after run over the touched product ids, with `source_documents` = the
  batch's SO numbers. Failure is logged, never fails the batch.
- **AC-V5-2 [BE]** After a non-dry purchase-order batch, active `scm_recommendation` PO lines for
  the same (product, supplier) are superseded (closed) exactly as `_supersede_crm_raised_pos`
  does for the upload, and `ProjectOrderInquiryService.relink_to_matching_lines(order_ids,
  trigger="autocount_ingest")` runs. Both best-effort.
- **AC-V5-3 [BE]** A canonical `partial` sales order counts as committed demand: either
  `SALES_ORDER_STATUS_MAP["partial"]` maps to `open` (recommended, see plan D6) or
  `scm.committed_v` + the upload's `live_statuses` admit `partially_delivered`. Pinned by a test
  that ingests a partial SO and reads `scm.committed_v`.
- **AC-V5-4 [BE]** Hooks never run on a dry run.
- **AC-V5-5 [T]** `planning_change_service.build_batch` is NOT run by ingest in v2 (needs the
  upload's `Diff`); recorded in the backlog with the trigger that would justify it.

## Group V7 - Line adoption at cutover (`tests/test_ingest_documents_v2_adoption.py`, plan D11)

- **AC-V7-1 [BE]** Given a sales order the xlsx upload created (header adopted by `so_number`,
  every line ref-less), when the first push carries lines that match by
  `(product_id, warehouse_id-or-NULL, outstanding)`, then each matched row keeps its id,
  gains `source_ref` = the payload line's DtlKey and `source_system='autocount'`, has its
  values restated from the payload, and a stock transfer / claim / GRN link that pointed at it
  still points at it. Same for purchase orders with `qty_received`.
- **AC-V7-2 [BE]** Given two ref-less rows with the same key, when two incoming lines match
  them, then position decides: incoming `line_number` order against the rows' `created_at, id`
  order.
- **AC-V7-3 [BE]** Given no outstanding match but exactly one remaining ref-less row for
  `(product_id, warehouse_id-or-NULL)`, then it is adopted (step 2). Given several, and the
  remaining ref-less row count equals the remaining incoming count, then position decides
  (step 3). Otherwise the incoming line is created and the leftover rows follow the existing
  delete-or-cancel rule.
- **AC-V7-4 [BE]** A row that already carries a `source_ref` is never adopted by another
  DtlKey; it matches by its own ref only (A3 rule unchanged).
- **AC-V7-5 [BE]** The verdict carries `lines: {adopted, created, updated, deleted,
  cancelled}` for every document record, on dry run too (dry run writes nothing).
- **AC-V7-6 [BE]** `line_number` is an optional int on every canonical line (SO, PO, SPO);
  a payload without it still adopts by steps 1-2 and falls back to payload order for step 3.
  Shipping-order row adoption (AC-V3-4) uses the same three steps.

## Group V6 - Definition of done

- **AC-V6-1 [T]** Full backend suite green on an EMPTY scratch database (CI rule).
- **AC-V6-2 [T]** `PLAN-autocount-cross-repo-contract.md` section 7 gains the v2 deviations;
  the shared-service session is told the release tag / version.
- **AC-V6-3 [T]** Permission grant sweep migration applied for `scm.shipping_orders.*`.
- **AC-V6-4 [T]** No FE change; DoD items 1, 4, 5 recorded as N/A in the PR.
