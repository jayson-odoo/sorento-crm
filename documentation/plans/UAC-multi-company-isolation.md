# UAC - Multi-Company Data Isolation (Sorento + Mocha)

**Companion to:** `PLAN-multi-company-isolation.md`
**Status:** Pre-code. Every AC must be self-verified on the stated side(s) end-to-end before handoff.
**Legend:** `[BE]` backend/pytest · `[FE]` frontend/vitest+playwright · `[E2E]` full FE→BE→DB · `[MCP]` MCP/n8n path · `[MIG]` migration/data.

Convention: **Given / When / Then**. An AC passes only when the Then is observed against the **real stack** (not mocks) for the side marked, per the three-phase loop (mocks in Phase 1, real in Phase 2).

---

## Group A - Company management & governance

- **AC-A1** `[FE][BE]` Given a superadmin, When they open **System Management → Companies**, Then they see a DataGrid of companies (Sorento seeded) with Add/Edit; a non-superadmin gets no nav entry and a 403 on the API.
- **AC-A2** `[BE]` Given the `companies` table, Then it has `id, name, code, is_active, autocount_ref (nullable), logo_url (nullable), created_at`; `code` is unique.
- **AC-A3** `[FE][BE]` Given superadmin creates a company "Mocha" (code `MCH`), Then it persists and immediately appears as a switch target for superadmin.
- **AC-A4** `[BE]` Given any non-superadmin principal, When they POST/PUT/DELETE `/companies*`, Then 403 (create/edit/grant management is superadmin-only).
- **AC-A5** `[FE]` Given the Company create/edit form, Then it works at ~375px width and is scrollable to the submit button (mobile-modal rule).

## Group B - User grants, switcher, persistence

- **AC-B1** `[BE]` Given `user_companies` grant M2M, Then `(user_id, company_id)` is unique; a user with grants {Sorento, Mocha} has two rows.
- **AC-B2** `[FE][E2E]` Given a user granted 2 companies, When logged in, Then a company switcher renders top-right showing only their granted companies (superadmin sees all).
- **AC-B3** `[FE]` Given a user granted exactly 1 company, Then the switcher is hidden and that company is auto-active.
- **AC-B4** `[E2E]` Given active company = Sorento, When the user switches to Mocha, Then `POST /companies/switch` fires, the JWT re-mints with `active_company_id=Mocha`, and every subsequent list shows Mocha data without a full re-login.
- **AC-B5** `[E2E]` Given a user last active in Mocha, When they log out and log back in, Then they land in **Mocha** (persisted `users.last_active_company_id`). Repeat with Sorento → lands Sorento.
- **AC-B6** `[BE]` Given a JWT whose `active_company_id` is NOT in the user's grants (tampered/stale), When any request arrives, Then it is rejected/re-resolved - never honored as scope.
- **AC-B7** `[E2E]` Given two browser tabs, one active Sorento one active Mocha, Then each tab's lists stay on their own company (claim-in-token, not a shared server row).
- **AC-B8** `[BE]` Given the NextAuth `jwt` callback at sign-in, Then it fetches grants + last-active from backend `GET /companies/my-context` (backend = SoT; grants NOT duplicated in Prisma).

## Group C - Read scoping (owned data, UI)

- **AC-C1** `[E2E]` Given active company = Sorento, When the user opens Products / Stock / Warehouses / Orders / Promotions / Packing Lists / SPO / GRN / Suppliers / Customers / resource Files, Then **only Sorento rows** appear; switching to Mocha shows only Mocha rows.
- **AC-C2** `[E2E]` Given Sorento "CHAIR-01" and Mocha "CHAIR-01" both exist, Then Sorento-active sees exactly one (Sorento's) and Mocha-active sees exactly one (Mocha's) - never both, never the other's.
- **AC-C3** `[BE]` Given ANY `db.query(Model)` on an owned table under an active-company scope, Then the emitted SQL contains `company_id IN (...)` automatically (via `do_orm_execute` reading `db.info["company_scope"]`) - no per-endpoint opt-in.
- **AC-C4** `[E2E]` Given the in-CRM AI assistant used by a Sorento-active staff, When it answers "show stock", Then it returns Sorento stock only (rides the same scope, no contact resolution).
- **AC-C5** `[E2E]` Given a stock-balance / order-analytics / complaint-analytics view (raw-SQL paths), Then results are company-scoped identically to the ORM lists (manually-scoped blind spots verified).

## Group D - Write scoping, edit, delete & imports

- **AC-D1** `[E2E]` Given active company = Mocha, When the user creates any owned row (product, promotion, warehouse…), Then the persisted row has `company_id = Mocha` with no explicit company field in the form (auto-stamp on insert).
- **AC-D2** `[E2E]` Given active = Sorento, When the user uploads an AutoCount Excel / DO / SPO import, Then every created row (products, orders, stock_ledger, GRN, packing lists) is stamped Sorento; switching to Mocha and re-uploading stamps Mocha.
- **AC-D3** `[BE]` Given an import enqueued while active = Mocha, Then the import-job row snapshots `company_id = Mocha` at enqueue, and the worker stamps rows from that snapshot (worker has no request context).
- **AC-D4** `[BE]` Given an X-API-Key/system write to an owned table with scope = `None` and no explicit `company_id`, Then the write is **rejected** (never inserts a null-company owned row).

### Edit / delete are company-scoped for EVERY owned entity (IDOR guard)

Applies to **all 34 owned tables** (Group J list) that expose GET-by-id / PUT / PATCH / DELETE - enumerate each in Phase 2 and assert the matrix below per entity. The central filter must apply to the row-load of a mutation-by-id, so a cross-company id is simply *not found in scope*.

- **AC-D5 (same-company edit)** `[E2E]` Given active = Mocha and a Mocha-owned row, When the user edits it (modal/detail PUT), Then the update succeeds and `company_id` is unchanged (immutable - the auto-stamp does not re-home it).
- **AC-D6 (cross-company edit denied)** `[E2E][BE]` Given active = Sorento, When the user attempts GET-by-id / PUT / PATCH on a **Mocha** row's id (direct API call or forged request), Then it returns **404 not-found** (scoped load misses it) - never 200, never a silent cross-company mutation.
- **AC-D7 (same-company delete)** `[E2E]` Given active = Mocha and a Mocha-owned row, When the user hard-deletes it via the AlertDialog confirm, Then the row is gone (hard delete per ADR) and only within Mocha.
- **AC-D8 (cross-company delete denied)** `[E2E][BE]` Given active = Sorento, When the user attempts DELETE on a **Mocha** row's id, Then **404 not-found**, and the Mocha row still exists afterward (verified by re-query as Mocha).
- **AC-D9 (bulk edit/delete stay in scope)** `[E2E]` Given a bulk edit/delete selection, When executed, Then it affects **only** active-company rows even if the payload id list is tampered to include another company's ids (each id re-checked against scope; out-of-scope ids no-op/404, count reflects only in-scope).
- **AC-D10 (child/line mutations scoped)** `[BE]` Given a line/child row (order_lines, picking_lines, promotion_products, inbound_shipment_lines, purchase_order_lines, sales_order_lines, customer_contacts, storage_zones, product_suppliers), When edited/deleted by id cross-company, Then 404 - line tables carry their own `company_id`, so direct-by-id mutation is scoped without a parent join.
- **AC-D11 (company_id not user-writable)** `[BE]` Given any create/update payload that includes a `company_id` field (owned entity), Then the server ignores/rejects the caller-supplied value and uses the active-company scope - a client cannot move a row to another company by sending `company_id`.

## Group E - Global & shared buckets

- **AC-E1** `[E2E]` Given a Sorento-active staff, When they open Complaints / Stock Inquiries / Purchase Requests / IT Tickets / SLA lists, Then they see **all** rows regardless of company (forms + SLA are global - accepted).
- **AC-E2** `[BE]` Given the `stock_inquiries`, `purchase_requests`, `purchase_request_lines`, `approval_tokens`, `view_tokens`, `order_statuses`, `attachment_types` tables, Then none carry a `company_id` column.
- **AC-E3** `[E2E]` Given a contact belonging to {Sorento, Mocha}, When their contact record is viewed by either company's staff, Then it is visible to both (shared, M2M-tagged).
- **AC-E4** `[FE]` Given the frontend UI anywhere, Then no `company_id` UUID is shown raw - company is rendered as name/code (no-UUID-in-UI rule).

## Group F - n8n / MCP tri-state scoping

- **AC-F1** `[MCP]` Given an MCP data tool called with **no** `contact_id`/`space_id`, Then it returns **all companies'** rows (backward-compat, scope=`None`).
- **AC-F2** `[MCP]` Given a tool called with `contact_id`+`space_id` resolving to a Mocha-only contact, Then only Mocha rows return; resolving to a Sorento+Mocha contact returns the **union**.
- **AC-F3** `[MCP]` Given `contact_id`+`space_id` present but NOT resolvable to a contact, Then **zero rows** (fail-closed) - not all.
- **AC-F4** `[MCP]` Given the same contact asks products, stock, orders, promotions, packing-list/incoming-stock, and resource attachments, Then all are scoped consistently to that contact's companies.
- **AC-F5** `[MCP]` Given `contact_id`+`space_id` are supplied by n8n, Then they are **deterministically bound from the Respond webhook payload** (verified they are NOT LLM-authored tool args).
- **AC-F6** `[BE]` Given the extended contact resolver, Then `resolve_contact_access_codes(respond_io_id, space_id)` returns the contact's `company_ids` (workspace-scoped join on `space_id`).

### AC-F7 - EXHAUSTIVE per-tool matrix (every MCP tool, both param states)

`[MCP]` **Every tool in the MCP `CATALOG` is tested in all four cells below - no sampling.** Build a parametrized test that iterates the catalog; a new tool added without a matrix entry fails the suite (mirrors the AC-H2 new-table guard, MCP side).

For each **company-scoped** tool (product/stock/order/promotion/attachment/warehouse/incoming-stock/customers/lookup families):

| Call | Expected |
|---|---|
| **no** `contact_id`/`space_id` | all-company rows (scope `None`) |
| `contact_id`+`space_id` → Sorento-only contact | Sorento rows only |
| `contact_id`+`space_id` → Mocha+Sorento contact | union of both |
| `contact_id`+`space_id` present but **unresolvable** | 0 rows (fail-closed) |

Enumerated company-scoped tools to cover (from catalog): `crm_master_products_list`, `crm_master_brands_list`, `crm_master_product_categories_list`, `crm_master_units_of_measure_list`, `crm_master_product_attachments_list`, `crm_marketing_promotions_list`, `crm_marketing_promotion_products_list`, `crm_marketing_promotion_attachments_list`, `crm_resource_attachments_list`, `crm_resource_attachments_catalogue`, `crm_resource_attachments_current_stock_list`, `crm_inventory_stock_balance_list`, `crm_inventory_warehouses_list`, `crm_order_management_orders_list`, `crm_order_management_orders_by_product_list`, `crm_order_analytics`, `crm_incoming_stock_by_product`, `crm_incoming_stock_shipments`, `crm_incoming_stock_list`, `crm_master_customers_list` (debtors), `crm_lookup_resolve`.

- **AC-F8 (global tools unaffected)** `[MCP]` Given a **global-bucket** MCP tool (`crm_complaints_list`, `crm_complaint_analytics`, `crm_sla_conversation_tracking_*`, `crm_forms_management_forms_list`, `crm_system_tool_capabilities_summary`, `crm_portal_link_get`), When called **with** or **without** `contact_id`/`space_id`, Then results are identical and unfiltered by company (these are global/contact-keyed, not owned) - the params must NOT accidentally start scoping them.
- **AC-F9 (write/action tools)** `[MCP]` Given write/action tools (`crm_it_support_ticket_create`, `crm_complaint_close`, `crm_order_cancel`, `crm_purchase_request_approve`, `crm_purchase_request_reject`): the created/affected entity's company behavior is asserted - form-creates land global; an action on an owned entity (order cancel) by id resolves within the caller's contact company scope, or 404 if out of scope (no cross-company action).

## Group G - Attachment binding endpoints (resource-derived scope)

- **AC-G1** `[BE][MCP]` Given an n8n binding call (packing-list create / product-attachment bind / promotion-attachment bind / form-create-with-attachment) with an attachment whose `company_id = Mocha`, Then the target entity is matched **only within Mocha**; a Sorento entity with the same code/number is never bound.
- **AC-G2** `[BE]` Given a binding call where no matching entity exists in the attachment's company, Then it **fails** (does not fall through to another company's row).
- **AC-G3** `[BE]` Given an attachment with `company_id = NULL` (form attachment) binding to a global form, Then no company scoping is applied (shared).

## Group H - Enforcement guarantees (the hard security ACs)

- **AC-H1 (leak test)** `[BE]` Given every `CompanyScopedMixin` model, When a query runs with scope = `UNSET`, Then it returns **0 rows** (fail-closed); with a company scope it returns only that company's rows. Automated, runs in CI.
- **AC-H2 (new-table guard)** `[BE]` Given a new owned table added without registering it in the mixin/filter set, Then a CI test **fails**.
- **AC-H3 (four-state)** `[BE]` Given scope values `UNSET`/`None`/`{ids}`/`{}`, Then the emitted predicate is `false()` / *(none)* / `company_id IN (ids)` / `false()` respectively. Empty set never leaks (no `.in_([])` footgun).
- **AC-H4** `[BE]` Given scope lives on `db.info["company_scope"]` (NOT a contextvar), Then the filter applies correctly across sync-dependency, flush, relationship-load, and worker paths (regression against the audit-attribution contextvar gotcha).
- **AC-H5** `[BE]` Given attachments under a non-`None` scope, Then predicate = `company_id IS NULL OR company_id IN (ids)`; shared (null) attachments remain visible; empty scope still shows `IS NULL` rows only.

## Group I - Blind-spot coverage

- **AC-I1** `[BE]` Given each raw-SQL/analytics endpoint (order analytics, complaint analytics, stock-balance latest-ledger subquery, MCP `exclude_zero_system_adjustment`, `crm_lookup_resolve`, order/SPO/GRN number-generation), Then each has an explicit company predicate and its own regression test.
- **AC-I2** `[BE]` Given order/SPO/GRN number generation, Then `max(number)+1` is computed **per company** (no cross-company collision or gap).
- **AC-I3** `[MCP][BE]` Given `crm_lookup_resolve` resolving a product code, Then it resolves within the caller's company scope (Mocha "CHAIR-01" never resolves to Sorento's row).
- **AC-I4 (RAG)** `[BE]` Given a Mocha-scoped semantic search ("office chairs?"), Then vector results contain **only Mocha** entities - no Sorento rows via similarity.
- **AC-I5** `[BE]` Given an owned entity is created/updated, Then the `embedding_change_listener` stamps the new embedding row's `company_id` from the source (fresh embeddings are never company-less).

## Group J - Uniqueness & import matching (per company)

- **AC-J1** `[MIG][BE]` Given owned tables' natural-key unique constraints, Then each is `UNIQUE(company_id, natural_key)` (product code, warehouse code, order no, SPO no, GRN/picking no, brand/category/UOM/supplier/customer/transporter codes).
- **AC-J2** `[E2E]` Given Sorento already has "CHAIR-01", When Mocha imports its own "CHAIR-01", Then the import **succeeds** (no unique violation) and creates a distinct Mocha row.
- **AC-J3** `[BE]` Given the import upsert/matching (product-code lookup, `_spo_match_key`, customer/transporter FK upsert), Then matching is scoped to the target company (Mocha import never upserts onto a Sorento row).

## Group K - Migration & backfill

- **AC-K1** `[MIG]` Given the migration runs on the current (Sorento-only) DB, Then all existing owned rows get `company_id = Sorento`; all users get grant {Sorento} + `last_active = Sorento`; all contacts get membership {Sorento}; all embedding rows get Sorento.
- **AC-K2** `[MIG]` Given phase 3 of the migration, Then owned `company_id` columns flip NOT NULL (except `attachments`, which stays nullable) and unique constraints become composite - with no orphan/null owned rows remaining.
- **AC-K3** `[MIG]` Given the down_revision, Then it chains onto the committed main head and `alembic heads` shows a single head after merge (dual-head hygiene).
- **AC-K4** `[MIG]` Given a newly-synced contact with no company tag (Q2 strict), Then they resolve to empty scope → 0 owned rows until an admin tags them; global forms/SLA still work.

## Group L - Coexistence / limitations

- **AC-L1** `[MCP]` Given a Mocha contact asking promotions, Then the result is filtered by **company (Mocha) AND `access_levels`** (their tier) - both applied, `access_levels` behavior unchanged from today.
- **AC-L2** `[E2E]` Given the complaint↔DO auto-linker on a global complaint, Then it matches DOs within the complaint's contact's company set; unique-in-one → link, ambiguous/none → skip (no cross-company mislink).
- **AC-L3** `[FE]` Given one active company at a time, Then there is **no** merged cross-company aggregate report in v1 (accepted limitation - documented, not a bug).

---

## Definition of Done (gate)

1. Every AC above verified on its marked side against the **real stack** (Phase 2), evidence captured (Playwright network + screenshots for `[E2E]`/`[FE]`; pytest for `[BE]`/`[MCP]`/`[MIG]`).
2. `AC-H1` leak-test + `AC-H2` new-table guard are green in CI and **fail** when deliberately broken (proven, not assumed).
3. **Edit/delete IDOR matrix (AC-D5 - D11) run for EVERY one of the 34 owned entities** - cross-company GET-by-id/PUT/DELETE returns 404 for all; `company_id` is never caller-writable. No entity skipped.
4. **AC-F7 MCP matrix is exhaustive** - a parametrized test iterates the whole `CATALOG`; every company-scoped tool passes all 4 param cells; global tools (AC-F8) proven unaffected; a catalog tool with no matrix entry fails the suite.
5. No owned table queried without the central filter (grep audit + `AC-C3`).
6. Contract doc + plan match what shipped; PR includes Phase-1 prototype screenshots.
