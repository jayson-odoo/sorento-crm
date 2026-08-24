# UAC - Form-banner person links (WHO · WHEN · wa.me hyperlink)

**Status:** Draft (pre-code) · **Classification:** CORE · **Domain:** forms / sla
**Plan:** `documentation/plans/forms/PLAN-form-banner-person-links.md`
**Contract:** every status/notice banner rendered ABOVE a form on a form-detail page shows
WHO and WHEN. WHO is a hyperlink to `https://wa.me/{digits}` when the person has a resolvable
phone; otherwise WHO is plain text. A UUID is never shown.

Tags: `[BE]` backend · `[FE]` frontend · `[E2E]` playwright round-trip · `[T]` unit/service test.
Each AC is independently verifiable in a browser (or via the cited endpoint) unless tagged `[T]`.

Banner scope (the four banners in `sorento_crm_frontend/app/(protected)/sla-management/_shared/`
+ `components/common/`):
1. `HandlingLockBanner` - WHO = the lock holder (`handled_by_id`), WHEN = `handled_at`.
2. `SlaEscalationBanner` - WHO = the **escalated-from** owner (who missed at the prior tier),
   WHEN = `escalated_at`. (Per decision: link the escalated-FROM person, not the new assignee.)
3. `SlaExtensionBanner` - WHO = the current assignee, WHEN = the extend event time.
4. `RejectionReasonBanner` - WHO = the rejecter, WHEN = `rejected_at` (add who+when; today has neither).

Consuming detail pages: `StockInquiryDetail.tsx`, `PurchaseRequestDetail.tsx`, `ComplaintDetail.tsx`.

---

## Group PR - Phone resolution (backend)

- **PR-1 `[T]`** GIVEN a `User` with a linked `respond_contact_id` whose `RespondContact.phone_number`
  is `60123456789`, WHEN the WHO-phone resolver runs for that user, THEN it returns `60123456789`
  (bare digits, no `+`, ready for `wa.me/`).
- **PR-2 `[T]`** GIVEN a `User` with no `respond_contact_id` but a `contact_number` that
  `normalize_msisdn` maps to a single matching `RespondContact`, WHEN the resolver runs, THEN it
  returns those digits (reusing `resolve_user_respond_contact`).
- **PR-3 `[T]`** GIVEN a `User` with no linked contact AND no phone-matchable `contact_number`,
  WHEN the resolver runs, THEN it returns `None` (banner will fall back to plain text - see Group FB).
- **PR-4 `[T]`** GIVEN a Complaint whose `rejected_by` holds a **`respond_user_id`** (NOT a `users.id`),
  WHEN the complaint rejecter is resolved, THEN the resolver first maps
  `User.respond_user_id == rejected_by` → `User`, then to a phone via PR-1/PR-2 (returns `None` if no
  such user or no phone). *(Discrepancy from brief - see plan Risk R1.)*
- **PR-5 `[T]`** GIVEN a StockInquiry whose `rejected_by` holds a `users.id`, WHEN the SI rejecter is
  resolved, THEN it maps directly `users.id → User → phone`.
- **PR-6 `[T]`** the resolver never raises on a missing/garbage id - it returns `None`.

## Group HL - Handling-lock banner link

- **HL-1 `[BE]`** GIVEN a form/complaint SLA tracker with `handled_by_id` set to a user with a phone,
  WHEN the handling-lock tracker DTO is fetched (`GET /api/v1/sla/form/...` and the complaint detail
  path), THEN the response includes `handled_by_wa_phone` = that user's digits alongside the existing
  `handled_by_name`.
- **HL-2 `[FE]`** GIVEN state `other_holds`/`admin_other_holds` and a tracker with
  `handled_by_wa_phone`, WHEN the banner renders "{name} is handling this since {when}", THEN {name}
  is an `<a href="https://wa.me/{digits}" target="_blank" rel="noopener noreferrer">` and {when} is
  `formatDateTimeInMalaysia(handled_at)`.
- **HL-3 `[FE]`** GIVEN state `not_eligible` with a phone, WHEN the banner renders "…handled by
  {name}", THEN {name} is the same wa.me link.
- **HL-4 `[FE]`** GIVEN a tracker with `handled_by_name` but `handled_by_wa_phone = null`, WHEN any
  handler-naming state renders, THEN the name is plain text (no anchor) - see FB-1.
- **HL-5 `[FE]`** The `TakeOverConfirmDialog` handler name is NOT required to be a link (it is a
  confirm-copy context, not a banner) - plain text is acceptable, no UUID.

## Group ESC - SLA escalated-from link

- **ESC-1 `[BE]`** GIVEN an escalation occurs on a conversation tracker (via
  `sla_service.escalate_tracking`), WHEN the escalation event log row is written, THEN its new
  `from_assigned_to_id` column captures the **prior** `assigned_to_id` (snapshotted BEFORE the new
  assignee overwrites it).
- **ESC-2 `[BE]`** GIVEN an escalation occurs on a **form** tracker (via
  `form_sla_service._escalate_tracker`), WHEN the escalation event log is written (`_write_event_log`),
  THEN `from_assigned_to_id` captures the prior `assigned_to_id` before overwrite.
- **ESC-3 `[BE]`** GIVEN an active tracker whose latest escalation event has a `from_assigned_to_id`
  that resolves to a user with a phone, WHEN the active-tracker DTO is served, THEN it includes
  `escalated_from_name` and `escalated_from_wa_phone`, AND `escalated_at` (the WHEN).
- **ESC-4 `[FE]`** GIVEN `escalation_reason` present and `escalated_from_name`/`escalated_from_wa_phone`
  set, WHEN `SlaEscalationBanner` renders, THEN it shows "SLA escalated - tier N · {escalated_at MY
  time} · escalated from {PersonLink(escalated_from)}", with {escalated_from} an active wa.me link.
  The current assignee context ("now assigned to …") stays as plain text.
- **ESC-5 `[FE]`** GIVEN `escalated_from_wa_phone = null` but `escalated_from_name` set, WHEN the
  banner renders, THEN the escalated-from name is plain text (FB-1), still showing WHEN.
- **ESC-6 `[FE]`** GIVEN no escalation (`escalation_reason` empty), WHEN the component renders, THEN
  it renders nothing (unchanged behaviour).

## Group EXT - Extension banner link

- **EXT-1 `[BE]`** GIVEN an active tracker, WHEN the active-tracker DTO is served, THEN it includes
  `assigned_user_wa_phone` alongside the existing `assigned_user_name`.
- **EXT-2 `[FE]`** GIVEN an extend event on the active stage and `assigned_user_wa_phone` set, WHEN
  `SlaExtensionBanner` renders "SLA deadline extended until {newDue} - tier N · assigned to
  {assignee}", THEN {assignee} is a wa.me link and the banner shows the extend event WHEN
  (`event_at`) rendered via `formatDateTimeInMalaysia`.
- **EXT-3 `[FE]`** GIVEN `assigned_user_wa_phone = null`, WHEN the extension banner renders, THEN the
  assignee is plain text (FB-1).

## Group REJ - Rejection banner: who + when + link (3 entities)

- **REJ-1 `[BE]`** GIVEN a rejected StockInquiry, WHEN its detail DTO is served, THEN it exposes
  `rejected_by_name`, `rejected_by_wa_phone`, and `rejected_at` (name resolved from the existing
  `rejected_by` = `users.id`).
- **REJ-2 `[BE]`** GIVEN a rejected Complaint, WHEN its detail DTO is served, THEN it exposes
  `rejected_by_name`, `rejected_by_wa_phone`, and `rejected_at` (resolved via PR-4:
  `rejected_by` = `respond_user_id`).
- **REJ-3 `[BE]`** GIVEN a Purchase Request rejected via the internal reject-submitted path, WHEN its
  detail DTO is served, THEN it exposes `rejected_by_name`, `rejected_by_wa_phone`, and a rejection
  WHEN timestamp, sourced from the new `rejected_by_id` column + `approved_at`.
- **REJ-4 `[BE]`** GIVEN a Purchase Request rejected by an **approval-decision** (approver via the
  approval link) whose approver is an external email with no CRM user, WHEN its detail DTO is served,
  THEN `rejected_by_wa_phone = null` and `rejected_by_name` shows the resolved display name / email  - 
  banner falls back to plain text (FB-1). No error, no UUID.
- **REJ-5 `[FE]`** GIVEN a rejected entity with `rejection_reason`, `rejected_by_name`,
  `rejected_by_wa_phone`, `rejected_at`, WHEN `RejectionReasonBanner` renders, THEN it shows
  "Rejected by {PersonLink(rejecter)} · {rejected_at MY time} - {reason}", with the name a wa.me link.
- **REJ-6 `[FE]`** GIVEN a rejected entity with a reason but `rejected_by_name = null`, WHEN the
  banner renders, THEN it shows "Rejected - {reason}" (today's copy) with no person clause, and still
  renders (no crash).

## Group FB - No-phone fallback (plain text)

- **FB-1 `[FE]`** GIVEN any banner WHO with a name but `wa_phone` null/empty/whitespace, WHEN
  `PersonLink` renders, THEN it emits a plain `<span>{name}</span>` - NO `<a>` element, NO `href`.
- **FB-2 `[T]`** GIVEN `PersonLink` with a name and a valid `waPhone`, THEN it renders exactly one
  anchor `href="https://wa.me/{digits}"`, `target="_blank"`, `rel="noopener noreferrer"`.
- **FB-3 `[FE]`** GIVEN a WHO with an empty/whitespace name, WHEN `PersonLink` renders, THEN it
  renders nothing or a neutral placeholder - never an empty link, never a UUID.

## Group UUID - No-UUID guarantee

- **UUID-1 `[FE]`** For EVERY banner state across all four banners, the rendered text and any `href`
  contains NO `users.id`/`respond_contact_id`/tracker UUID. The `href` is `wa.me/{phone-digits}` only;
  the visible text is a human name.
- **UUID-2 `[T]`** `PersonLink` given only a UUID-looking `name` and no phone still renders that
  string verbatim (component doesn't fabricate) - but the calling banners MUST pass a resolved
  display name, asserted by BE tests PR/REJ/ESC/HL emitting `*_name` from `_resolve_*_display_name`,
  never a raw id.

## Group HIST - Historical rows (name-only where no id)

- **HIST-1 `[BE]`** GIVEN a pre-existing escalation event log row with `from_assigned_to_id = NULL`
  (created before this feature) and NOT covered by the backfill, WHEN the active-tracker DTO is
  served, THEN `escalated_from_name`/`escalated_from_wa_phone` are `null` and the escalation banner
  renders without the "escalated from" clause (still shows tier + WHEN).
- **HIST-2 `[BE][T]`** GIVEN escalation event logs predating the `from_assigned_to_id` column, WHEN
  the backfill script runs, THEN each escalation row's `from_assigned_to_id` is set to the
  `assigned_to_id` of the immediately-prior event-log row for the same `sla_tracking_id` ordered by
  `event_at` (best-effort heuristic - see plan Risk R2), and rows with no prior event stay `NULL`.
- **HIST-3 `[BE]`** GIVEN a legacy PR rejected before the `rejected_by_id` column existed, WHEN its
  detail DTO is served, THEN `rejected_by_id` is `NULL`, `rejected_by_wa_phone` is `null`, and
  `rejected_by_name` falls back to the legacy `approved_by` name string (plain text, no link, no
  crash).

## Group E2E - Round-trip

- **E2E-1 `[E2E]`** Navigate via sidebar to a rejected StockInquiry detail; assert the rejection
  banner shows "Rejected by {name} · {when} - {reason}"; assert the name renders as an `<a>` whose
  `href` starts `https://wa.me/`; assert `browser_network_requests` shows the detail GET returning
  `rejected_by_wa_phone`.
- **E2E-2 `[E2E]`** On a tracker in `other_holds` state, assert the handling-lock banner names the
  holder as a wa.me link; on a fixture with no phone, assert plain text.

---

## Test report skeleton (fill in Phase 2, key back to these ids)

| AC id | Layer | Test file / verification | Result |
|-------|-------|--------------------------|--------|
| PR-1..PR-6 | pytest | `tests/test_banner_person_phone_resolver.py` | ☐ |
| HL-1 | pytest | `tests/test_form_sla_tracking_dto.py` | ☐ |
| HL-2..HL-5 | vitest | `HandlingLockBanner.test.tsx` | ☐ |
| ESC-1,ESC-2 | pytest | `tests/test_sla_escalation_from_snapshot.py` | ☐ |
| ESC-3 | pytest | `tests/test_active_tracker_dto.py` | ☐ |
| ESC-4..ESC-6 | vitest | `SlaEscalationBanner.test.tsx` | ☐ |
| EXT-1 | pytest | `tests/test_active_tracker_dto.py` | ☐ |
| EXT-2,EXT-3 | vitest | `SlaExtensionBanner.test.tsx` | ☐ |
| REJ-1 | pytest | `tests/test_stock_inquiry_reject_dto.py` | ☐ |
| REJ-2 | pytest | `tests/test_complaint_reject_dto.py` | ☐ |
| REJ-3,REJ-4 | pytest | `tests/test_pr_reject_dto.py` | ☐ |
| REJ-5,REJ-6 | vitest | `RejectionReasonBanner.test.tsx` | ☐ |
| FB-1..FB-3 | vitest | `PersonLink.test.tsx` | ☐ |
| UUID-1,UUID-2 | vitest + pytest | across banner + DTO tests | ☐ |
| HIST-1 | pytest | `tests/test_active_tracker_dto.py` | ☐ |
| HIST-2 | pytest | `tests/test_escalation_backfill.py` | ☐ |
| HIST-3 | pytest | `tests/test_pr_reject_dto.py` | ☐ |
| E2E-1,E2E-2 | playwright | `e2e/form-banner-person-links.spec.ts` | ☐ |
