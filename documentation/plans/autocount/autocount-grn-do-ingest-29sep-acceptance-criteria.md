# UAC: AutoCount DO and GRN ingest, branch table, PO/SO line links (#1354, S2)

Companion to `PLAN-autocount-grn-do-ingest-29sep.md`. Every AC is pinned by a pytest in
`sorento_crm_backend/tests/` on Postgres (`tests/_pg_fixture.py`). Fixtures
`tests/fixtures/autocount/do_live_sample.json` and `grn_live_sample.json` recreate the live
payloads' field lists (issue #1354, orchestrator comment) with anonymised values.

## Endpoints and verdicts

- **AC-AG001** `POST /external/ingest/delivery_orders` with the DO sample (book `db1`) answers
  200, every record `created`, `source_ref` `db1:DO:{DocKey}`, one `orders` row per DocKey with
  one `order_lines` row per Details row.
- **AC-AG002** `POST /external/ingest/goods_receive_notes` with the GRN sample: every record
  `created`, one `picking_headers` row (`picking_type='goods_received'`, `picking_status=
  'approved'`, `source_system='autocount'`) per DocKey, one `picking_lines` row per Details row.
- **AC-AG003** Re-pushing the same sample answers `unchanged` for every record and moves no
  `updated_at` / `last_synced_at`.
- **AC-AG004** A push with a later `LastModified` and a changed field answers `updated`; the
  field changes; a kept line keeps its id; a dropped line is deleted; a new line is created.
- **AC-AG005** A push with an OLDER `LastModified` answers `unchanged` + `stale_ignored` and
  writes nothing, even when its content differs.
- **AC-AG006** A push with the SAME `LastModified` but different content answers `updated`.
- **AC-AG007** `Cancelled: "T"` answers `updated`; DO `is_cancelled=true`; GRN `is_cancelled=
  true` and `picking_status='cancelled'`; rows and lines stay.
- **AC-AG008** `?dry_run=true` answers the same verdicts and writes nothing.
- **AC-AG009** Per-record validation: a record with no `DocKey`, no `DocNo`, a bad `DocDate`, a
  line with no `DtlKey`, or two lines sharing a `DtlKey` is `failed` with the field named; the
  other records land.
- **AC-AG010** Envelope: no `book` or a bad `book` is 422 `INVALID_BODY`; over 1000 records is
  413 `BATCH_TOO_LARGE`; no `companyCode` and no binding is 422 `COMPANY_ANCHOR_REQUIRED`.
- **AC-AG011** An unresolved `ItemCode` or `Location` makes the record `retryable` with
  `errors["Details.N.ItemCode"]` / `errors["Details.N.Location"]`; nothing of it is written.
- **AC-AG012** A Details row with no `ItemCode` is not written as a line; `lines.skipped` counts
  it; warning `line_without_item`; the row stays in `source_record`.
- **AC-AG013** `POST /external/read/delivery_orders` / `goods_receive_notes` returns the stored
  typed values and lines for known refs and lists unknown and other-company refs in `not_found`.
- **AC-AG014** `GET /external/contract` answers version `2.7` and lists `delivery_orders`,
  `goods_receive_notes`, `branches`.
- **AC-AG015** The doors take the existing slugs: without `order_management.orders.edit` the DO
  ingest is 403; `branches` has no read door (404).

## Column groups

- **AC-AG020** DO header: `order_number`, `order_date`, `created_time`, `debtor_code`,
  `debtor_name`, `customer_id` (resolved), `agent`, `ship_via`, `ship_info`, `ref`, `ref_doc_no`,
  `remarks` (Remark1..4 joined), `description`, `doc_status`, `currency_code`, `currency_rate`,
  `subtotal_amount`, `tax_amount`, `total_amount`, `local_net_total` hold the sample's values.
- **AC-AG021** DO delivery block: `deliver_address` is the non-empty DeliverAddr1..4 joined by
  newline; `deliver_contact`, `deliver_phone` as sent.
- **AC-AG022** Identity and provenance: `source_book`, `doc_key`, `source_modified_at` (the naive
  LastModified read as Malaysia time), `source_record` equal to the record as sent, Details
  included.
- **AC-AG023** DO lines: `dtl_key`, `line_sequence` (Seq), `item_code`, `product_id`,
  `location_code`, `warehouse_id`, `description`, `quantity`, `foc_qty`, `uom`, `unit_price`,
  `discount_text`, `discount`, `total`, `batch_no`, `delivery_date`, `proj_no`, `your_po_no`,
  `your_po_date` hold the sample's values.
- **AC-AG024** GRN header: `creditor_code`, `creditor_name`, `supplier_do_no`, `purchase_agent`,
  `ref`, `remarks`, totals, identity columns hold the sample's values.
- **AC-AG025** GRN lines: `dtl_key`, `seq`, `item_code`, `qty` (exact), `quantity_picked` and
  `quantity_expected` (rounded), `unit_cost`, `line_total`, `destination_warehouse_id`,
  `batch_number_picked`, `our_po_no`, `our_po_date` hold the sample's values.
- **AC-AG026** An unresolved `DebtorCode` lands with `customer_id` null, the code kept, warning
  `customer_unresolved`.

## Link rules

- **AC-AG030** Without `FromDoc*` fields and with empty `RefDocNo` / `OurPONo` (the live
  shape), every line lands with its link null and `lines.unlinked` counts every line.
- **AC-AG031** A DO line carrying `FromDocType "SO"`, `FromDocNo`, `FromDocDtlKey` whose SO line
  exists (`source_ref` ending `:{DtlKey}`) gets `sales_order_line_id`; `lines.linked` counts it.
- **AC-AG032** The same with no matching SO line lands null, `from_*` kept, warning
  `so_line_unresolved`.
- **AC-AG033** A GRN line with `FromDocDtlKey` matching a PO line gets `po_line_id`; one matching
  an SPO allocation gets `spo_allocation_id`.
- **AC-AG034** A DO with `RefDocNo` naming one sales order gets `orders.sales_order_id`; the line
  link stays null. Naming none: warning `sales_order_unresolved`.
- **AC-AG035** A GRN line with `OurPONo` naming one purchase order gets `purchase_order_id` and
  `from_doc_type 'PO'`; the line link stays null; `spo_number_raw` is not written.
- **AC-AG036** A DO landed with an unresolved `FromDocDtlKey`, then the SO line arrives: the next
  non-dry DO batch (any document) fills `sales_order_line_id`.
- **AC-AG037** A later push of the same DO that now carries `FromDoc*` fields fills the link.

## Ownership rules

- **AC-AG040** A DO pushed over a row the tracking upload created (same DocNo, no `doc_key`) is
  adopted: `updated` + `adopted_by_doc_no`, same `orders.id`, `doc_key` set; `actual_delivery_date`,
  `pickup_time`, `transporter`, `transporter_id`, `driver_name`, `lorry_plate`, `checker`,
  `trips`, `delivery_days`, `kpi_warning`, `customer_ref`, `salesman`, `warehouse`,
  `delivery_remarks`, `delivery_remarks_cs`, `remarks_cs`, `order_status_id` unchanged.
- **AC-AG041** The adopted DO's existing lines are matched by (product, warehouse, quantity) and
  keep their ids; unmatched old lines are deleted.
- **AC-AG042** A later AutoCount update of an adopted DO leaves every tracking column unchanged.
- **AC-AG043** The tracking upload's Master sheet on an AutoCount-owned DO does not change
  `order_date`, `debtor_code`, `debtor_name`, `agent`, `is_cancelled`, `customer_id`; it still
  writes `remarks_cs`.
- **AC-AG044** A DocNo held by a row with a different `doc_key` is `failed` with `errors.DocNo`.
- **AC-AG045** A GRN pushed over an Excel-imported GRN of the same number is adopted; a legacy line
  linked to an SPO allocation whose (product, quantity) matches keeps its id and its
  `spo_allocation_id`.
- **AC-AG046** The DO detail import skips a row whose DO is AutoCount-owned, outcome
  `autocount_owned`.

## Deletion rules

- **AC-AG050** `/deletions` with a pushed DocKey inside the range: `deactivated`; the DO is
  `is_cancelled`, `source_vanished_at` set, row and lines still present.
- **AC-AG051** The same for a GRN: `picking_status='cancelled'`, `is_cancelled`, row stays.
- **AC-AG052** An unknown DocKey: `not_found`. A DocKey whose stored DocDate is outside the range:
  `failed`, `errors.doc_date`, nothing written.
- **AC-AG053** Repeating a deletion answers `deactivated` and writes nothing; `dry_run` writes
  nothing.
- **AC-AG054** A vanished DocKey pushed again is restored: `updated` + `restored`,
  `source_vanished_at` null, `is_cancelled` from the payload.
- **AC-AG055** Body errors: missing `doc_keys`, missing or inverted dates: 422 `INVALID_BODY`.

## Branch table

- **AC-AG060** `POST /external/ingest/branches` creates one `branches` row per record, keyed by
  (book, AccNo, BranchCode), with name and `source_record`.
- **AC-AG061** Re-push unchanged: `unchanged`; a renamed branch: `updated`.
- **AC-AG062** A DO with `BranchCode` + `DebtorCode` of a known branch stores `branch_code` and
  `branch_name`; an unknown one keeps the code, name null, warning `branch_unresolved`; an empty
  `BranchCode` warns nothing.
- **AC-AG063** A branch pushed (or renamed) after its DOs fills or refreshes their
  `branch_name`.
- **AC-AG064** A record without `BranchCode` is `failed` with `errors.BranchCode`.

## Migration

- **AC-AG070** The migration creates `branches`, adds every column in plan 2.2 to 2.5 (nullable)
  and the two partial unique indexes; downgrade removes them; one alembic head.
