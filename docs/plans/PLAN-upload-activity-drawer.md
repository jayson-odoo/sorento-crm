# PLAN — Upload Activity Drawer

**Date:** 2026-06-02
**Owner:** TBD
**Status:** Phase 1 ✅ verified by user · Phase 2 ✅ BE wired + 67 tests green · Phase 3 (code review) pending

## 1. Problem

Today three pain points for attachment upload visibility:

1. **No feedback for single + multi-file uploads.** `POST /api/v1/resources/attachments` fires the n8n webhook in a background thread. After modal closes, user has zero indication that integration linking is in flight, succeeded, or failed.
2. **`LatestImportStatusPanel` rejected.** Current bulk-ZIP progress bar:
   - Steals top-of-grid space.
   - Minimised X-button hides into bottom-right, colliding with the AI Assistant FAB.
   - Tracks only the RQ extraction job (`import_jobs`) — has no view into the per-file n8n webhook outcomes.
3. **`AttachmentDetailModal` has no integration log surface.** User has no way to see "why was this attachment linked to product X?" or "why isn't it linked?" without leaving the modal for `/integration-management/integration-logs`. The raw log there is technical, not user-friendly.

## 2. Solution overview

One unified **Upload Activity drawer**:

- Top-nav icon next to the notification bell. Badge counts only `in-flight` + `needs-action` items.
- Click icon → right-side drawer slides out. Closed by default — never steals layout space.
- Drawer groups all upload events into **sessions**:
  - Single upload = 1-file session
  - Multi-file modal = group by `upload_batch_id`
  - Bulk ZIP = group by `import_job_id` (stored on each attachment's `upload_batch_id`)
- Each session expandable, showing per-file integration status with **friendly translation** of `integration_log.response_payload` (the v1 schema below). Raw technical details collapsed behind a "View raw log ↗" link.
- `AttachmentDetailModal` gains a status chip in the header + a new **Integration card** below Linkages with the same friendly summary.

Removes `LatestImportStatusPanel` entirely; new drawer covers both the extraction phase and the n8n phase for bulk ZIPs in one session row.

## 3. Locked decisions

| # | Decision |
|---|----------|
| 1 | **UI placement** — top-nav icon next to bell; right-side drawer; no floating minimised state. |
| 2 | **Grouping** — session-grouped, expandable: single upload \| multi-file batch (`upload_batch_id`) \| bulk ZIP (`import_job_id`). |
| 3 | **Feed endpoint** — new `GET /api/v1/resources/upload-activity?scope=me&since=ts`; BE joins `import_jobs` + `integration_logs` grouped by `upload_batch_id`. |
| 3b | **Scope** — `created_by = current_user.id`. Admins use existing `/integration-management/integration-logs`. |
| 3c | **Polling** — React Query 5s while any session in-flight; stop when all terminal. Drawer-open + new-upload force immediate refetch. |
| 4 | **Callback schema v1** — Pydantic-validated, see §5. |
| 5 | **Drawer content** — rolling 7-day window. Badge counts in-flight + needs-action only. |
| 6 | **Detail modal** — header status chip + new "Integration" card under Linkages. |
| 7 | **Ambiguous outcome dropped** — existing `/external/attachments/link-products` already auto-links every ILIKE match; user removes unwanted via Linkages tab. |
| 8 | **Resubmit** — header `Resubmit` button stays as today (calls `POST /attachments/{id}/resubmit`, refreshes signed URL, force_resend). No duplicate in Integration card. |
| 9 | **Old panel** — delete `LatestImportStatusPanel` mount from `AttachmentsInFolderPanel`. |
| 10 | **Modal submit** — modal closes immediately, drawer auto-opens, force-refetch, optimistic entry shown. |
| 11 | **Optimistic state** — FE upload manager injects placeholder session on submit; POSTs reconcile each entry; force-refetch on all-POSTs-done. |
| 12 | **Stuck timeout** — extend existing 2-min sweeper to include `sent` status with 10-min cutoff → mark `failed` with `error_code='N8N_CALLBACK_TIMEOUT'`. Configurable via setting. |
| 13 | **Translation** — friendly summary in drawer + card; error_code → human map; raw log behind "View raw log ↗". |
| 14 | **Surface scope** — all attachment uploads (Files, Promotion, Product, Forms, Packing List, Bulk ZIP). Drawer = integration-centric, not page-centric. |
| 15 | **POST failure** — optimistic entry flips to "❌ Upload failed: \<reason\>" + Retry button (uses cached File blob). Error toast also fires. |
| 16 | **ZIP expand** — counts dashboard + "Needs attention" default subtab (failed + unlinked only); "All files" tab lazy-loaded with virtual scroll. |
| 17 | **Row click** — file row → `AttachmentDetailModal` opens at attachment, Integration card scrolled in; session header → expand/collapse. Bulk ZIP session has secondary "Open in Files" link. |

## 4. Backend implementation

### 4.1 Schema migration

```
alembic revision -m "bulk_import_sets_upload_batch_id_to_job_id"
```

No new columns. Backfill optional (legacy ZIP imports have no batch tag — they appear in drawer as orphaned single sessions).

### 4.2 `app/tasks/import_tasks.py`

For each created attachment inside `process_attachment_bulk_import()`:

```python
attachment = service.create_attachment(
    AttachmentCreate(
        ...
        upload_batch_id=str(import_job.job_id),  # NEW
    ),
    current_user_id=user_id,
)
```

Lets `/upload-activity` group bulk ZIP files by the same `upload_batch_id` mechanism as multi-file modal uploads.

### 4.3 New endpoint `app/api/v1/resources/upload_activity.py`

```
GET /api/v1/resources/upload-activity
Query: scope=me (only value for now), since=<iso8601 ts, default now-7d>, limit=<int, default 50>
Response: { sessions: UploadActivitySession[] }
```

`UploadActivitySession` shape:

```python
class UploadActivitySession(BaseModel):
    session_id: str               # upload_batch_id or import_job.job_id
    session_type: Literal["single", "multi", "bulk_zip"]
    title: str                    # filename | "5 files" | "brand_2026.zip"
    started_at: datetime
    finished_at: datetime | None
    status: Literal["uploading", "processing", "linked", "partial", "failed"]
    aggregate: SessionAggregate   # counts: total, linked, unlinked, failed, in_flight
    files: list[UploadActivityFile]
    import_job_id: str | None     # bulk ZIP only
    needs_action: bool            # any file in failed/unlinked-with-no-match
```

`UploadActivityFile`:

```python
class UploadActivityFile(BaseModel):
    attachment_id: str | None     # null if POST still in-flight
    filename: str
    status: Literal["uploading", "processing", "linked", "unlinked", "failed"]
    summary: str                  # friendly one-liner
    linked: list[LinkedEntity]
    error_code: str | None
    error_message: str | None
    integration_log_id: str | None
    last_updated_at: datetime
```

**Query strategy:**
- Pull `import_jobs` where `job_type='attachment_bulk_import'` AND `user_id = current_user.id` AND `created_at >= since`.
- Pull `integration_logs` where `business_table='attachments'` AND `business_id IN (SELECT id FROM attachments WHERE created_by=$user AND created_at >= since)`.
- Group integration_logs by `attachments.upload_batch_id` (LEFT JOIN attachments).
- Stitch into sessions: bulk-zip session if upload_batch_id matches an import_job.job_id, otherwise multi/single by file count.

### 4.4 n8n callback schema validator

Update `IntegrationLogUpdateRequest` (or wrap in a new validator chained from `PUT /integrations/logs/{id}`) to require for n8n channel:

```python
class N8nCallbackPayloadV1(BaseModel):
    schema_version: Literal[1]
    outcome: Literal["linked", "unlinked", "failed", "partial"]
    summary: str = Field(..., max_length=500)
    linked: list[LinkedEntityV1] = []
    unlinked_reasons: list[UnlinkedReasonV1] = []
    errors: list[ErrorEntryV1] = []

class LinkedEntityV1(BaseModel):
    entity_type: str
    entity_id: str
    display_name: str
    matched_by: str               # "filename_token:CBMC5570" etc.

class UnlinkedReasonV1(BaseModel):
    reason: str

class ErrorEntryV1(BaseModel):
    code: str
    message: str
    retryable: bool = False
```

Accept legacy free-form during a deprecation window (log a warning, render as-is). Reject malformed v1 with 422.

### 4.5 Sweeper extension

`app/services/integration_service.py::process_pending_logs`:

```python
# Existing: pull status in ("pending", "processing") with next_retry_at <= now
# ADD: pull status == "sent" with processed_at <= now - timedelta(minutes=N8N_CALLBACK_TIMEOUT_MINUTES)
# Mark each as failed with error_code='N8N_CALLBACK_TIMEOUT', error_message='n8n did not respond within X minutes'
```

New setting `n8n_callback_timeout_minutes` (default 10) read from `SystemSetting` (fall back to env / constant).

Idempotency: when n8n eventually calls back PUT after timeout, accept the update — the row already says `failed`, so the callback either confirms or upgrades to `success`. Add an audit entry on out-of-order update.

### 4.6 Attachment endpoint changes

None. Existing webhook trigger code (`attachment_webhook_helper.create_and_send_webhook`) already creates `integration_log` rows correctly. Only bulk-import path needs the `upload_batch_id` set (§4.2).

## 5. Frontend implementation

### 5.1 Files to create

```
sorento_crm_frontend/
  components/upload-activity/
    UploadActivityIcon.tsx           # top-nav badge button
    UploadActivityDrawer.tsx         # right-side drawer container
    UploadSessionRow.tsx             # collapsible session row
    UploadFileRow.tsx                # per-file leaf
    EmptyState.tsx
    translation.ts                   # error_code → friendly text map
  hooks/upload-activity/
    useUploadActivity.ts             # React Query polling hook
    useUploadManager.ts              # Zustand store for optimistic in-flight POSTs + File blob refs for retry
  services/uploadActivityService.ts  # API client
```

### 5.2 Files to modify

| File | Change |
|------|--------|
| `app/(protected)/layout.tsx` (or wherever top nav lives) | Mount `<UploadActivityIcon />` next to notification bell |
| `app/(protected)/resource-management/attachment-directories/components/AttachmentsInFolderPanel.tsx` | **Remove** `LatestImportStatusPanel` import + mount |
| `app/(protected)/resource-management/attachments/components/AttachmentUploadDialog.tsx` | On submit: generate `upload_batch_id`, push optimistic session via `useUploadManager`, close modal immediately, fire POSTs in background, reconcile each on response |
| `app/(protected)/resource-management/attachments/components/AttachmentDetailModal.tsx` | Add header status chip; render new `<IntegrationCard />` below Linkages |
| `components/import-jobs/LatestImportStatusPanel.tsx` | **Delete** (or keep for non-attachment job types if any reference it — verify) |

### 5.3 Upload manager (Zustand) — outline

```typescript
type OptimisticFile = {
  client_id: string;      // FE-generated UUID per file
  attachment_id?: string; // filled when POST returns
  filename: string;
  status: "queued" | "uploading" | "uploaded" | "post_failed";
  file_blob?: File;       // cached for retry
  error?: string;
};

type OptimisticSession = {
  session_id: string;     // upload_batch_id
  session_type: "single" | "multi";
  files: OptimisticFile[];
};

interface UploadManagerState {
  optimisticSessions: Record<string, OptimisticSession>;
  pushSession: (session: OptimisticSession) => void;
  markFilePosted: (sessionId: string, clientId: string, attachmentId: string) => void;
  markFileFailed: (sessionId: string, clientId: string, error: string) => void;
  retryFile: (sessionId: string, clientId: string) => Promise<void>;
  clearReconciledSession: (sessionId: string) => void;  // called once BE has all attachments
}
```

`useUploadActivity` hook merges this store with the BE feed: for each session in BE response, drop the optimistic version. Sessions in optimistic but not yet in BE keep showing.

### 5.4 Translation map

```typescript
// translation.ts
export const ERROR_CODE_FRIENDLY: Record<string, string> = {
  N8N_CALLBACK_TIMEOUT: "Integration server didn't respond in 10 minutes",
  MAX_RETRIES_EXCEEDED: "Tried 3 times, all failed",
  HTTP_5XX: "Integration server error",
  HTTP_4XX: "Bad request to integration server",
  WEBHOOK_DISABLED: "Integration webhook is not configured",
};

export function summarise(file: UploadActivityFile): string {
  if (file.status === "linked") {
    const names = file.linked.map(l => l.display_name).join(", ");
    return `Linked to ${file.linked.length} ${file.linked[0]?.entity_type ?? "item"}${file.linked.length > 1 ? "s" : ""}: ${names}`;
  }
  if (file.status === "unlinked") return file.summary || "No matching record found";
  if (file.status === "failed") return ERROR_CODE_FRIENDLY[file.error_code ?? ""] ?? file.error_message ?? "Integration failed";
  if (file.status === "processing") return "Linking…";
  if (file.status === "uploading") return "Uploading…";
  return file.summary;
}
```

### 5.5 Drawer freshness invariants

Per `feedback_drawer_no_stale_data` memory:

- On drawer open: `queryClient.invalidateQueries(['upload-activity']); refetch();`
- Poll cadence: `refetchInterval: anyInFlight ? 5000 : false`
- New upload submit (modal): explicit `refetch()` after pushing optimistic entries
- Stale cap (BE-side): sweeper at 10 min eliminates infinite "Processing…" states

### 5.6 ZIP expand UX

```
[▼] Bulk ZIP — brand_2026.zip                     3 min ago
    42 / 50 files extracted · 38 linked · 12 processing · 0 failed
    Tabs: [Needs attention (0)] [All files (50)]
    ─ Needs attention (default) ─
       (empty state: "All files linked successfully")
    ─ All files (lazy-loaded with react-window) ─
       ✅ CBFAL5570_1.jpg  Linked to product CBMC5570
       ⏳ CBFAL5570_2.jpg  Linking…
       ...
    [Open in Files ↗]
```

## 6. n8n flow update (out-of-repo, but blocking)

Existing n8n flow that POSTs back to `PUT /api/v1/integrations/logs/{id}` must emit v1 schema (§4.4). Until updated:

- BE accepts legacy free-form with a deprecation warning logged.
- FE translation falls back to raw `error_message` / "Linking…" when v1 fields absent.

Coordinate cutover: update n8n flow → deploy BE validator in non-strict mode → verify zero legacy callbacks for 1 week → flip BE to strict (422 on malformed).

## 7. Rollout — three-phase methodology

Per `CLAUDE.md → Development methodology`. Phase 1 (FE prototype with mocks) ships and gets sign-off BEFORE Phase 2 (BE wiring + tests).

### Phase 1 — Frontend prototype (mocks only, no BE work)

**Goal:** click-through drawer + integration card with synthetic data covering every state. Validate UX before building backend.

- Build all FE components in §5.1 against a hard-coded mock store. Mock store seeds:
  - In-flight single upload session
  - Multi-file (5 files) with mixed outcomes: 3 linked, 1 unlinked, 1 failed
  - Bulk ZIP session with 50 files (3 in needs-attention)
  - Empty state
  - Post-failure entry with Retry button
- Stub `useUploadActivity` hook to return the mock store. Real `/upload-activity` endpoint not built yet.
- Stub `useUploadManager` Zustand store with full optimistic flow (push → mark posted → mark failed → retry), wire to `AttachmentUploadDialog`.
- Modify `AttachmentDetailModal` with header chip + Integration card rendering from mock log data.
- Remove `LatestImportStatusPanel` mount.
- Mount `UploadActivityIcon` in top nav next to bell.
- Verify via Playwright MCP: sidebar → Files → upload single → drawer opens. Click multi-file mock → 5 children render. Click bulk-ZIP mock → counts dashboard + "Needs attention" tab. Trigger mock POST failure → entry flips + retry. Open detail modal → Integration card scrolled in.
- Screenshot every state for PR description.
- **Document API contract** at top of `services/uploadActivityService.ts`: GET response shape, expected status enums, callback schema v1 fields. This is the binding contract for Phase 2.
- **No tests written yet.** UX may shift after stakeholder review of prototype.

**Exit criteria:** prototype branch reviewed; contract doc agreed; sign-off to proceed.

### Phase 2 — Backend wiring + tests

**Goal:** real `/upload-activity` endpoint, sweeper extension, n8n v1 validator, FE off-mocks, full test coverage.

Backend:
- §4.2 `import_tasks.py` sets `upload_batch_id = job_id`.
- §4.3 new `GET /api/v1/resources/upload-activity` endpoint matching Phase 1 contract.
- §4.4 n8n callback v1 Pydantic validator (non-strict at first).
- §4.5 sweeper extension for `sent` timeout.

Frontend:
- Replace mock `useUploadActivity` with real React Query hook hitting the endpoint.
- Replace mock POST in upload manager with real `api-client` calls.
- Delete `__mocks__/upload-activity.ts` (or wherever Phase 1 seeded).
- Verify drawer freshness invariants (force refetch on open, 5s polling while in-flight, stop when terminal).

Tests (all three suites land in this phase, none deferred):
- **Vitest** (FE):
  - `UploadActivityDrawer.test.tsx` — renders empty, loading, sessions list, badge count.
  - `UploadSessionRow.test.tsx` — expand/collapse, aggregate counts, click leaf opens modal.
  - `UploadFileRow.test.tsx` — every status renders friendly summary correctly.
  - `IntegrationCard.test.tsx` — chip + summary + raw-log link.
  - `useUploadManager.test.ts` — push → mark posted → mark failed → retry flow.
  - `translation.test.ts` — error_code map covers every known code.
- **Playwright spec** (`e2e/upload-activity-drawer.spec.ts`):
  - Sidebar → Files → upload real fixture (`e2e/fixtures/CBFAL5570_1.jpg`) → drawer opens with in-flight session → BE endpoint hit → wait for n8n callback (mock or real depending on env) → drawer shows "Linked".
  - Multi-file modal with 3 fixtures → session has 3 children → all reconcile.
  - `browser_network_requests` asserts `GET /api/v1/resources/upload-activity` polled at 5s cadence while in-flight.
- **pytest** (BE):
  - `tests/test_upload_activity_endpoint.py` — happy path returns sessions grouped correctly; auth denied for other users; pagination via `since`.
  - `tests/test_integration_log_sweeper.py` — seed `sent` row aged 11 min → sweep → marked failed with `N8N_CALLBACK_TIMEOUT`.
  - `tests/test_n8n_callback_v1.py` — valid v1 payload accepted; malformed rejected with warning (non-strict mode).
  - `tests/test_bulk_import_batch_id.py` — bulk ZIP run sets `upload_batch_id = job_id` on every attachment.

Re-verify with Playwright MCP against live stack. All three test suites green in CI.

**Exit criteria:** BE merged, FE off-mocks, all tests green.

### Phase 3 — Code review

- Run `/code-review` (or `/code-review ultra` if diff > 1000 LOC) on the Phase 1 + Phase 2 combined branch.
- Address findings via `/code-review --fix` / `/simplify`.
- Open human PR with: Phase 1 screenshots, Phase 2 test summary, contract doc, sweeper migration note for ops.
- Reviewer checklist:
  - `docs/PR-CHECKLIST.md` standard items
  - Phase 1 screenshots present?
  - Vitest + Playwright + pytest all added?
  - Contract doc matches shipped endpoint?
  - `LatestImportStatusPanel` mount actually removed (not just FE component left orphaned)?
  - n8n v1 schema doc updated for the team running n8n flows?

### Out-of-repo blocker (parallel to Phase 2)

n8n flow update to emit v1 callback schema (§6). Schedule with n8n owners so it lands during Phase 2 test window. Until n8n updated, BE validator stays non-strict; flip to strict after one week of clean v1 callbacks.

## 8. Out of scope / deferred

- Admin RBAC override (drawer scope=tenant) — defer until support team requests
- Mobile drawer width / responsive design — verify but don't optimise
- AI Assistant FAB z-index when drawer open — drawer covers FAB, fine; revisit if FAB needs to stay tappable
- In-app notification table integration — drawer is the UI channel, `attachment_notification_helper` keeps coalescing emails separately
- AI assistant chat tool "show my failed uploads" — nice future addition, separate skill

## 9. Open questions

None blocking. All branches resolved in grilling session 2026-06-02.

## 10. References

- Memory: `feedback_drawer_no_stale_data.md` — freshness invariants
- Memory: `feedback_attachment_replace_uniform.md` — replace semantics across 4 entity types
- Memory: `project_files_page_component.md` — `AttachmentsInFolderPanel` is the host
- Existing: `sorento_crm_backend/app/services/attachment_webhook_helper.py:40-107` — webhook trigger (unchanged)
- Existing: `sorento_crm_backend/app/services/integration_service.py:370-505` — webhook send + sweeper (extend)
- Existing: `sorento_crm_backend/app/api/v1/integrations/logs.py:85-118` — n8n callback endpoint (add validator)
- Existing: `sorento_crm_frontend/app/(protected)/resource-management/attachments/components/AttachmentDetailModal.tsx:962-970` — header Resubmit button (keep)
- Existing: `sorento_crm_frontend/components/import-jobs/LatestImportStatusPanel.tsx` — to delete
