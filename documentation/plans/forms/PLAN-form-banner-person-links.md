# PLAN - Form-banner person links (WHO · WHEN · wa.me hyperlink)

**Status:** Merged to main - BE+FE built, 30 FE vitest + 21 BE pytest green, rejection + SLA-escalation
banners verified live in-browser (wa.me links + underline + no-phone plain-text). Escalation banner
links both current assignee and escalated-from owner. Local heuristic backfill run (151 rows set).
Pending: run the backfill on the real prod DB at deploy.
**Classification:** **CORE** - attribution on core form-detail banners (SLA / handling-lock /
rejection). Not toggleable, `public` schema, normal FKs. No `app_modules_catalog` entry.
**Domain:** forms / sla · **UAC:** `documentation/plans/forms/form-banner-person-links-acceptance-criteria.md`
**Owner:** TBD · **Branch:** `feat/form-banner-person-links`

## 1. Goal

Every status/notice banner rendered ABOVE a form on a form-detail page must show **WHO** did the
thing and **WHEN**, and the WHO must be a hyperlink to `https://wa.me/{phone-digits}` of that person
so a reviewer can one-click WhatsApp them. Phone comes from the user's optional linked Respond.io
contact. No linked contact / no phone → name renders as plain text (no link). A UUID is never shown.

Four banners in scope (all read a person that today renders as an unlinked name - or, for rejection,
no person at all):

| Banner | File | WHO | WHEN |
|--------|------|-----|------|
| Handling lock | `_shared/HandlingLockBanner.tsx` | `handled_by_id` holder | `handled_at` |
| SLA escalation | `_shared/SlaEscalationBanner.tsx` | **escalated-from** owner | `escalated_at` |
| SLA extension | `_shared/SlaExtensionBanner.tsx` | current assignee | extend `event_at` |
| Rejection | `components/common/RejectionReasonBanner.tsx` | rejecter | `rejected_at` |

## 2. Approach (recommended, with justification)

- **One shared FE component `PersonLink`** - a single presentational primitive reused by all four
  banners (component-library discipline, PRINCIPLES §2). Props `{ name, waPhone?, className? }`.
  Renders an anchor when `waPhone` is a non-empty string, else a plain `<span>`. This is the only
  place the `wa.me` URL is built, so the "no UUID / correct rel attrs" rule is enforced once.
- **One shared BE phone-resolver helper** wrapping the existing
  `respond_link_service.resolve_user_respond_contact`, returning `wa.me` digits for: (a) a `users.id`,
  (b) a `respond_user_id`. Every banner DTO calls it; no per-feature phone lookup.
- **Escalated-from is snapshotted structurally**, not reconstructed at read time, because both
  escalation write paths overwrite `assigned_to_id` before logging. A new
  `conversation_sla_event_log.from_assigned_to_id` column captures the prior owner at write time; the
  banner reads the latest escalation event. A best-effort backfill reconstructs historical rows.
- **PR gains a dedicated `rejected_by_id`** rather than overloading `requested_approval_by_user_id`
  (which already doubles as "who sent for approval"). See Risk R3.

## 3. Verified codebase facts + discrepancies flagged

Verified against source (line numbers to re-confirm before editing - file may drift):

- Phone digits: `app/services/phone_utils.py::normalize_msisdn` returns **bare digits incl. `60`
  country code, no `+`** - exactly what `wa.me/{digits}` wants. `respond_contacts.phone_number` is
  stored in that form. ✅ matches brief.
- Resolver exists: `respond_link_service.resolve_user_respond_contact(db, user)` →
  `RespondContact | None`; `.phone_number` is the digits. ✅
- `users.respond_contact_id` FK → `respond_contacts.id`; `users.contact_number` fallback
  (`app/models/user.py:28,40` - `respond_user_id` at line 40, `contact_number` at 28). ✅
- `conversation_sla_event_log` (`app/models/sla.py:184-217`): has `assigned_to_id`, `event_at`,
  `event_type`, `trigger`, `triggered_by_id`. **No `from_assigned_to_id`** - to be added.
- Conversation escalate: `sla_service.escalate_tracking` (`app/services/sla_service.py:~2146`).
  Prior owner = `tracking.assigned_to_id` read BEFORE the `if assigned_to_id is not None:` overwrite
  (~line 2168). Event log built via `create_event_log(...)`.
- Form escalate: `form_sla_service._escalate_tracker` (`app/services/form_sla_service.py:~448`).
  Prior owner = `tracker.assigned_to_id` read BEFORE `tracker.assigned_to_id = assignee["id"]`
  (~line 511). Event log via `_write_event_log(...)`.
- Handling-lock tracker: `handled_by_id` FK + `handled_at` (`app/models/sla.py:105-106`). No
  `handled_by_name` column - resolved in the DTO builder. `handled_by_name` is emitted at
  `app/api/v1/sla/form_sla_tracking.py:73` (`_assignee_name(db, t.handled_by_id)`) and, for
  complaints, via `_handled_name(complaint)` override (`complaints_service.py:~342/749`). Schemas:
  `app/schemas/procurement.py:661,805,837`, `app/schemas/complaints.py:230`.
- StockInquiry rejection: `rejected_by` = **`users.id`** (`procurement_service.py:3739,3807`),
  `rejected_at`, `rejection_reason` (`app/models/procurement.py:297-299`). A `rejected_by_name`
  serializer ALREADY exists at `procurement_service.py:2724` via `_resolve_user_display_name`. ✅
- Complaint rejection: `rejected_by` = **`respond_user_id`** (`complaints_service.py:1981`
  `complaint.rejected_by = respond_user_id`), `rejected_at`, `rejection_reason`
  (`app/models/complaints.py:46-48`). **⚠ Discrepancy from brief** (which implied `users.id`) →
  Risk R1: resolve via `User.respond_user_id`.
- PurchaseRequestHeader: NO `rejected_by`/`rejected_at`. Reject-submitted path
  (`procurement_service.py:6143-6152`) sets `approval_status='rejected'`, `status='rejected'`,
  `approval_comments=reason`, `approved_at=now`, `approved_by=_resolve_actor_display_name(actor)`
  (a NAME string), and **already stores the actor id in `requested_approval_by_user_id`**. The
  approval-DECISION reject path `_apply_approval_decision` (`procurement_service.py:6577`) sets
  `approved_by = approved_by or approver_email or ""` - the approver may be an **external email with
  no CRM user** (→ no phone; plain-text fallback). **⚠ Risk R3.**
- FE helper: `formatDateTimeInMalaysia(input)` at `lib/helpers.ts:432` - takes the raw string,
  no `new Date()` round-trip (per memory rule). ✅
- FE types: `HandlingLockTracker` (`_shared/handlingLock.ts:36-39`) has `handled_by_id/name/at`;
  `ConversationSLATrackingDetail` (`conversation-sla-tracking/types/conversationSLATracking.types.ts`)
  has `assigned_user_name` (~line 65). Both need new phone/escalated-from fields.
- Banner consumers: `StockInquiryDetail.tsx`, `PurchaseRequestDetail.tsx`, `ComplaintDetail.tsx`
  (`app/(protected)/…`).

## 4. Schema / migration changes

Alembic revision `add_banner_person_link_fields` (chain onto the current committed main head  - 
verify `alembic heads` after fetching main; id ≤ 32 chars).

1. `conversation_sla_event_log.from_assigned_to_id` - `String` FK → `users.id`
   `ondelete="SET NULL"`, nullable. Index `ix_conversation_sla_event_log_from_assigned_to_id`.
   Model add in `app/models/sla.py` (next to `assigned_to_id`, line ~197).
2. `purchase_requests.rejected_by_id` - `String` (matches `users.id` type), nullable, no hard FK
   needed but add one `ondelete="SET NULL"` for consistency. Model add in
   `app/models/procurement.py` (near `approved_by`, line ~352).

No changes to `stock_inquiries` / `complaints` (their rejecter ids already exist).
No `users` / `respond_contacts` schema change - phone is read-through, not stored on the banner rows.

### Backfill (DoD gate §2 - new columns on tables with existing rows)

Script `scripts/backfill_escalation_from_assignee.py` (idempotent, JOIN-based):

- For each `conversation_sla_event_log` row with `event_type='escalation'` and
  `from_assigned_to_id IS NULL`: set it to the `assigned_to_id` of the immediately-prior event-log
  row for the same `sla_tracking_id` ordered by `event_at ASC` (window `LAG`). Rows with no prior
  event stay `NULL`.
- **Best-effort heuristic** (Risk R2): breaks if a mid-tier reassign wrote an intervening non-escalation
  event that changed `assigned_to_id`. Log every row it sets AND every row left NULL with a summary
  count. Document in the script docstring + PR body that this is reconstructive, not authoritative.
- `purchase_requests.rejected_by_id` backfill: leave NULL for legacy rejected PRs - there is no
  reliable structural source (the old path only kept a name string). Banner falls back to
  `approved_by` name plain-text (HIST-3). Note this explicitly; do NOT fabricate an id.

## 5. Backend wiring

### 5.1 Shared phone resolver

New `app/services/banner_person_service.py` (or extend `respond_link_service`):

- `wa_phone_for_user_id(db, user_id: str | None) -> str | None` - load `User` by pk, delegate to
  `resolve_user_respond_contact`, return `.phone_number` or `None`. (PR-1/2/3/5/6)
- `wa_phone_for_respond_user_id(db, respond_user_id: str | None) -> str | None` - `User` lookup by
  `User.respond_user_id`, then as above. (PR-4)
- Both never raise; garbage/None → `None`.
- Provide a name+phone pair helper mirroring the existing `_resolve_user_display_name` so DTOs emit
  `{*_name, *_wa_phone}` together.

### 5.2 Escalation write-path edits (2 sites)

- `sla_service.escalate_tracking`: capture `prev_assigned_to_id = getattr(tracking,
  "assigned_to_id", None)` BEFORE the overwrite block (~line 2168); pass it into the
  `ConversationSLAEventLogCreate(...)` as `from_assigned_to_id=prev_assigned_to_id`. Extend
  `ConversationSLAEventLogCreate` schema + `create_event_log` to persist it. (ESC-1)
- `form_sla_service._escalate_tracker`: capture `prev_assigned_to_id = tracker.assigned_to_id`
  BEFORE `tracker.assigned_to_id = assignee["id"]` (~line 511); pass into `_write_event_log(...,
  from_assigned_to_id=prev_assigned_to_id)`. Extend `_write_event_log` signature + insert. (ESC-2)

### 5.3 DTO / schema / serializer additions

Emit alongside each existing person NAME field (DoD gate §4 - reach the FE via the manual dict
builders, not schema inheritance alone):

- **Handling lock** (`form_sla_tracking.py:73` + complaints `_handled_name` override,
  `complaints_service.py:342`): add `handled_by_wa_phone`. Schemas
  `procurement.py:661/805/837`, `complaints.py:230`. (HL-1)
- **Active tracker DTO** (conversation-sla-tracking serializer feeding
  `ConversationSLATrackingDetail`): add `escalated_from_name`, `escalated_from_wa_phone` (resolved
  from the latest `event_type='escalation'` event's `from_assigned_to_id`), `assigned_user_wa_phone`
  (current assignee), and confirm/emit `escalated_at`. (ESC-3, EXT-1)
- **StockInquiry detail** (`procurement_service.py:2724` dict): add `rejected_by_wa_phone`
  (`wa_phone_for_user_id(rejected_by)`); `rejected_by_name` + `rejected_at` already present. (REJ-1)
- **Complaint detail**: add `rejected_by_name` (resolve `respond_user_id`→name),
  `rejected_by_wa_phone` (via `wa_phone_for_respond_user_id`), `rejected_at`. (REJ-2)
- **PR reject paths**: populate `rejected_by_id` in BOTH `reject_submitted` (`actor_user_id`,
  line ~6150) and `_apply_approval_decision` (the deciding user's id when resolvable, else NULL,
  line ~6577). PR detail DTO emits `rejected_by_name` (resolve from `rejected_by_id`, else legacy
  `approved_by` string), `rejected_by_wa_phone`, and a WHEN (`approved_at`). (REJ-3, REJ-4, HIST-3)

## 6. Frontend wiring

### 6.1 New shared component

`components/common/PersonLink.tsx`:

```tsx
export function PersonLink({ name, waPhone, className }: {
  name?: string | null; waPhone?: string | null; className?: string;
}) {
  const label = name?.trim();
  if (!label) return null;                 // FB-3: never an empty link
  const digits = waPhone?.replace(/\D/g, ''); // defence-in-depth; BE already sends digits
  if (!digits) return <span className={className}>{label}</span>; // FB-1
  return (
    <a href={`https://wa.me/${digits}`} target="_blank" rel="noopener noreferrer"
       className={className}>{label}</a>                          // FB-2
  );
}
```

No UUID ever passes through (UUID-1). Export via `components/common/index.ts`.

### 6.2 Banner edits

- **HandlingLockBanner.tsx** - replace the `{handlerName}` spans (`other_holds`/`admin_other_holds`
  line ~97, `not_eligible` line ~147) with `<PersonLink name={tracker?.handled_by_name}
  waPhone={tracker?.handled_by_wa_phone} />`. Add `handled_by_wa_phone` to `HandlingLockTracker`
  (`handlingLock.ts:37`). (HL-2..HL-4)
- **SlaEscalationBanner.tsx** - add props `escalatedFromName`, `escalatedFromWaPhone`, `escalatedAt`.
  Render WHEN (`formatDateTimeInMalaysia(escalatedAt)`) + "escalated from {PersonLink(...)}"; keep
  "now assigned to {assignee}" as plain text context. (ESC-4..ESC-6)
- **SlaExtensionBanner.tsx** - add prop `assigneeWaPhone`; wrap `{assignee}` in `PersonLink`; add
  the extend `event_at` as WHEN via `formatDateTimeInMalaysia`. (EXT-2/EXT-3)
- **SlaActiveTrackerControls.tsx** - thread the new tracker fields
  (`escalated_from_name`/`escalated_from_wa_phone`/`escalated_at`/`assigned_user_wa_phone`) from
  `activeTracker` into the two banners.
- **RejectionReasonBanner.tsx** - add props `rejectedByName`, `rejectedByWaPhone`, `rejectedAt`.
  When name present: "Rejected by {PersonLink} · {formatDateTimeInMalaysia(rejectedAt)} - {reason}";
  else today's "Rejected - {reason}". Update the 3 detail-page call sites to pass the new fields.
  (REJ-5/REJ-6)

Timestamps: always `formatDateTimeInMalaysia(rawString)` on the raw naive string - never
`formatDateTime(new Date())` (memory rule). NB `SlaExtensionBanner` currently uses `formatDateTime`
for `newDue`; keep that for the due date but use `formatDateTimeInMalaysia` for the WHEN.

## 7. Three-phase breakdown

### Phase 1 - FE prototype (mocks, no BE)
- Build `PersonLink` + wire all four banners against inline mock fixtures covering: linked phone
  (link renders), no phone (plain text), no name (nothing), long name (truncate/title). Include a
  no-phone fixture for EACH banner.
- Mock the four DTO shapes with the new fields at the top of each banner's story/fixture; document
  the expected contract (field names in §5.3) as the API contract block in the plan/service file.
- Verify in browser via Playwright MCP: sidebar → each of the 3 detail pages → screenshot golden +
  no-phone states. Check console clean. No tests yet, no BE code.

### Phase 2 - BE wiring, test-first (red → green → refactor)
- **pytest (write failing first):**
  - `test_banner_person_phone_resolver.py` - PR-1..PR-6 (incl. respond_user_id path PR-4).
  - `test_sla_escalation_from_snapshot.py` - ESC-1/ESC-2 (both write paths snapshot prior owner).
  - `test_active_tracker_dto.py` - ESC-3, EXT-1, HIST-1.
  - `test_stock_inquiry_reject_dto.py` / `test_complaint_reject_dto.py` / `test_pr_reject_dto.py`  - 
    REJ-1..REJ-4, HIST-3 (+ happy / auth-denial / validation per route).
  - `test_escalation_backfill.py` - HIST-2 (heuristic sets prior-event assignee; no-prior stays NULL).
- Implement migration → models → resolver → escalation edits → serializers to green. Run backfill on
  the local prod-copy DB; capture the set/NULL summary.
- **vitest (test-first for logic, component-state after prototype settles):**
  `PersonLink.test.tsx` (FB-1/FB-2/FB-3/UUID-2), plus link+no-phone+WHEN states for
  `HandlingLockBanner`, `SlaEscalationBanner`, `SlaExtensionBanner`, `RejectionReasonBanner`.
- Swap FE mocks for real hooks/service/api-client calls (one-line at the service boundary); delete
  fixtures not reused by tests.
- **playwright:** `e2e/form-banner-person-links.spec.ts` - E2E-1 (rejected SI, wa.me href +
  network assert) and E2E-2 (handling-lock holder link vs no-phone plain text). Add real fixtures.
- Re-verify live at 375px + 1280px (fresh `rm -rf .next && npm run build`).

### Phase 3 - Code review
- `/code-review` (ultra if diff large) → address via `--fix`/`/simplify` → open PR.
- PR body: Phase-1 screenshots, confirmation Phase-2 drove from failing tests, the filled test
  report keyed to UAC ids, and the backfill summary (rows set vs left NULL).

## 8. Cross-cutting impact checklist

- **Migrations:** 2 columns + 1 backfill script (§4). Verify single alembic head post-merge.
- **RBAC / module guard:** none new - reuses existing detail-read permissions on the 3 domains.
- **list_query registry:** no change (banners read detail DTOs, not DataGrid columns).
- **Embedding pipeline:** no change (phones/attribution are not embedded).
- **Worker / RQ:** none - all read-path resolution is synchronous in the request.
- **New permission grant sweep:** N/A (no new permission).
- **Manual dict builders (DoD §4):** the new `*_wa_phone` / `*_name` fields MUST be added to the
  hand-built dicts (`get_stock_inquiry_dict` @2720, complaint detail builder, PR detail builder,
  `form_sla_tracking.py` DTO) - schema inheritance alone will drop them.
- **CLAUDE.md gotchas that apply:** MY-time render via `formatDateTimeInMalaysia(raw)` not
  `formatDateTime(new Date())`; naive-UTC storage; no UUID in UI; searchable-dropdown rule N/A (no
  new dropdown); FE prod-build no-HMR rebuild before browser verify.

## 9. Risks / open decisions (flag for the user)

- **R1 (design, resolved in plan):** Complaint `rejected_by` stores a **`respond_user_id`**, not a
  `users.id` - contrary to the brief's implication. Handled via a dedicated
  `wa_phone_for_respond_user_id` resolver. No schema change needed.
- **R2 (data quality):** the escalated-from backfill is a best-effort heuristic (prior-event
  `assigned_to_id`). It is wrong when a mid-tier reassign changed the assignee between escalations.
  It is clearly logged and NULL-safe. **Decision needed:** accept best-effort, or leave all historical
  escalation banners person-less (NULL) and only attribute go-forward escalations? Recommend:
  best-effort + log.
- **R3 (schema minimalism):** PR reject-submitted already persists the actor id in
  `requested_approval_by_user_id`. Adding `rejected_by_id` is cleaner (that field is overloaded with
  "who sent for approval") but is technically redundant for that one path. **Decision needed:** add
  the dedicated column (recommended, unambiguous), or reuse `requested_approval_by_user_id` and skip
  the migration? Recommend the dedicated column.
- **R4 (scope):** PRs rejected by an **external-email approver** (no CRM user) have no phone - banner
  correctly falls back to plain text. Confirm that's acceptable (no attempt to WhatsApp a
  non-CRM approver). Recommend: accept plain-text fallback.
- **R5 (UX):** escalation banner links the **escalated-FROM** person (who missed) while extension
  links the **current assignee**. Intentional per the brief, but the two banners then link different
  roles. Confirm this asymmetry is desired; documented in UAC ESC/EXT.

## 10. Test report (fill in Phase 2)

See the table in the UAC file; mirror it here with PASS/FAIL/DEFERRED per id on completion.
