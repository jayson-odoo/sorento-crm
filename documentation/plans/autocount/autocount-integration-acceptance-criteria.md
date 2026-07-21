# AutoCount Integration (Sorento side) — User Acceptance Criteria

> **Status:** Group A GRILLED + LOCKED (2026-07-21). Groups B–I still DRAFT.
> Contract for `documentation/plans/autocount/PLAN-autocount-integration.md`
> **Counterpart repo:** `foundryx-shared-service` → `documentation/plans/sprint-4/13-autocount-esb-acceptance-criteria.md`
> **Read that first if you need the full picture.** This file is self-contained for the Sorento work.

## Context (read this — it explains why the shape is what it is)

Customers run **AutoCount on-premise**. Sorento runs in the cloud. They cannot reach each other directly.
A new **ESB module in the FoundryX shared service** sits between them: it holds the AutoCount credentials,
owns the single static egress IP that customers whitelist, translates AutoCount's schema into a
**canonical shape**, and pushes into Sorento. Sorento **never calls AutoCount** and never learns
AutoCount's field names.

```
AutoCount (on-prem)  ⇄  FoundryX ESB (cloud, static IP)  ⇄  Sorento CRM (cloud)
        ▲                                                          │
        └────────── writes (PO/SQ/PR/SO) ──── events ──────────────┘
```

This matches what Sorento already documented in `documentation/reference/SCM_Module_Build_Plan.md:11-21`
("The SCM core never reads AutoCount… every table has `source_system` and `source_ref`").
**That design is adopted, not replaced.**

**Direction of truth:** AutoCount is the system of record for masters. Sorento owns transactions it
originates (PR, SQ, SO, PO) and pushes them out.

**One company per Sorento deployment.** The ESB is multi-company; Sorento consumes exactly one,
explicitly configured. Sorento's master codes are globally unique and must not be asked to hold two
companies' code spaces.

---

## Group A — Integration object and credentials (do this first)

> Today: a single static `EXTERNAL_API_KEY` env var, shared with n8n, compared with plain `!=` in
> `app/dependencies.py:546-582` on a dependency that applies **no permission check**. That is not an
> acceptable trust boundary for a caller that writes master data and raises purchase orders.
> Model the replacement on the shared service's `connections` + `IntegrationProvider` design
> (`service_backend/app/models/connection.py`, `app/integrations/base.py`, `app/secrets.py`).

### AC-AC-01 `[BE]` An integration is a first-class record, not an env var
**Given** an administrator
**When** they create an integration
**Then** a row is persisted with: name, type, status (`ACTIVE`/`UNVERIFIED`/`ERROR`), non-secret config, and encrypted credentials
**And** no integration identity or secret is read from environment variables.

### AC-AC-02 `[BE]` Each integration has its own API key
**Given** two integrations (`foundryx-esb`, `n8n`)
**When** each calls Sorento
**Then** each authenticates with its **own** key
**And** revoking one does not affect the other
**And** the caller's identity is recorded on every request.
> Directly replaces the shared-secret model.

### AC-AC-03 `[BE]` Keys are stored hashed, shown once
**Given** a newly created integration
**When** the key is generated
**Then** the plaintext is displayed **once** at creation
**And** only a hash is persisted
**And** it can never be retrieved again — only rotated.

### AC-AC-04 `[BE]` Key comparison is constant-time
**Given** an inbound request
**When** the key is verified
**Then** comparison uses `hmac.compare_digest`
**And** no code path uses `==`/`!=` on a secret.
> `app/dependencies.py:546-582` currently does. Fix it.

### AC-AC-05 `[BE]` Every external endpoint enforces the caller's RBAC permissions
**Given** an integration whose role lacks `master_data.products.edit`
**When** it calls a masters-write endpoint
**Then** the request is rejected `403`
**And** **all 17** `/external/*` endpoints enforce permissions against the integration's
`act_as_user_id` via `require_permission_with_api_key`.
> Revised 2026-07-21 (decisions A1/A3/A8). There is **no separate scope vocabulary** — RBAC slugs
> are the single authorization source. `get_external_api_user` applies no permission check at all
> today; that dependency is retired.

### AC-AC-05a `[BE]` An integration acts as a real user
**Given** any integration
**When** it writes a record
**Then** `created_by`/`updated_by` and the audit trail resolve to a real `users` row named for that
integration
**And** no code path passes the string `"system"` as a user id.
> `get_external_api_user` currently returns a hardcoded fake `{"id": "system"}` matching no row.

### AC-AC-05b `[BE]` Integration users cannot log in interactively
**Given** an integration's user row
**When** anyone attempts an interactive login as it
**Then** the attempt fails
**And** the row is flagged `is_integration`, distinct from `is_protected`.
> `is_protected` already selects notification recipients (`automation_service.py:34`); overloading
> it would silently enrol the ESB into automation emails.

### AC-AC-06 `[BE]` Rotation without downtime
**Given** an active integration
**When** its key is rotated
**Then** a grace window (**default 7 days**) accepts both old and new
**And** the old key stops working when `expires_at` lapses, **evaluated at request time — no cron**
**And** an admin can revoke the old key immediately rather than waiting out the window
**And** both events are audit-logged.
> The scheduler is opt-in and defaults off, so a cron-driven expiry would fail **open**.

### AC-AC-06a `[BE]` Expiry is diagnosable
**Given** a key whose grace window has lapsed
**When** it is used
**Then** the response carries a distinct `key_expired` code, not a generic invalid-key error
**And** the old key's `last_used_at` is visible **before** expiry so migration can be confirmed.

### AC-AC-07 `[BE]` Credentials encrypted at rest
**Given** any stored secret on an integration
**When** persisted
**Then** it is Fernet-encrypted (reuse `app/utils/field_encryption.py`)
**And** never returned by any read endpoint
**And** a blank value on update means "keep existing", never "clear".

### AC-AC-08 `[FE]` Integration management UI
**Given** an administrator
**When** they open integration settings
**Then** they can create, view status, rotate, revoke and delete integrations
**And** secret fields are masked with a reveal toggle
**And** last-used timestamp and last error are visible.

### AC-AC-09 `[BE]` Migration off the env key — seeded once, no runtime fallback
**Given** the existing `EXTERNAL_API_KEY`, shared by **n8n and the MCP server**
**When** this group ships
**Then** a migration reads the env var **once, at migration time** and seeds a `legacy-shared-key`
integration carrying its hash, so both callers keep working with **zero changes**
**And** **no runtime code path ever reads the env var** — no dual-accept fallback is written
**And** if the env var is absent the migration seeds nothing and logs loudly, never an empty hash.
> Existing n8n traffic must not break. This is a live system. Revised 2026-07-21 (decision A6):
> seeding the *hash of the same value* satisfies both "n8n keeps working" and "nothing reads env at
> runtime", so AC-AC-01 and AC-AC-09 no longer conflict.

### AC-AC-09a `[BE]` The MCP server gets its own integration
**Given** `sorento_crm_mcp` authenticates with the same shared `EXTERNAL_API_KEY`
**When** per-caller identity is established
**Then** the MCP server has its **own** integration and key, distinct from n8n's
**And** the read-only tool surface it fronts remains reachable.
> n8n reaches MCP tools transitively via `sub-get-results`. Omitting this breaks that path.

### AC-AC-09b `[BE]` The leaked production key is rotated
**Given** the current key is a plaintext literal in ~40 n8n nodes (not an n8n credential)
**When** per-caller keys are issued
**Then** the shared key is rotated and the legacy integration revoked once its `last_used_at`
goes quiet.
> The 7-day grace window (AC-AC-06) exists because ~40 nodes must be edited.

### AC-AC-10 `[BE]` Rate limiting on external endpoints
**Given** an integration exceeding its configured rate
**When** it calls
**Then** `429` with `Retry-After` is returned
**And** the limit is per integration, not global
**And** when the limiter backend is unavailable the request is **allowed** (fail-open) and an alert
is raised.
> `/external` has no rate limiting today. Fail-open matches `app/services/rate_limit.py`'s existing,
> deliberate semantics (decision A7): rate limiting here is abuse control, not authorization — a
> dead limiter grants no access, since authentication is DB-backed and still enforced. Fail-closed
> would turn a Redis blip into a simultaneous ESB-sync and n8n outage.

---

## Group B — Ingest endpoints (ESB → Sorento)

### AC-AC-11 `[BE]` Ingest accepts canonical shapes
**Given** the ESB pushing a batch
**When** it calls the ingest endpoint for an entity
**Then** the payload is the **canonical** shape (no AutoCount field names)
**And** unknown fields are rejected explicitly, not silently ignored.

### AC-AC-12 `[BE]` Ingest is idempotent on `(source_system, source_ref)`
**Given** a record already ingested
**When** the identical payload is pushed again
**Then** no duplicate is created
**And** the existing record is updated in place
**And** the response distinguishes created from updated.

### AC-AC-13 `[BE]` Per-record structured errors
**Given** a batch of 50 where 3 fail validation
**When** it is processed
**Then** the response names each failing record, field and reason in a machine-readable map
**And** the ESB can log per record without parsing prose.

### AC-AC-14 `[BE]` Transactions are all-or-nothing per document
**Given** a GRN whose line 3 is invalid
**When** ingested
**Then** neither header nor any line is persisted
**And** other documents in the batch are unaffected.

### AC-AC-15 `[BE]` Masters quarantine, they do not block
**Given** a masters batch of 10,000 with 12 invalid
**When** ingested
**Then** 9,988 persist
**And** 12 are reported as failures for ESB-side quarantine
**And** valid rows are never withheld because of invalid siblings.

### AC-AC-16 `[BE]` Missing referenced master ⇒ retryable, not fatal
**Given** a GRN referencing a product not yet present
**When** ingested
**Then** the response marks it retryable (distinct from a validation failure)
**And** re-pushing after the product exists succeeds with no manual intervention.

### AC-AC-17 `[BE]` Entities covered
Ingest exists for: Product, Stock, Warehouse, Supplier/Creditor, Customer/Debtor, Payment Terms, Tax,
Delivery Order (+lines), Goods Received Note (+lines).

### AC-AC-18 `[BE]` Ingest never fires outbound sync events
**Given** an ingested record
**When** it is written
**Then** no document-lifecycle event is emitted back to the ESB
**And** no sync loop can form.
> A GRN arriving from AutoCount must not trigger a write back to AutoCount.

---

## Group C — Read endpoints (for diffing)

### AC-AC-19 `[BE]` Current-state read for diff rendering
**Given** the ESB preparing an approval diff
**When** it requests current values for a set of records
**Then** Sorento returns them in canonical shape
**And** the request is batched (no per-record round-trip)
**And** it is scoped by the caller's integration permissions.

### AC-AC-20 `[BE]` Read endpoints are paginated and bounded
**Given** a request for many records
**When** it exceeds the page cap
**Then** a documented cap applies and pagination is offered
**And** exceeding it returns a clear error rather than a truncated body.

---

## Group D — `source_system` / `source_ref`

### AC-AC-21 `[BE]` Consumed tables carry source columns
**Given** every table the ESB writes
**When** the migration runs
**Then** each has `source_system` (`manual`/`seed`/`autocount`) and `source_ref`
**And** existing rows backfill to `manual`
**And** a unique index supports lookup by `(source_system, source_ref)`.
> Pattern already designed in `SCM_Module_Build_Plan.md`; extend beyond the SCM branch.

### AC-AC-22 `[BE]` `source_ref` holds AutoCount's stable key
**Given** an AutoCount document with `DocKey` and `DocNo`
**When** it is ingested
**Then** `source_ref` holds the stable surrogate (`DocKey`), not the mutable `DocNo`
**And** a renumbered document still resolves to the same Sorento row.

### AC-AC-23 `[BE]` Backfill is a real migration, not seed-if-absent
**Given** existing production rows
**When** this ships
**Then** a migration populates the new columns for rows that already exist
**And** no row is left in a state that breaks a later sync.

---

## Group E — Per-field ownership

### AC-AC-24 `[BE]` AutoCount-owned fields are protected
**Given** a supplier whose `payment_terms_days` is AutoCount-owned
**When** a Sorento user attempts to edit it via API
**Then** the write is rejected
**And** consumer-owned fields on the same record remain editable.

### AC-AC-25 `[FE]` Owned fields are visibly managed, not silently reverted
**Given** an AutoCount-owned field in the UI
**When** the user views the record
**Then** the field is disabled with an indication it is managed in AutoCount
**And** the user is never able to type a change that a later sync silently discards.

### AC-AC-26 `[BE]` Ownership is configuration
**Given** a change to which fields AutoCount owns
**When** configuration is updated
**Then** enforcement changes with no code deploy.

---

## Group F — Document lifecycle events (Sorento → ESB)

### AC-AC-27 `[BE]` Generic lifecycle event, not per-trigger hooks
**Given** any tracked document changing state
**When** the transition commits
**Then** one generic event `{doc_type, event, doc_id, occurred_at}` is emitted
**And** adding a new trigger option requires **no new Sorento code**.
> The ESB filters. Do not build a bespoke hook per trigger — that hardcodes the thing being made configurable.

### AC-AC-28 `[BE]` Coverage
Events fire for PO, SQ, PR/RFQ, SO on at least: created, submitted, approved, rejected, cancelled.

### AC-AC-29 `[BE]` Delivery is reliable
**Given** the ESB is unreachable
**When** an event fires
**Then** it is persisted and retried with backoff
**And** it is never lost
**And** after exhausting retries it dead-letters visibly.
> Use the existing `integration_log` retry machinery (`app/services/integration_service.py:704,799`).

### AC-AC-30 `[BE]` Emission never breaks the originating transaction
**Given** the event path throws
**When** a user approves a document
**Then** the approval still commits
**And** the failure is isolated and logged.

### AC-AC-31 `[BE]` Events are deduplicated
**Given** a retried delivery
**When** the ESB receives it twice
**Then** each event carries a stable id allowing the ESB to discard the duplicate.

---

## Group G — Sync status on documents

### AC-AC-32 `[BE]` Documents carry sync state
**Given** a document configured to sync
**When** it is pushed
**Then** it exposes `PENDING` / `SYNCED` / `FAILED`
**And** `SYNCED` carries the AutoCount document number
**And** `FAILED` carries the error.

### AC-AC-33 `[FE]` Sync state is visible where the user works
**Given** a user viewing a document
**When** it has a sync state
**Then** it is shown on the document
**And** `FAILED` explains what went wrong and offers retry (permission-gated).
> Users must never believe a document reached AutoCount when it did not.

### AC-AC-34 `[FE]` Async is honest in the UI
**Given** a user approves a document
**When** the approval succeeds
**Then** the UI does not claim it exists in AutoCount until confirmed
**And** the pending state is explicit.

---

## Group H — New masters

### AC-AC-35 `[BE]` Tax master
**Given** no tax master exists today
**When** this ships
**Then** a tax table exists with code, rate, description, active flag
**And** it carries `source_system`/`source_ref`.

### AC-AC-36 `[BE]` Payment terms master
**Given** only `suppliers.payment_terms_days` (int) and free-text elsewhere
**When** this ships
**Then** a payment-terms master exists
**And** existing values migrate to reference it
**And** it carries `source_system`/`source_ref`.

---

## Group I — Company scoping

### AC-AC-37 `[BE]` Exactly one AutoCount company per deployment, explicitly configured
**Given** deployment configuration
**When** the integration is set up
**Then** the AutoCount company is named explicitly
**And** ingest from any other company is **rejected**, not silently accepted.
> Sorento's `product_code`/`supplier_code`/`warehouse_code` are globally unique. Two companies'
> code spaces would collide and corrupt master data. This rejection is the guard.

---

## Cross-cutting

### AC-AC-38 `[BE]` Audit trail
Every ingest, event emission and ownership rejection is attributable to an integration identity and timestamp.

### AC-AC-39 `[BE]` No secret leakage
Keys and credentials never appear in logs, audit records, error messages or responses.

### AC-AC-40 `[FE]` Responsive at 375px and 1280px
Integration settings, sync-status surfaces and error views work at both widths.

### AC-AC-41 `[T]` Tests
pytest covers: key auth (valid/invalid/revoked/rotated/scoped), ingest idempotency, per-document
atomicity, masters quarantine, retryable-missing-reference, ownership enforcement, event emission
+ retry + isolation, company rejection.

### AC-AC-42 `[E2E]` Real-click journeys
Create an integration and copy its key; push a GRN through ingest and see it in the UI; approve a
document and observe `PENDING → SYNCED`; attempt to edit an AutoCount-owned field and be blocked.
Navigate by clicking, never by direct URL.

---

## Dependencies and risks

| # | Item | Impact |
|---|---|---|
| 1 | **`feat/scm-reorder-copilot` must merge** — `purchase_orders`, `sales_orders` and their line tables do not exist on main | Blocks Groups B/F/G for those doc types |
| 2 | **No Tax or Payment Terms tables exist** | Group H is net-new schema |
| 3 | **No event bus exists** — closest is `AutomationService.dispatch_event` (email-only actions) and the funnel at `app/services/procurement_service.py:6546-6639` | Group F is net-new infrastructure |
| 4 | **`EXTERNAL_API_KEY` is live and shared with n8n** | Group A must migrate without breaking n8n (AC-AC-09) |
| 5 | **Naming mismatch** — AutoCount GRN ≈ Sorento `picking_headers`/`picking_lines`; AutoCount DO ≈ `orders`/`order_lines` | Mapping must be explicit; do not assume name equivalence |
| 6 | **Sorento appears single-tenant** (no `tenant_id` on domain models) | Confirm before designing multi-tenant ingest |
| 7 | **PO write overturns a documented hard rule** (`SCM_Module_Build_Plan.md:37`) | Requires doc update + named sign-off |

## Definition of Done

1. No phase-1 mock remains — real backend wired and verified with real data.
2. Every new column on an existing table has a **backfill migration**, not seed-if-absent.
3. No code hardcode-looks-up a user-editable key.
4. Every new permission has a grant path for **existing** roles.
5. Verified end-to-end from the user's perspective at 375px and 1280px on a fresh build.
