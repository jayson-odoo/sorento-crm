# PLAN — Complaint ↔ Delivery Order Auto-Fulfilment (keyed by Remarks CS)

**Status:** Drafted (grilled with user 2026-06-30). Awaiting final plan review → then Phase 1.

## Problem

CS resolves a complaint by raising a **replacement / fulfilment Delivery Order (DO)** and typing the
complaint number(s) into the DO's **Remarks CS** field. The system must:

1. **Auto-link** that DO to the named complaint(s).
2. Let CS **see the fulfilment DO(s) from the complaint detail view** (and the reverse).
3. **Auto-fulfil** (close to a new `fulfilled` status) the complaint when its replacement is delivered.
4. **Notify** per delivery: the customer contact + the complaint team.
5. Handle **amendment** of Remarks CS sanely (relink / unlink / freeze).

The complaint's existing `delivery_order_number` (the *original* complained-about order) is a **separate**
relationship and stays untouched.

## Ground truth (verified in code)

- **Complaint** — `app/models/complaints.py`, table `complaints`.
  - `complaint_number` (Text), `delivery_order_number` (Text, original order — leave alone),
    `status` (String(50), default `new`), `contact_id` (Text → RespondContact),
    `assigned_to` (Text), `salesperson`/`contact_person`/`contact_number` (free text).
  - Statuses: `new, submitted, updated, responded, approved, rejected, processed_by_cs, closed`.
  - Terminal finalize: `_finalize_complaint()` (~1635) emits
    `emit_form_event(db, "complaint", id, "resolved", contact_id=...)`.
  - Audit-tracked (`__audit_track__`).
- **Order (DO)** — `app/models/order.py`, table `orders`.
  - `order_number` (unique), `remarks_cs` (Text — **the field CS types into**, backs the list grid column
    `OrdersList.tsx:253`), `delivery_remarks_cs` (Text — *not* used here),
    `actual_delivery_date` (DateTime — **the delivered signal**), `order_status_id` (FK OrderStatus),
    `is_cancelled` (Boolean, `order.py:173`).
  - DO `status` codes: `NEW, PENDING, APPROVED, PROCESSING, SHIPPED, DELIVERED (="Picked Up / In Transit",
    Final=Yes), CANCELLED, COMPLETED`. Import only ever sets `new`/`delivered` (delivered ⇔
    `actual_delivery_date` present).
  - **Import = UPSERT** by `order_number`, blind `setattr` (overwrites `remarks_cs` every run, blank→NULL).
    `import_excel_tracking()` (`order_service.py:1421-1893`); `validate_only=True` = dry-run + rollback
    returning `{valid, errors, warnings, summary}`; real import is async via RQ `imports` queue
    (`process_order_tracking_import`), warnings land in `ImportJob.result['warnings']` + `ImportLog.warnings`.
  - `PUT /orders/{id}` → `update_order()` (`order_service.py:1107`) — interactive single edit.
- **Complaint team** — Tier **1 + Tier 2** of Access Agent code `complaint`, team set code `complaint`.
  `_get_complaint_handler_user_ids()` (`complaints_service.py:640`); team notify
  `notify_team_complaint_external_created()` (in-app + email via `NotificationService`).
- **Customer notify** — `_notify_complaint_field()` (`complaints_service.py:1953`) → Respond/WhatsApp via
  `contact_id`. Every Respond send must write `integration_log` on success AND failure (outbox rule).

## Decisions (locked via grilling)

### Linking
- **Match key:** split `remarks_cs` on `&`, `,`, and whitespace → trim tokens → **exact case-insensitive
  match** against `complaint_number` in DB (format-agnostic; `CMP26-0042` going forward, legacy bare numbers
  still work). Non-matching token → ignored (optional info note). One batched
  `WHERE lower(complaint_number) IN (tokens)` per import — **no per-row queries** (import speed constraint).
- **Link eligibility gate:** a DO can only link to a complaint that is **already `processed_by_cs`** (or
  already `fulfilled`). Linkable statuses = `{processed_by_cs, fulfilled}`. A token matching a complaint in an
  earlier open state (`new/submitted/updated/responded/approved`) or sticky-terminal (`closed/rejected`) →
  **do NOT link, log warning** ("Order X: complaint Y not yet processed by CS / is closed — not linked").
- **Cardinality:** many-to-many. One DO can name many complaints; one complaint can have many DOs (partial
  shipments).
- **Storage:** new join table **`complaint_fulfilment_orders`**:
  `id, complaint_id (FK), order_id (FK), linked_at, delivery_notified_at (nullable)`.
  Unique `(complaint_id, order_id)`.
- **Link only on change:** snapshot DB `remarks_cs` **before** `setattr`, diff old vs new; only changed rows
  enter the link pass. Identical re-import = zero extra work, no events.

### Fulfilment (close) — status machine
- New complaint status **`fulfilled`** (label "Fulfilled", own pill colour).
- **Only path:** `processed_by_cs ⇄ fulfilled` (linking is gated on `processed_by_cs`, see eligibility gate).
  `processed_by_cs` is the single open state in this loop.
- **Sticky terminal** = `{closed, rejected}` — automation never sets/overrides (a delivery notice may still
  fire as a fact, but status untouched). Cannot be linked.
- **Close rule:** on any DO-input change, recompute the affected complaint. Complaint → `fulfilled` when it is
  `processed_by_cs` AND **every non-cancelled linked DO** (`is_cancelled = false`) is delivered
  (`actual_delivery_date` not null). `is_cancelled` DOs are excluded from the check.
- **Auto-reopen (allowed, safe):** if a complaint is `fulfilled` and a new non-delivered DO links (or a
  delivered DO un-delivers — edge), it reopens **to a fixed `processed_by_cs`**. No `status_before_fulfilment`
  storage needed — the only pre-fulfilment state is `processed_by_cs` by the eligibility gate.
- On `fulfilled`, mirror `_finalize_complaint` SLA close (`emit_form_event "resolved"`).
  **SLA on reopen:** nothing to resurrect — `processed_by_cs` already closed the CS-response SLA; reopening to
  `processed_by_cs` leaves SLA closed. (Resolved by the gate, not a risk.)

### Notification — decoupled from status (per-DO-delivery fact)
- Fires **per linked DO delivery**, not on the status flip. Content: *"Complaint CMP26-0042 — DO
  REPPS2605-0012 delivered, items: [code × qty …]"*. **Never announces "fulfilled".**
- **Idempotency:** stamp `complaint_fulfilment_orders.delivery_notified_at` when sent; re-import of an
  already-notified delivery does not resend. Once per `(complaint, DO)` delivery.
- **Recipients / channels:**
  - **Customer contact** (`complaint.contact_id`) → Respond/WhatsApp, logged to `integration_log`
    (success + failure). Skip gracefully if `contact_id` null.
  - **Complaint team** (Tier 1 + Tier 2, agent `complaint`, set `complaint`) → in-app + email. Recipients =
    team **membership** (controlled in User Management → Teams / Access Agents, single source of truth,
    auto-tracked). **No automation-engine event** — the engine is email-only, can't WhatsApp, can't resolve
    `contact_id`, and recipients are roles/users not teams. Hardcode both audiences.
- Side effects are **best-effort post-commit** (catch + warn, never raise). Run only in the **real** import
  (`validate_only=False`) / committed PUT — never during dry-run.

### Amendment / freeze
- **Pending/in-transit DO:** `remarks_cs` fully editable — relink, add/remove complaint numbers, unlink. Safe
  (nothing fulfilled/notified yet). Removing a token before delivery just drops the link; complaint stays
  open.
- **Delivered DO with ≥1 linked complaint → `remarks_cs` FROZEN** (its fulfilment is historical; the delivery
  notice already fired). Keys off the DO's own monotonic delivered state, not the (flapping) complaint status.
  - **Import:** if incoming `remarks_cs` differs from frozen DB value → **keep DB value, skip that field
    only**, append warning *("Order X: Remarks CS change ignored — DO already delivered and linked to
    complaint Y")*. Never aborts the import. Surfaces in test-import warnings + real-import job/ImportLog.
  - **`PUT /orders/{id}`:** **BE rejects** the `remarks_cs` change (`AppException` 422); **FE renders
    remarks_cs readonly** when frozen. Order response exposes a `remarks_cs_locked` boolean.

### Triggers — one centralized helper
`recompute_complaint_fulfilment(order, old_remarks, new_remarks)` (or similar) called from **all input-change
sites**:
1. **Import row** (`import_excel_tracking`) — after remarks/delivery applied, batched per import.
2. **`PUT /orders/{id}`** (`update_order`) — remarks_cs and/or actual_delivery_date and/or is_cancelled.
3. **`is_cancelled` flip** — cancelling the lone pending DO can make "all non-cancelled delivered" true →
   recompute.
Logic lives once: (a) reconcile links from remarks delta, (b) recompute fulfil/reopen status, (c) emit
per-DO delivery notifications for newly-delivered linked DOs.

### Backfill (one-time, idempotent)
Script scans all orders' `remarks_cs`, creates links, sets `fulfilled` where all non-cancelled linked DOs
already delivered — **but stamps `delivery_notified_at = now()` WITHOUT sending** (no historical spam). System
starts in a correct, already-notified state; only genuinely new deliveries notify going forward. Re-runnable
(JOIN-based "set to correct value where mismatch").

### Display
- **Complaint detail** — new always-rendered **"Fulfilment Delivery Orders"** section (after Respond
  conversation, before Assignee). Table per linked DO: **DO Number** (link to DO detail, human number, no
  UUID), **Status** pill, **Delivery Date** (or "—"), and an **icon → popup** showing that DO's line items
  (code × qty). Empty state: *"No replacement delivery order linked yet."*
- Register `fulfilled` in FE `lib/complaint-status.ts` pill class + label maps.
- **Reverse view (in scope)** — **DO detail page** shows *"Fulfils complaints: CMP26-0042 …"* linking back to
  each complaint detail.

## UAC — User Acceptance Criteria (verify FE + BE against every line before handoff)

### Linking
- **UAC-L1** — DO with `remarks_cs = "CMP26-0042"` (complaint is `processed_by_cs`) imported → link row created;
  the DO appears in the complaint's "Fulfilment Delivery Orders" section.
- **UAC-L2** — `remarks_cs = "CMP26-0001 & CMP26-0002"` → both complaints linked to that DO.
- **UAC-L3** — token matching no complaint → ignored; import does not error.
- **UAC-L4** — token matches a complaint NOT `processed_by_cs` (e.g. `new/responded/approved`) → **not linked**;
  import logs a warning ("complaint not yet processed by CS — not linked").
- **UAC-L5** — token matches a `closed`/`rejected` complaint → not linked; warning logged.
- **UAC-L6** — re-import with identical `remarks_cs` → no new link, no event, no notification.
- **UAC-L7** — match is case-insensitive; separators `&`, `,`, whitespace all split correctly.
- **UAC-L8** — one DO links many complaints; one complaint accumulates many DOs.

### Fulfil / status
- **UAC-F1** — complaint `processed_by_cs`, its single linked DO gets `actual_delivery_date` → complaint
  `fulfilled`.
- **UAC-F2** — complaint with 2 linked DOs, one delivered one pending → stays `processed_by_cs`.
- **UAC-F3** — both linked DOs delivered → `fulfilled`.
- **UAC-F4** — linked DOs: one delivered, one `is_cancelled` → `fulfilled` (cancelled excluded).
- **UAC-F5** — `fulfilled` complaint, a new non-delivered DO links → reopens to `processed_by_cs`.
- **UAC-F6** — after reopen, the new DO delivers → all non-cancelled delivered → `fulfilled` again.
- **UAC-F7** — cancelling the lone pending DO triggers recompute → `fulfilled`.
- **UAC-F8** — `closed`/`rejected` complaint + a linked DO delivers → status unchanged (sticky).
- **UAC-F9** — on `fulfilled`, complaint SLA stage closes (`emit_form_event "resolved"`); on reopen, SLA is not
  resurrected.

### Notify (per-DO-delivery, once)
- **UAC-N1** — when a linked DO newly delivers, the complaint's `contact_id` receives a Respond/WhatsApp
  message naming complaint#, DO#, and delivered items; `integration_log` written on success.
- **UAC-N2** — Respond send fails (wrong creds) → `integration_log` still written (failure) +
  `notification_delivery` = failed (outbox rule).
- **UAC-N3** — complaint team (Tier 1+2) receives in-app + email with the same per-delivery content.
- **UAC-N4** — re-import / re-save of an already-notified delivered DO → no re-notification
  (`delivery_notified_at` gate).
- **UAC-N5** — `contact_id` null → customer notify skipped gracefully; team still notified.
- **UAC-N6** — notification wording is a delivery fact, never "complaint fulfilled".
- **UAC-N7** — dry-run import (`validate_only=true`) sends nothing and creates no links (rolled back).
- **UAC-N8** — a notify failure does not 500 the import/PUT (best-effort post-commit).

### Freeze (amendment guard)
- **UAC-Z1** — DO delivered + linked: import with a changed `remarks_cs` → DB value kept, field skipped,
  warning surfaced in BOTH test-import response and real-import job/ImportLog.
- **UAC-Z2** — `PUT /orders/{id}` changing a frozen `remarks_cs` → 422 rejected with clear message.
- **UAC-Z3** — FE order edit renders `remarks_cs` readonly when the order response `remarks_cs_locked` is true.
- **UAC-Z4** — pending (not-delivered) DO: `remarks_cs` editable; removing a token unlinks; linked complaint
  stays open.

### Display
- **UAC-D1** — complaint detail always renders the "Fulfilment Delivery Orders" section; empty state shows
  "No replacement delivery order linked yet."
- **UAC-D2** — each linked DO row shows DO number (links to DO detail), status pill, delivery date (or "—").
- **UAC-D3** — an icon on each DO row opens a popup listing that DO's line items (product code × qty).
- **UAC-D4** — `fulfilled` renders its own status pill + label on list and detail.
- **UAC-D5** — DO detail page shows "Fulfils complaints: CMP26-…" linking to each complaint.
- **UAC-D6** — no UUIDs shown anywhere in the new UI (human numbers only).

### Backfill / performance
- **UAC-B1** — backfill creates links + sets `fulfilled` where all non-cancelled linked DOs already delivered,
  stamping `delivery_notified_at` WITHOUT sending any message.
- **UAC-B2** — backfill is idempotent (re-run creates no duplicates, corrects mismatches).
- **UAC-P1** — importing N orders with no `remarks_cs` change issues no per-row complaint queries (batched,
  delta-only) — import throughput unchanged.

## Three-phase breakdown

### Phase 1 — FE prototype (mock data)
- Complaint detail "Fulfilment Delivery Orders" section + items popup + empty state, off mock fixtures.
- `fulfilled` status pill/label.
- Order edit: `remarks_cs` readonly state driven by mock `remarks_cs_locked`.
- DO detail "Fulfils complaints" reverse block (mock).
- Document the API contract (link list shape, `remarks_cs_locked`, reverse list) at top of the service files.
- Verify via Playwright MCP through the sidebar. No backend, no tests yet.

### Phase 2 — BE wiring + tests
- Migration: `complaint_fulfilment_orders` table; new `fulfilled` status accepted (no enum change — status is
  String(50)). No `status_before_fulfilment` column — reopen target is fixed `processed_by_cs`.
- `recompute_complaint_fulfilment` helper (link reconcile + fulfil/reopen + per-DO delivery notify); batched,
  delta-only; wired into import / PUT / cancel.
- Freeze enforcement: import warn+skip; PUT BE reject; `remarks_cs_locked` on order response.
- Notify: customer (Respond + integration_log) + team (in-app + email), idempotent on `delivery_notified_at`,
  best-effort post-commit.
- `fulfilled` SLA close mirrors `_finalize_complaint`.
- Endpoints: complaint detail returns linked fulfilment DOs (+ items for popup); DO detail returns fulfilled
  complaints.
- Idempotent backfill script (stamp-without-send).
- FE off mocks onto real hooks/services.
- **Tests (land here):** pytest (link match incl. multi-token & non-match, eligibility gate = link only
  when `processed_by_cs`, fulfil-on-all-delivered, cancelled-excluded, reopen-to-`processed_by_cs`,
  sticky-terminal not-linked, freeze import-warn + PUT-reject, notify-once idempotency, backfill no-send); vitest (section states, items popup, readonly remarks, reverse block);
  playwright (import DO w/ complaint# → link appears on complaint → mark delivered → status fulfilled +
  notification logged).

### Phase 3 — Code review
`/code-review` → address → PR with Phase-1 screenshots + contract doc.

## Open risks / notes
- `contact_id` null on legacy complaints → customer notify skipped (team still notified).
- Token that matches no complaint → ignored (optional info-log; do not warn-spam).
- Backfill must run AFTER the new code is deployed so freeze/idempotency columns exist.
