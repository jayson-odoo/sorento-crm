# PLAN - Complaint team feedback: response automation, working-hours SLA, complaint PDF, CS team handoff

**Status:** Implemented 2026-06-09 (backend verified end-to-end; FE typechecks clean, pending browser rebuild). Grill session + execution same day. Four items from Sorento complaint team feedback.

### As-built deltas vs the original plan (extra constraints from the user)

- **Item 1:** the 3 actions are decoupled best-effort in `update_complaint_and_reply` - (a) save technical response (committed first), (b) enqueue Respond.io message (try/except), (c) email automation `dispatch_event` (try/except). One failing never affects the others or the DB state.
- **Item 2:** working-hours applies to **create + escalate** (conversation `create_tracking`/`escalate_tracking` + form `_start_for_config`/`scan_overdue_and_escalate`) and admin test-override. The assignee-team-derivation routing reset (`apply_assignee_team_derivation`) was **reverted to calendar math** - it's a team-flip correction, out of the "create + escalate" scope, and its unit tests assert calendar semantics. External-API create + escalate both verified still working. New helper `CalendarService.add_working_hours` (9 unit tests).
- **Item 3:** PDF generation is **async + decoupled** - `POST /complaints/{id}/export/pdf` creates a `user_downloads` row + enqueues `generate_complaint_pdf` (imports queue); the worker renders (WeasyPrint), uploads to the storage provider, marks the row ready/failed. New **My Downloads drawer** (top-nav icon + Sheet, polls while in-flight) consumes `GET /api/v1/downloads` + `GET /api/v1/downloads/{id}/url`. Verified live: render→upload→signed-URL round-trip (35KB PDF from a real complaint). Worker needs `DYLD_FALLBACK_LIBRARY_PATH` locally (see memory).
- **Item 4 (revised after live feedback):** two CS finalize actions on an approved complaint, both close the CS SLA stage (emit `resolved` form-SLA event) and send a Respond.io status-update message (+ optional note) to the contact:
 - **"Processed by CS"** → status `processed_by_cs` (emerald pill). Endpoint `POST /complaints/{id}/process`, perm `complaint_management.complaints.resolve`. (Renamed from "resolve" - CS processed it, it isn't literally resolved.)
 - **"Mark as closed"** → status `closed` (slate pill). Endpoint `POST /complaints/{id}/close`, **separate** perm `complaint_management.complaints.close` so it can be hidden independently. For the can't-resolve case.
 - Migration 227 adds `resolved_at`/`resolved_by` (used as the generic finalized-at/by for both). Status renders as a coloured pill; `processed_by_cs` shows the label "Processed by CS". Both finalize paths are decoupled best-effort (status commits first; Respond send + SLA emit are try/except).
 - **Pre-existing bug fixed:** `lookup_write_listener` re-validated *all* columns on every UPDATE, so any update to a complaint holding a legacy unmapped lookup value (e.g. `defects_discovered="Before DLP"`) 422'd. Now `before_update` only validates *changed* columns (`app/services/lookup_write_listener.py`; regression tests in `test_lookup_write_enforcement.py`). This had been silently blocking status changes on real complaints.

### Test status

- New/green: `test_working_hours_sla` (10), `test_complaint_resolve` (3), `test_complaint_pdf_export` (4). Full suite: 484 passed (was 465 baseline), same 24 pre-existing environmental errors, −2 failures vs baseline - zero regressions.
- Migrations 227 (resolved cols) + 228 (user_downloads) applied to dev DB.
- FE: `tsc --noEmit` clean. Browser verification pending FE rebuild (user owns `:3000`).

## Context

Four requests from the Sorento complaint team, grilled against the codebase 2026-06-09:

1. When a complaint's technical-team response is sent, notify target users via the automation function.
2. SLA escalation should honor working days (weekends + public holidays), not calendar days.
3. Print a formal PDF copy of a complaint for supporting-document purposes.
4. Complaint SLA: complaint-team stage on submit, hand off to customer-service team after approval.

### Premise correction (item 2)

The team believed conversation SLA forward-calc already skips weekends/holidays. **It does not.** Verified:

- Conversation SLA - `sla_service.py:1786` - `due_at = current_tier_started_at + timedelta(hours=response_hours)`. Hours pulled straight from the policy tier KPI (`:1781`). No `CalendarService`, no `public_holidays` lookup, no weekday skip (grep for `business|working|calendar|holiday` = 0 hits in the file).
- Form SLA - `form_sla_service.py:371`, `:238` - identical raw `timedelta(hours=...)`.
- `CalendarService.add_business_days()` (`calendar_service.py:233`) skips weekends + `public_holidays` and is used by `order_service` + task scheduling - but **neither SLA touches it**.

So today a 24h SLA started Fri noon is due Sat noon; holidays ignored everywhere in SLA.

---

## Item 1 - Technical-response automation

**Goal:** When the technical-team response is sent to the customer, email a configurable set of target users.

**Decisions:**
- Fires on **`update_complaint_and_reply` only** (status → `responded`, customer actually receives the reply). NOT on the internal `update_complaint` draft save.
- **Email only** (existing automation pipeline). No in-app.
- Recipients via existing `recipient_config` (user_ids / role_ids / extra_emails).

**Build:**
1. New trigger in `app/services/automation_triggers.py`:
   ```python
   register(
       TriggerSpec(type="complaint_technical_response_updated",
                   label="Complaint technical response sent",
                   description="Fires when a complaint's technical-team response is sent to the customer (Update & Reply).",
                   config_schema={...}),
       _trigger_complaint_technical_response_updated,  # event-driven, returns []
   )
   ```
2. Dispatch in `complaints_service.update_complaint_and_reply` after `status="responded"` commit, **best-effort** (catch + warn, never raise - post-commit side-effect rule):
   ```python
   AutomationService(self.db).dispatch_event(
       "complaint_technical_response_updated",
       context={"complaint": {...complaint fields, "link": ..., "technical_team_response": ...}, "today": ...},
       source_kind="complaint", source_id=str(complaint.id),
   )
   ```
3. Add `complaint.technical_team_response` to the template var catalog in `email_template_service.py` so admins can include the reply text.

**Tests (pytest):** new trigger dispatches on update-and-reply; does NOT dispatch on internal update; recipient resolution; best-effort swallow on dispatch failure. Mirror `tests/test_complaint_approval_dispatches_automation.py`.

**Config (admin):** create an Automation with trigger `complaint_technical_response_updated`, recipients, email template.

---

## Item 2 - Working-hours SLA (both systems)

**Goal:** SLA clock advances only during working hours; skips nights, weekends, configured public holidays. Applies to **both** conversation and form SLA.

**Decisions:**
- **Working-hours accumulator** (not whole-day skip, not land-date push). Clock ticks only Mon - Fri 09:00 - 17:00 (from `WorkCalendarConfig`), skips `public_holidays`. Example: 4h tier started Fri 16:00 → 1h Fri + 3h Mon → due **Mon 12:00**.
- Timezone: naive-UTC stored, working windows in `Asia/Kuala_Lumpur` (UTC+8, `calendar_service.DEFAULT_WORKING_TZ`).
- **New rows only.** No backfill; existing open trackers keep their calendar-style `due_at` and age out.

**Build:**
1. New helper `CalendarService.add_working_hours(start_naive_utc, hours) -> datetime` (naive UTC out):
 - Convert start → KL local.
 - Walk forward consuming `hours` only within working windows (weekday flag true, not a holiday, time within `work_day_start_time`..`work_day_end_time`).
 - If start is outside a window, accumulation begins at the next window open.
 - Convert result back to naive UTC.
 - Honor partial-hour fractions (tiers can be non-integer hours).
2. Replace every due_at computation site:
 - `sla_service.py`: `create_tracking` (1786), `escalate_tracking` (1093), `apply_assignee_team_derivation` (1577), `admin_test_override_tracking` (2162). Both `due_at` and `due_at_resolution`.
 - `form_sla_service.py`: `_start_for_config` (371), `scan_overdue_and_escalate` (238).
3. No change to breach scan / time-remaining math - they compare wall-clock `now` vs `due_at`, still correct.

**No n8n double-count risk:** `create_tracking` reads tier hours from the DB; n8n sends `policy_id`, not hours or dates.

**Tests (pytest):** accumulator unit tests (within-hours start, after-hours start, weekend start, holiday spanning, multi-day, fractional hours, DST not applicable for KL but assert tz-stable); create/escalate due_at uses working hours for both services; in-flight rows untouched (no migration).

---

## Item 3 - Complaint PDF

**Goal:** Download a formal PDF copy of a complaint for supporting-document purposes.

**Decisions:**
- **Server-side WeasyPrint** + Jinja template → `GET /api/v1/complaints/{id}/export/pdf` returns `application/pdf`.
- **Internal only**, gated by complaint view permission. Not on the portal/external view.
- **Formal subset:** complaint details, customer info, product lines, defect description, technical response, resolution. **Excludes** audit trail, assignee, SLA internals.
- **Image attachments** (jpg/png/webp) embedded as data-URIs via `storage_router`; non-image files listed by filename only.

**Build:**
1. Add `weasyprint` to `requirements.txt`. ⚠️ **Deploy:** needs cairo/pango/gdk-pixbuf system libs in the backend Docker image - add the apt packages to the backend Dockerfile.
2. `app/templates/complaint_pdf.html` - Jinja, branded header/logo, the formal subset.
3. `ComplaintPDFService` (`app/services/`): load complaint + product_lines + image attachments (fetch bytes via `storage_router`, base64 data-URI), render HTML, WeasyPrint → bytes.
4. Endpoint in `app/api/v1/complaints/complaints.py`: `Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="complaint-{number}.pdf"'})`.
5. FE: "Download PDF" item in `ComplaintDetail.tsx` action menu (reuse file-download pattern).

**Tests:** pytest - endpoint returns 200 `application/pdf` happy path, 404 unknown id, auth denial; service embeds image attachment, skips non-image. Vitest - action-menu item renders + triggers download. Playwright MCP - open complaint detail → Download PDF → file downloaded.

---

## Item 4 - Complaint SLA team handoff (complaint → customer_service)

**Goal:** On submit, SLA under complaint team (complaint agent). After approval, hand off to customer-service team (same agent). Customer-service closes it with an explicit resolve.

**Existing machinery (no code needed):** form SLA multi-stage chain via `FormSLAConfig.next_config_id` + `team_set_code` + round-robin `get_next_assignee`. Complaint already emits `submit` (start), `technical_team_response` (respond), `approved`/`rejected` (resolve + spawn next). Verified `complaints_service.py:818/1017/1126`, `form_sla_service.py:66/410/443`.

**Gap:** No event closes the customer-service stage - terminal complaint status today is `approved`. Decision: **add a new explicit resolve action.**

**Decisions:**
- After approval, stage 2 spawns as a **new tracker** with its **own SLA policy** and a **round-robin** assignee from the customer_service team.
- Stage 2 resolved by a **new "mark resolved" action** (status `resolved`, emits `resolved` event).

**Build (code):**
1. New `resolve` action: `POST /api/v1/complaints/{id}/resolve` → sets `status="resolved"`, emits `emit_form_event(..., "resolved", ...)` best-effort. New RBAC permission. Validate prior status is `approved`.
2. Add `resolved` to the event vocabulary:
 - BE emit (above).
 - FE `FORM_SLA_EVENT_OPTIONS.complaint` in `_shared/formSLAService.ts:155` → append `'resolved'`.
3. FE: "Mark resolved" button on `ComplaintDetail.tsx` for the customer-service team (RBAC-gated).

**Config data (admin UI - set up, no code):**
- **SLA Management → SLA Policies** - new customer-service policy (own response/resolution hours).
- **SLA Management → Form SLA Config**:
 - Stage 1: `source=complaint`, `agent_code=complaint`, `team_set_code=complaint`, `start_event=submit`, `respond_event=technical_team_response`, `resolve_event=approved`, `next_config_id`→stage 2, `policy_id`=complaint-team policy.
 - Stage 2: `source=complaint`, `agent_code=complaint`, `team_set_code=customer_service`, `resolve_event=resolved`, `policy_id`=CS policy. (Started by stage 1's spawn, not a `start_event`.)
- **Access Agent admin** - complaint agent needs an `AgentTeam` row: `team_set_code=customer_service`, tier 1 → Customer Service `Team` (with `TeamMember`s for round-robin).

**Tests (pytest):** submit → stage 1 tracker under complaint team; approve → stage 1 resolved + stage 2 spawned under customer_service round-robin; resolve action → status `resolved` + stage 2 resolved; resolve rejected when status not `approved`; auth denial. Vitest - Mark-resolved button gating. Playwright - submit → approve → resolve round-trip.

---

## Open build-details (sensible defaults; flag if wrong)

- Email template var name for the response text (`complaint.technical_team_response`).
- PDF filename format (`complaint-{complaint_number}.pdf`).
- Stage 2 only spawns on `approved`; `rejected` does not hand off to customer_service (assumed terminal).
- WeasyPrint chosen over PyMuPDF/reportlab for HTML-template fidelity; accept the Docker system-deps cost.

## Sequencing

Four independent PRs. Suggested order: Item 1 (smallest, isolated) → Item 4 (config-heavy, mostly existing machinery) → Item 3 (new dep + Docker change) → Item 2 (touches both SLA services, highest blast radius - do last with full test coverage).
