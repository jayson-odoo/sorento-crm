# PLAN - Multi-Company Data Isolation (Sorento + Mocha)

**Status:** BUILT through Phase 3 (2026-07-24). Migrations 302 - 306 applied to local DB. Enforcement + resolver + `/companies/*` + MCP params + FE claim/off-mocks + binding/embedding/analytics scoping all shipped. Scope test matrices green (78: leak/four-state/IDOR/MCP-resolver/uniqueness/RAG/stock-ledger). Phase-3 review done - 2 real leaks (C1 stock-ledger bulk-insert, H1 stale-grant fallback) + M1/M2/L1/L3 fixed & regression-tested on Postgres. FE prod build clean, all services healthy. Uncommitted on `feat/promo-expiry-rule-engine`. REMAINING: interactive browser click-through (needs dev login); commit/PR. Branch has ~173 PRE-EXISTING (non-feature) test failures - not addressed, documented via the `COMPANY_SCOPE_ENFORCE=0` baseline.
**Branch (proposed):** `feat/multi-company-isolation`
**Slug:** multi-company-isolation
**Date:** 2026-07-24
**UAC:** `UAC-multi-company-isolation.md` (12 groups A - L, ~65 acceptance criteria incl. full edit/delete IDOR matrix + exhaustive per-MCP-tool matrix - verify each before handoff)

---

## 1. Problem

Onboard a second company (**Mocha**) alongside **Sorento** on one deployment. In AutoCount these are two separate companies; in the CRM they must be **isolated data partitions** for owned business data (products, stock, warehouses, promotions, packing lists, SPO, GRN, orders, resource attachments, etc.).

Constraints:
- **Users shared** - one login, one role, switch company via top-right switcher; one active company at a time.
- **Respond contacts shared** - a contact can belong to Sorento, Mocha, or both.
- **Respond workspace shared** - both companies can use the same workspace (workspace ≠ company).
- **n8n/MCP calls must be company-bounded** - a Mocha contact asking for products/stock/etc. sees only Mocha data; a Mocha+Sorento contact sees both.

## 2. Current state (verified)

- **No real multi-tenancy.** `tenant_id` exists only on 4 infra tables (`tenant_modules`, `module_install_events`, `lookup_sets`, `lookup_bindings`) for module toggles + lookups. `_tenant_id_for_request()` = hardcoded `"__default__"`. No business table carries any org column.
- **No `company` concept.** (`order.customer_type="company"` is unrelated - individual-vs-company enum.)
- **Principal** = plain dict, no org field. JWT path `get_current_user` (`app/dependencies.py:185`); X-API-Key act-as path `get_current_user_or_api_key` (`:585`) / `_user_dict_from_api_key_act_as` (`:492`); pure external = `"system"` user (`get_external_api_user` `:546`).
- **MCP → backend** = single shared `EXTERNAL_API_KEY` (`X-API-Key`), no per-caller identity forwarded. Most data GETs (products/stock/orders/warehouses/incoming-stock) receive **no** contact/space param today.
- **Existing company-ish signal**: `respond_contact_access_types` M2M with values `"sorento dealer"` / `"mocha office"` / `"end user"`, consumed by promotions + product/resource attachments as `access_levels` only. `RespondContact.workspace_id` → 1 workspace (scalar FK). Workspace-scoped resolver exists: `ContactAccessTypeService.resolve_contact_access_codes(respond_io_id, space_id)` joins `RespondContact`→`RespondWorkspace` on `space_id`.
- **List query** fans out per-service (`list_query_search_service.py`), not one generic ORM query; shared clause via `compile_optional_filter`.

## 3. Locked decisions (from grill)

### Model
1. **`company` = new dimension, partition below tenant.** Both companies stay `tenant="__default__"`. New first-class `companies` table. Not overloading `tenant_id`, not the `access_levels` strings.
2. **Direct `company_id` FK on each owned table.** Nullable → backfill Sorento → NOT NULL. Products/masters belong to exactly one company (separate AutoCount masters; Mocha "CHAIR-01" ≠ Sorento "CHAIR-01" = separate rows).
3. **`UNIQUE(company_id, natural_key)`** on all owned tables. All code lookups/upserts company-scoped.

### Entity buckets
4. **① Owned (hard-filtered by `company_id`):** products, brands, product_categories, units_of_measure, product_attachments, warehouses, stock, stock_ledger, stock_batches, promotions, promotion_products, promotion_attachments, inbound_shipments (packing lists), spo_allocations, purchase_orders, picking_headers, picking_lines (GRN), orders, sales_orders, resource attachments, suppliers, customers/debtors, transporters.
5. **② Shared, membership-tagged (M2M, union scope):** `respond_contacts` (via `respond_contact_companies`), `users` (via `user_companies`).
6. **③ Global (no company):** roles, permissions, lookups (already tenant-scoped), respond_workspaces, system_settings, **all form entities** (complaints, stock_inquiries, purchase_requests, IT tickets), **SLA tracking / conversation SLA**. Rationale: anything keyed to a (multi-company) contact can't be attributed to one company. **Consequence accepted:** staff see all forms/SLA regardless of active company (CS is a shared function).
   - **[F5 / Q3 decision - A] Global form → owned entity by a per-company key.** The Complaint↔DO auto-fulfilment linker matches `delivery_order_number` against owned orders, whose numbers become unique *per company*. Resolution: the linker **scopes candidate DOs to the complaint's contact's company set**; if the DO number exists in exactly one of those companies → link; ambiguous (in multiple) or none → **skip** (matches the existing silent-skip-on-no-match behavior - see [[project_complaint_do_auto_fulfilment]]). No `company_id` column added to the global complaint.
7. **Attachments** = **nullable** `company_id`. Null = shared (form-entity attachments), non-null = owned (resource/product/promotion). Filter predicate: `company_id IS NULL OR company_id IN {scope}`.

### Enforcement
8. **Central app-layer global filter.** `CompanyScopedMixin` on owned models + SQLAlchemy `do_orm_execute` event injecting the scope predicate automatically. **Fail-closed.**
   - **[F1 - grill fix] Scope lives on `db.info["company_scope"]`, NOT a contextvar.** Known codebase gotcha ([[project_audit_contact_attr_gotchas]]): a contextvar set in a FastAPI sync dependency does not propagate to the ORM flush. Set the resolved scope on the session's `db.info` at request entry (via the DB-session dependency); the `do_orm_execute` handler reads it from `context.session.info`. This also survives worker paths (worker sets `db.info` from the job snapshot).
   - **Leak test (mandatory):** enumerate every `CompanyScopedMixin` model; assert `UNSET`→0 rows (fail-closed) and scoped query → only that company's rows.
   - **New-table guard (mandatory):** CI test fails if an owned table is added without being registered in the mixin/filter set.
9. **[F2 - grill fix] FOUR-state scope** (resolved at request entry, stored on `db.info`). The default MUST be a distinct `UNSET` sentinel - not `None` - or a code path that never runs the resolver would fall into the `None`="all" branch and leak everything. Empty set MUST compile to `false()` (never rely on SQLAlchemy `.in_([])`).

   | State | Caller | Predicate | Behavior |
   |---|---|---|---|
   | `UNSET` (default) | resolver never ran (bug / non-HTTP path) | `false()` | 0 rows (fail-closed) - leak-test asserts this |
   | `None` | X-API-Key, no contact_id/space_id | *(no predicate added)* | **all companies** (backward-compat, minimal n8n disruption) |
   | `frozenset{ids}` | JWT UI user (`{active}`) / X-API-Key contact resolved (union) | `company_id IN (ids)` | those companies |
   | `frozenset()` empty | X-API-Key, contact params present but unresolved | `false()` | 0 rows (fail-closed) |

   Attachments predicate under a non-`None` scope: `company_id IS NULL OR company_id IN (ids)`; under empty scope: `company_id IS NULL` still shows (shared form attachments are visible by definition - fail-closed applies to *owned* rows only).

   **Accepted risk:** a contact-facing n8n branch that forgets to pass identity is indistinguishable from a system call → returns all companies. Audit contact-facing n8n branches to always pass identity.
10. **Blind spots - manually scoped + individually tested:**
    - **(a) Raw SQL / analytics** (`db.execute(text())`, correlated subqueries): order analytics, complaint analytics, stock-balance (latest-ledger subquery), MCP stock-balance `exclude_zero_system_adjustment`. The ORM `do_orm_execute` filter does NOT cover these. **[F6 - grill fix] Also in this set:** `crm_lookup_resolve` (`POST /lookup/resolve` - can resolve product/entity codes cross-company; takes active/contact company) and **order/SPO/GRN number-generation** (`max(number)+1` must scope its `max()` by company or numbers collide/gap across companies). Enumerate the full set early in Phase 2 - likely 12 - 20 spots, not "small".
    - **(b) Embeddings / RAG:** embedding rows must carry `company_id`; vector search must filter by scope, else semantic search silently leaks cross-company. **[F7 - grill fix]** The `embedding_change_listener` must **copy `company_id` from the source entity on every write** - backfill alone isn't enough; fresh embeddings on entity change would otherwise land company-less and gradually re-leak. In scope, not deferred.

### Identity / context
11. **UI active company:**
    - New `user_companies` grant M2M (user ↔ allowed companies). **Global role** - one role per user, applies across all their companies (RBAC orthogonal to company).
    - New `users.last_active_company_id` (persisted).
    - JWT claim `active_company_id`; backend validates it ∈ grants → sets `db.info` scope.
    - **[Q1 decision - A] NextAuth ↔ FastAPI claim plumbing:** the NextAuth `jwt` callback calls the **backend** `GET /companies/my-context` at sign-in (returns grants + `last_active_company_id`) and embeds `active_company_id` + grant list in the token. Backend is the single source of truth - grants are NOT duplicated into the frontend Prisma DB. On switch: FE calls backend `POST /companies/switch` (validates grant, persists `last_active_company_id`) → FE triggers NextAuth `session.update()` → `jwt` callback re-mints with the new `active_company_id`. This FE↔BE token dance is its own Phase-2 slice (`/companies/my-context` + `/companies/switch` + `jwt`/`session` callback wiring).
    - `POST /companies/switch` → validate grant → persist `last_active_company_id` → re-mint token. **Logout → login returns to same company.**
    - One active company at a time (no merged view). Single-grant users auto-selected, switcher hidden. Superadmin sees all companies in switcher.
12. **Active company drives read AND write.** Insert to owned table auto-stamps `company_id = active` (via `before_insert` listener on `CompanyScopedMixin`). **Imports snapshot `active_company_id` at enqueue** onto the import-job row (worker has no request context; stamps from snapshot). Switch → upload AutoCount/DO/SPO → stamped with active company.
    - **Edge:** X-API-Key/system write (scope `None`) to an owned table has no company to stamp → **require explicit `company_id` or reject**; never insert an owned row with null company.
13. **n8n/MCP identity:** explicit `contact_id` (respond_io_id) + `space_id` params on each company-scoped ToolSpec, **expression-bound in n8n from the Respond webhook payload** (deterministic, not LLM-filled). MCP forwards as query params. Backend extends `resolve_contact_access_codes` to also return `company_ids`. Contact↔company = **explicit `respond_contact_companies` M2M, admin-managed** (not derived from access_types).
    - **[Q2 decision - C, strict] Newly-synced untagged contacts get NO default company** → resolve to empty scope → **0 rows** until an admin tags them. Chosen over defaulting-to-Sorento: strongest isolation, no accidental cross-company exposure. **Operational cost accepted:** every new contact needs manual company-tagging before self-service (product/stock/etc.) works for them; forms/SLA (global) still work unassigned. Mitigation to consider later (not v1): an admin "untagged contacts" queue/alert so they don't sit silently empty.
14. **Binding endpoints exception** (packing-list create, product-attachment bind, promotion-attachment bind, form-create-with-attachment - all n8n-called under X-API-Key, no active company): scope entity match by **`attachment.company_id`**, not the caller. Resolve/bind only within that company; no match in that company → **fail** (never fall through to another company's row). Only applies when `attachment.company_id` is non-null (null = form attachment, no scoping).
15. `access_levels` and `company` **coexist (AND)**; `access_levels` untouched (company = outer filter, access_levels = inner tier filter). In-CRM AI assistant rides the active-company contextvar like any UI query.

### Governance
16. **`companies` table:** `id` (uuid), `name`, `code` (short, e.g. `SRT`/`MCH`), `is_active`, `autocount_ref` (nullable), `logo_url` (nullable), `created_at`. **Superadmin-only** CRUD + grant/membership management. Nav: **System Management → Companies**. Backfill all existing data → Sorento; user creates Mocha + tags Mocha contacts/users manually.

## 4. Schema changes

**New tables**
- `companies` (§16).
- `user_companies` (user_id, company_id) - grant M2M. Unique (user_id, company_id).
- `respond_contact_companies` (respond_contact_id, company_id) - membership M2M. Unique (contact_id, company_id).

**New columns**
- `users.last_active_company_id` (nullable FK).
- `company_id` FK on every owned table - see the **authoritative table list** below. Nullable on `attachments`; nullable-then-NOT-NULL on the rest.
- `company_id` on embedding rows.
- `company_id` (snapshot) on import-job table.

### 4.1 Authoritative table list - where `company_id` lands

**GETS `company_id` (owned, hard-filtered) - 34 tables.** Line/child tables get their **own** denormalized `company_id` (stamped from parent at insert) so the central `do_orm_execute` filter covers a direct query on them too - no reliance on a parent join (consistent with the "direct column, not transitive" decision §3.2).

| Model file | Tables |
|---|---|
| `product.py` | `product_categories`, `brands`, `units_of_measure`, `products`, `product_attachments` |
| `inventory.py` | `warehouses`, `storage_zones`, `stock`, `stock_ledger`, `stock_batches` |
| `marketing.py` | `promotions`, `promotion_groups`, `promotion_products`, `promotion_attachments`, `marketing_campaigns`, `campaign_types` |
| `procurement.py` | `suppliers`, `product_suppliers`, `inbound_shipments` (packing list), `inbound_shipment_lines`, `spo_allocations`, `picking_headers` (GRN), `picking_lines`, `purchase_orders`, `purchase_order_lines` |
| `order.py` | `customers` (debtors), `customer_contacts`, `transporters`, `orders`, `order_lines`, `sales_orders`, `sales_order_lines` |
| `resources.py` | `attachment_directories`, `attachments` (**nullable** - null = shared form attachment) |
| pipeline | embedding rows table, import-job table (`company_id` snapshot) |

All 4 previously-ambiguous tables ruled **per-company** by user: `campaign_types`, `attachment_directories`, `product_suppliers`, `storage_zones`.

**Does NOT get `company_id`:**
- **Global form entities (bucket ③):** `stock_inquiries`, `purchase_requests`, `purchase_request_lines`, `approval_tokens`, `view_tokens` - form/contact-keyed, stay global. (Note: `purchase_orders` = internal procurement = **owned**; `purchase_requests` = the contact-facing PR/SF form = **global**. Don't conflate.)
- **Global reference/lookups:** `order_statuses`, `attachment_types`.
- **Shared, M2M-tagged (bucket ②):** `respond_contacts`, `users` (via join tables, no direct column).

**Constraint changes**
- Every owned-table `UNIQUE(natural_key)` → `UNIQUE(company_id, natural_key)`. Enumerate during Phase 2 (candidates: product code, warehouse code, order number, SPO number, GRN/picking number, brand/category/UOM codes, supplier/customer/transporter codes).

**Migration ordering (two-phase, safe)**
1. Add `companies`, insert Sorento (+ user adds Mocha later). Add M2M tables. Add nullable `company_id` columns. Add `last_active_company_id`.
2. Backfill: all owned rows → Sorento; `user_companies` = {Sorento} for all users; `respond_contact_companies` = {Sorento} for all contacts; `last_active_company_id` = Sorento; embedding rows → Sorento.
3. Flip owned `company_id` NOT NULL (except `attachments`). Swap unique constraints to composite.
- down_revision must chain onto committed main head (per lessons: `alembic heads` reads filesystem; verify single head).

## 5. Implementation phases (three-phase loop)

### Phase 1 - FE prototype (mocks)
- Company switcher (top-right), companies admin CRUD, user↔company grants UI, contact↔company membership UI - all against mock data.
- Verify states via Playwright MCP (multi-grant switch, single-grant hidden, superadmin all).

### Phase 2 - BE wiring + tests
- Migrations + models + `CompanyScopedMixin` + global filter + contextvar + tri-state resolver at request entry.
- Auto-stamp on insert; import enqueue snapshot; worker stamp.
- Extend contact resolver → company_ids; add `contact_id`+`space_id` to company-scoped ToolSpecs; MCP forward.
- Binding-endpoint attachment-scoped resolution.
- Raw-SQL/analytics manual scoping; embedding company_id + scoped vector search.
- `/companies/switch` re-mint + persist; JWT claim plumbing (NextAuth ↔ FastAPI).
- **Tests (land here, not deferred):**
  - **Leak test** + **new-table guard** (pytest).
  - Tri-state resolver test (all 4 rows of the table).
  - Uniqueness-per-company test (Mocha "CHAIR-01" imports alongside Sorento's).
  - Per-endpoint analytics/raw-SQL scoping tests.
  - Embedding/RAG scoping test.
  - Binding-endpoint attachment-company test (Mocha attachment never binds Sorento entity).
  - vitest for switcher + admin screens; playwright FE→BE→DB for switch + scoped list.

### Phase 3 - Code review
- `/code-review ultra` (large diff). Verify leak-test green, no unscoped owned query, no raw-SQL blind spot missed.

## 6. Accepted limitations (v1)
- **[Q4 decision - A] No cross-company aggregate report.** One active company at a time → a combined "both companies" view requires switching + manual add. No merged finance dashboard in v1. Revisit later via a superadmin read-only `scope=None` analytics view if needed.

## 7. Open items to enumerate during Phase 2 (mechanical, not decisions)
- Exact list of owned tables' natural-key unique constraints → composite `(company_id, key)`.
- Full raw-SQL/analytics/number-gen/lookup-resolve set needing manual predicate (F6) - enumerate early, ~12 - 20 spots.
- `/companies/my-context` + `/companies/switch` endpoints + NextAuth `jwt`/`session.update()` wiring (Q1 slice).
- Notifications scoping (follow entity; low risk).

## 8b. Phase-2 insertion points (verified against code)

| Concern | Exact location |
|---|---|
| `Base` | `app/database.py:26` (`declarative_base()`). New `CompanyScopedMixin` → new `app/models/base.py`; apply via `class Product(Base, CompanyScopedMixin)`. Enumerate targets via `app/models/__init__.py`. |
| Set `db.info["company_scope"]` (API) | `app/database.py:29` `get_db` generator (or a post-auth dependency). Precedent for `session.info` use: audit service already uses `session.info["audit_*"]`. |
| Set scope (worker/import) | `app/tasks/import_tasks.py` right after each `db = SessionLocal()` (e.g. `:270` `process_product_import`, `:344` order import) - read snapshot from the `ImportJob` row. |
| **Register `do_orm_execute` + `before_insert` at IMPORT TIME** | ⚠️ The RQ **worker never runs `main.py` `startup_event`** - audit/embedding listeners registered only there are ABSENT in the worker. Register the company filter + auto-stamp at import time (mirror `app/services/lookup_write_listener.py`, imported at `main.py:125`) so worker writes are scoped too. |
| Coexisting listeners | audit `audit_service.py:388` (before/after_flush), embedding `embedding_change_listener.py:156` (after_insert/update/delete), lookup `lookup_write_listener.py:18` (mapper before_insert/update), attachment `resources.py:138` (model before_insert). Filter must coexist. |
| Migration | `alembic/versions/302_<slug>.py`, down_revision `301_promo_expiry_rule_engine` (current single head). Style = raw `op.execute("ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...")` + matching `DROP ... IF EXISTS` downgrade. **Revision id ≤32 chars** (`alembic_version.version_num` varchar(32)). |
| Import-job snapshot | `app/models/job.py` `ImportJob` (`import_jobs`, note `UUID(as_uuid=True)` PK) - add `company_id`; write it at the `JobService.create_job(...)` call in each import route (`orders.py:1090`, `resources/attachments.py:1289`, `procurement/spo_allocations.py:101`, `procurement/grn.py`, `inventory/warehouses.py:173`, `inventory/stock.py:310`). |
| Embedding `company_id` | add column to `app/models/embeddings.py` `EmbeddingDocument`/`EmbeddingChunk` (+ maybe `EmbeddingQueue`); populate in `embedding_change_listener.py:112` `_queue_from_mapper` (has `target` → `target.company_id`) + materialize in `embedding_worker.py`. Scoped source models listed `embedding_change_listener.py:160-175`. |
| MCP `contact_id`/`space_id` | add to `ToolSpec.query_params` in `catalog.py` (precedent: form-create spec uses `body_params=("contact_id","space_id",...)`). Auto-forwards via `_compile_tool` `q_dict` (`server.py:1425`) → `http_client.request` params (`http_client.py:81`). `_UUID_PARAM_EXEMPT` already exempts both (`server.py:252`). |
| Contact→company | extend `contact_access_type_service.py:322` `resolve_contact_access_codes` (already joins RespondContact→RespondWorkspace on space_id) → add sibling `resolve_contact_company_ids(...)`. |
| Binding scope-by-attachment | `external/packing_lists.py:42`, `external/product_attachments.py:105` (`db.query(Attachment).filter(id==...)`), `external/promotions.py:114`, `external/forms.py:24`, `external/entity_attachments.py:46`. Add `company_id` to `Attachment` (`resources.py`), scope the entity match by it. |
| ORM lists (auto-covered) | `OrderService.list_orders` (`order_service.py:57`), `ProductService.list_products` (`product_service.py:401`), `order_analytics` (`order_service.py:771`), `complaint_analytics` (`complaints_service.py:459`) - all `db.query(Model)`, covered by `do_orm_execute`. |
| **Raw-SQL blind spots (manual scope)** | `app/services/scm/analytics_service.py` (`execute(text(...))` at `:77,81,89,93,122,134,281,316,325,329`) + `scm/dashboard_service.py`; plus `text()` in `marketing_service.py`, `variant_link_service.py`. Stock-balance/ABC/supplier analytics = raw SQL → add `WHERE company_id = :scope` by hand + per-endpoint test. |

## 8. Related memory
- [[project_core_vs_module_schema]] - core vs module doctrine (company = partition, not a module/tenant).
- [[project_docs_restructure_foundryx_fusion]] - plans live under `documentation/plans/`.
- [[project_alembic_dual_head_merge]], [[project_migration_downrev_uncommitted_ancestor]] - migration hygiene.
- [[project_test_wipes_real_dev_db]] - scope all test cleanup to marker rows (local DB is prod-copy).
- [[feedback_uac_first_then_verify_both]], [[feedback_grill_plan_before_implementing]] - grill the plan before code; UAC + verify both sides.
