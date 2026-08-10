# PLAN - Portal submission revisions

Status: DRAFT - not started. **ON HOLD at the user's request** - discuss before any code. Grilled once (2026-08-10, 10 findings folded in: revision fence, stale purchasing response, history-vs-cap split, attachment_id keying, idempotency, KPI exclusion, frozen requestor, single restart knob, team notify fallback, company scope), then user-reviewed in Lavish over two rounds (11 decisions answered; **no open questions remain**, see the UAC). Two of those decisions rest on beliefs that turned out to be factually wrong and were corrected in the docs rather than silently followed - see UAC section O and N6.
UAC: `documentation/plans/UAC-portal-submission-revisions.md` (contract - read it first)
Slug: `portal-submission-revisions`
Branch: `feat/portal-submission-revisions`

## Decisions already locked by the user

| Question | Decision |
|---|---|
| Revise window | **Configurable per form.** Stock inquiry revisable even after purchasing responded. Complaint never revisable. PR / SF undecided → seeded disabled. |
| In-flight SLA stage | **Void it and restart** the chain from stage 1. |
| Scope | **Superseded in round 3.** Now: generic engine with **three adapters wired and enabled from day one** - `stock_inquiry`, `purchase_request`, `sponsorship_form`. `complaint` ships disabled but flippable. |
| Cap counting | **Separate counters.** Office reject → resubmit does not burn a contact revision. |

Round 2 (Lavish review): Q6 snapshot-and-clear · Q7 fence **every** office write on **every** revisable form · Q4 **suffix the document number** per revision · Q2 assignment prefs but revision-specific copy · Q3 revise while locked allowed · Q5 blocked on all three terminal statuses · Q8 say "the office", never "purchasing". Full table in the UAC.

---

## Existing ground (verified, not assumed)

- Portal submissions live in `app/services/portal_service.py`. `SUPPORTED_TYPES = ("complaint","stock_inquiry","purchase_request","sponsorship_form")`. Editability is gated on `portal_draft_at IS NOT NULL`; `submit_draft()` clears it and fires the per-type notifications. A `rejected → resubmit` path already exists (`previous_status in ("draft","rejected","responded")`).
- Portal routes: `app/api/v1/public/portal.py` - `GET/POST/PUT/DELETE /submissions/...`, `POST /submissions/{kind}/{id}/submit`, `/attachments` list + upload + delete, and `_list_attachments_for()` as the attachment serializer.
- Stock inquiry status chain: `new → pending_project_sales → pending_purchasing → responded`, plus reject (`rejected_from`, `rejection_reason`) / reopen / void columns on `StockInquiry` (`app/models/procurement.py:506`).
- Form SLA: `app/services/form_sla_service.py`. `FormSLAOrchestrator.emit_event(...)` / module helper `emit_form_event(...)` drive stage spawn; `_active_tracker()` finds the live tracker; `_escalate_tracker()` is the closest precedent for "change tracker state + write event log + void takeovers" (`SlaTakeoverService.void_for_tracking`). **There is no existing void/cancel-a-tracker call - it must be added.**
- `components/common/AttachmentPreviewModal.tsx` is already shared and already documents a `fetchBytes` escape hatch **explicitly for the contact portal** (portal has no JWT session, so `apiFetch` 401s). Portal currently opens attachments via `<a target="_blank">` in `app/(auth)/portal/components/AttachmentDropzone.tsx:502,510`.
- `system_settings` is a hard singleton (unique index on `((true))`); new columns must be added to **both** manual builders (GET dict and `SystemSettingUpdate`).
- The `forms` table is the marketing/downloadable form catalog - **not** the portal submission-type registry. Per-type revision config therefore needs its own table.

---

## Data model

### New table `portal_form_revisions`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `source_entity_type` | varchar(50) NOT NULL | `stock_inquiry`, ... |
| `source_entity_id` | uuid NOT NULL | matches the entity's id column type. **Corrected in S1:** all four portal types (`complaints`, `stock_inquiries`, `purchase_requests`) key on a uuid `id`, and the sibling polymorphic column `conversation_sla_tracking.source_entity_id` is already uuid (migration 300). Text here would accept a `uuid = text` mismatch Postgres would otherwise reject at write time. |
| `version_no` | int NOT NULL | **every** submitted version - history ordering |
| `revision_no` | int NOT NULL | contact-initiated revisions only - the cap counter |
| `kind` | varchar(20) NOT NULL | `original` \| `revision` \| `resubmission` |
| `reason` | text NULL | NULL only for `original`; the rejection answered, for `resubmission` |
| `invalidated_json` | JSONB NULL | stage output cleared by this revision (UAC FB2), e.g. the superseded `purchasing_response` |
| `snapshot_json` | JSONB NOT NULL | post-edit field values incl. line items |
| `attachments_json` | JSONB NOT NULL | `[{attachment_id, link_id, filename, size, mime}]` |
| `voided_stage_code` | varchar(100) NULL | the PRIMARY (newest) stage this revision voided (NULL for rev 0, and when nothing was open) |
| `voided_assignee_user_id` | text NULL | who was working it |
| `voided_stages_json` | JSONB NULL | **every** stage this revision voided, newest first: `[{stage_code, assignee_user_id}]`. A form can have two stages open at once (project sales + approval), and the revision voids all of them and notifies all of their handlers, so the two scalar columns above alone under-report the cancellation (UAC H3a). They stay populated with the first entry so every single-stage reader is unchanged. |
| `submitted_at` | timestamp NOT NULL | naive UTC, per repo convention |
| `submitted_by_contact_id` | text NULL FK `respond_contacts.id` ON DELETE SET NULL | |
| `is_reconstructed` | bool NOT NULL default false | rev 0 backfilled from current state |
| `created_at` | timestamp default now() | |

Constraints: `UNIQUE (source_entity_type, source_entity_id, version_no)`, index on `(source_entity_type, source_entity_id)`. **Not** unique on `revision_no` - a resubmission repeats the current `revision_no` by design.

### New table `portal_revision_configs`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `source_entity_type` | varchar(50) NOT NULL **UNIQUE** | one row per portal type |
| `is_enabled` | bool NOT NULL default false | fail closed |
| `max_revisions` | int NULL | NULL = inherit global |
| `allowed_statuses` | JSONB NOT NULL default `'[]'` | statuses at which revision is permitted |
| `restart_stage_code` | varchar(100) NULL | NULL = first stage of the chain |
| `created_at` / `updated_at` | timestamp | |

Seed (migration), as shipped in S1 - this supersedes the pre-round-3 line that had PR/SF disabled:

| type | `is_enabled` | `allowed_statuses` | `max_revisions` | `restart_stage_code` |
|---|---|---|---|---|
| `stock_inquiry` | true | `["pending_project_sales","pending_purchasing","responded"]` | NULL | NULL |
| `purchase_request` | true | `["submitted","approved"]` | NULL | NULL |
| `sponsorship_form` | true | `["submitted","approved"]` | NULL | NULL |
| `complaint` | false | `[]` | NULL | NULL |

PR/SF statuses were read off the chain, not invented. Their lifecycle is
`draft -> submitted -> approved -> processed_by_cs | closed`, where `submitted` spans both
the `main` (project sales) and `project_sales_manager` stages - pending-approval is an
`approval_status` sub-state, not a lifecycle status - and `approved` is the CS stage.
`processed_by_cs`, `closed`, `rejected` and `voided` are terminal
(`ProcurementService._VOID_BLOCKED_STATUSES`), so they are excluded per Q5.

### `system_settings` additions

- `portal_revisions_enabled` bool NOT NULL server_default `true`
- `portal_max_revisions` int NOT NULL server_default `2`

### Entity additions (denormalized, adapter-declared)

- `stock_inquiries.revision_no` int NOT NULL server_default `0`, `stock_inquiries.last_revised_at` timestamp NULL
- `purchase_requests.revision_no` / `purchase_requests.last_revised_at`, same types. **One pair covers both PR and SF** - they share the `purchase_requests` table, discriminated by `request_type`.

Rationale: the list badge (H4) must not fire a per-row query. Only the count and timestamp are denormalized; the reason is read from the latest revision row, so there is nothing to drift.

---

## Backend design

### `app/services/portal_revision_service.py` (new, generic)

```python
@dataclass(frozen=True)
class RevisionAdapter:
    source_entity_type: str
    model: type                          # StockInquiry
    snapshot_fields: tuple[str, ...]     # what goes into snapshot_json
    serialize_lines: Callable | None     # child lines -> list[dict] (None for SI)
    frozen_on_revise: tuple[str, ...]    # UAC AB2 - SI: salesperson, salesperson_contact_id
    invalidated_on_revise: tuple[str, ...]  # UAC FB2 - SI: purchasing_response,
                                            # last_responded_by, last_responded_at
    status_for_stage: Callable[[str], str]  # stage_code -> entity status (UAC J4)
    revision_no_attr: str = "revision_no"
    last_revised_at_attr: str = "last_revised_at"

ADAPTERS: dict[str, RevisionAdapter] = {
    "stock_inquiry": ...,     # purchasing_response invalidated; restart at pending_project_sales
    "purchase_request": ...,  # line items via serialize_lines; own approval chain
    "sponsorship_form": ...,  # shares the PR table, separate chain and PDF
}   # complaint: config row exists, disabled - no adapter until it is turned on
```

The restart target is declared **once**, on `portal_revision_configs.restart_stage_code` (NULL = first stage of the chain). The adapter only translates that stage into the status the entity should carry, and supplies the stage's `start_event` by reading `form_sla_configs`. No `restart_status` constant on the adapter (UAC J4).

Public surface:

- `resolve_policy(db, entity_type, row) -> RevisionPolicy` → `{enabled, allowed, used, max, remaining, blocked_reason}`. Blocked reasons are a small enum mapped to one human sentence each (UAC B2).
- `record_initial(db, entity_type, row, contact_id)` → writes `revision_no = 0`. Called from `PortalService.submit_draft()` on the transition out of draft. Idempotent (no-op if rev 0 exists).
- `list_revisions(db, entity_type, entity_id) -> list[dict]`
- `revise(db, token, entity_type, row, payload, reason) -> dict`

`revise()` ordering - matters:

0. **Idempotency / stale-write guard** (UAC C5): the request carries the `revision_no` the contact was viewing; mismatch → 409, no side effects. Combined with the existing `idempotency_middleware`, a double tap yields one revision, not two voids and two restarts.
1. `resolve_policy` → raise `handle_validation_error(blocked_reason)` (422) if not allowed.
2. Validate reason (5..2000 chars, non-blank after strip).
3. `record_initial(...)` backfill with `is_reconstructed = True` if version 0 missing (UAC G2).
4. Capture the active tracker's `stage_code` + `assignee_user_id` **before** voiding (needed for the revision row and the notification).
5. Apply the payload through the **existing** `PortalService._apply_payload` + `_replace_*_lines_if_needed`, using `_editable_fields(kind)` **minus `adapter.frozen_on_revise`** (UAC AB1/AB2). No second field whitelist - one source of truth. (`respond_inbox_url` stays excluded, per the standing rule.)
6. Snapshot `adapter.invalidated_on_revise` into `invalidated_json`, then **clear those fields on the entity** (UAC FB2 - the superseded purchasing answer must not read as current).
7. Increment `revision_no` and `version_no`, stamp `last_revised_at`.
8. Write the `portal_form_revisions` row (post-edit snapshot + reason + attachments + voided-stage context + `invalidated_json`, `kind = "revision"`).
9. `FormSLAOrchestrator.void_active_for_source(...)` (new - see below).
10. Set `row.status = adapter.status_for_stage(restart_stage_code)`.
11. `db.commit()`.
12. **Post-commit, best-effort** (catch + warn, never raise, per the post-commit side-effects rule): `emit_form_event(db, entity_type, id, start_event, contact_id=...)` to spawn stage 1, then the voided-handler notification (falling back to the stage team when the tracker had no assignee - UAC FT1).

`submit_draft()` also gains a history write for the **resubmit-after-rejection** path: `kind = "resubmission"`, `version_no + 1`, `revision_no` unchanged, reason = the rejection being answered (UAC C4).

> Note on step 11: `emit_event` already swallows its own errors by design ("SLA orchestration must not block the underlying state transition"), which is exactly the behaviour we want here.

### `FormSLAOrchestrator.void_active_for_source(...)` (new)

Mirrors `_escalate_tracker`'s bookkeeping, minus the reassignment:

- Find every active tracker for `(source_entity_type, source_entity_id)` - reuse the `conversation_tracking_scope()` discipline so conversation-SLA rows are never touched.
- Mark resolved + a void marker (`resolution_reason = "revised_by_contact"`, plus the void columns the tracker model already carries if present - **verify at implementation time**; if the tracker has no void concept, add `voided_at` / `void_reason` in the same migration rather than overloading `is_resolved` semantics).
- The void marker is what dashboard queries filter on to keep voided stages out of open-tracker and breach KPIs while remaining explainable (UAC F4a). Find and update those aggregate queries in the same slice - a revision feature that silently doubles the breach count is a worse bug than the one it fixes.
- Write a `conversation_sla_event_log` row per tracker. **Wrap every naive-UTC datetime through `_to_aware_utc()` before it enters an event-log payload** (the -8h Malaysia-time trap).
- `SlaTakeoverService(db).void_for_tracking(tracker_id, "revised")` for pending takeovers.
- Return the voided trackers so the caller can notify.

### As built (S2 + S3) - deltas from the sketch above

Recorded here rather than left as drift. Everything else shipped as written.

1. **Step order inside `revise()`.** The restart status (step 10 above) is set BEFORE
   the tracker void (step 9), and the void is the last thing in the transaction. Reason:
   the shared event-log writer (`ConversationSLATrackingService.create_event_log`)
   commits, so anything still unwritten when the void runs would land in a *later*
   commit. Voiding last makes the event-log commit the one that carries the whole
   revision. Net effect is stronger atomicity, not weaker.
2. **Pending takeovers are voided AFTER the commit**, not inside
   `void_active_for_source`. `SlaTakeoverService.void_for_tracking` commits and rolls
   back on failure by design, so calling it mid-transaction would commit a half-applied
   revision. This mirrors `escalate_form_tracking`, which also commits first and voids
   takeovers second. `void_active_for_source` returns the trackers; `revise` voids their
   takeovers in its post-commit block.
3. **`snapshot_fields` is `snapshot_extra_fields`.** The snapshot base is
   `PortalService._editable_fields(kind)`, read at runtime; the adapter only declares
   the read-only context beyond it (document number, status). Naming it "extra" keeps
   the one-whitelist rule visible at the definition site.
4. **Frozen and invalidated field lists for PR / SF** (the UAC only spelled out stock
   inquiry): frozen `requested_by`, `requested_by_contact_id` (same CS-pin argument as
   AB2); invalidated `approval_status`, `approval_comments`, `approved_at`,
   `approved_by`, `approval_signature_ref` - an approval granted to the superseded
   version is stage output exactly as a purchasing response is, and a form revised back
   to `submitted` while still reading `approved` would be wrong on every screen.
5. **The handling-lock holder is notified too**, alongside the assignee. The void
   releases the lock (`handled_by_id` cleared, as escalation does), and the holder is by
   definition the person actually mid-work. `void_active_for_source` smuggles the prior
   holder out on the returned instance (`_voided_handled_by_id`) because the column is
   empty by the time the notifier runs.
6. **`_suffixed_number` is local to `portal_revision_service`** until the shared
   render/strip pair (N4, slice S3c) lands. It is three lines and the format is fixed by
   N1; collapse it to an import when S3c ships.
7. **Open-tracker exclusion is a shared predicate**, `app/services/sla_scope.py`
   (`not_voided()` / `open_tracker_scope()`), applied to the KPI funnel
   (`sla_kpi_service._base_filters`, which feeds summary + leaderboard + tasks + trend),
   the overdue scan, `_active_tracker`, the form-tracking route, the handling lock, form
   skip, form-void notify, automation recipients, the daily digest, and the complaint /
   PR / SI list assignee lookups. `_active_tracker` is not optional: without it the
   restart would find the stage it had just voided and never spawn stage 1.
8. **`submitted_at` on PR / SF is NOT re-stamped by a revision.** Not specified in the
   UAC, and `last_revised_at` already carries the revision instant. Flagged in case the
   PDF's top Date should follow the revision.

### As built (S3b + S3c) - deltas from the sketch above

1. **The fence travels as a request HEADER, `X-Revision-No`.** The UAC says an office
   write "carries the `revision_no` the user was looking at" without naming a transport.
   A header is the only uniform one: several fenced endpoints (approve, process, close,
   submit-for-project-sales, DELETE) take no body at all, so a body field would have
   meant inventing one per route and would have fragmented the "one shared dependency"
   requirement of CB3.
2. **The header is optional; absent means unfenced.** Every existing integration
   principal (n8n, the MCP server, the external API, any older client) sends no such
   header and must keep working. The fence protects the surface that CAN send it - the
   office UI - while the portal revise path keeps its own MANDATORY `expected_revision_no`
   guard (UAC C5), which is where a missing expectation is genuinely a bug.
3. **The fence authenticates.** FastAPI solves route-level dependencies BEFORE the
   handler's own, so without an auth dependency inside it an anonymous caller could probe
   a record's revision through the 409. It depends on `get_current_user_or_api_key`. A
   consequence: on a permission-gated route a stale header yields 409 before 403. Harmless
   (the write still never happens) and recorded rather than left to be rediscovered.
4. **`revision_no` + `last_revised_at` are declared on `StockInquiryResponse` and
   `PurchaseRequestHeaderResponse`.** A `response_model` silently drops any field it does
   not name, so without this the office client has no way to learn what to echo back and
   the fence has nothing to compare. Same fields the "Rev N" list badge (H4) needs.
5. **Office list / detail responses keep the number BARE**; the revision reaches those
   screens through `revision_no` (the H4 badge), not through the number string. Suffixing
   `PurchaseRequestHeaderResponse.request_number` would round-trip into storage - the
   number is user-assignable there and `update_request` writes what it is given, unlike
   `inquiry_number` which is popped. `_strip_number_suffix_in_place` now defends the
   column on every PR write path regardless, but the display decision belongs with the
   office FE slice (S5) and is left to it.
6. **Item 6 of the S2+S3 list is resolved.** `_suffixed_number` is gone;
   `portal_revision_service` imports `suffix_revision` from the shared module.
7. **`external/purchase-requests` cannot create a brand-new `purchase_request`** -
   `PurchaseRequestExternalCreate` declares no `sales_type` while
   `_PR_REQUIRED_FIELDS_BY_TYPE` requires one, so the completeness gate always fails on a
   create (the resubmit path passes, because it falls back to the existing row). Found
   while writing the N6 tests, pre-existing, unrelated to revisions, NOT fixed here.

### Notification (new kind `form_revised`)

Reuse `create_with_channel_preferences(...)` with `email_pref_attr="notify_email_on_assignment"`, `whatsapp_pref_attr="notify_whatsapp_on_assignment"` (Q2). In-app always. Link target is the **internal** detail URL (`_build_stock_inquiry_internal_url`-style helper), never the public `?token=` view.

The body is **revision-specific, not recycled assignment copy** (UAC F6a): suffixed document number, which revision, who submitted it, the reason verbatim, the stage that was voided. A recipient must know why their work stopped without opening the record.

### Document number suffix (UAC N)

One shared module with **two** functions, so render and parse can never disagree:

- `display_document_number(row) -> "SI-26-0184-R2"` - derived from `revision_no`, never stored. Consumed by the list, detail, portal, notifications, chat message builders, **both PDF services** (body + filename), and external API responses (N5: everywhere, integration payloads included).
- `strip_revision_suffix(value) -> "SI-26-0184"` - applied at **every inbound lookup-by-number** (N6). The call sites that matter:
  - `procurement_service.py:3441` (`StockInquiry.inquiry_number == lookup`) and `:5409` (`PurchaseRequestHeader.request_number == lookup`) - the **create-or-resubmit** decision behind `POST /api/v1/external/stock-inquiries` and the PR equivalent. A miss here does not 404, it **inserts a duplicate** instead of updating the rejected row.
  - `external/view_link.py` - **ignore.** Public view links are retired (routes gated by `require_public_view_links_enabled`; the user confirms only in-system view and portal links are used). Do not spend effort there.
  - Grep `_number ==` before implementing; assume this list is incomplete.

The stored `inquiry_number` / `request_number` stays bare, so indexes, imports and existing rows are untouched.

### Response gating (UAC section O) - bigger than it looks

`update-and-reply` currently **sends a message and records the response in one call**, on both stock inquiry and complaint, with no status guard on either. Gating "the response but not the chat" therefore means splitting that endpoint, not adding an `if`:

- The send path stays open at any status (AC O2).
- The response write (`purchasing_response`, `technical_team_response`) is refused outside the type's allowed response statuses (AC O1).
- Both then also pass the revision fence (AC O4).

This is live-behaviour change with its own regression risk, independent of revisions. It deserves its own tests and its own line in the release note.

### API contract

**Portal (token auth, `app/api/v1/public/portal.py`)**

```
GET  /api/v1/public/portal/submissions/{kind}/{id}
  -> ...existing..., + "revision": {
       enabled: bool, allowed: bool, used: int, max: int,
       remaining: int, blocked_reason: string | null,
       restart_stage_label: string | null   # S6b - names the destination (E1a)
     }

GET  /api/v1/public/portal/submissions/{kind}/{id}/revisions
  -> { items: [{
       revision_no, label, reason, submitted_at, submitted_by,
       is_reconstructed, snapshot,
       attachments: [{attachment_id, link_id, filename, size, mime, url}],
       voided_stage_code, voided_assignee_name,
       voided_stages: [{stage_code, assignee_name}],
       changes: [{field, label, from, to}]
     }] }        # `changes` computed server-side vs revision_no - 1
                 # `voided_stages` is EVERY stage the revision voided (newest
                 #  first); the two scalars are its first entry (UAC H3a)
                 # `url` is resolved at READ time (S6b), never stored

POST /api/v1/public/portal/submissions/{kind}/{id}/revise
  body: { reason: string, expected_revision_no: int, ...submit payload shape }
  -> { submission: {...}, revision: {...policy after...} }
  409 { detail: "This submission changed. Reload and try again." }   # stale expected_revision_no
  422 { detail: "<one human sentence>" }   # via handle_validation_error / AppException

GET  /api/v1/public/portal/attachments/{attachment_id}/download
  -> streams bytes under portal-token auth (add if absent; needed for I2/I5).
     Keyed on attachment_id, NOT link_id: an attachment dropped during a revision
     has no EntityAttachmentLink left (UAC G6), so a link-keyed route 404s on exactly
     the historical files this route exists to serve. Authorisation walks
     token -> contact owns the submission -> attachment appears in one of its
     revision snapshots.
```

**Office (protected)**

```
GET /api/v1/procurement/stock-inquiries/{id}/revisions
  -> same shape as the portal history route; gated by the existing
     stock inquiry view permission. Service is generic; only the mount is per-domain.

GET /api/v1/procurement/stock-inquiries/{id}     # StockInquiryResponse
GET /api/v1/complaints-management/complaints/{id}  # ComplaintResponse
  -> ...existing..., + response_write_allowed: bool   # S6b, UAC O1
     Whether the type's response column may be written at this status. The FE gates
     every response affordance on it instead of mirroring the status lists.
```

**Config**

```
GET /api/v1/forms-management/revision-configs         -> { items: [...] }, one row per portal type
PUT /api/v1/forms-management/revision-configs/{type}  -> upsert, returns the updated row
POST /api/v1/user-management/settings/general         -> existing setattr path carries the two globals
```

Body of the PUT: `{ is_enabled, max_revisions, allowed_statuses, restart_stage_code }`.
`max_revisions: null` inherits the global cap; `restart_stage_code: null` means the first
stage of the chain.

> **Correction (S6, recorded at implementation time):** the earlier draft wrote these as
> `/api/v1/forms/...`. There is no `/api/v1/forms` prefix - `app/api/v1/__init__.py` mounts
> the forms router at **`/forms-management`**, so `/api/v1/forms/revision-configs` would
> 404. The frontend calls `/api/v1/forms-management/revision-configs`; the backend route
> must be added under the existing `forms` router. **Implemented in S6b** (see below) at
> `app/api/v1/forms/revision_configs.py`. The two globals already worked (they go through
> the general-settings setattr path, which carries them).

> Reminder: `apiFetch('/api/<domain>/...')` rewrites straight to FastAPI `/api/v1/<domain>/...` and **bypasses** any Next `route.ts` proxy. Do not add a Next proxy for the settings save.

---

## Frontend design

### Portal (`app/(auth)/portal/`)

- `[type]/[id]/page.tsx` - Revise action + remaining count + blocked sentence (UAC B2/B3); Revision history section that **always renders** (G3).
- `components/RevisionHistory.tsx` (new) - timeline; each entry expandable: reason, timestamp, changes list, attachments with in-place preview.
- `components/ReviseDialog.tsx` (new) or a `mode="revise"` branch on `SubmissionForm.tsx` - pre-filled, required reason field, `AlertDialog` confirm with the three-consequence copy (E1). Prefer the mode branch: the field rendering, lookups and validation are already there and must not fork.
- `components/AttachmentDropzone.tsx` - replace both `<a target="_blank">` (lines ~502, ~510) with `AttachmentPreviewModal` + a portal `fetchBytes` that hits the portal download route with the portal token.
- `components/PortalLanding.tsx` → `SubmissionPreviewDialog` - the long-press preview card gains the same Revise action and remaining-count line as the detail page (UAC B6). `onLongPress` → `setPreviewRow` already exists at `PortalLanding.tsx:537`; this adds an action to the dialog it opens, nothing new plumbed.
- Revision timeline follows the packing-list timeline pattern (`PackingListDetail.tsx`) rather than a new visual language (UAC G8).
- `lib/portal-client.ts` - `getRevisions`, `revise`, `fetchAttachmentBytes`.

### Office (`app/(protected)/procurement-management/stock-inquiries/`)

- `components/StockInquiryDetail.tsx` - mount `RevisionBanner` (H1) and a **Revisions** tab (H2, always rendered with an empty state). **Addition only** - attachments, chat and every existing section keep their current placement (UAC H2a).
- `components/common/RevisionBanner.tsx` (new, shared) - sibling of `RejectionReasonBanner.tsx` / `VoidBanner.tsx`, same visual language.
- `components/common/RevisionTimeline.tsx` (new, shared) - one component serving both the portal history and the office tab; the office variant additionally shows the voided-stage context (H3).
- `components/StockInquiriesList.tsx` - "Rev N" badge column off the denormalized `revision_no`.

### Settings (`app/(protected)/user-management/settings/`)

- New "Portal revisions" section: the two globals plus a DataGrid of per-type config rows, edited via modal (A6). DataGrid must use `tableLayout: { width: 'fixed', columnsResizable: true }` with explicit `size` per column.

### As built (S5 + S6) - deltas from the sketch above

1. **Revisions renders as a titled panel, not a tab.** Neither `StockInquiryDetail` nor
   `PurchaseRequestDetail` uses `Tabs` today - both are stacked sections. Introducing a
   tab shell for Revisions would mean either re-tabbing the page (forbidden outright by
   UAC H2a) or shipping a one-tab tab strip, which reads as broken. It therefore mounts
   as `RevisionsSection`, a `Card` titled "Revisions", appended after Attachments and
   before the Audit Trail. Everything H2 actually asks for holds: it always renders, it
   carries an explicit empty state, and it is an addition only - no existing section
   moved, was re-ordered or was re-grouped. If a real tab shell is wanted later it is a
   wrapper change on one component, not a rework.
2. **Both detail pages and both lists are wired**, not just stock inquiry: the purchase
   request router serves sponsorship forms off the same route, so `PurchaseRequestDetail`
   / `PurchaseRequestsList` cover two of the three enabled types.
3. **The "Rev N" badge is its own narrow column, and the number column carries the
   suffix.** H4 asks for a badge to scan, N1 asks for the suffix wherever the number
   appears; both are satisfied without one hiding the other, and either column can be
   hidden through the normal column preferences.
4. **The revision banner reads its reason and submitter from the lineage query**, not
   from the entity: the entity carries only `revision_no` / `last_revised_at`, so the
   banner paints the revision, the suffixed number and the timestamp immediately and
   fills the reason in when the lineage arrives.
5. **Empty state fires on "no lineage", not on "revision_no = 0".** A resubmit after
   rejection writes a history row without consuming a revision (UAC C4), so a second
   entry at revision 0 is real lineage and must render.
6. **`invalidated` is rendered through a label whitelist** (`purchasing_response`,
   `approval_comments`, `approval_status`). The remaining invalidated columns hold user
   ids and timestamps, and a raw id must never reach the UI.
7. **Response gating is a shared FE mirror of `response_gate.py`** (`lib/response-gate.ts`),
   applied to every affordance that opens a response editor on stock inquiry and
   complaint: the header CTA, the gear-menu "Update & Reply", and the inline pencil.
   "Chat records" is deliberately untouched on both (UAC O2). The two status lists must
   stay in lockstep with the backend module.
8. **The document-number helper lives at `lib/document-number.ts`** with the render and
   strip pair together, mirroring the backend's N4/N7 discipline. **Superseded in S6b
   for the response gate only** (item 7 above): `lib/response-gate.ts` mirrored the
   backend's status lists, which is two sources for one rule. The backend now states
   the answer per record as `response_write_allowed` and the FE reads it. The document
   number helper is unaffected - it renders a suffix from a number the server already
   sent, it does not restate a server-side rule.

### As built (S6b - backend gap closure) - deltas from the sketch above

Four gaps between what the frontend was built against and what the backend served.

1. **`GET` / `PUT /api/v1/forms-management/revision-configs`** now exist
   (`app/api/v1/forms/revision_configs.py`, mounted at the forms router root so the
   path is NOT under `/forms`). Gated exactly like its neighbours in that router:
   `get_current_user_or_api_key` to read, `get_current_user` to write.
   * **GET returns one entry per portal submission type, always** - a type with no row
     is synthesised as `is_enabled: false`, which is what a missing row already
     resolves to (A3, fail closed). Without this the settings table renders four rows
     on a migrated database and none on a fresh one, and there would be no row to
     click into to turn a type on.
   * **PUT upserts by `source_entity_type`** and normalises `allowed_statuses`
     (trimmed, lowercased, de-duplicated) - the policy resolver lowercases before
     comparing, so storing anything else makes the settings table disagree with what
     it enforces. A type outside `SUPPORTED_TYPES` is refused.
2. **Snapshot attachments carry a `url`, resolved at read time.** `attachments_json`
   still stores no url (a stored signed url would be dead by the time history is
   read); `list_revisions` resolves one per entry through `storage_router` against the
   attachment row's own `storage_provider`, in one batched query for the whole
   lineage. Both the portal and the office route get it, because both read the same
   service. A hard-deleted attachment row degrades to `url: null` rather than taking
   the history down. This is what makes UAC I2a real: without it a file dropped by an
   earlier revision reached the preview modal with nothing to fetch.
3. **`restart_stage_label` on the policy block.** Derived from
   `restart_stage_code`, or from the first stage of the chain when NULL - the SAME
   selection `_restart_stage` uses for the actual restart (`_restart_stage_row`), so
   the dialog cannot promise a destination the revision does not go to. A display
   label, never a code. A stage code that names a POSITION rather than a team
   (`main`, which is where purchase_request / sponsorship_form / complaint start) is
   labelled from its `team_set_code` instead, so PR/SF read "Project Sales" rather
   than "Main". `null` when there is genuinely nothing to name, and only then does the
   generic sentence stand.
4. **`response_write_allowed` on the stock inquiry and complaint detail responses.**
   A python property on both models reading `response_gate.is_response_status_allowed`
   - the same module the write path raises from - so the flag and the rule cannot
   disagree. Declared on `StockInquiryResponse` / `ComplaintResponse` (a
   `response_model` drops what it does not name) and copied into both manual dict
   builders (`get_inquiry_for_response`, `_serialize_complaint`), because
   `column_attrs` skips properties. `lib/response-gate.ts` is deleted on the FE side in
   the same change.

---

## Migrations

Chain linearly off the **actual** current head at implementation time - run `alembic heads` against the DB, and re-verify `down_revision` after any merge (the dual-head-after-merge trap).

**Shipped in S1 as ONE revision**, `portal_rev_0001` (file
`alembic/versions/portal_rev_0001_portal_submission_revisions.py`), `down_revision = "311m_spec_tables_uuid_id"`.
All five items below are one atomic slice, so splitting them across five files would only add
dual-head risk with no rollback benefit. The revision id is deliberately non-numeric: the
numeric space up to `345` is already claimed by parallel worktrees (project-sales, scm-base,
after-sales-warranty), so a `32x`/`34x` id would collide at merge time.

1. `portal_form_revisions` table.
2. `portal_revision_configs` table + the four seed rows (idempotent `ON CONFLICT DO NOTHING`).
3. `system_settings`: `portal_revisions_enabled`, `portal_max_revisions`.
4. `stock_inquiries` **and `purchase_requests`**: `revision_no`, `last_revised_at`.
5. Tracker void columns - **confirmed required.** `conversation_sla_tracking` has no void
   concept today (`is_resolved` / `resolved_at` / `resolved_by` only; `resolution_reason`
   lives on the *takeover* table, not the tracker), so S1 adds `voided_at` +
   `void_reason varchar(50)` rather than overloading `is_resolved`.

No data backfill: revision 0 is written lazily on first revise (G2). Do **not** bulk-write rev 0 for every historical submission.

**Test substrate warning:** the four config rows are seeded by the migration body, so a suite
that builds its schema with `Base.metadata.create_all` gets the tables but **no rows**. Since a
missing config row means disabled (A3, fail closed), every revision test must seed its own
config row - do not assume the seed is present.

---

## Three-phase execution

### Phase 1 - Frontend prototype (no backend)

Mock fixtures only. Build and demo:

- Portal detail with Revise available / blocked-by-status / blocked-by-cap / type-disabled.
- Revise form pre-filled, reason validation, confirm dialog copy.
- Revision history: 1 entry (original only), 3 entries, reconstructed-original.
- Attachment preview in place for image / PDF / Excel / unpreviewable.
- Office banner + Revisions tab + empty state + list badge.

Verify through Playwright MCP by **clicking in from the sidebar**, never a deep URL. Screenshot the golden path and every edge state. No tests yet - the shape can still move.

### Phase 2 - Backend wiring + tests (test-first)

Order: migrations → models → `portal_revision_service` → `void_active_for_source` → routes → FE off mocks.

**pytest** (`sorento_crm_backend/tests/`) - every test seeds its own chain (policy → config → entity → tracker) with a marker prefix; **never** `LIMIT 1` off an existing table; Postgres only, never sqlite; cleanup deletes children first.

- Policy matrix: global off / per-type off / missing config row / status not in `allowed_statuses` / cap reached / `max_revisions = 0` / NULL inherits global / still a draft.
- Revise happy path: rev row written, counter incremented, status reset, tracker voided + event log, takeover voided, stage 1 respawned.
- Rev 0 backfill on a pre-feature row sets `is_reconstructed`.
- Reject → resubmit does **not** increment `revision_no`, **does** increment `version_no`, and **does** write a `kind="resubmission"` history row (C1/C4).
- `invalidated_on_revise` fields are cleared on the entity and readable in the revision row (FB2/FB3).
- Frozen fields: a revise payload attempting to change `salesperson_contact_id` leaves it untouched (AB2).
- Revision fence: an office respond / approve / reject carrying a stale `revision_no` returns 409 and writes nothing - including the "send from any status" chat path (CB1/CB2).
- Replaying a revise with the same `expected_revision_no` produces one revision, not two (C5).
- Attachment cap: three revisions each adding and removing a file do not exhaust `max_count_per_entity` (G7).
- Voided trackers are absent from open/breach dashboard aggregates and carry `void_reason` (F4a).
- A voided tracker with no assignee notifies the stage team (FT1).
- Response gating: a response write outside the allowed statuses is refused on **both** stock inquiry and complaint, while a plain chat send on a closed record still succeeds (O1/O2/O3).
- A suffixed number posted to the external create endpoint resubmits the existing rejected row rather than inserting a duplicate (N6), for stock inquiry and purchase request.
- The whole policy / revise / fence matrix runs for `purchase_request` and `sponsorship_form`, not just stock inquiry - including line-item snapshots and diffs.
- Complaint revise → 422 with the human sentence.
- Notification row written for the voided assignee; a raising notifier does **not** 500 the revise (F5).
- Event-log timestamps are not shifted -8h.
- Ownership: another contact's token cannot revise or read history.

**vitest** - Revise button states, reason validation, confirm copy, history empty/one/many, changes rendering, preview modal opens with the portal `fetchBytes`, banner renders only when `revision_no > 0`, list badge. (DataGrid rows do render under jsdom - mock `useListingColumnPreferences`.)

**playwright** (`e2e/`) - portal revise round trip: open submission → Revise → edit → reason → confirm → status reads "Revision 1 - Pending project sales approval" → history shows both versions → office detail shows banner + tab. Assert the `/api/v1/public/portal/.../revise` call in `browser_network_requests`.

### Phase 3 - Review

`/code-review` on the full diff, then `/simplify`, then PR. Checklist additions: Phase 1 screenshots in the PR body; all three suites green; the API contract in this file matches what shipped.

---

## Risks and traps

| Risk | Mitigation |
|---|---|
| Voiding a tracker leaks into **conversation** SLA rows | Every query goes through `conversation_tracking_scope()`. The two systems share `conversation_sla_tracking` and are discriminated only by `source_entity_type`. |
| Naive-UTC datetimes shifted -8h in event logs | `_to_aware_utc()` on `event_at` / `from_time` / `due_at` / `last_reminder_at` before building any event-log payload. |
| A failing notification 500s a revision that actually committed | Post-commit side effects are catch-and-warn (F5). The retry path would take the idempotent branch and never backfill. |
| Two field whitelists drift | `revise()` reuses `PortalService._apply_payload` + `_editable_fields`. Do not write a second one. |
| History previews 404 after an attachment delete | Portal attachment delete becomes unlink-if-referenced-by-a-revision (G6). |
| New `system_settings` columns invisible in the UI | Add to **both** manual builders - the GET dict AND `SystemSettingUpdate`. Inheriting the field is not enough. |
| A response field is silently dropped | The `revision` block must be declared on the response model, or FastAPI strips it. Assert the contract in a test. |
| Tests pass locally, fail in CI | CI's DB is empty. Seed the whole chain per test; verify against a fresh scratch DB before pushing. |
| Alembic dual head | Re-check `down_revision` against `alembic heads` **on the DB**, not the filesystem, after any merge. |
| Restarting the chain double-notifies stage 1 | Stage-1 spawn goes through the normal `emit_event` path exactly once; the voided-handler notify is a separate, distinct kind. |
| **Purchasing answers a version the revision already voided** | `procurement_service.py` explicitly permits a send **from any status** ("Chat can be sent from any status"), so voiding the tracker does not stop a stale tab. The revision fence (UAC CB1-CB3) is the actual guard: office writes carry `revision_no`, server 409s on mismatch. Verified gap, not hypothetical. |
| **A stale purchasing response reads as an answer to the new version** | Snapshot into `invalidated_json`, clear on the entity (UAC FB2). Adapter-declared field list. |
| **Double-tapped Revise burns two revisions** | `expected_revision_no` guard + `idempotency_middleware` (UAC C5). |
| **History silently skips the resubmit-after-rejection version** | `submit_draft` writes a `kind="resubmission"` row: `version_no` advances, `revision_no` does not (UAC C4). |
| **Portal preview 404s on files removed in an earlier revision** | Download route keyed on `attachment_id`, not `link_id` (UAC I2a). |
| **Cumulative attachments exhaust the per-entity cap across revisions** | `_check_quota` counts live links only, and G6 unlinks rather than deletes - so the cap tracks the current version. Cover with a test (UAC G7), do not leave to luck. |
| **A revision silently re-routes the inquiry to a different CS** | `salesperson_contact_id` frozen on revise (UAC AB2). |
| **Voided tracker with no assignee notifies nobody** | Fall back to the stage team via `resolve_team_with_tier_fallback` (UAC FT1). |
| Two knobs for the restart target drift apart | Restart stage declared once on the config; the adapter only maps stage → status (UAC J4). |
| **A suffixed number creates a duplicate record** | The external-API create path decides create-vs-resubmit by exact match on the document number. Fed `SI-26-0184-R2`, it misses the rejected row and inserts a new one - silent duplication, not a visible error. `strip_revision_suffix` at every inbound lookup (UAC N6). Grep `_number ==`; assume the known list is incomplete. |
| **Response gating breaks live behaviour** | Neither response path has a status guard today, so this is a new restriction, not a codification. Split send from response-write; ordinary chat must keep working on closed records (UAC O2/O3). Own tests, own release-note line. |
| **Three chains at once** | PR and SF ship enabled from day one. Each brings line items, its own approval chain, its own PDF, its own invalidated fields. The per-type differences live in adapters; the engine must stay type-agnostic or this triples the maintenance surface. |

---

## Sequencing (suggested slices)

| Slice | Content | Ships alone? |
|---|---|---|
| **S0** | Portal attachment preview via `AttachmentPreviewModal` + portal download route | **Yes** - independent of everything else, smallest win, do it first |
| **S1** | Migrations + models + `portal_revision_configs` seed | No |
| **S2** | `portal_revision_service`: policy + `record_initial` + `list_revisions` (read-only, no revise yet) | No |
| **S3** | `void_active_for_source` + revise transaction + routes + **dashboard aggregates excluding voided trackers** | No |
| **S3b** | **Revision fence** as one shared dependency across **every office write on every revisable form** (Q7), 409 on mismatch, FE passes what it was viewing. Includes tightening the "chat can be sent from any status" path per UAC open question 2. | With S3 - the feature is unsafe without it |
| **S3c** | Document-number suffix helper + every consumer including both PDF services (UAC N) | With S5 |
| **S4** | Portal FE: revise flow + history | With S3 |
| **S5** | Office FE: banner + Revisions tab + list badge | With S3 |
| **S6** | Settings UI for globals + per-type config | Yes |
| **S7** | Tests (land inside S2-S5, not after) | - |
| **S3d** | **Response gating** (UAC O): split send from response-write on stock inquiry and complaint, then gate the write by status | With S3b - shares the same endpoints |
| **S8** | ~~Scale to PR / SF later~~ - **superseded**. PR and SF adapters are in scope from day one (round 3), so they land inside S1-S5 rather than after them. Budget accordingly: three chains, three PDF exports, three test matrices. | Folded into S1-S5 |

S0 is genuinely independent and worth landing on its own while the rest is being reviewed.

---

## Merge-time hazard: known alembic fork (recorded 2026-08-10)

`311m_spec_tables_uuid_id` will have **two children** once both branches land:

- `312a_sla_form_actions` -> `312b_seed_form_action_task` - the user's uncommitted WIP on `feat/resolver-and-mode-match-honesty`
- `portal_rev_0001` - this branch

This branch is single-head and correct in isolation (`alembic heads` reports `portal_rev_0001` only, and `312a/312b` do not exist here). The fork appears only when both reach main.

**Resolution at merge, in order of preference:**
1. Whichever branch lands second re-chains its `down_revision` onto the other's head. Since the WIP is uncommitted, re-chaining `portal_rev_0001` is the cheaper move if that work merges first.
2. Failing that, `alembic merge` the two heads.

**Status (checked 2026-08-10, after the build):** nothing to fix today. `312a` / `312b` are **untracked** - they exist in no commit on any branch - so re-chaining `portal_rev_0001` onto them is impossible: a `down_revision` pointing at a revision git does not have breaks this branch's chain and CI immediately, to avoid a conflict that may never happen. This branch is verifiably single-headed (`alembic heads` -> `portal_rev_0001`, and `tests/test_alembic_revision_ids.py::test_migration_graph_has_a_single_head` passes).

**The fork cannot ship silently.** `test_migration_graph_has_a_single_head` already exists in this repo and asserts exactly this invariant, so whichever branch merges second fails CI on that test rather than failing a deploy. The merge-time action above is then a two-line `down_revision` edit, done with the failure in hand.

Do NOT discover this during a deploy - a dual head fails the deploy, and this repo has been bitten before.
