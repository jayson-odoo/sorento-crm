# PLAN: AutoCount document ingest, contract v2 (xlsx-import parity)

**Status:** APPROVED 2026-09-05. Grilled via Lavish; the captain took the recommended option
on every decision (D1, D2, D3, D4, D6a, D7, D10, and D5/D8/D9 as written). Slices S0-S6 in
progress on `feat/autocount-document-ingest-v2`. **UAC:** `autocount-document-ingest-v2-acceptance-criteria.md` alongside.
**Requested by:** foundryx-shared-service session, addendum
`foundryx-shared-service/documentation/plans/sprint-5/02-autocount-document-mapping-sorento-addendum.md`.
The ESB gates every new key behind `sorento_contract_version = 2` on its consumer connection.
**Baseline:** origin/main f240d015; `PLAN-autocount-cross-repo-contract.md` section 3 (A3).
**Classification:** CORE (see UAC). **Phase 1 (FE mock):** NOT APPLICABLE, no UI surface.
**Branch (proposed):** `feat/autocount-document-ingest-v2`, backend only, worktree
`.claude/worktrees/autocount-ingest-v2`.

## 0. What already exists (measured, so nothing is rebuilt)

| Ask in the addendum | State on main | Consequence |
| --- | --- | --- |
| 5. `/ingest/{entity}/deletions` for documents | **Already built** for `sales_orders` and `purchase_orders`: `deletion_service.ENTITY_MODELS` is masters + `DOCUMENT_SPECS` (`deletion_service.py:112-121`), two-stage line probe, `cancelled` in place when referenced. Tests `test_ingest_deletions.py:461-544`. | Only `shipping_orders` is new work. |
| 3. `shipping_orders` entity | No header table exists. A shipping order is a GROUP of `spo_allocations` rows keyed `(company_id, spo_number, spo_line_number)` (`procurement.py:400-509`, unique `uk_spo_allocations_company_spo_line`). Header-ish columns (`supplier_id`, `issue_date`, `expected_date`, `currency`) live per row. No `source_ref` column. | The entity is a line-set, not header + lines. Two columns added (D3). |
| 1. back-create supplier / agent | `supplier_back_create.back_create_supplier` + `supplier_slug` (`scm/supplier_back_create.py:42,64`); `sales_agent_service.resolve_or_create` (`scm/sales_agent_service.py:100`). | Reused as is. |
| 1. back-create customer | No helper. Identity is the `(code, name)` PAIR per company (`uq_customers_company_code_name_lower`, `order.py:151-171`). Precedent `order_service._upsert_customer_from_debtor` (`order_service.py:1721`). | Small new helper, pair-keyed (D2). |
| 2. demand classification | `_classify_demand` ladder in `outstanding_import_service.py:862-955`; `demand_class.class_of`; `_segment_of` :766. All keyed on the upload's `_Resolved`. | Ladder is extracted into a function both callers use (D4). |
| 4. `from_so_numbers` claims | `order_link_service.claim_book_pairing` :248 + `resolve` :63. `source` is a CHECK constraint (`scm.py:1178`), `autocount` not admitted. | One migration (458 pattern) + constant. |
| 6. committed demand | `scm.committed_v` (migration 428 body) predicate `so.status = 'open' AND sol.line_status = 'open'`. `partially_delivered` falls out; so does `_existing_lines` (`live_statuses=("open",)`). | Decision D6. |
| 7. hooks | All exist as functions on the upload path, several keyed on upload-only objects (`_Resolved`, `Diff`). | Called where the signature allows; `planning_change` deferred (D7). |
| contract version endpoint | Nothing under `/external` exposes a version. `test_external_permission_coverage.py` demands a permission dependency or a `PATH_RESOLVED_PREFIXES` entry on every external route. | New route, fixed slug (D8). |
| permission slugs | `scm.sales_orders.*` / `scm.purchase_orders.*` created + swept by migration `445_autocount_grant_sweep.py`. | Copy for `scm.shipping_orders.*`. |

## 1. Decisions to grill (each with the recommendation; the user rules)

- **D1. Resolution order and what "created" means.** Ref, then code (upper/trim, anchor
  company), then name (supplier only), then back-create for supplier / agent / customer;
  products and warehouses never created. Recommendation: as the addendum asks, mirroring the
  upload, PLUS report every creation in `warnings` so the ESB's log shows what Sorento minted.
  Open question for the ESB: it should ALWAYS send `*_ref` next to code/name so the created row
  can be registered under it; Sorento will not mint a ref it was not given (no `DatabaseName`
  to build one from).
  **As built (S1, approved 2026-09-05):** a ref that is SENT but unresolved falls through to
  code/name/back-create when either is also present, rather than failing the record outright -
  sending more identifying information must never make a push worse off than sending the ref
  alone; the ref is then linked to whatever resolves, so the next push is step 1. `ReferenceConflict`
  gained an optional `field_name` (default `"source_ref"`) so a cross-company MASTER ref
  (`customer_ref`, `supplier_ref`, ...) files its verdict error under its own key instead of
  always under `source_ref`.
- **D2. Customer back-create identity.** The upload does NOT create customers (keeps the code
  on the header, links nothing). The addendum asks to create. Recommendation: create only when
  BOTH `customer_code` and `customer_name` are present (the unique index is on the pair;
  a code-only row would collide with a later named one), pair-matched first, no market
  segment. Code-only lands unlinked with `debtor_code` written, as the upload does today.
- **D3. Shipping-order identity and shape.** No header table. Recommendation: add
  `spo_allocations.source_ref` (line DtlKey) and `spo_allocations.source_doc_ref` (header
  DocKey). Header lookup = rows with `source_doc_ref = DocKey` in the anchor company, else
  adopt rows with `spo_number = DocNo AND source_doc_ref IS NULL` (xlsx-era rows). Line upsert
  by `source_ref`; absent lines CLOSED in place (never deleted: GRN lines and claims point at
  them and the upload never deletes either). `integration_references` is NOT used for
  shipping-order identity (it needs one entity_id per ref and there is no header row); the
  header verdict's `entity_id` is `null` and read-back is keyed by `source_doc_ref`. Alternative
  considered: a new `shipping_orders` header table. Rejected: nothing reads one, and every
  consumer (`on_order_v`, GRN matching, claims) is keyed on `spo_allocations`.
- **D4. Demand ladder extraction.** Pull the four-step ladder out of
  `outstanding_import_service._classify_demand` into `scm/demand_class.py` (or a sibling that
  may import models) as `classify_document(db, *, stored_order_type, stated_order_type,
  agent_demand_class, debtor_code, company_id) -> Optional[str]`, and have the upload call it.
  Recommendation: yes, one ladder, two callers; the upload's refuse-the-file behaviour stays in
  the upload, ingest lands + warns.
- **D5. `SPO-` numbers under `purchase_orders`.** Refuse per record (`failed`). Recommendation:
  yes; the guard is one `doc_family()` call.
- **D6. Committed demand for `partial` sales orders.** Two options. (a) Map canonical
  `partial` -> stored `open` for sales orders; the per-line `qty_delivered` already carries the
  partial fact; read-back reports `open`. Zero view changes; every SCM reader that keys on
  `status = 'open'` keeps working. (b) Widen `committed_v`, `_existing_lines`
  `live_statuses`, and audit every other `sales_orders.status = 'open'` reader. Recommendation:
  **(a)**, recorded as a v2 deviation (`partially_delivered` stays a valid stored status for
  the CS side, ingest just never writes it). The ESB then emits `partial` freely.
  **As built (S5):** option (a). `SALES_ORDER_STATUS_MAP["partial"] = "open"`; the map is no
  longer injective, so `_canonical_status` returns the FIRST canonical word whose mapping
  matches the stored value (`open`, declared before `partial`) - a stored `open` row always
  reads back `open`, never `partial`. `PURCHASE_ORDER_STATUS_MAP` untouched.
- **D7. Hooks.** Run per batch after commit, best-effort, never on dry run: SO -> plan-exception
  snapshot/generate_batch over touched products; PO -> supersede CRM-raised POs (refactor
  `_supersede_crm_raised_pos` to take `(product_id, supplier_id, po_number)` triples so both
  callers share it), `relink_to_matching_lines(trigger="autocount_ingest")`, link claims (V4).
  SPO -> close-by-absence is WITHIN the pushed document only (a push is per document; the
  book-wide close the upload does is the ESB's deletion call). `planning_change_service.build_batch`
  needs the upload's `Diff` of `Line`s; recommendation: defer to backlog with trigger "the
  captain asks why an ingested SO changed the plan and there is no change batch to show".
- **D8. Contract endpoint guard.** `GET /api/v1/external/contract` guarded by
  `require_external_permission("master_data.products.view")`? No: recommendation is a new
  `integration.contract.read` slug (registered in `NEW_INTEGRATION_PERMISSIONS`, prefix
  `contract` in `EXTERNAL_ENDPOINT_PERMISSIONS`, granted to every role that holds
  `scm.sales_orders.edit` by the same sweep migration). Response
  `{"version": 2, "entities": sorted(SUPPORTED_ENTITIES)}`.
- **D9. Warnings vocabulary.** Fixed strings: `customer_created`, `customer_unresolved`,
  `supplier_created`, `agent_created`, `unclassified_demand`, `warehouse_unresolved` (D10).
  Recommendation: module constants in `document_ingest_service`, listed in the cross-repo plan
  section 7.
- **D10. Unresolvable warehouse on a line (asked by the ESB 2026-09-05).** Today a SENT
  `warehouse_ref` that does not resolve makes the record `retryable` (A3). The ESB asks for
  `warehouse_id = NULL` + `warnings: ["warehouse_unresolved"]` instead, because the warehouse
  is optional and an unlocated line is a supported state (`scm` nets unlocated demand;
  `spo_allocations` keeps `location_code` when no warehouse matches). The upload SKIPS such
  a row on SO/PO and NULLs it on SPO. Recommendation: accept for v2 (ref and code alike), keep
  `location_code` on SPO rows, and record it as a v2 deviation since it changes v1 behaviour
  for a bad `warehouse_ref` (the ESB is the only caller). Products stay retryable.

- **D11. Adopt xlsx-era lines at cutover instead of replacing them (ESB ask, 2026-09-05,
  from their captain's review).** Today `_sync_lines` treats every ref-less line of a header
  adopted by number as stale: deleted, or cancelled in place when referenced, and the payload's
  lines are inserted fresh. Every allocation, claim and GRN link then hangs off a cancelled
  row. Revised rule, applied ONLY to ref-less lines of a header adopted by number (a line that
  already carries a `source_ref` matches by it, as today): (1) match an incoming line to one
  remaining ref-less line by `(product_id, warehouse_id-or-NULL, outstanding)` where
  outstanding = `qty_ordered - qty_delivered|qty_received` on the row and
  `qty_ordered - qty_delivered|qty_received` on the payload; tie-break by position
  (`line_number` order vs `created_at, id` order); (2) else by `(product_id,
  warehouse_id-or-NULL)` when exactly one such row remains; (3) else by position among the
  remaining ref-less rows when counts agree; (4) a matched row keeps its id: `source_ref` =
  DtlKey stamped on the COLUMN (lines are never in `integration_references`, that is the A3
  rule), `source_system = 'autocount'`, values restated from the payload; (5) the true
  remainder follows the existing delete-or-cancel rule; (6) the verdict carries
  `lines: {adopted, created, updated, deleted, cancelled}`, same on dry run. **Why not
  `qty_ordered` in the key:** the upload writes `qty_ordered = outstanding` and
  `qty_delivered = 0` on an open line it inserts (`outstanding_import_service.py:2297-2298`)
  and `qty_ordered = fulfilled + outstanding` on update (:2364), so `qty_ordered` on an
  xlsx-era row is not AutoCount's Qty; the OUTSTANDING figure is what both sides agree on.
  New optional wire field `line_number` (int, AutoCount Seq) on every line, used for position
  only (no column exists on `sales_order_lines` / `purchase_order_lines`; the SPO
  `spo_line_number` keeps its own sequence). Same three steps drive SPO row adoption in 2.4.
  Recommendation: accept; slice S1b.

**ESB answers received 2026-09-05** (shared-service session): Q1 the ESB always sends `*_ref`
next to code/name; Q2 code-only customers stay unlinked; Q3 vocabulary accepted plus
`warehouse_unresolved`; Q4 `agent_code` on PO/SPO accepted-and-ignored is fine; Q5 fine;
Q6 claims with the resolved `product_code`, unresolved SO numbers still claimed; Q7 hooks as
proposed, `planning_change` deferred, book-wide SPO close-by-absence stays theirs via
`/ingest/shipping_orders/deletions`. D6 option (a) accepted: they will emit `partial` once v2
ships. Contract endpoint + slug accepted.

## 2. Design

### 2.1 Schema additions (`app/schemas/canonical_documents.py`)

All optional, `extra="forbid"` unchanged, so a v1 payload is untouched (AC-V0-2).

```
CanonicalSalesOrder      += customer_code?, customer_name?, agent_code?, order_type?
CanonicalPurchaseOrder   += supplier_code?, supplier_name?, agent_code?   (agent_code accepted, ignored: PO has no agent FK; documented)
_CanonicalLine           += product_code?, product_name?, warehouse_code?
CanonicalPurchaseOrderLine += from_so_numbers?: list[str]
CanonicalShippingOrder:  source_ref*, spo_number*, supplier_ref?, supplier_code?, supplier_name?,
                         issue_date?, expected_date?, currency?, status*, lines[]
CanonicalShippingOrderLine: source_ref*, product_ref?, product_code?, product_name?, warehouse_ref?,
                         warehouse_code?, qty_ordered*, qty_received?, unit_cost?, uom?, expected_date?,
                         from_so_numbers?
```

`product_ref` becomes optional on every line ONLY in the sense that `product_code` may stand in
for it; a validator requires at least one of the two (`product_ref or product_code`).
`product_name` is accepted and unused (a typo must never become a SKU); documented.

### 2.2 Resolution (`document_ingest_service._resolve_ref` grows a ladder)

```
_resolve_master(field, *, ref, code, name, model, back_create: Callable | None) -> tuple[id | None, warnings]
  1. ref  -> refs.resolve + _require_same_company (today's path; unresolved SENT ref is
             MissingReference -> retryable, unchanged)
  2. code -> query model where upper(btrim(code_col)) == norm(code) [and company_id == anchor
             for company-scoped models]; shared sales_agents via sales_agent_service.resolve
  3. name -> supplier only: upper(cleaned name) == supplier_name, order_by id desc (upload rule)
  4. back_create -> supplier: back_create_supplier(code=code or supplier_slug(name), name=name or code)
                    agent: resolve_or_create(code)
                    customer: new customer_back_create.get_or_create(db, code, name) pair-keyed
     then, if `ref` was sent: refs.link(entity_type, new_id, ref) so the next push is step 1.
  Products / warehouses: steps 1-2 only; a miss on a SENT code is MissingReference (retryable).
```

Rule kept from A3: everything resolves before anything is written. Back-creates happen inside
the record's savepoint, so a later failure in the same record takes the created master with it.
Dry run: created masters are rolled back with everything else (AC-V1-10).

`sales_orders.debtor_code` = `normalize_debtor_code(customer_code)` whenever `customer_code` is
sent (fill AND restate, the upload restates it).

### 2.3 Demand classification (`scm/demand_class.py` grows `classify_document`)

Called from `_header_values` for `sales_orders` only, after refs resolve:
`stored order_type` (existing header) -> payload `order_type` (fill-only write to `order_type`)
-> agent's `demand_class` -> customer segment (`_segment_of` moved next to it). Result written
to `demand_class` when not None; never blanked; `unclassified_demand` warning otherwise.

### 2.4 Shipping orders (`document_ingest_service` gains a third spec, different write shape)

`DocumentSpec` assumes header + line models. A shipping order has one model. Rather than bend
`DocumentSpec`, a small `ShippingOrderIngest` (same `ingest()` signature, same `RecordResult`)
lives in `app/services/shipping_order_ingest_service.py`, and `ingest.py` dispatches on the
entity name as it does between masters and documents. Write path per record:

1. resolve supplier (ladder), products, warehouses for every line first;
2. rows = `spo_allocations` where `company_id = anchor AND (source_doc_ref = DocKey OR
   (spo_number = DocNo AND source_doc_ref IS NULL))`;
3. match by `source_ref` (DtlKey); unmatched ref-less rows adopted by `(product_id,
   upper(location_code))` in `spo_line_number` order (the upload's own occurrence rule);
4. insert new rows with `spo_line_number = max + 1..`; update matched rows; close the rest;
5. per row: `allocated_quantity`, `quantity_received`, `receipt_status`, `line_status` derived
   exactly as `_write_spo_lines` (`outstanding_import_service.py:1516-1550`), `source_system =
   'autocount'`, `source_ref`, `source_doc_ref`, `supplier_id`, `issue_date`, `expected_date`,
   `unit_cost`, `currency` (default CNY), `location_code`, `warehouse_id`;
6. `from_so_numbers` -> claims (2.5).

Read-back: rows grouped by `source_doc_ref`. Deletions: `deletion_service` gains a
`shipping_orders` branch (rows by `source_doc_ref`; unreferenced -> delete, referenced ->
`closed`, verdict `deactivated`). `integration_reference_service.SUPPORTED_ENTITY_TYPES` is NOT
extended (D3).

Migration: `spo_allocations.source_ref VARCHAR(255) NULL`, `source_doc_ref VARCHAR(255) NULL`,
index `(company_id, source_doc_ref)`, partial unique `(company_id, source_ref) WHERE source_ref
IS NOT NULL`.

### 2.5 Links (`from_so_numbers`)

After lines are flushed: for each line with `from_so_numbers`, for each number,
`claim_book_pairing(company_id=anchor, so_number, po_number, item_code=product.product_code,
source=SOURCE_AUTOCOUNT, po_line_id | spo_allocation_id)`, dedupe within the record, then
`resolve(db, so_numbers=...)`. Migration: recreate `ck_scm_order_link_claim_source` with
`'autocount'` (copy `458_scm_claim_crm_supply_source.py`), constant `SOURCE_AUTOCOUNT` in
`order_link_service`.

### 2.6 Hooks (route level, after `db.commit()`, non-dry only)

`ingest.py` collects from the service `touched_product_ids`, `written_header_ids`,
`(product_id, supplier_id, po_number)` triples, then:

- `sales_orders`: `plan_exception_service.snapshot` is taken BEFORE the batch (route calls the
  service for the product ids of the payload's lines by code/ref before ingest; cheap), and
  `generate_batch(..., source_documents=so_numbers)` after commit.
- `purchase_orders`: `supersede_crm_raised_pos(db, triples)` (extracted from the upload's
  `_supersede_crm_raised_pos`, which becomes a thin adapter), then
  `ProjectOrderInquiryService.relink_to_matching_lines(header_ids, trigger="autocount_ingest")`.
- each wrapped `try/except -> logger.warning`, committed separately.

### 2.7 Contract endpoint

`GET /api/v1/external/contract` in `app/api/v1/external/contract.py`, guarded by the fixed slug
from D8. Body `{"version": 2, "entities": [...]}`. Version constant `CONTRACT_VERSION = 2` in
`ingest.py`.

### 2.8 Verdict `warnings`

`RecordResult.warnings: list[str]`, emitted only when non-empty (`as_dict`). Set on every path
above.

## 3. Slices (tracer bullets, each TDD, backend only)

| id | scope | ACs | blocked by |
| --- | --- | --- | --- |
| S0 | `warnings` on `RecordResult`; v1 golden test; contract endpoint + slug + sweep migration (also seeds `scm.shipping_orders.*`); `autocount` claim source migration | V0-1..3, V3-1 (slugs), V4-3 | - |
| S1 | code/name ladder + back-create supplier/agent/customer + `debtor_code` + CNY default | V1-1..10 | S0 |
| S1b | line adoption at cutover (D11): three-step match of ref-less lines, `line_number` wire field, `lines` counts on the verdict | V7-1..6 | S1 |
| S2 | `classify_document` extraction, upload rewired onto it, SO ingest classification + warning | V2-1..7 | S1 |
| S3 | `spo_allocations` columns migration; `ShippingOrderIngest` ingest/read/deletions; `SPO-` guard on PO | V3-2..8, D5 | S1 |
| S4 | `from_so_numbers` claims on PO + SPO lines | V4-1,2,4 | S3 |
| S5 | hooks (plan exceptions, supersede extraction, relink) + D6 status mapping + committed_v test | V5-1..5 | S2, S4 |
| S6 | review (`reviewer` + `security-reviewer`, external ingest surface), empty-DB full suite, section 7 deviations, PR, tell the ESB the tag | V6-1..4 | S5 |

Each slice: `tester` writes the red tests from the UAC ids first, `coder` (one, kept alive)
makes them green, in the worktree. Tests on Postgres only; seed every chain
(`tests/_pg_fixture.blank_session`, the `test_ingest_documents._Env` pattern).

## 4. Testing seams (agreed before Phase 2)

- `_resolve_master` is pure given a session: tested directly for the ladder order with seeded
  masters, no HTTP.
- `classify_document` tested with four seeded states; the upload's existing tests must stay
  green after rewiring (they are the parity proof).
- `ShippingOrderIngest` tested through the real app (`test_ingest_documents.env` pattern) so
  permissions, anchor and dispatch are covered.
- Hooks tested by asserting the side tables (`scm.plan_exception_batch`, superseded PO line
  status, `projects.order_inquiry_links`) after a route call, with the hook services NOT mocked.

## 5. Out of scope / backlog

- `planning_change_service.build_batch` on ingest (D7; trigger recorded).
- Book-wide close-by-absence (the ESB owns deletions).
- Any FE surface for `warnings` (the ESB log is the surface; revisit if the captain asks where
  created suppliers came from: the existing supplier list already shows them).
- Notifications on ingest.

## 6. Order of work

S0 -> S1 -> S2 -> S3 -> S4 -> S5 -> S6. S2 and S3 could run in parallel lanes once S1 is
merged; S4 and S5 are sequential on S3.
