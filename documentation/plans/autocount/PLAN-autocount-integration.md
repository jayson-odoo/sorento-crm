# PLAN - AutoCount Integration (Sorento side)

> **UAC:** `documentation/plans/autocount/autocount-integration-acceptance-criteria.md` - the contract.
> **Counterpart repo:** `foundryx-shared-service` → `documentation/plans/sprint-4/13-autocount-esb.md`
> **Status:** Group A **BUILT** (AC-01 - 10, 38, 39; 13 commits). UAC Group D **BUILT** as
> sequencing Phase B (`integration_references`). Remaining groups DRAFT.
> **Caution:** sequencing letters (§11 Phase A - H) and UAC letters (Group A - I) are different
> schemes and only A coincides.
> **Self-contained** - you can start from this file without the originating design conversation.

## 1. What is being built and why

Customers run **AutoCount on-premise**; Sorento runs in the cloud. They cannot reach each other.
A new **ESB module in the FoundryX shared service** sits between them. It holds AutoCount credentials,
owns the single static egress IP customers whitelist, translates AutoCount's schema into a **canonical
shape**, and pushes into Sorento.

```
AutoCount (on-prem)  ⇄  FoundryX ESB (cloud, static IP)  ⇄  Sorento CRM
        ▲                                                       │
        └──────── writes (PO/SQ/PR/SO) ◀── lifecycle events ────┘
```

**Sorento never calls AutoCount and never sees AutoCount field names.** This is exactly what Sorento
already documented in `documentation/reference/SCM_Module_Build_Plan.md:11-21`:

> "The SCM core never reads AutoCount. It reads our own canonical tables… Every table the core
> consumes has a `source_system` column (`manual | seed | autocount`) and a `source_ref`…
> If AutoCount calls it `DocKey`, that stays in the sync layer and maps to our `source_ref`."

That design is **adopted, not replaced**. This plan extends it beyond the SCM branch.

**Sorento's five jobs:**

1. Accept pushed data on **ingest endpoints** (canonical shape, idempotent).
2. Expose **read endpoints** so the ESB can render before→after diffs for human approval.
3. Carry **`source_system` / `source_ref`** on consumed tables.
4. Emit a **generic document-lifecycle event** so the ESB knows when to write outward.
5. Replace the shared env API key with a **proper integration object**, per-integration keys.

**Direction of truth:** AutoCount is system of record for masters. Sorento owns transactions it
originates (PR, SQ, SO, PO) and pushes them out.

## 2. Group A first - the integration object

**This is task one. Nothing else ships before it.**

Today (`app/dependencies.py:546-582`, `app/config.py:58-61`):

- One static `EXTERNAL_API_KEY` env var, **shared with n8n**
- Compared with plain `!=` - not constant-time
- `get_external_api_user` applies **no permission check at all**
- No key table, no scopes, no rotation, no expiry, no per-caller identity
- No rate limiting on `/external`

Giving the ESB this key grants it everything n8n has, on a system that will write master data and
raise purchase orders. That is not an adequate trust boundary.

### Model it on the shared service

Read these before designing - the pattern is proven and should be mirrored, adapted to Sorento's
single-tenant shape:

| Concept | Shared-service reference |
|---|---|
| Connection record, config vs credentials split | `service_backend/app/models/connection.py` |
| Provider contract (`fields()`, `test()`, registry) | `service_backend/app/integrations/base.py` |
| Fernet encryption, graceful undecryptable handling | `service_backend/app/secrets.py`, `app/services/integration_service.py:52-66` |
| Blank-means-keep on secret PATCH | `app/services/integration_service.py:291-296` |
| Status model (`ACTIVE`/`UNVERIFIED`/`ERROR`), `last_tested_at`, `last_error` | `app/models/connection.py` |

### Decisions (grilled 2026-07-21 - settled, do not re-litigate)

| # | Decision |
|---|---|
| A1 | An integration **acts as a real `users` row** via `act_as_user_id`. Each integration gets its **own** user and its **own** role. Authorization is plain RBAC. |
| A2 | Integration users carry a new **`users.is_integration`** flag. Do **not** overload `is_protected` - that already selects notification recipients (`automation_service.py:34`). |
| A3 | **Full sweep.** All 17 `/external` endpoints enforce permissions in Group A. No audit-mode, no deferral. |
| A4 | `integrations` is a **bidirectional counterparty** object: inbound keys *and* outbound destination + credentials. Only the ESB is migrated in Group A. |
| A5 | Rotation grace closes by **passive `expires_at`** evaluated at request time, plus manual immediate-revoke. Default grace **7 days**. No cron. |
| A6 | Env key seeded **once, in a migration**. **No runtime env fallback ever ships.** |
| A7 | Rate limiting **fails open** and alerts when the limiter is unavailable. |
| A8 | **No `scopes_json`.** RBAC permission slugs are the single authorization vocabulary. |

Rationale for A1/A8: Sorento already has 230 permission slugs, `require_permission_with_api_key`,
the act-as mechanism and a module guard. A separate scope vocabulary would be a second
authorization system beside a working one - and when the two disagree, the bug is invisible
(the endpoint checks slugs, the reviewer reads scopes, everyone concludes it's fine).
Key-level narrowing below an integration's role can be added later as a nullable column with
null = "no narrowing"; nothing shipped has to change.

Rationale for A5: the scheduler is **opt-in and defaults off** (`ENABLE_SCHEDULER != true`), so a
cron-dependent expiry would leave the old key valid forever wherever that var is unset. A security
control must not fail **open** because an unrelated env var is missing.

### Schema

```
integrations
  id, name, type, status(ACTIVE|UNVERIFIED|ERROR),
  act_as_user_id,                 -- FK users.id - principal writes are attributed to (A1)
  config_json,                    -- non-secret, displayable (ESB base URL, autocount company code)
  credentials_json,               -- Fernet ciphertext, write-only over API; the outbound key for
                                  --   calling the ESB (Group F). Empty for inbound-only rows. (A4)
  is_active, last_used_at, last_error, created_at, updated_at

integration_api_keys
  id, integration_id, key_hash,   -- hash only; plaintext shown once at creation
  key_prefix,                     -- short display fragment for identification
  expires_at, revoked_at, rotated_from_id, last_used_at, created_at
                                  -- NO scopes_json (A8)
```

**Rules:**

- Plaintext key shown **once**, at creation. Only the hash persists. Never retrievable.
- Verification uses `hmac.compare_digest` - no `==`/`!=` on a secret anywhere.
- Every external endpoint enforces the caller's **RBAC permissions**, through the existing
  `require_permission_with_api_key` path against `act_as_user_id` (A1/A3/A8).
- Rotation: `expires_at` on the old key, evaluated at request time (A5). An expired key returns a
  distinct `key_expired` code, never a generic invalid-key error - otherwise the operator has no
  way to know rotation caused the 3am 401. This leaks nothing: an attacker would need a valid
  (if expired) key to observe it.
- The old key's `last_used_at` must be visible so an admin can confirm the caller actually migrated
  **before** the window closes. Without it, rotation is a coin flip.
- Credentials Fernet-encrypted (reuse `app/utils/field_encryption.py`); blank on update = keep.
- Per-integration rate limiting with `429` + `Retry-After`; fail-open + alert (A7). Rate limiting
  here is **abuse control, not authorization** - a dead limiter grants no access, since auth is
  DB-backed and still enforced.

### Three keys - do not conflate them

| # | Key | Direction | Issued by | Stored | Rotated by AC-AC-06? |
|---|---|---|---|---|---|
| 1 | n8n / MCP inbound key | caller → Sorento | Sorento | hash in `integration_api_keys` | **Yes** |
| 2 | ESB inbound key | ESB → Sorento | Sorento | hash in `integration_api_keys` | **Yes** |
| 3 | Sorento→ESB outbound key | Sorento → ESB | the shared service | Fernet in `integrations.credentials_json` | **No** - the ESB owns its own rotation |

### Migration off the env key (AC-AC-09) - do not skip

`EXTERNAL_API_KEY` is live and shared by **two** callers: n8n *and* the MCP server
(`sorento_crm_mcp` authenticates with it, and it is how n8n reaches read-only tools via
`sub-get-results`). Missing the MCP server breaks that path.

Sequence:

1. A migration reads `EXTERNAL_API_KEY` **once, at migration time** and seeds a single
   `legacy-shared-key` integration carrying its hash. n8n and the MCP server keep working with
   **zero changes**. If the env var is absent: seed nothing and log loudly - never an empty hash.
2. Issue separate keys for the `n8n` and `sorento-mcp` integrations; migrate each caller on its own
   schedule. **This step is also the leak remediation** (below).
3. When `legacy-shared-key.last_used_at` goes quiet, revoke it - self-evidencing.

No dual-accept fallback is ever written, so there is no deprecation debt to chase (A6).

### Known security findings to remediate here (found 2026-07-21)

1. **The production API key is a hardcoded plaintext literal in ~40 n8n nodes**, not an n8n
   credential reference - so it lives in workflow JSON, every export, and the n8n database.
   Step 2 above rotates it. The 7-day grace exists precisely because ~40 nodes need editing.
2. **`sorento-consume-main TEST` is ACTIVE** against the production host, calling the same 10
   endpoints as the live workflow. Confirm intent - likely duplicate production traffic.
3. Node `integration-log-update3` in `system-upload-attachments` sends `x-api-key: test` and has
   been failing silently.

### What n8n actually calls (scanned 2026-07-21, 66 workflows, 100% coverage)

**25 distinct Sorento paths**, all via `X-API-Key`:

- **17 under `/external/*`** → `get_external_api_user` → **no RBAC today**. This is the A3 sweep.
- **8 non-`/external`** (`master-data/products`, 5× `sla-management/conversation-sla-tracking/*`,
  `system/references/resolve`, `integration-management/integration-logs/:id/status`) → already run
  through `get_current_user_or_api_key`, so they **already enforce slugs** against the act-as user.

Therefore n8n's role is **derivable, not guessable**:
`(current act-as user's permissions) ∪ (slugs assigned to the 17 /external paths)`.
The first half already exists in the database. Do not hand-guess this set.

## 3. Group B - ingest endpoints

One endpoint per entity, canonical shapes, authenticated by integration key with scopes.

**Entities:** Product, Stock, Warehouse, Supplier, Customer, Payment Terms, Tax,
Delivery Order (+lines), Goods Received Note (+lines).

**Naming - do not assume equivalence.** Map explicitly:

| AutoCount | Canonical | Sorento |
|---|---|---|
| GRN | `goods_receipt` | `picking_headers` / `picking_lines` |
| DO | `delivery_order` | `orders` / `order_lines` |
| Creditor | `supplier` | `suppliers` |
| Debtor | `customer` | `customers` |
| Item | `product` | `products` |

**Semantics:**

- **Idempotent** on `(source_system, source_ref)` - re-push updates in place, never duplicates.
  Response distinguishes created from updated.
- **Transactions all-or-nothing per document** - a GRN with one bad line persists nothing, and does
  not affect other documents in the batch.
- **Masters quarantine, never block** - 10,000 products with 12 invalid ⇒ 9,988 persist, 12 reported
  as failures for ESB-side quarantine. Valid rows are never withheld because siblings failed.
- **Missing referenced master ⇒ retryable, not fatal.** A GRN referencing an absent product returns a
  *retryable* marker distinct from a validation failure; re-push after the product exists succeeds
  with no manual intervention. (The ESB drains these automatically.)
- **Structured per-record errors** - machine-readable map of record → field → reason. The ESB logs
  per record and must not parse prose.
- **Ingest emits no lifecycle events** (AC-AC-18). A GRN arriving *from* AutoCount must never trigger
  a write *back* to AutoCount. This is the sync-loop guard and it is not optional.

Master resolution by natural code already exists and should be reused  - 
`app/api/v1/external/utils.py`: `get_products_by_code`, `get_warehouses_by_code_or_name`.

## 4. Group C - read endpoints

The ESB stages changes for human approval and renders **before → after** diffs. It needs Sorento's
current values to do that.

- Batched (never per-record round-trips), canonical shape, scope-enforced.
- Paginated with a documented cap; exceeding it errors rather than silently truncating.

## 5. Group D - source tracking via a reference table

> **Naming:** the sequencing table in §11 uses letters (**Phase A - H**) that do **not** match the UAC
> group letters (**Group A - I**). Only A coincides. This section is **UAC Group D**, delivered as
> **sequencing Phase B**. Read the two schemes as separate vocabularies.

> **Revised 2026-07-21 (built).** The original design put `source_system` / `source_ref` columns on
> every consumed table. That is superseded by a single mapping table, `integration_references`.

Consumed entities: `products`, `stock`, `warehouses`, `suppliers`, `customers`,
`picking_headers`, `picking_lines`, `orders`, `order_lines`.

```
integration_references
  id, entity_type, entity_id,        -- which business table, which row
  source_system,                     -- 'autocount'
  source_ref,                        -- AutoCount DocKey (stable)
  source_doc_no,                     -- display only, expected to change
  integration_id,                    -- which integration wrote it
  first_seen_at, last_synced_at, created_at, updated_at

  UNIQUE (source_system, entity_type, source_ref)   -- one document -> one record
  UNIQUE (entity_type, entity_id)                   -- one record  -> one origin
  INDEX  (entity_type, entity_id), (source_ref), (integration_id), (last_synced_at)
```

**Why a table rather than columns.** The nine tables hold ~110k rows (`order_lines` 68k, `orders`
25k, `products` 11k). Columns would mean nine migrations plus a backfill writing `manual` into every
existing row - 110k rows carrying no information, and an invariant every future manual create would
have to maintain or quietly break. The table also makes "what came from AutoCount?" one query
instead of nine, and lets a tenth entity type arrive with no DDL.

**No backfill (revises AC-AC-23).** Absence of a reference means the record was created locally.
That delivers what AC-AC-23 protects against - no row left in a state that breaks a later sync  - 
without materialising rows that say nothing.

**`source_ref` is `DocKey`, never `DocNo`** (AC-AC-22). `DocNo` is mutable - AutoCount exposes
`NewDocNo` - so correlating on it would create a duplicate the first time a document is renumbered.
`DocNo` is kept in `source_doc_no` for display.

**The cost of polymorphism, and how it is paid.** `entity_id` addresses nine tables, so it cannot
carry a foreign key. Two guarantees a FK would have given are enforced in
`IntegrationReferenceService` instead:

- **`entity_type` is an allowlist.** It resolves to a table name and arrives from an ingest payload;
  an unchecked value is an injection surface. Unknown types raise before reaching SQL.
- **A reference whose target was deleted does not resolve**, and is cleared when read. Nothing
  cascades, so a stale row would otherwise make ingest "update" a record that is gone. Deliberately
  not a scheduled sweep - `ENABLE_SCHEDULER` is opt-in and defaults off, and a correctness guarantee
  must not depend on an env var somebody forgot.
- **A second claimant on a `source_ref` raises** rather than silently returning the existing
  mapping, which would leave the caller believing it linked a record it did not.

**Identifier typing trap.** The consumed tables key on Postgres `uuid`, but `entity_id` is varchar
because the nine keys are not all the same type. `resolve()` therefore returns `str`, and
`UUID(x) == str(x)` is **False** - comparing with `==` would make ingest treat every existing record
as new and create exactly the duplicates this table prevents. Compare as strings, or pass the value
into a query filter and let SQLAlchemy cast it.

## 6. Group E - per-field ownership

AutoCount owns some fields on a shared record; Sorento owns others. A supplier is **co-owned**:
AutoCount owns code, name, payment terms, lead time; Sorento owns account owner, relationship notes,
tags, activity history.

- Ownership is **configuration**, not hardcoded (AC-AC-26).
- API writes to AutoCount-owned fields are **rejected**.
- UI renders them **disabled with a "managed in AutoCount" affordance** - never editable-then-silently-
  reverted. A user typing a change that a later sync discards reads as data loss and destroys trust in
  the whole integration.

## 7. Group F - document lifecycle events

The ESB decides *when* to write to AutoCount. Which Sorento event triggers a write is
**configuration per document type** (`on_draft_created` / `on_approved` / `on_status_change` / `manual`).

**Therefore Sorento emits broadly and the ESB filters.** Emit one generic event:

```json
{ "event_id": "…", "doc_type": "purchase_order", "event": "approved",
  "doc_id": "…", "occurred_at": "…" }
```

**Do not build a bespoke hook per trigger.** A hook per trigger hardcodes the exact thing being made
configurable - every new trigger option would then need new Sorento code. One emitter, all transitions.

**Coverage:** PO, SQ, PR/RFQ, SO - at least created, submitted, approved, rejected, cancelled.

**Where it attaches:** `app/services/procurement_service.py:6546-6639`
(`PurchaseRequestService._apply_approval_decision`) is the single funnel for PR approval - both the
public-token flow and the authenticated flow route through it. On the SCM branch, PO confirm is
`PurchaseOrderService.bulk_confirm`.

**No event bus exists.** Closest is `AutomationService.dispatch_event`
(`app/services/automation_service.py:210-252`), whose actions are **email-only**. Two viable routes:

- **(a)** Add an outbound-webhook `action_type` to `Automation` - reuses the existing trigger registry.
- **(b)** A dedicated emitter writing to `integration_log` and drained by the existing retry machinery
  (`app/services/integration_service.py:704, 799`).

**Recommend (b)** - it reuses proven retry/backoff/dead-letter, keeps event delivery independent of
the email-shaped automation model, and gives per-event observability. (a) risks bending an
email-notification abstraction into a transport it was not designed for.

**Non-negotiables:**

- Persisted and retried with backoff; never lost; visible dead-letter after exhaustion.
- **Emission failure must never break the originating transaction.** A user's approval commits even if
  the ESB is unreachable. Fully isolated, logged.
- Stable `event_id` so the ESB can discard duplicates from retries.

## 8. Group G - sync status on documents

Everything is async. Sorento cannot create a PO and receive the AutoCount document number in the same
request. **This is UX work, not only plumbing** - it is the thing most likely to surprise stakeholders
late.

- Documents expose `PENDING` / `SYNCED` / `FAILED`.
- `SYNCED` carries the AutoCount document number; `FAILED` carries the error.
- State is visible **where the user works**, with a permission-gated retry on failure.
- The UI must not imply a document exists in AutoCount until confirmed.

## 9. Group H - new masters

Neither exists today.

- **Tax** - no model at all; only `orders.tax_amount` and `order_lines.tax`.
- **Payment Terms** - only `suppliers.payment_terms_days` (int) and free text on commercial quotations.

Both need a real master with `source_system`/`source_ref`, and existing values migrate to reference them.

## 10. Group I - company scoping

AutoCount is multi-company; a customer may run several company databases. **Sorento consumes exactly
one**, named explicitly in configuration.

**Why this matters:** `products.product_code`, `suppliers.supplier_code` and `warehouses.warehouse_code`
are **globally unique** with no company dimension. AutoCount codes (`001`, `300-V021`) are per-company
and will collide. Ingest from a company other than the configured one must be **rejected**, not
silently accepted - silent acceptance corrupts master data irreversibly.

Adding a company dimension to Sorento's masters is a large migration across every master table and
every query; it is deliberately **not** in scope. If cross-company reporting is ever required, that is
a separate plan decided on its own merits.

## 11. Sequencing

| Phase | Scope | Depends on |
|---|---|---|
| **A** | Integration object + per-integration keys + RBAC enforcement + rotation + rate limit + n8n cutover (UAC Group A). **BUILT** | - |
| **B** | Source tracking - `integration_references` table (UAC Group D). **BUILT** - no backfill; absence means locally created | A |
| **C** | Ingest for masters (Product, Supplier, Customer, Warehouse) + read endpoints for diffing | B |
| **D** | New masters (Tax, Payment Terms) | B |
| **E** | Ingest for transactions (GRN, DO) | C |
| **F** | Per-field ownership enforcement + UI | C |
| **G** | Lifecycle event emitter + retry | A |
| **H** | Sync status on documents + UI | G |

Phases C/D and G can run in parallel once A and B land.

## 12. Dependencies and risks

| # | Item | Impact |
|---|---|---|
| 1 | **`feat/scm-reorder-copilot` must merge** - `purchase_orders`, `sales_orders`, `purchase_order_lines`, `sales_order_lines` **do not exist on main** | Blocks B/F/G for those doc types |
| 2 | No Tax or Payment Terms tables | Phase D is net-new schema |
| 3 | No event bus | Phase G is net-new infrastructure |
| 4 | `EXTERNAL_API_KEY` is live and shared with n8n | Phase A must migrate without breaking n8n |
| 5 | Naming mismatch (GRN≈picking, DO≈orders) | Mapping must be explicit |
| 6 | Sorento appears **single-tenant** (no `tenant_id` on domain models) | Confirm before designing ingest scoping |
| 7 | **PO write overturns a documented hard rule** | See §13 |

## 13. The PO hard rule - must be resolved explicitly

`SCM_Module_Build_Plan.md:37` and `documentation/plans/scm/scm-m4-cash-copilot-acceptance-criteria.md:64`
state:

> "The platform never raises a PO… AutoCount PO transmission (never - hard rule)."

The AutoCount integration **does** write POs. That rule is being overturned deliberately, and the
capability sits behind an explicit per-tenant switch that defaults **off**.

**Required before the PO-write slice merges:**

1. Named sign-off from whoever owns that rule - someone wrote "never" for a reason, presumably that an
   automated system creating real financial commitments in the accounting system was judged too risky.
2. Both documents updated to describe the new, gated behaviour.

`CLAUDE.md` treats those documents as **binding**. A plan that silently contradicts them should be
rejected at review. Do not let an integration quietly overturn a hard rule - that is how trust in the
whole sync dies.

## 14. Definition of Done

1. **No mock remains.** A frontend-first mock is debt, not done. Real backend wired and verified with real data.
2. **Every new column on an existing table has a backfill migration**, not seed-if-absent.
3. **No hardcoded lookup of a user-editable key.**
4. **Every new permission has a grant path for existing roles** - permissions computed at provision
   time do not reach existing roles automatically; the feature silently 403s otherwise.
5. **Verified end-to-end from the user's perspective**, with real data, at 375px and 1280px, on a
   freshly rebuilt frontend.

## 15. Testing

**pytest:** key auth (valid / invalid / revoked / rotated / out-of-scope); constant-time comparison;
ingest idempotency; per-document atomicity; masters quarantine; retryable-missing-reference;
ownership enforcement; event emission + retry + isolation from the originating transaction;
foreign-company rejection.

**E2E, real clicks (never direct URL navigation):** create an integration and copy its key; push a GRN
and see it in the UI; approve a document and observe `PENDING → SYNCED`; attempt to edit an
AutoCount-owned field and be blocked.

A test report keyed to AC ids (PASS / FAIL / DEFERRED) is required before merge.

### 15.1 Postgres, not sqlite

Every test in this feature runs against Postgres. The helpers live in `tests/_pg_fixture.py`:

- `pg_session()` - the live database inside a transaction that is rolled back. Use for anything
  reading or writing real tables. **Scope assertions to test-created rows** (`unique_code()` yields
  a `ZZT-` prefixed value); those tables hold production data, so a bare `count()` or `.one()` is
  answering a different question than the one asked.
- `pg_empty_schema(tables)` - the same model DDL emitted into a throwaway Postgres schema via
  `schema_translate_map`. Use where a blank slate is the point (seeding, fixed-name fixtures). FK
  dependencies and the tables the global flush listeners query are pulled in automatically.

**Why this is not a style preference.** Converting these nine files surfaced three defects the
sqlite versions could not have caught, because sqlite was not merely a different database but a
substantially weaker one:

| What sqlite did | What it hid |
|---|---|
| Every id is VARCHAR | `integration_references.integration_id` is `uuid` with an FK to `integrations`. A test passed the string `"int-9"` and was green. |
| Foreign keys unenforced (no `PRAGMA foreign_keys`) | `act_as_user_id` is `ON DELETE RESTRICT`. A test deleted an in-use principal and asserted the resolver coped - rehearsing a state the database forbids, while the real guarantee went untested. |
| A fresh empty engine per test | `integrations.name` and `users.email` are unique against rows migration 297 already created. Uniqueness held trivially against an empty table. |
| No SAVEPOINT semantics | Per-record ingest isolation - what stops one bad row costing a 10,000-row batch - was unprovable, and broke outright once `app.main` registered its global flush listeners. |

### 15.2 The whole suite moves off sqlite

**Decision: no sqlite anywhere in the backend test suite.** Not converted opportunistically -- all
121 remaining files, in one sweep.

The enabling helper is `blank_session()`, which replaces the suite's dominant fixture shape:

```python
# before
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
session = sessionmaker(bind=engine)()

# after
with blank_session() as session:
    ...
```

It yields a session over an empty copy of the **entire** real schema -- all 199 tables including
the `scm.*` models sqlite could not create at all -- built once per session in about 0.6s, with
every write discarded at teardown. `join_transaction_mode="create_savepoint"` means tests that call
`commit()` still work and are still rolled back, so the conversion does not force fixtures to be
rewritten around a different transaction model.

Three fixture shapes now cover everything:

| Helper | Use for |
|---|---|
| `blank_session()` | the default. An empty full schema. Replaces every in-memory sqlite fixture. |
| `pg_session()` | tests that must read real data. Scope assertions to `ZZT-` rows. |
| `pg_empty_schema(tables)` | a subset schema in isolation, where the full one is unhelpful. |

**Why a sweep and not attrition.** The sqlite failures were not inert. `test_rbac.py`'s four tests
failed at baseline with `OperationalError`, which reads as sqlite schema flakiness and had been
carried as such; on Postgres the real cause appeared immediately -- the fixture passes `role_id=`
to `User`, a column that no longer exists. That defect was legible only after the substrate was
right, and the same masking is presumed elsewhere. Leaving 121 files on sqlite means leaving an
unknown number of real defects behind a misleading error message.

The DoD for the sweep: no `create_engine("sqlite` anywhere under `tests/`, `_sqlite_compat.py`
deleted, the sqlite type-compiler shims removed from `conftest.py`, and the failing-test set no
larger than the 128-name baseline captured before the work began.
