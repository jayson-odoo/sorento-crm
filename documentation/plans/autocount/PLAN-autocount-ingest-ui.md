# PLAN — AutoCount ingest targets + read-only mirror UI

> **Status:** ALL 8 SLICES DONE + gated (BE + FE, tests + Playwright). Pre-PR housekeeping done: (1) startup seeder `integration_ingest_grants.grant_ingest_permissions` auto-grants every external-ingest slug to the integration roles; (2) origin/main merged in, migration chain re-rooted 307_admin_listing_company → 302..309_autocount_so_po_pricing (SINGLE head, verified). 89 autocount pytest green post-merge. Committed on branch `fix/ingest-status-codes-and-dry-run` (af6beb67d + 526ead953). NOT pushed / no PR opened (awaiting user go).
> **Post-merge multi-company note:** the merge made orders/sales_orders/purchase_orders (+line tables) `CompanyScopedMixin`; the DO/SO/PO ingest services now stamp the header's `company_id` onto their raw-SQL line inserts. The NEW mirror tables (credit_terms, tax_codes, sales_agents, payment_methods, tax_entities, item_packages(+lines), stock_balance runs/rows, quotations(+lines), request_quotations(+lines)) are NOT `CompanyScopedMixin` — fine for the current single-company (Sorento) reality; **FOLLOW-UP** if AutoCount data must be partitioned per company, add company_id + the mixin + a migration to each.
> **Slice 8 notes:** SO/PO REUSE the SCM `sales_orders`/`purchase_orders` (they already carry `source_system`/`source_ref` — idempotency uses those columns directly, NOT integration_references). Migration 309 ALTERs the line tables (SO lines +8 pricing cols, PO lines +description/sub_total) and both headers (+source_doc_no/internal_note/follow_up). `SalesOrderService`/`PurchaseOrderService` 403 (`AUTOCOUNT_READ_ONLY`) on update/delete/create-do (SO) + create-gr (PO) when source_system='autocount'; `annotate()` is the carve-out. Serializers expose `source` (PO's now tri-state: autocount|recommendation|manual). External ingest slugs `scm.sales_orders.edit`/`scm.purchase_orders.edit` (new `_crud` registrations).
> **Slice 5 deviation:** the plan claimed "`orders` already has `sync_source`" — it does NOT (that column is on `CustomerContact`). Migration 306 ALTERs `orders` to add `sync_source` + the two annotation columns (`internal_note`, `follow_up`). integration_references `entity_type` MUST be a real table name (`orders`), because its existence check interpolates it into `SELECT 1 FROM {entity_type}`; a logical `delivery_orders` aborts the txn. DocKey stays unique so DO rows don't collide with other `orders` linkages.
> **Consumer-side of** shared-service slice 19/20 (`documentation/plans/sprint-4/20-sorento-autocount-ingest-targets.md`).
> **Builds on** `PLAN-autocount-integration.md` (Group A — per-integration keys, `/external` RBAC, `integration_references`, `master_ingest_service`, GRN-style docs). Reuse those primitives; do NOT re-invent.
> **Source of truth for payloads:** `Sorento/phase-2/autocount/API documentation.postman_collection.json` (fields quoted below are from the live collection, not the summary doc).

## Goal

Absorb 13 more AutoCount entities into Sorento as ingest targets (tables + `/external` ingest endpoints) **and** give each a read-only mirror UI in its natural business module, so staff can see AutoCount data inside the CRM without leaving it.

## Locked decisions (from grill round 1)

1. **UI mode = read-only + local annotations.** Ingested fields render read-only. Every ingested entity carries two Sorento-only, ingest-safe columns: `internal_note TEXT NULL`, `follow_up BOOLEAN NOT NULL DEFAULT false`. Ingest column-maps never write them, so they survive re-sync. Every entity gets a **list AND a detail page** (detail hosts the annotation editor).
2. **Placement = scatter into business modules** (not a dedicated AutoCount section). Map in §2.
3. **Reused tables = source-gate read-only.** `orders`, `sales_orders`, `purchase_orders` mix native + ingested rows. A uniform computed `source` field (`"autocount" | "manual"`) is added to each list/detail serializer. FE gates edit/delete on it: `source == "autocount"` → read-only + annotations; else full CRUD as today. Native create/edit paths untouched.
4. **Phasing = vertical slices by tier**, doc's build order. 8 PRs (§6). Each slice = model + migration + ingest spec/endpoint + FE list/detail + tests (pytest + vitest + one playwright), fully green before the next.
5. **Stock balance = run-history snapshots.** `stock_balance_snapshot_runs` (header per ingest run) + `stock_balance_snapshots` (rows FK to run). Append per run; FE run-selector compares runs. No per-row annotations (rows ephemeral); the run header carries `internal_note`/`follow_up` for parity.
6. **Reused ALTER columns surfaced read-only** in existing SO/PO detail line tables.

## Cross-cutting conventions (inherited, restated so no slice re-derives them)

- **PK** `id = UUID string` (`default=lambda: str(uuid.uuid4())`). **Timestamps** `created_at`/`updated_at` (`server_default=func.now()`, `onupdate`). **No `tenant_id`**.
- **Idempotency** via `integration_references(source_system='autocount', entity_type=<table>, source_ref=<key>, source_doc_no=<DocNo>)`, `UNIQUE(source_system, entity_type, source_ref)` + `UNIQUE(entity_type, entity_id)`. Key = `DocKey` for documents; `PackageCode` for item packages; snapshot **run** for stock balance. Do NOT add `source_system`/`source_ref` columns to NEW tables — use the side table. Reused SCM tables (`sales_order_lines`, `purchase_order_lines`) already HAVE `source_system`/`source_ref`; `orders` already has `sync_source` — reuse those for provenance on reused tables.
- **Booleans** `"T"`/`"F"` → real bool. **Money** `Numeric(15,2)`, **Qty** `Numeric(15,4)` — NEVER `Integer` (truncates fractional/negative AutoCount qty). **Dates** via `utils.parse_date_value`.
- **Design = reuse existing system components, do NOT invent a new look.** Lists use the shared `DataGrid` (`tableLayout: {width:'fixed', columnsResizable:true}`, `columnResizeMode:'onChange'`, explicit `size`, `truncate`+`title`) exactly like `products`/`orders`. Detail pages reuse the existing detail-page shell (same header/section/card layout as complaint / PR-SF / stock-inquiry detail — always render every section with empty states). The annotation editor (note + follow_up) reuses existing form controls (`Textarea`, `Switch/Checkbox`, shared `Button`), NOT a bespoke widget. Read-only fields render with the same label/value pattern already used across detail pages. No new design language for either list or form. Every new page keeps the FE layering (UI → hooks → feature service → `lib/api-client`), `extractApiError`, `buildDataGridParams`, `userSelectService`.
- **Masters** extend `master_ingest_service.ENTITY_SPECS` → free dry-run, per-record SAVEPOINT, adopt-by-code, verdict `{dry_run, summary, records:[{source_ref, outcome, entity_id, errors?, diff?}]}`, HTTP 200, `?dry_run=true`. **Documents** clone `app/api/v1/external/grn.py` (single/array body, resolve masters, 201, 400 on missing master).
- **Master resolution (docs):** `ItemCode→products.product_code` (missing = reject 400), `UOM→units_of_measure`, `Location→warehouses` (code or name), `DebtorCode→customers`, `CreditorCode→suppliers`, `TaxCode→tax_codes`.
- **Migrations run real DDL.** New-module tables are absent on legacy `create_all`-built DBs; every new table ships an Alembic migration with an explicit `op.create_table` (memory: new-module-table-legacy-createall-gap). Chain `down_revision` onto the committed head, not a WIP migration.
- **RBAC — two distinct wiring paths (CI-enforced), do not conflate:**
  - **Flat masters** (credit_terms, tax_codes, sales_agents, payment_methods, tax_entities) go into `ENTITY_SPECS`. `test_path_resolved_routes_cover_every_entity_they_serve` asserts `set(INGEST_PERMISSIONS) == set(ENTITY_SPECS)` AND `set(READ_PERMISSIONS) == set(ENTITY_SPECS)`. So each new master is a **4-place edit**: `ENTITY_SPECS` + `ingest.py:INGEST_PERMISSIONS` + `ingest.py:READ_PERMISSIONS` + the slug registered in `PERMISSION_REGISTRY` (`test_every_mapped_slug_exists_in_the_registry`). Miss one → red CI.
  - **Non-flat / documents** (item_packages, stock_balance, quotations, request_quotations, DO, and SO/PO reuse) are NOT in `ENTITY_SPECS`. Each gets its own router mounted under `/external/<prefix>` with an `EXTERNAL_ENDPOINT_PERMISSIONS[<prefix>]` entry (`test_every_mounted_prefix_has_a_mapping_entry` + `test_every_external_route_carries_a_permission_dependency` enforce the guard). Clone the GRN mount.
  - Each FE mirror page also needs a **view** slug in `PERMISSION_REGISTRY` (e.g. `master_data.tax_codes.view`, `order_management.quotations.view`) + a `menu.config.tsx` entry gated on it.

## 1. Provenance signal (shared, build once in PR1)

A single helper the list/detail serializers call so the FE gets a uniform `source`:

```
def resolve_source(entity_type, entity_id, *, sync_source=None, source_system=None) -> str:
    # reused tables: prefer their own column
    if sync_source and sync_source != "manual": return sync_source          # orders
    if source_system == "autocount": return "autocount"                     # SCM SO/PO
    # new tables: integration_references lookup
    if integration_reference_exists("autocount", entity_type, entity_id): return "autocount"
    return "manual"
```

Expose `source: "autocount" | "manual"` on every list row + detail response. FE `isReadOnly = source === "autocount"`. New tables are always `"autocount"` (only ingest creates them) — the field is still emitted for a uniform FE contract.

## 2. Entity → module → table map

| # | AutoCount entity | Module | Table(s) | Reuse/New | Ingest style |
|---|---|---|---|---|---|
| 1 | credit term | Master Data | `credit_terms` (new) | New | master |
| 2 | tax code | Master Data | `tax_codes` (new) | New | master |
| 3 | sales agent | Master Data | `sales_agents` (new) | New | master |
| 4 | payment method | Master Data | `payment_methods` (new) | New | master |
| 5 | tax entity | Master Data | `tax_entities` (new) | New | master |
| 6 | item package | Master Data | `item_packages` + `item_package_lines` (new) | New | master (parent+lines) |
| 7 | stock balance | Inventory | `stock_balance_snapshot_runs` + `stock_balance_snapshots` (new) | New | report/run |
| 8 | delivery order | Order Mgmt | `orders` + `order_lines` | Reuse | document (GRN clone) |
| 9 | quotation | Order Mgmt | `quotations` + `quotation_lines` (new) | New | document |
| 10 | request quotation | Procurement | `request_quotations` + `request_quotation_lines` (new) | New | document |
| 11 | sales order | Order Mgmt | `sales_orders` + `sales_order_lines` (ALTER lines) | Reuse+ALTER | document |
| 12 | purchase order | Procurement | `purchase_orders` + `purchase_order_lines` (ALTER lines) | Reuse+ALTER | document |

(item + item group already live: `products`, `product_categories`.)

## 3. New master tables — DDL + column map

All carry `id, created_at, updated_at, internal_note TEXT, follow_up BOOL DEFAULT false`. Adopt-by the unique business code.

**`credit_terms`** — unblocks supplier/customer `payment_terms_code`.
Wire: `{DisplayTerm, Terms, TermDays}`.
`display_term VARCHAR UNIQUE NOT NULL` (adopt key) · `terms VARCHAR` · `term_days INTEGER`.
After build: wire `_supplier_columns`/`_customer_columns` to resolve `payment_terms_code → credit_terms.display_term` (store `term_days` into existing `payment_terms_days`) instead of raising `MissingReference`.

**`tax_codes`** — resolve-target for doc-line `TaxCode`.
Wire: `{TaxCode, SupplyPurchase(S/P), TaxRate}`.
`tax_code VARCHAR UNIQUE NOT NULL` · `supply_purchase VARCHAR(1)` · `tax_rate NUMERIC(9,4)`.

**`sales_agents`** — ⚠ NOT `access_agents` (respond.io routing).
Wire: `{SalesAgent, Description, IsActive}`.
`sales_agent VARCHAR UNIQUE NOT NULL` (code==name) · `description VARCHAR` · `is_active BOOL DEFAULT true`.

**`payment_methods`**.
Wire: `{PaymentMethod, Description, BankAccount, JournalType, ...}`.
`payment_method VARCHAR UNIQUE NOT NULL` · `description VARCHAR` · `bank_account VARCHAR` · `journal_type VARCHAR`.

**`tax_entities`** — e-Invoice party. Wire (confirmed from GET response):
`{TaxEntityID, Name, IdentityNo, TIN/FullTIN, TaxBranchID, Address, PostCode, Phone, EmailAddress, TaxClassification, GSTRegisterNo, SSTRegisterNo, TradeName, TourismTaxRegisterNo, BusinessActivityDesc, MSICCode, City, StateCode, CountryCode}`.
`tax_entity_id VARCHAR UNIQUE NOT NULL` (adopt key; surrogate) · `tin VARCHAR` · `name VARCHAR` · `identity_no VARCHAR` · `tax_classification INTEGER` · `gst_register_no`/`sst_register_no`/`tourism_tax_register_no VARCHAR` · `trade_name VARCHAR` · `msic_code VARCHAR` · `business_activity_desc VARCHAR` · address block (`address, post_code, city, state_code, country_code, phone, email_address`).

**`item_packages` + `item_package_lines`** — parent+lines master.
Header wire: `{PackageCode, Description, ExpiryDate, LimitedQty, OpeningQty, UserUOM, BarCode, FurtherDescription}`.
`item_packages`: `package_code VARCHAR UNIQUE NOT NULL` (adopt key) · `description VARCHAR` · `expiry_date DATE` · `limited_qty NUMERIC(15,4)` · `opening_qty NUMERIC(15,4)` · `user_uom VARCHAR` · `bar_code VARCHAR` · `further_description TEXT`.
Line wire `PackageDTL[]`: `{ItemCode, UOM, Qty, UnitPrice}`.
`item_package_lines`: `item_package_id FK CASCADE` · `product_id FK products (resolve ItemCode, missing = reject the line's parent 400? — decide in grill Q3)` · `uom VARCHAR` · `qty NUMERIC(15,4)` · `unit_price NUMERIC(15,2)`.
Idempotency = `PackageCode` (no DocKey). Master-style verdict, but with child lines → needs a small parent+lines adopter (ENTITY_SPECS handles flat masters only; item_packages needs a bespoke spec or a doc-style endpoint — flag in grill Q4).

## 4. Stock balance — run-history snapshot (Inventory)

Report wire (bare array, no DocKey): per `{Location, ItemCode, UOM, BatchNo, Balance(signed), SmallestBalQty, StandardCost, TotalCost, AverageCost, Rate, Description, ReportUOM, LocationDesc, CostingMethodString, Shelf}`.

**`stock_balance_snapshot_runs`** (header): `id` · `captured_at TIMESTAMP` (run time) · `row_count INTEGER` · `source VARCHAR DEFAULT 'autocount'` · `internal_note TEXT` · `follow_up BOOL` · `created_at`.
**`stock_balance_snapshots`** (rows): `id` · `run_id FK CASCADE` · `product_id FK NULL` (resolve ItemCode; **missing ≠ reject** — keep raw `item_code`) · `warehouse_id FK NULL` (resolve Location) · `item_code VARCHAR` (raw, always) · `location_code VARCHAR` · `uom VARCHAR` · `batch_no VARCHAR` · `balance NUMERIC(15,4)` (signed!) · `smallest_bal_qty NUMERIC(15,4)` · `standard_cost/total_cost/average_cost NUMERIC(15,2)` · `rate NUMERIC(15,4)` · `description VARCHAR`.
Endpoint: `POST /external/ingest/stock_balance` — creates ONE run, bulk-inserts rows. Not `integration_references` (append semantics). Index `(run_id, product_id)`, `(run_id, warehouse_id)`.
FE: run selector (latest default) → read-only grid; optional prior-run compare.

## 5. New/reused document tables

**quotation → NEW `quotations` + `quotation_lines`.** Header (from GET): `{DebtorCode*, DebtorName, DocNo, DocDate, Cancelled, Attention, BranchCode, DeliverAddr1-4, terms, SalesAgent}`. `QTDTL[]`: `{ItemCode→product_id reject, UOM, Location, Qty, UnitPrice, SubTotal, DiscountAmt, TaxCode, TaxRate, Tax, Description, FurtherDescription, PackageCode, ProjNo, DeptNo}`. Idempotency `DocKey`. `so_number`-analog `quote_number = AC-{DocKey}`, `source_doc_no = DocNo`.

**request quotation → NEW `request_quotations` + `request_quotation_lines`** (⚠ NOT `purchase_requests`). Header `{CreditorCode*→supplier_id, DocNo, DocDate, PurchaseAgent}`. `RQDTL[]`: `{ItemCode→product_id reject, UOM, Location, Qty, UnitPrice, SubTotal}`. Idempotency `DocKey`.

**delivery order → REUSE `orders` + `order_lines`** (cleanest). **Verified `order_lines` cols:** `quantity, unit_price, discount, tax, total, total_excluding_tax, total_including_tax, warehouse_id, line_sequence` (NO `discount_amount`/`tax_amount`/`warehouse` string — those are on a different class). Header→`orders` (`order_number=AC-{DocKey}`, `DebtorCode→customer_id` + debtor_code/name, `Cancelled→is_cancelled`, agent string, `sync_source='autocount'`). `DODTL[]`→`order_lines` (`ItemCode→product_id` reject, `Location→warehouse_id` **NOT NULL reject**, `Qty→quantity`, `UnitPrice→unit_price`, `DiscountAmt→discount`, `Tax→tax`, `SubTotal→total`). Mirror GRN endpoint helpers directly.

**sales order → REUSE `sales_orders` + ALTER `sales_order_lines`.** Lines currently lack pricing. **ALTER add:** `unit_price NUMERIC(15,2)`, `discount_amt NUMERIC(15,2)`, `tax_rate NUMERIC(9,4)`, `tax_amt NUMERIC(15,2)`, `sub_total NUMERIC(15,2)`, `delivery_date DATE`, `uom VARCHAR`, `tax_code VARCHAR`. Header: `DebtorCode→customer_id`, `so_number=AC-{DocKey}`, `source_doc_no=DocNo`, `DocDate→order_date`, `source_system='autocount'`. `SODTL[]`: `Qty→qty_ordered`, `TransferedQty→qty_delivered`, `UnitPrice→unit_price`[new], DeliveryDate/Tax/Discount[new]. Surface new cols read-only in existing SO detail.

**purchase order → REUSE `purchase_orders` + ALTER `purchase_order_lines`** (has `unit_cost`, `expected_date`; add `description VARCHAR`, `sub_total NUMERIC(15,2)`). Header `CreditorCode→supplier_id`, `po_number=AC-{DocKey}`, `DocDate→issue_date`, `Cancelled→status`, `source_system='autocount'`. `PODTL[]`: `ItemCode→product_id` reject, `Location→warehouse_id`, `Qty→qty_ordered`, `UnitPrice→unit_cost`. Surface read-only in existing PO detail.

## 6. Build order (8 slices / PRs)

| PR | Scope | Notes |
|---|---|---|
| 1 | `credit_terms` + `tax_codes` + provenance helper (§1) | Unblock supplier/customer `payment_terms_code`; tax_codes = doc-line resolve target. Full stack + wire supplier/customer resolution. |
| 2 | `sales_agents`, `payment_methods`, `tax_entities` | Flat masters via ENTITY_SPECS. |
| 3 | `item_packages` + `item_package_lines` | Parent+lines master (bespoke adopter). |
| 4 | `stock_balance_snapshot_runs` + `stock_balance_snapshots` | Run-history; run-selector UI. |
| 5 | delivery order → `orders`/`order_lines` | GRN-endpoint clone; source-gate read-only in existing Orders UI. |
| 6 | `quotations` + `quotation_lines` | New document + UI. |
| 7 | `request_quotations` + `request_quotation_lines` | New document + UI. |
| 8 | sales order + purchase order (ALTER + surface) | Reuse + ALTER; read-only cols in existing SO/PO detail. |

## 7. Per-slice deliverables (Definition of Done)

- BE: model + Alembic migration (real DDL) + ingest spec/endpoint matching the two-way verdict/GRN contract + `source` in serializer.
- FE: list page (DataGrid, `tableLayout: fixed`, resizable, explicit `size`, `truncate`+`title`, `buildDataGridParams`, `extractApiError`) + detail page (all sections always rendered, empty states) + annotation editor (note + follow_up) + read-only gating on `source`. Menu entry + view permission slug.
- Tests: pytest (ingest happy + auth denial + validation/missing-master 400 + adopt-by-code + dry-run), vitest (list + detail loading/empty/error/data + read-only gating), one playwright (sidebar → list → detail → annotate → save).
- Verify in prod build via Playwright MCP before handoff.

## 8. Internal grill (round 2) — resolutions

Verified against code; each resolved unless marked **[USER]** (needs your call in grill round 3).

- **Q1 (annotation on reused rows) → RESOLVED: add the two columns to `orders`/`sales_orders`/`purchase_orders`.** Matches new tables, cheap, ingest already writes only mapped cols so they're safe. (Side table rejected — extra join for no gain.)
- **Q2 (source-gate scope) → RESOLVED: block ALL mutating actions** (edit form, line CRUD, cancel/archive/status) when `source == "autocount"`. Enforce BE-side too (a 403 in the header/line mutation routes when the row is AutoCount-sourced), not FE-only — FE gating is UX, BE is the guard.
- **Q3 (missing master in child) → RESOLVED:** item_packages **reject the whole parent** on a phantom `ItemCode` (a package with a non-existent item is corrupt); stock_balance **keep raw `item_code`/`location_code`**, `product_id`/`warehouse_id` NULL (it's a report, partial resolution is expected).
- **Q4 (item_packages ingest path) → RESOLVED: bespoke parent+lines adopter with its own `/external/ingest-item-packages` router + `EXTERNAL_ENDPOINT_PERMISSIONS` entry**, NOT `ENTITY_SPECS` (which is flat-only — verified: `EntitySpec.to_columns` returns a scalar dict, no line handling). Keep the master-style dry-run/verdict shape for parity.
- **Q5 (list_query registration) → RESOLVED: register each list in `list_query_registry`** (model + response schema + serializer). Gets DataGrid column personalization + `buildDataGridParams` for free, consistent with existing listings. The `source` field (§1) is a serialized column.
- **Q6 (number display) → RESOLVED: `DocNo` (`source_doc_no`) is the primary human column; `AC-{DocKey}` is the stable internal id, not shown** (no-UUIDs-in-UI rule; DocKey is surrogate-ugly). Search matches both.
- **Q7 (menu volume) → RESOLVED [USER]: flat top-level entries** under each module (5 Master Data reference masters as siblings of products/UOM/brands, no "Reference" subgroup).
- **Q8 (NEW, from grill — RBAC coupling) → RESOLVED:** the 4-place edit for flat masters + dedicated-router path for non-flat is now spelled out in Cross-cutting §RBAC. Per-slice DoD (§7) must add "coverage tests green" explicitly. This is the single most likely CI-breaker — the same class as the `test_external_permission_coverage` failure just fixed on PR #34.
- **Q9 (NEW, from grill — DO column names) → RESOLVED:** corrected §5 DO mapping to the real `order_lines` columns (`discount`/`tax`/`total`, not `discount_amount`/`tax_amount`). Re-verify each reused table's actual columns at slice start; the summary doc's column names were not all accurate.

## 9. Residual risk / watch-list

- **Discount semantics:** live wire uses `DiscountAmt` (numeric amount) + separate `TaxRate`/`Tax`, resolving the summary doc's "bare string, amount-vs-percent ambiguous" friction. Treat `DiscountAmt` as an absolute amount. Confirm on first live sync.
- **`UDF[]` per line** (DriverName etc.) and **per-UOM `ItemDTL` / `PackageDTL` on doc lines** have no Sorento home — drop for now, JSONB later if needed. Note in the contract back to the ESB so it knows what's dropped.
- **Alembic head:** 8 slices = 8+ migrations; each `down_revision` must chain onto the prior slice's COMMITTED head (memory: migration-downrev-uncommitted-ancestor). Watch for dual-head after any merge with `main`.
- **`sales_order_lines` ALTER** adds 8 columns to an SCM table also used by the reorder engine — confirm no reorder code assumes the old column set (grep `sales_order_lines` usage before ALTER).
