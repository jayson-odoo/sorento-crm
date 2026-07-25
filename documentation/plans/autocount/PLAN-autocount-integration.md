# PLAN — AutoCount Integration (Sorento side)

> **UAC:** `documentation/plans/autocount/autocount-integration-acceptance-criteria.md` — the contract.
> **Counterpart repo:** `foundryx-shared-service` → `documentation/plans/sprint-4/13-autocount-esb.md`
> **Status:** DRAFT
> **Self-contained** — you can start from this file without the originating design conversation.

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

## 2. Group A first — the integration object

**This is task one. Nothing else ships before it.**

Today (`app/dependencies.py:546-582`, `app/config.py:58-61`):

- One static `EXTERNAL_API_KEY` env var, **shared with n8n**
- Compared with plain `!=` — not constant-time
- `get_external_api_user` applies **no permission check at all**
- No key table, no scopes, no rotation, no expiry, no per-caller identity
- No rate limiting on `/external`

Giving the ESB this key grants it everything n8n has, on a system that will write master data and
raise purchase orders. That is not an adequate trust boundary.

### Model it on the shared service

Read these before designing — the pattern is proven and should be mirrored, adapted to Sorento's
single-tenant shape:

| Concept | Shared-service reference |
|---|---|
| Connection record, config vs credentials split | `service_backend/app/models/connection.py` |
| Provider contract (`fields()`, `test()`, registry) | `service_backend/app/integrations/base.py` |
| Fernet encryption, graceful undecryptable handling | `service_backend/app/secrets.py`, `app/services/integration_service.py:52-66` |
| Blank-means-keep on secret PATCH | `app/services/integration_service.py:291-296` |
| Status model (`ACTIVE`/`UNVERIFIED`/`ERROR`), `last_tested_at`, `last_error` | `app/models/connection.py` |

### Schema

```
integrations
  id, name, type, status(ACTIVE|UNVERIFIED|ERROR),
  config_json,                    -- non-secret, displayable
  credentials_json,               -- Fernet ciphertext, write-only over API
  is_active, last_used_at, last_error, created_at, updated_at

integration_api_keys
  id, integration_id, key_hash,   -- hash only; plaintext shown once at creation
  key_prefix,                     -- short display fragment for identification
  scopes_json,                    -- e.g. ["masters:write","procurement:read"]
  expires_at, revoked_at, rotated_from_id, last_used_at, created_at
```

**Rules:**

- Plaintext key shown **once**, at creation. Only the hash persists. Never retrievable.
- Verification uses `hmac.compare_digest` — no `==`/`!=` on a secret anywhere.
- Every external endpoint enforces the caller's **scopes**.
- Rotation supports a grace window accepting old and new; both events audit-logged.
- Credentials Fernet-encrypted (reuse `app/utils/field_encryption.py`); blank on update = keep.
- Per-integration rate limiting with `429` + `Retry-After`.

### Migration off the env key (AC-AC-09) — do not skip

n8n is live on `EXTERNAL_API_KEY`. Sequence:

1. Ship the tables and the new dependency, accepting **both** new keys and the legacy env key.
2. Seed an integration record carrying the existing key so n8n continues working unchanged.
3. Migrate n8n to its own key.
4. Mark the env var deprecated with a removal date; remove the fallback.

Breaking n8n mid-migration is the main risk in this group. Steps 1–2 must land together.

## 3. Group B — ingest endpoints

One endpoint per entity, canonical shapes, authenticated by integration key with scopes.

**Entities:** Product, Stock, Warehouse, Supplier, Customer, Payment Terms, Tax,
Delivery Order (+lines), Goods Received Note (+lines).

**Naming — do not assume equivalence.** Map explicitly:

| AutoCount | Canonical | Sorento |
|---|---|---|
| GRN | `goods_receipt` | `picking_headers` / `picking_lines` |
| DO | `delivery_order` | `orders` / `order_lines` |
| Creditor | `supplier` | `suppliers` |
| Debtor | `customer` | `customers` |
| Item | `product` | `products` |

**Semantics:**

- **Idempotent** on `(source_system, source_ref)` — re-push updates in place, never duplicates.
  Response distinguishes created from updated.
- **Transactions all-or-nothing per document** — a GRN with one bad line persists nothing, and does
  not affect other documents in the batch.
- **Masters quarantine, never block** — 10,000 products with 12 invalid ⇒ 9,988 persist, 12 reported
  as failures for ESB-side quarantine. Valid rows are never withheld because siblings failed.
- **Missing referenced master ⇒ retryable, not fatal.** A GRN referencing an absent product returns a
  *retryable* marker distinct from a validation failure; re-push after the product exists succeeds
  with no manual intervention. (The ESB drains these automatically.)
- **Structured per-record errors** — machine-readable map of record → field → reason. The ESB logs
  per record and must not parse prose.
- **Ingest emits no lifecycle events** (AC-AC-18). A GRN arriving *from* AutoCount must never trigger
  a write *back* to AutoCount. This is the sync-loop guard and it is not optional.

Master resolution by natural code already exists and should be reused —
`app/api/v1/external/utils.py`: `get_products_by_code`, `get_warehouses_by_code_or_name`.

## 4. Group C — read endpoints

The ESB stages changes for human approval and renders **before → after** diffs. It needs Sorento's
current values to do that.

- Batched (never per-record round-trips), canonical shape, scope-enforced.
- Paginated with a documented cap; exceeding it errors rather than silently truncating.

## 5. Group D — `source_system` / `source_ref`

Every consumed table gains:

- `source_system` — `manual` | `seed` | `autocount`
- `source_ref` — AutoCount's **stable surrogate key** (`DocKey`), **not** `DocNo`

`DocNo` is mutable — AutoCount exposes a `NewDocNo` field. Correlating on it breaks when a document
is renumbered. Store `DocNo` for display if useful; correlate on `DocKey`.

**A real backfill migration is required** (AC-AC-23), not seed-if-absent. Existing production rows
backfill to `source_system='manual'`. Add a unique index supporting `(source_system, source_ref)`
lookup. Leaving old rows unpopulated breaks the first sync in a way that is hard to diagnose later.

## 6. Group E — per-field ownership

AutoCount owns some fields on a shared record; Sorento owns others. A supplier is **co-owned**:
AutoCount owns code, name, payment terms, lead time; Sorento owns account owner, relationship notes,
tags, activity history.

- Ownership is **configuration**, not hardcoded (AC-AC-26).
- API writes to AutoCount-owned fields are **rejected**.
- UI renders them **disabled with a "managed in AutoCount" affordance** — never editable-then-silently-
  reverted. A user typing a change that a later sync discards reads as data loss and destroys trust in
  the whole integration.

## 7. Group F — document lifecycle events

The ESB decides *when* to write to AutoCount. Which Sorento event triggers a write is
**configuration per document type** (`on_draft_created` / `on_approved` / `on_status_change` / `manual`).

**Therefore Sorento emits broadly and the ESB filters.** Emit one generic event:

```json
{ "event_id": "…", "doc_type": "purchase_order", "event": "approved",
  "doc_id": "…", "occurred_at": "…" }
```

**Do not build a bespoke hook per trigger.** A hook per trigger hardcodes the exact thing being made
configurable — every new trigger option would then need new Sorento code. One emitter, all transitions.

**Coverage:** PO, SQ, PR/RFQ, SO — at least created, submitted, approved, rejected, cancelled.

**Where it attaches:** `app/services/procurement_service.py:6546-6639`
(`PurchaseRequestService._apply_approval_decision`) is the single funnel for PR approval — both the
public-token flow and the authenticated flow route through it. On the SCM branch, PO confirm is
`PurchaseOrderService.bulk_confirm`.

**No event bus exists.** Closest is `AutomationService.dispatch_event`
(`app/services/automation_service.py:210-252`), whose actions are **email-only**. Two viable routes:

- **(a)** Add an outbound-webhook `action_type` to `Automation` — reuses the existing trigger registry.
- **(b)** A dedicated emitter writing to `integration_log` and drained by the existing retry machinery
  (`app/services/integration_service.py:704, 799`).

**Recommend (b)** — it reuses proven retry/backoff/dead-letter, keeps event delivery independent of
the email-shaped automation model, and gives per-event observability. (a) risks bending an
email-notification abstraction into a transport it was not designed for.

**Non-negotiables:**

- Persisted and retried with backoff; never lost; visible dead-letter after exhaustion.
- **Emission failure must never break the originating transaction.** A user's approval commits even if
  the ESB is unreachable. Fully isolated, logged.
- Stable `event_id` so the ESB can discard duplicates from retries.

## 8. Group G — sync status on documents

Everything is async. Sorento cannot create a PO and receive the AutoCount document number in the same
request. **This is UX work, not only plumbing** — it is the thing most likely to surprise stakeholders
late.

- Documents expose `PENDING` / `SYNCED` / `FAILED`.
- `SYNCED` carries the AutoCount document number; `FAILED` carries the error.
- State is visible **where the user works**, with a permission-gated retry on failure.
- The UI must not imply a document exists in AutoCount until confirmed.

## 9. Group H — new masters

Neither exists today.

- **Tax** — no model at all; only `orders.tax_amount` and `order_lines.tax`.
- **Payment Terms** — only `suppliers.payment_terms_days` (int) and free text on commercial quotations.

Both need a real master with `source_system`/`source_ref`, and existing values migrate to reference them.

## 10. Group I — company scoping

AutoCount is multi-company; a customer may run several company databases. **Sorento consumes exactly
one**, named explicitly in configuration.

**Why this matters:** `products.product_code`, `suppliers.supplier_code` and `warehouses.warehouse_code`
are **globally unique** with no company dimension. AutoCount codes (`001`, `300-V021`) are per-company
and will collide. Ingest from a company other than the configured one must be **rejected**, not
silently accepted — silent acceptance corrupts master data irreversibly.

Adding a company dimension to Sorento's masters is a large migration across every master table and
every query; it is deliberately **not** in scope. If cross-company reporting is ever required, that is
a separate plan decided on its own merits.

## 11. Sequencing

| Phase | Scope | Depends on |
|---|---|---|
| **A** | Integration object + per-integration keys + scopes + rotation + rate limit + n8n migration | — |
| **B** | `source_system`/`source_ref` columns + backfill migration | A |
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
| 1 | **`feat/scm-reorder-copilot` must merge** — `purchase_orders`, `sales_orders`, `purchase_order_lines`, `sales_order_lines` **do not exist on main** | Blocks B/F/G for those doc types |
| 2 | No Tax or Payment Terms tables | Phase D is net-new schema |
| 3 | No event bus | Phase G is net-new infrastructure |
| 4 | `EXTERNAL_API_KEY` is live and shared with n8n | Phase A must migrate without breaking n8n |
| 5 | Naming mismatch (GRN≈picking, DO≈orders) | Mapping must be explicit |
| 6 | Sorento appears **single-tenant** (no `tenant_id` on domain models) | Confirm before designing ingest scoping |
| 7 | **PO write overturns a documented hard rule** | See §13 |

## 13. The PO hard rule — must be resolved explicitly

`SCM_Module_Build_Plan.md:37` and `documentation/plans/scm/scm-m4-cash-copilot-acceptance-criteria.md:64`
state:

> "The platform never raises a PO… AutoCount PO transmission (never — hard rule)."

The AutoCount integration **does** write POs. That rule is being overturned deliberately, and the
capability sits behind an explicit per-tenant switch that defaults **off**.

**Required before the PO-write slice merges:**

1. Named sign-off from whoever owns that rule — someone wrote "never" for a reason, presumably that an
   automated system creating real financial commitments in the accounting system was judged too risky.
2. Both documents updated to describe the new, gated behaviour.

`CLAUDE.md` treats those documents as **binding**. A plan that silently contradicts them should be
rejected at review. Do not let an integration quietly overturn a hard rule — that is how trust in the
whole sync dies.

## 14. Definition of Done

1. **No mock remains.** A frontend-first mock is debt, not done. Real backend wired and verified with real data.
2. **Every new column on an existing table has a backfill migration**, not seed-if-absent.
3. **No hardcoded lookup of a user-editable key.**
4. **Every new permission has a grant path for existing roles** — permissions computed at provision
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
