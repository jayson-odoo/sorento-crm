# PLAN: ingest parity standardisation (xlsx / manual vs ESB)

Status: IN PROGRESS 2026-09-06. S0 green (1f38359d2 + 2fa492be3), S1 green (7b3f19e68), S2 green (e8659ee54, migration 476), S3 in progress; red tests for S0-S4 on the branch. Lane branch `feat/ingest-parity` on top of
`feat/autocount-document-ingest-v2` (PR #670) until #670 merges, then rebased onto main.
UAC: `ingest-parity-standardisation-acceptance-criteria.md` (same folder). Grill record:
`.lavish/ingest-parity-standardisation.html` (worktree-local).

## 0. Why

The captain: "I want Excel upload and ESB to behave exactly the same." Measured 2026-09-06 (two
Explore sweeps, file:line evidence in the grill): the ESB masters/document ingest re-derives
nothing the uploads derive (discontinued from `****`, dimensions, default supplier, reference
back-creation, container link), keys customers differently (code-only vs (code, name)), blanks
omitted fields where every other writer leaves them alone, drops accepted fields silently, and
writes through raw SQL so audit / embedding / `updated_at` never fire. The uploads themselves are
not consistent with each other either (warehouse xlsx case-insensitive, manual create exact).

Scope boundary (D21 = B): the ESB's AutoCount grant is 13 tables; delivery orders, GRNs, invoices
and stock stay upload-only and are untouched here.

## 1. Decisions (all final, from the grill)

| id | decision |
| --- | --- |
| D1 | Shared rules live in `app/services/rules/<entity>_rules.py` as pure functions over resolved values; both channels call them |
| D2 | `is_discontinued = flag if sent else description.startswith("****")` on every path; flag wins; true to false resets the notify watermark |
| D3 | Unknown category / UOM / brand on a product is created on both channels (`ensure_reference`); warnings `category_created` / `uom_created` / `brand_created`; blank UOM = configured default |
| D4 | Dimensions parsed on both channels with the parser extended for AutoCount forms; `Item.Desc2` arrives as a separate `remark`, never concatenated (xlsx keeps its Desc 2 concat) |
| D5 | Default supplier + lead time linked on ESB create/update exactly as the Excel import does (source = System Settings); `brand_code` on the payload, resolve-or-create |
| D6 | `spo_allocations.container_number` column; shared `extract_container_number` (strip `F-` prefix, `(BRAND)` suffix, Loading-Date-cell text after first space); shared `link_allocation_to_shipment`; relink job; SPO family = prefix OR flag |
| D7 | ESB SPO push runs GRN forward-match once per SPO at batch end; received guard reports `received_locked` |
| D8 | Both channels back-create a customer when code AND name are present, with segment + region when the source has them; otherwise `debtor_code` + `customer_unresolved` |
| D9 | Product unresolved = line dropped + reported on both; location unresolved = NULL + `warehouse_unresolved` on both; no more retryable for a missing product ref |
| D10 | ESB SO push writes the planning-change batch (BL-058 closed) |
| D11 | One SPO writer identity: adopt across `source_system` by (spo_number, product, location); sweep sees both |
| D12 | One lane, one PR; slices S0 to S4 |
| D13 | Customer identity on the masters push = lower-trimmed (code, name); never rename |
| D14 | Absent = untouched, null = cleared, on every master (pydantic `model_fields_set`); insert defaults follow manual create |
| D15 | Supplier contact/address block written (S0); `credit_limit`, `payment_terms_days` (customer) and `payment_terms_code` accepted-and-ignored with warning `deprecated_field` until S4 flips the contract endpoint to 2.1, then removed from the schemas (ESB sequencing ask 2026-09-06) |
| D16 | Payload gains AutoCount-owned fields only: customer `market_segment_code`, `region`; product `is_discontinued`, `remark`, `brand_code`; SPO `container_number`, `is_shipping_order`. CRM-owned judgement (warehouse planning config, category searchable/order, agent annotations) never touched by any ingest |
| D17 | One `upper(btrim())` code match for every master on every path; supplier suffix cleaning + ambiguity refusal shared. As built (S1): the ESB and the warehouse xlsx/manual paths ADOPT a case variant; a manual Create of a supplier / category / UOM that only differs by case or whitespace from an existing row is REFUSED as a conflict (surfacing beats silently editing another admin's row from a Create click) |
| D18 | Masters writer moves to the ORM upsert path (audit, embedding, company stamp, `updated_at`); agents `source='autocount'` |
| D19 | Importer-only review aids (trigram, width pre-check) stay importer-only; dry run stays a rolled-back real run; book-wide close-by-absence stays the deletion endpoint's job |
| D20 | `status` optional on every document payload; absent = shared `derive_document_status` (upload rules) |
| D21 | B: no grant widening; DO / GRN / stock stay uploads |
| D22 | AutoCount location on an SO line wins; Order Inquiry fills blanks only; conflicts listed on the worklist |

## 2. Design

### 2.1 Rules module

```
app/services/rules/
  __init__.py
  product_rules.py       is_discontinued(flag, description) ; parse_dimensions(description)
                         ; ensure_reference(db, model, code, company_id) ; link_default_supplier(db, product, settings)
  master_rules.py        normalize_code(code) = upper(btrim) ; clean_supplier_name(name) ; resolve_master_by_code(db, model, code, company_id)
                         ; resolve_supplier_by_name(db, name, company_id) -> id | Ambiguous
  customer_rules.py      customer_identity(code, name) ; back_create_customer(db, code, name, segment, region, company_id)
  document_rules.py      derive_document_status(lines, existing_status) ; line_status(header, ordered, delivered)
                         ; resolve_line_product(...) -> id | Dropped ; resolve_line_warehouse(...) -> id | None+warning
  shipping_order_rules.py extract_container_number(text) ; link_allocation_to_shipment(db, allocation, container)
                         ; received_guard(allocation, new_qty) -> ok | received_locked
```

Every function is pure over already-loaded rows or takes `db` for one lookup; none knows about
cells, payloads, previews or verdicts. Existing implementations MOVE here (no second copy): the
bodies come from `product_service` (`is_discontinued_from_description`, `parse_dimensions_from_description`,
`ensure_reference`, `link_default_supplier`), `outstanding_import_service` (`_clean_supplier_name`,
`_to_activate`/`lift`, `_complete_documents`), `po_history_service` (ambiguity refusal),
`import_tasks._spo_import_extract_container`, `procurement_service` (received guard),
`sales_agent_service.normalize_code` (already the shared normaliser; reused, not moved).

### 2.2 Callers

| channel | today | after |
| --- | --- | --- |
| product manual create/edit | `product_service.create_product` / `update_product` | call `product_rules` |
| product Excel import | `product_service.bulk_import_products` | call `product_rules` (same functions, moved) |
| ESB products | `master_ingest_service._product_columns` | call `product_rules` + `ensure_reference`, warnings on the verdict |
| warehouse / supplier / category / UOM manual + xlsx | per-service exact or lower match | `master_rules.resolve_master_by_code` |
| ESB masters | `_lookup_id` exact | `master_rules.resolve_master_by_code`; customers via `customer_rules.customer_identity` |
| outstanding SO/PO upload | own `_resolve`, `_resolve_parties`, `_to_activate` | `document_rules`, `customer_rules.back_create_customer` |
| ESB SO/PO | `MasterRefResolver` ladder | ladder keeps ref-first; code/name rungs call `master_rules` / `customer_rules`; status via `document_rules` when absent |
| SPO xlsx import | `_spo_import_extract_container`, direct link | `shipping_order_rules` |
| ESB SPO | `shipping_order_ingest_service` | `shipping_order_rules` + GRN forward match at batch end |

### 2.3 Masters writer (D14, D18)

`MasterIngestService._apply` builds `values` from `payload.model_fields_set` only (plus the
identity columns), then upserts through the ORM: `db.query(Model).filter(identity).first()`,
setattr the present fields, `db.add` on create. Company stamp comes from `CompanyScopedMixin`
(no more hand-stamped raw INSERT); audit listeners and the embedding listener fire on flush.
Savepoint-per-record and the verdict shapes are unchanged. Perf: measured after; budget 2x the
current 14.5s per 1,000 products.

Canonical schemas: every optional field `Optional[X] = None`; `is_active: Optional[bool] = None`
(insert default true applied in the writer); `decimal_places: Optional[int] = None`. Removed:
`CanonicalCustomer.credit_limit`, `.payment_terms_days`, `.payment_terms_code`,
`CanonicalSupplier.payment_terms_code`. Added: `CanonicalProduct.is_discontinued`, `.remark`,
`.brand_code`; `CanonicalCustomer.market_segment_code`, `.region`; `CanonicalSalesOrder.customer_segment`,
`.customer_region`, `status: Optional`; `CanonicalPurchaseOrder.status: Optional`;
`CanonicalShippingOrder.container_number`, `.is_shipping_order`, `status: Optional`.

### 2.4 Customer identity (D13)

`customer_rules.customer_identity(code, name) -> (lower(btrim(code)), lower(btrim(name)))`; the
masters ingest and the SO ladder's code rung both match on it. A new name under a known code
creates a row; `customer_name` is never in the update set. `integration_references` for customers
links the pair's row.

### 2.5 SPO container (D6, D11)

Migration `475_spo_allocations_container_number.py`: `ALTER TABLE spo_allocations ADD COLUMN
container_number VARCHAR(100) NULL` + index. Backfill script `scripts/backfill_spo_container_number.py`
from linked shipments. `link_allocation_to_shipment` = case-insensitive match on
`inbound_shipments.shipping_container_number`, any status. Relink: `InboundShipmentService.create_shipment`
post-commit calls `relink_allocations_for_container(container)`; a scheduled task does the same
nightly for NULL links. Adoption key across sources: `(company, spo_number, product_id,
coalesce(warehouse_id, location_code))`; the upload's `_write_spo_lines` and `_spo_lines_to_close`
drop their `source_system == SPO_UPLOAD_SOURCE` filter and use the key for the SPO numbers the
file names.

### 2.6 Status derivation (D20)

`derive_document_status(lines, existing)`: `cancelled` never derived; all lines settled
(delivered >= ordered or received >= ordered) = `closed`; else `open`; existing `draft` lifted
to `open` (SO) / `active` (PO) exactly as `_to_activate`. The outstanding upload replaces its
inline `_complete_documents` + `lift` with this call.

### 2.7 Order Inquiry collision (D22)

`project_order_inquiry_import_service` writes `warehouse_id` only where NULL. The ESB SO line
writer writes `warehouse_id` when the payload has a location; when it overwrites a non-NULL value
that differs, it appends `(so_number, line, previous, new)` to `order_inquiry_conflicts` (new
small table or a JSON column on the inquiry run) which the worklist renders.

### 2.8 Retirement (S4)

Delete `so_history_service.py`, `po_history_service.py`, `po_listing_reader.py` (if only they use
it), routes in `app/api/v1/scm/purchase_history.py` for sales-history / purchase-history apply
and preview, tasks `process_sales_history_import` / `process_po_history_import`, their tests, the
FE pages and sidebar entries. `supersede_crm_raised_pos` gains an idempotency check (already
superseded lines are skipped) with a test.

## 3. Slices

| slice | decisions | issue |
| --- | --- | --- |
| S0 masters ingest hygiene | D13, D14, D15, D18 | #690 |
| S1 shared resolver + product rules | D17, D2, D3, D4, D5, D16 (product fields) | #691 |
| S2 SO / PO rules | D8, D9, D10, D16 (customer fields), D20, D22 | #692 |
| S3 SPO rules | D6, D7, D11, D20 (SPO) | #693 |
| S4 retire + contract 2.1 | history importers, supersede idempotency, contract endpoint, guide | #694 |

Each slice: tester writes the red tests from the UAC ids, coder makes them green, parity test per
slice. Reviewer + security-reviewer + browser verification once at the end of the lane.

## 4. Contract v2.1 (for the ESB)

Additions: products `is_discontinued`, `remark`, `brand_code`; customers `market_segment_code`,
`region`; sales_orders `customer_segment`, `customer_region`; shipping_orders `container_number`,
`is_shipping_order`; `status` optional on all three documents.
Removals: customers `credit_limit`, `payment_terms_days`, `payment_terms_code`; suppliers
`payment_terms_code`. Suppliers' contact/address block now written.
Semantics: on masters, absent = untouched, null = cleared.
Warnings added: `category_created`, `uom_created`, `brand_created`, `segment_unknown`,
`lines.dropped`, `received_locked`, `container_unresolved`. `retryable` no longer answers a
missing product ref (line dropped instead).

## 5. Risks

- ORM writer slower than raw SQL: measured on the lane with the real 11.7k products; fallback is
  bulk `session.execute(insert(...).values([...]))` for creates only, keeping ORM for updates.
- Case-normalised matching exposes existing case-variant duplicates: the S1 report lists them for
  the captain before the rule lands; the rule never merges rows on its own.
- Dropping a line instead of retryable loses the automatic retry: accepted in D9; the ESB
  reconcile re-offers on hash change.

## 6. Out of scope, named

DO / GRN / stock / invoices (D21 B); non-AutoCount uploads (packing lists, container status,
proforma invoices, supplier stock, certificates, flyers, promotions, project docs); category
hierarchy and UOM conversion (absent in AutoCount); importer review aids (D19).

## 7. Test debt (close before the PR is marked ready)

- AC-P2-4: the red test spies `build_batch`; add a test asserting a real `planning_change_batches`
  row with one row per changed line once S2 is green.
- AC-P2-7: the red test uses one representative document; widen to the 30-document SO/PO fixture
  the UAC names, then run the same fixture on the lane DB (DoD 4).
- S2 migrations surfaced by the tester: `customers.region` (D16) and the `order_inquiry_conflicts`
  table (D22); S1: `products.remark` (D4); S3: `spo_allocations.container_number` (D6). One
  migration per slice, chained on main's head via `./scripts/alembic-reparent.sh` at PR time.
- `tests/test_ingest_documents_v2_hooks.py::TestPlanningChangeIsNotRunByIngest` guards the old
  D7 deferral and must be inverted when AC-P2-4 goes green.
- S3 finding (tester): `SPOAllocationCreate` (the SPO xlsx / n8n path) does not expose `currency`,
  so an upload-written allocation has NULL currency while the ESB writes one. Add `currency` to
  the xlsx writer in S3 (default the PO currency rule) so AC-P3-8 can stop excluding it.
- Parity fixtures in S0-S3 are representative (1-3 documents each); the 20/30-record fixtures
  the UAC names run as the lane-DB proof in S4 (DoD 4), not as unit tests.
