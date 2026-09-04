# PLAN - Portal: make a `responded` Stock Inquiry editable + resubmittable

**Status:** Built + verified (Playwright + pytest) - 2026-07-23. Not committed.
**Superseded 2026-08-20 (captain):** a `responded` stock inquiry is read-only on the portal again; it changes only through Revise (`PortalRevisionService.revise`, UAC-portal-submission-revisions). The plain submit/draft gates reject `responded`. Branch `fm/si-revision-ux`.

> **Build note - plan missed two backend gates.** The editability gate that actually
> raised "This submission is not editable." is `_fetch_for_edit:1134`
> (`portal_draft_at OR status=='rejected' OR approval_rejected`), shared by BOTH
> `submit_draft` and `create_or_update_draft` - not the `submit_draft` precondition the
> plan named. Also the serializer `is_editable` (`_serialize_stock_inquiry_summary`).
> Both fixed (scoped to stock_inquiry, since `responded` is SI-only). Full change set below.
**Branch (suggested):** `feat/si-responded-editable-resubmit`

## Problem

Purchasing sometimes hits **respond** (update-and-reply, e.g. "the size can change 220mm dia x
100mm H?") on a Stock Inquiry when the intent is really "send it back to the salesperson to
revise". The SI lands in status `responded`. On the **portal** (salesperson-facing
`SubmissionForm`), a `responded` submission shows **"This submission is not editable."** - a
dead-end. The salesperson cannot act on purchasing's clarifying question without purchasing first
doing a formal `purchasing_reject`.

## Decision (locked via grill)

Make a `responded` Stock Inquiry **editable + resubmittable on the portal**, mirroring the existing
`rejected`-resubmit path exactly.

Resolved decisions:
1. **Surface = portal salesperson** (the screenshot). Internal purchasing already can
   `purchasing_reject` a `responded` SI; that path is untouched.
2. **Resubmit lands `responded → pending_project_sales`** - identical to today's rejected-resubmit.
   The salesperson edited spec/size fields, so project-sales re-vetting is correct, not redundant.
   Reuses the existing state transition + notification verbatim.
3. **Submit-only** - draft-save blocked on `responded`, mirroring `rejected`.
4. **Keep** `last_responded_by/at` audit stamps. **Keep** purchasing's comment bubble visible (the
   salesperson needs to read the question while editing; it renders independently of `isEditable`).
   **No** dedicated "superseded" notification to purchasing.

## Why this is small / safe

- **SLA is free.** Portal `submit_draft` already emits form-SLA `submit`
  (`portal_service.py:930-947`) → starts the `project_sales` stage tracker. `responded` reuses it.
- **No orphan tracker.** `purchasing_respond` sits in BOTH Respond + Resolve columns of
  `form_sla_configs`, so responding already **resolved** (`is_resolved=True`) the purchasing-stage
  tracker. At `responded` there is no open purchasing tracker to leak when the new project_sales
  tracker spawns.
- **`responded` is an SI-only status.** `isEditable` and `submit_draft` are shared across portal
  kinds (complaint / PR / SF), but only stock_inquiry ever has `responded`, so no cross-kind risk.
- **Race is self-guarding.** Once resubmitted, status = `pending_project_sales`; a late
  `purchasing_reject` (requires `pending_purchasing`/`responded`) fails with a clear precondition
  error.

## Change set

### Backend - `sorento_crm_backend/app/services/portal_service.py`

1. **`submit_draft`, stock_inquiry branch (~line 879)** - allow resubmit from `responded`:
   ```python
   if previous_status not in ("draft", "rejected", "responded"):
       raise handle_validation_error(...)
   ```
   The existing rejection-field clears (887-890) are harmless on `responded` (already None).

2. **`_post_submit_notify` call (~line 922)** - treat responded-resubmit as a resubmission so the
   Project Sales team notification uses the resubmitted event, not a fresh-submit event:
   ```python
   is_resubmission=previous_status in ("rejected", "responded")
   ```

3. **`create_or_update_draft` (~lines 840-848)** - block draft-save on `responded` too (submit-only,
   mirrors rejected). Add a `row_status_responded` check that raises the same submit-only message.

### Frontend - `sorento_crm_frontend/app/(auth)/portal/components/SubmissionForm.tsx`

4. **`isEditable` (267-270)** - add `|| detail.status === 'responded'`.

5. **Save-as-draft button gate (1137)** - also hide when `responded`
   (`![...'rejected','responded'].includes(detail?.status)`).

6. **Confirm-submit dialog copy (1161-1162)** - reword "unless it is rejected" to cover the
   returned-for-changes case, e.g. "…You can no longer edit unless it is returned to you for
   changes." (keep it human, no UUID/jargon).

No backend state-machine, model, migration, or form-SLA-config change. No internal
StockInquiryDetail change.

## Tests (Phase 2 - land with the code)

- **pytest** (`sorento_crm_backend/`):
 - `submit_draft` on a `responded` SI → status `pending_project_sales`; asserts a `project_sales`
    form-SLA tracker exists (form-SLA `submit` emitted).
 - `create_or_update_draft` on a `responded` SI → raises submit-only validation error.
 - Notification path: `_post_submit_notify` called with `is_resubmission=True` for a responded
    resubmit (event type = resubmitted).
 - Regression: `rejected`-resubmit still lands `pending_project_sales` unchanged.
- **vitest** (`sorento_crm_frontend/`): `SubmissionForm` renders fields editable + Save-as-draft
  hidden when `detail.status === 'responded'`; not-editable banner gone.
- **playwright** (`e2e/`): portal SI in `responded` → edit a field → Submit → status pill shows
  "Pending project sales"; `browser_network_requests` confirms the submit endpoint hit.

## Phasing note

Mostly **Phase 2** - no new UI, just enabling existing portal UI on one more status. Phase-1
prototype is trivial (the screen already exists). Browser-verify the portal round-trip before
handoff (prod build).
