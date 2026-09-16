# UAC: ingest parity standardisation (xlsx / manual vs ESB)

Status: DONE 2026-09-06, merged with PR #699 (approved the same day from the Lavish grill `.lavish/ingest-parity-standardisation.html`, all
recommended options; D5 / D6 / D20 per captain markup; D21 = B; D22 = A).
Plan: `PLAN-ingest-parity-standardisation.md` (same folder).

## Journey

**Actor:** the planner who today drops the AutoCount exports into Sorento (product listing,
warehouse listing, debtor listing, outstanding SO book, outstanding PO/SPO book, SPO allocation
file) and who, after the ESB cutover, stops uploading because the ESB pushes the same books
every few seconds.

1. They open a product, a sales order, a purchase order or an SPO allocation. They do not know,
   and must not need to know, which channel wrote it.
2. The record looks identical either way: a product whose AutoCount description starts with
   `****` is discontinued, its dimensions are parsed, its category / UOM / brand exist, its default
   supplier is linked; an SPO whose reference names a container carries that container and is
   linked to the inbound shipment when one exists; a sales order whose debtor is unknown is
   handled the same way on both channels.
3. When the two channels touch the same document, the later write wins and the earlier channel's
   row is adopted, never duplicated.
4. The only decision the planner makes is on the upload preview screen, exactly as today. The
   ESB makes none.
5. Nothing else changes for anyone: the demand engine, reorder, dealer kit and the MCP tools read
   the same columns.

**Principle:** one rule function per behaviour, in one module, called by both channels. A channel
may differ only in what it receives (a cell vs a payload field), never in what it derives.

Scope boundary (D21 = B): the ESB's AutoCount grant covers 13 tables. Delivery orders, GRNs,
invoices and stock balances stay upload-only; nothing in this UAC touches those importers except
the retirement of the SO / PO history importers (superseded by the ESB's 3-year load).

## Tags

`[BE]` backend, `[T]` test, `[C]` contract change the ESB must implement, `[M]` migration.

## Phase S0: masters ingest hygiene

- **AC-P0-1 [BE][T]** (D13) Given company C holds customers `(301-S007, "ALPHA")` and
  `(301-S007, "BETA")`, when the ESB pushes customer `code=301-S007 name="BETA"`, then the row
  named BETA is updated and ALPHA is untouched; when it pushes `code=301-S007 name="GAMMA"`, then
  a third row is created and neither existing row is renamed. Identity is the lower-trimmed
  (code, name) pair, the same key `customer_import_service`, manual create and
  `customer_back_create` use.
- **AC-P0-2 [BE][T]** (D14) Given a warehouse with `location="Rack 4"` and `is_active=false`, when
  the ESB pushes `{code, name}` only, then `location` stays "Rack 4" and `is_active` stays false.
  When it pushes `{"location": null}`, then `location` is cleared. Applies to every optional
  column of every master (customers, suppliers, agents, warehouses, categories, UOMs, products):
  absent = untouched, null = cleared. `is_active` on insert defaults true; on update it is written
  only when sent.
- **AC-P0-3 [BE][T]** (D14) Given UOM `kg` with `decimal_places=3`, when the ESB pushes `kg`
  without `decimal_places`, then it stays 3. Given sales agent `A01` with `person_label="Ah Seng"`,
  when the ESB re-pushes `A01` without `person_label`, then the label stays.
- **AC-P0-4 [BE][T]** (D15) When the ESB pushes a supplier with `contact_name`, `address_line1`,
  `address_line2`, `city`, `state`, `postal_code`, `country`, then every one of those lands on the
  supplier row. Customer `credit_limit` / `payment_terms_days` and `payment_terms_code` on
  any master keep being accepted and ignored during S0 to S3 with warning `deprecated_field`
  (the ESB's live tasks still emit them and its sink switches payloads on the contract version);
  in S4, when `GET /external/contract` flips to 2.1, they are removed from the schemas and a push
  carrying them fails with a field-named 422 (extra=forbid), never silently dropped and never
  retryable.
- **AC-P0-5 [BE][T]** (D14) Given a supplier created by the ESB without `payment_terms_days`,
  then `payment_terms_days` is 30 (the manual-create default), not NULL.
- **AC-P0-6 [BE][T]** (D18) When the ESB creates or updates any master, then an `audit_logs`
  row exists for the change (same entity type the manual edit writes), the embedding change
  listener fires for embedded entities (customers, products), `updated_at` is stamped on update,
  and an ESB-created sales agent carries `source='autocount'`.
- **AC-P0-7 [T]** Parity test: the same master fixture (one row per entity, then a second push
  with two fields changed and one omitted) goes through the manual create/update service and
  through the ESB masters ingest into two companies; a row-by-row diff of every mapped column is
  empty apart from ids, timestamps and `source`.

## Phase S1: shared resolver and product rules

- **AC-P1-1 [BE][T]** (D17) Given warehouse `BRW` exists, when the xlsx warehouse import, the
  manual create, or the ESB pushes `brw` / ` BRW `, then all three adopt the existing row. Same
  for supplier, category, UOM and product codes on every path. A one-off report lists existing
  rows that differ only by case/whitespace before the rule lands.
- **AC-P1-2 [BE][T]** (D17) When the ESB masters push or the manual create names supplier
  `"ACME (RMB)"`, then the currency suffix is stripped the way the outstanding upload strips it,
  and when the cleaned name is held twice the push is refused as ambiguous with both codes named,
  the way `po_history_service` refuses.
- **AC-P1-3 [BE][T]** (D2) `is_discontinued = explicit flag if sent else description starts with
  ****` on the manual create, the manual edit, the Excel import and the ESB push. Given
  `is_discontinued=false` sent with a `****` description, then discontinued is false (flag wins).
  Given no flag and a `****` description, then true. Flipping true to false resets
  `discontinued_notified_at` and `discontinued_notify_batch_id` on both channels.
- **AC-P1-4 [BE][T][C]** (D3) When the ESB pushes a product whose `category_code`, `uom_code` or
  `brand_code` is unknown, then the reference is created (`code = name = raw value`, as
  `ensure_reference` does) and the product lands with warning `category_created` /
  `uom_created` / `brand_created`. A blank `uom_code` resolves to the configured default UOM,
  as the upload does. No product is retryable for a missing reference any more.
- **AC-P1-5 [BE][T]** (D4) The dimension parser accepts `880x450x220MM`, `(600X470X430MM)`,
  `1000x500` (2-D, height NULL), mixed `x`/`X`, optional parentheses and MM suffix; both channels
  write `length_mm`/`width_mm`/`height_mm` (existing columns) from the description. Golden set:
  10 real AutoCount descriptions with expected values, written as failing tests first.
- **AC-P1-6 [BE][T][C]** (D4) The ESB product payload gains optional `remark` (AutoCount
  `Item.Desc2`); it is stored on the product's remark column (or a new nullable `remark` column if
  none exists) and is never concatenated into `description`. The xlsx import keeps its Desc 2
  concatenation.
- **AC-P1-7 [BE][T]** (D5) When the ESB creates a product, then a `product_suppliers` row for the
  tenant's default supplier with the default standard lead time exists, exactly as after the
  Excel import; when it updates a product, the default row's lead time is refreshed the way the
  import refreshes it. When no default supplier is configured, nothing is linked on either channel.
- **AC-P1-8 [BE][T][C]** (D5) The ESB product payload gains optional `brand_code`; both channels
  resolve-or-create the brand and set `products.brand_id`.
- **AC-P1-9 [T]** Parity test: 20 real product rows (fixture from the AED_SORENTO listing,
  including `****`, dimension, brand and blank-UOM cases) through the Excel import and through the
  ESB push into two companies; column diff empty apart from ids / timestamps / `remark` (xlsx
  concatenates, ESB stores separately, by decision).

## Phase S2: sales order and purchase order rules

- **AC-P2-1 [BE][T]** (D8) When the outstanding SO upload names a debtor code AND name that does
  not exist, then the customer is back-created (same `customer_back_create.get_or_create`), the
  preview and the apply report count it, and the order links to it. Code without name: the order
  lands with `debtor_code` and warning / row note `customer_unresolved`, same as the ESB.
- **AC-P2-2 [BE][T][C]** (D8, D16) The ESB customer payload gains optional `market_segment_code`
  (AutoCount `Debtor.DebtorType`) and `region` (`Debtor.AreaCode`); the sales_orders payload gains
  optional `customer_segment` / `customer_region` used only when back-creating. An unknown
  segment spelling is dropped with warning `segment_unknown`, folding through the same FK lookup
  the customer importer uses. A segment already set by hand is never overwritten (fill-only).
- **AC-P2-3 [BE][T]** (D9) On both channels: a line whose product does not resolve is dropped
  and reported (`lines.dropped` on the ESB verdict, a row problem on the preview); the rest of the
  document lands. A line whose location does not resolve is kept with `warehouse_id` NULL and
  warning `warehouse_unresolved` on both. The ESB no longer answers retryable for a missing
  product ref.
- **AC-P2-4 [BE][T]** (D10) After a non-dry ESB sales_orders batch, one
  `planning_change_batches` row exists built from the same before/after line `Diff` the upload
  builds, with one row per changed line; a dry run writes none.
- **AC-P2-5 [BE][T][C]** (D20) `status` is optional on the SO and PO payload. When absent, the
  shared `derive_document_status(lines, existing)` applies the upload's rules: all lines settled
  = closed, otherwise open; an existing draft is lifted to placed. The outstanding upload calls
  the same function. When sent, the canonical word wins as today.
- **AC-P2-6 [BE][T]** (D22) Given an SO line whose warehouse was set by the Order Inquiry sheet,
  when the ESB pushes the line with an AutoCount location, then the AutoCount location wins and
  the disagreement appears on the inquiry worklist; when the ESB pushes the line without a
  location, then the inquiry's warehouse stays. The inquiry sheet never overwrites a non-NULL
  warehouse.
- **AC-P2-7 [T]** Parity test: the existing xlsx-vs-ingest proof (`parity_xlsx_vs_ingest.py`
  shape) becomes a pytest on the blank_session substrate: the same 30-document SO/PO fixture
  through the outstanding upload and through the ESB push; line-level diff empty.

## Phase S3: shipping order rules

- **AC-P3-1 [BE][M][T]** (D6) `spo_allocations` gains `container_number VARCHAR(100) NULL`.
  Migration is additive; a backfill script fills it from `inbound_shipments.shipping_container_number`
  for rows already linked.
- **AC-P3-2 [BE][T][C]** (D6) One shared `extract_container_number(text)` returns `WHSU8488069`
  for `F-WHSU8488069 (MOCHA)`, `TRHU4104785` for `TRHU4104785`, and the text after the first space
  for the SPO xlsx Loading Date cell; the ESB shipping_orders header gains optional
  `container_number` (raw `PO.Ref`). Both writers store the cleaned value on every allocation of
  the document and call one `link_allocation_to_shipment` that sets `inbound_shipment_id` when a
  shipment with that container exists; no match = warning `container_unresolved`, never a failure.
- **AC-P3-3 [BE][T]** (D6) A nightly / on-shipment-create relink fills `inbound_shipment_id` on
  allocations whose `container_number` now matches a shipment; the packing-list and n8n shipment
  writers call it after creating a shipment.
- **AC-P3-4 [BE][T]** (D7) After a non-dry ESB shipping_orders batch,
  `forward_match_grn_lines_for_spo_best_effort` runs once per SPO number touched (end of batch,
  not per row). An allocation with `quantity_received > 0` is not reduced below its received
  quantity by an ESB push; the line is reported `received_locked` and the rest of the document
  lands.
- **AC-P3-5 [BE][T]** (D11) The SPO xlsx import adopts an ESB-written allocation by
  `(spo_number, product, location)` and the ESB adopts an upload-written one the same way; the
  upload's close-by-absence sweep considers rows of both `source_system` values for the SPO
  numbers the file names. No duplicate open allocation for one real SPO line after any sequence
  of upload / push / upload.
- **AC-P3-6 [BE][T][C]** (D20) `status` optional on the shipping_orders payload; absent derives
  from lines via the same shared function (all allocations received = closed, else open).
- **AC-P3-7 [BE][T]** (D6) The ESB's SPO family test on the Sorento side (`doc_family`) accepts
  a document as SPO when the number starts with `SPO-` OR the payload says `is_shipping_order`
  (from `UDF_ShipOrder`); the outstanding book keeps prefix-only because it has no flag.
- **AC-P3-8 [T]** Parity test: the SPO fixture through the SPO xlsx import and through the ESB
  push; diff empty including `container_number` and `inbound_shipment_id`.

## Phase S2b: unclassified demand (D23, captain 2026-09-06)

- **AC-P2-8 [BE][T]** (D23) Given an outstanding SO book containing a document whose agent has
  no demand class and whose customer has no market segment, when it is previewed and applied,
  then the file is NOT refused: the document lands with `demand_class` NULL, the preview and the
  apply report list it under `unclassified_documents` (count + capped document numbers), and the
  ESB push of the same document lands with warning `unclassified_demand`, as today. Parity test:
  the same unclassified document through both channels yields identical rows.

## Phase S1b: product column convention (D24, captain 2026-09-06)

- **AC-P1-10 [BE][T][C]** (D24) Given an ESB product push with `code=SRTWT2114-NL` and
  `name="****SORENTO TWO WAY WATER TAP"` and no `description`, when it lands (create or update),
  then `product_name = "SRTWT2114-NL"`, `description = "****SORENTO TWO WAY WATER TAP"`,
  `is_discontinued = true`, and dimensions are parsed from that description. The Excel import of
  the same item (Item Code + Description columns) yields identical columns. A push carrying
  `description` uses it and ignores `name` for the text.

## Phase S4: retire and clean up

- **AC-P4-1 [BE]** The SO history and PO history importers (`so_history_service`,
  `po_history_service`, their routes and tasks) are removed; their tests deleted; the sidebar
  entries removed; a note in the SCM guide says closed history now arrives through the ESB.
- **AC-P4-2 [BE][T]** `supersede_crm_raised_pos` runs once per document regardless of channel
  (a PO pushed by the ESB and then uploaded does not supersede twice; the second run is a no-op).
- **AC-P4-3 [C]** `GET /api/v1/external/contract` answers `version: 2.1` listing the added
  fields, the removed fields, the absent-vs-null rule and the new warning vocabulary
  (`category_created`, `uom_created`, `brand_created`, `segment_unknown`, `lines.dropped`,
  `received_locked`, `container_unresolved`).

## Definition of done (every slice)

1. Rule lives in `app/services/rules/<entity>_rules.py`, both channels import it, no second copy.
2. Red tests first (tester), then green (coder); parity test per slice on the blank_session
   substrate with two companies.
3. Existing ingest suites and upload suites green; CI empty-DB run green.
4. Lane DB proof: the ESB re-pushes SIM masters + documents and the SPO fixture; DB diff against
   an xlsx upload of the same books is empty.
5. Guide-writer updates the SCM upload guide and the integration contract page.
