# PLAN: Form void (with reason + banner)

**Status:** Design locked (grill 2026-07-19). Not built.
**Classification:** CORE (adds a terminal state + reason columns to existing form tables; `public`
schema; no new tables; reuses event bus, banner, notify, status-pill).
**Domain:** forms / procurement / complaints
**UAC:** `documentation/plans/forms/form-void-acceptance-criteria.md` (written first)
**Owner:** Claude + Jayson · **Created:** 2026-07-19
**Depends on / aligns with:** `form-banner-person-links` (VoidBanner reuses `PersonLink` wa.me),
`PLAN-procurement-cs-handoff-and-pinpoint-routing` (status-update send path).

## Problem

No dedicated void state today - forms use `status` strings + rejection only. A mistaken form cannot
be cleanly killed; a kill must stop the SLA and inform assignee + handler + salesperson.

## Solution

Terminal `status='voided'` + reason quad on the 3 form tables; void emits `voided` (SLA stop is pure
config); gray `VoidBanner`; full read-only lock; three-target notify.

## Decisions

| # | Decision |
|---|----------|
| D1 | **Terminal `status='voided'`** + `void_reason` TEXT (req, free-text ≥3) / `voided_by` FK→users / `voided_at`. On `purchase_requests` (PR+SF), `complaints`, `stock_inquiries`. Chosen over an `is_void` boolean (plays with status-pill/banner gating, no contradictory state). |
| D2 | **Pill = muted gray/slate** in `status-pill.ts` (distinct from rejection-red). |
| D3 | **Voidable from any NON-terminal state**; blocked once `voided`/`rejected`/`resolved`/`closed`. |
| D4 | **Per-form permission** `<form>.void` (`purchase_request.void`, `sponsorship_form.void`, `complaint.void`, `stock_inquiry.void`). PR+SF share the router but keep separate slugs (mirrors the `.process`/`.close` precedent). |
| D5 | **SLA stop = pure config.** Void calls `emit_form_event(..., 'voided')`; admin adds `voided` to each `form_sla_config.resolve_event`. No bespoke stop code. |
| D6 | **Irreversible.** No un-void/reopen. |
| D7 | **`VoidBanner`** mirrors `RejectionReasonBanner` (gray), reuses `PersonLink` (wa.me / plain-text fallback), gated on `status==='voided'`, on all 4 detail pages. |
| D8 | **Voided form = fully read-only** - hide every action button. |
| D9 | **Notify 3 targets:** assignee (in-app) + handling-lock holder (in-app) + salesperson `respond_contact_id` (WhatsApp via `send_text_or_template`, `integration_log` on success+failure). No egress to anyone else. Best-effort post-commit. |

## Critical files

- BE: migration (status value + reason quad ×3 tables);
  `app/models/procurement.py` (PR + StockInquiry cols), `app/models/complaints.py` (Complaint cols);
  new void service methods + routes - `app/services/procurement_service.py` (PR/SF + SI),
  `app/services/complaints_service.py` (Complaint); `app/api/v1/procurement/*`, `.../complaints/*`
  (`/void` endpoints, `require_module_enabled_with_api_key` + `<form>.void` guard);
  `emit_form_event` call; `send_text_or_template` for the salesperson WhatsApp; notification service
  for in-app; DTO builders add `voided_*` + resolver phone (BAN-1); RBAC slug registration + grant
  sweep.
- FE: new `VoidBanner.tsx` (+ `PersonLink`); new `VoidDialog.tsx` (reason textarea, destructive);
  wire into `PurchaseRequestDetail.tsx`, sponsorship detail, `ComplaintDetail.tsx`,
  `StockInquiryDetail.tsx`; `lib/status-pill.ts` gray `voided`; read-only gating in each detail page;
  void mutation hook + feature-service method.

## Phase mapping

- **Phase 1 (FE prototype):** build `VoidDialog` + `VoidBanner` + the read-only-locked detail + gray
  pill against **mock** state, on all 4 detail pages. Tune reason validation, destructive confirm
  copy, banner responsive at 375/1280, empty/error. Document the `/void` request/response contract +
  the `voided_*` DTO fields. Playwright MCP sidebar-click verify. NO backend, NO tests yet.
- **Phase 2 (BE, test-FIRST):** author SCH/ACT/SLA/NTF as failing tests first; implement migration +
  void services + routes + event emit + notify + DTO fields; swap FE mocks for real hooks; land pytest
  + vitest + Playwright E2E (void PR + void Complaint). SLA-3 + auth-denial (ACT-4) are gates.
- **Phase 3:** `/code-review`; reviewer checks: terminal-state guard completeness (ACT-3/-5), notify
  best-effort (never raises, NTF-5), egress scoping (NTF-4), read-only lock covers **every** button
  (BAN-3), DoD (new permission grant sweep, new columns reach FE + manual dict builders).

## DoD-gate specifics (PRINCIPLES)

- **New permission → grant sweep:** 4 new `<form>.void` slugs must be granted to the appropriate
  existing roles or the action silently 403s / hides.
- **New columns reach FE:** `voided_*` added to each form's detail schema/DTO (and any manual dict
  builder), plus the person-phone resolver output.
- **No backfill needed:** existing forms keep their current status; `voided` is only ever set forward.
  Admin must add `voided` to each `form_sla_config.resolve_event` (config task, called out; SLA-3
  proves the void itself doesn't depend on it).

## Risks

- **R1 - read-only completeness:** every detail page has its own action set (approve/reject/process/
  close/reply/extend/take-over). Missing one leaves an actionable button on a voided form. Enumerate
  per page in Phase 1; assert in vitest (BAN-3).
- **R2 - terminal-state matrix:** "non-terminal" differs per form (PR uses `approval_status` +
  `status`; SI has reopen fields; Complaint has its own states). Define the voidable-state predicate
  per form explicitly, don't assume a shared string set.
- **R3 - SF via shared router:** the PR router serves both; the `/void` endpoint must apply the right
  slug (`sponsorship_form.void` when `request_type='sponsorship_form'`) and the right status-message
  use_case.
- **R4 - WhatsApp closed-window:** reuse `send_text_or_template` exactly as the process/close messages
  do (per the pin-point plan D10) so a closed 24h window falls back to a template - no new gap.
