# UAC - Form void (with reason + banner)

**Status:** Draft (pre-code) · **Classification:** CORE · **Domain:** forms / procurement / complaints
**Plan:** `documentation/plans/forms/PLAN-form-void.md`
**Contract:** each of the four forms (Purchase Request, Sponsorship Form, Complaint, Stock Inquiry)
can be **voided with a required free-text reason** from any non-terminal state, gated by a per-form
`<form>.void` permission. Voiding is **irreversible**, sets a terminal `status='voided'`, emits a
`voided` form-SLA event (which - by config - closes the running tracker), renders a gray `VoidBanner`
(WHO · WHEN · reason) at the top of the detail page, makes the form fully read-only, and notifies the
assignee + handling-lock holder (in-app) + the salesperson (`respond_contact_id`) via WhatsApp using
the existing status-update path.

Tags: `[BE]` backend · `[FE]` frontend · `[E2E]` playwright · `[T]` unit/service test.

Code anchors: forms = `PurchaseRequestHeader`/`purchase_requests` (`app/models/procurement.py:316`,
covers PR + SF via `request_type`), `Complaint`/`complaints` (`app/models/complaints.py:14`),
`StockInquiry`/`stock_inquiries` (`app/models/procurement.py:273`); event bus `emit_form_event` +
`form_sla_configs.resolve_event`; banner precedent `RejectionReasonBanner.tsx` +
`PersonLink`/wa.me from `form-banner-person-links`; pill helper `lib/status-pill.ts`;
notify path `send_text_or_template`.

---

## Group SCH - schema + state

- **SCH-1 `[BE][T]`** GIVEN the migration, THEN `status` value `voided` is accepted and columns
  `void_reason TEXT`, `voided_by` (FK→users), `voided_at TIMESTAMP` exist on `purchase_requests`,
  `complaints`, `stock_inquiries`; idempotent; downgrade clean.
- **SCH-2 `[BE]`** GIVEN a void action succeeds, THEN the row has `status='voided'`,
  `voided_by = actor user id`, `voided_at = now (naive UTC)`, `void_reason = supplied text`.
- **SCH-3 `[BE]`** `void_reason` is required and free-text ≥ 3 chars - blank / whitespace / too-short
  → **422**.

## Group ACT - void action + guards (per form × 4)

- **ACT-1 `[BE]`** GIVEN a PR in a non-terminal state (`draft` / pending approval / in-progress /
  escalated), WHEN `POST /api/v1/procurement/purchase-requests/{id}/void` with a reason is called by a
  user holding `purchase_request.void`, THEN it voids (200) and returns the updated form.
- **ACT-2 `[BE]`** same for **Sponsorship Form** (shared router, `sponsorship_form.void` slug), for
  **Complaint** (`complaint.void`), and for **Stock Inquiry** (`stock_inquiry.void`).
- **ACT-3 `[BE]`** GIVEN a form already in a terminal state (`voided` / `rejected` / `resolved` /
  `closed`), WHEN void is called, THEN **409/422** (no second void, no re-void of a rejected form).
- **ACT-4 `[BE]`** GIVEN a user WITHOUT the form's `<form>.void` permission, WHEN void is called, THEN
  **403** (auth denial).
- **ACT-5 `[BE]`** **Irreversible** - there is no un-void / reopen endpoint for a voided form; a voided
  form cannot transition to any other status.

## Group SLA - tracker stop via config (no bespoke code)

- **SLA-1 `[BE]`** GIVEN a void succeeds, THEN exactly one `emit_form_event(..., 'voided')` is emitted
  for the form (verify the event row) - the void service contains **no** direct tracker-stop code.
- **SLA-2 `[BE]`** GIVEN `voided` is listed in the form's `form_sla_config.resolve_event`, WHEN the
  `voided` event fires, THEN the active `conversation_sla_tracking` row is **closed** (no further
  escalation / no staff ripple), via the existing orchestrator machinery.
- **SLA-3 `[BE]` (REGRESSION)** GIVEN a form whose config does NOT list `voided`, WHEN it is voided,
  THEN the void still succeeds (status + banner + notify) and the tracker simply is not auto-closed - 
  documents the config dependency; no crash. *(Config wiring is an admin task, noted in the plan.)*

## Group BAN - banner + read-only lock (per form × 4)

- **BAN-1 `[BE]`** GIVEN a voided form, WHEN its detail DTO is served, THEN it exposes
  `voided_by_name`, `voided_by_wa_phone` (via the `form-banner-person-links` resolver), `voided_at`,
  and `void_reason`.
- **BAN-2 `[FE]`** GIVEN `status==='voided'`, WHEN a detail page renders, THEN a **gray/muted**
  `VoidBanner` at the top shows "Voided by {PersonLink(voided_by)} · {voided_at MY time} - 
  {void_reason}", the name a wa.me link when a phone resolves else plain text (FB-1 pattern); no UUID.
- **BAN-3 `[FE]`** GIVEN a voided form, THEN the page is **fully read-only** - every action button
  (edit, approve, reject, reply/respond, resolve/close, process, and void itself) is hidden/disabled.
- **BAN-4 `[FE]`** GIVEN the `voided` status, WHEN the status pill renders in list AND detail, THEN it
  is the **gray/muted** variant in `status-pill.ts`, visually distinct from rejection-red.
- **BAN-5 `[FE]`** the VoidBanner renders correctly at **375px AND 1280px** (responsive, non-clipped).

## Group NTF - notifications on void

- **NTF-1 `[BE]`** GIVEN a voided form with a current **assignee**, THEN the assignee receives an
  **in-app** notification (reuse existing notification system).
- **NTF-2 `[BE]`** GIVEN the form has a **handling-lock holder** (`handled_by_id`), THEN that person
  also receives an in-app notification (skipped cleanly when unset).
- **NTF-3 `[BE]`** GIVEN the form's `respond_contact_id` (salesperson), THEN a **WhatsApp** status
  update is sent via the existing `send_text_or_template` path (template/closed-window handling
  reused); an `integration_log` row is written on success AND failure.
- **NTF-4 `[BE]`** **no** WhatsApp / comment egress to any party other than the form's own salesperson
  contact (assignee + handler get in-app only).
- **NTF-5 `[BE]`** notifications are **best-effort** post-commit (catch + warn, never raise) - a notify
  failure does not roll back the void.

## Group VD - void dialog (per form × 4)

- **VD-1 `[FE]`** GIVEN a user with `<form>.void` on a non-terminal form, THEN a **Void** action is
  present; clicking it opens a confirm dialog with a **required reason** textarea (destructive styling,
  `AlertDialog`/`ConfirmDeleteDialog` family - this is a destructive action).
- **VD-2 `[FE]`** GIVEN the void dialog, WHEN the reason is blank, THEN submit is blocked with an
  inline message; WHEN filled and confirmed, THEN it calls the `/void` endpoint and on success the
  banner + read-only state appear (query invalidation + toast).
- **VD-3 `[FE]`** GIVEN a user WITHOUT the permission, THEN the Void action is not rendered.

## Group E2E - round-trip (per representative form)

- **E2E-1 `[E2E]`** Navigate via sidebar to a non-terminal PR detail; click Void; enter a reason;
  confirm; assert `browser_network_requests` shows the `/void` POST; assert the gray VoidBanner shows
  "Voided by {name} · {when} - {reason}"; assert all action buttons are gone; assert the list pill is
  gray.
- **E2E-2 `[E2E]`** Repeat the void flow for a Complaint (different table/router) to prove the shared
  pattern; assert the salesperson WhatsApp send fired via `browser_network_requests` / integration_log
  (or a stubbed send in the test env - never a real contact).

---

## Test report skeleton (fill in Phase 2, key back to these ids)

| AC id | Layer | Test file / verification | Result |
|-------|-------|--------------------------|--------|
| SCH-1..SCH-3 | pytest | `tests/test_form_void_schema.py` | ☐ |
| ACT-1..ACT-5 | pytest | `tests/test_form_void_action.py` | ☐ |
| SLA-1..SLA-3 | pytest | `tests/test_form_void_sla_stop.py` | ☐ |
| BAN-1 | pytest | `tests/test_form_void_dto.py` | ☐ |
| BAN-2..BAN-5 | vitest | `VoidBanner.test.tsx`, `status-pill.test.ts` | ☐ |
| NTF-1..NTF-5 | pytest | `tests/test_form_void_notify.py` | ☐ |
| VD-1..VD-3 | vitest | `VoidDialog.test.tsx` | ☐ |
| E2E-1,E2E-2 | playwright | `e2e/form-void.spec.ts` | ☐ |
