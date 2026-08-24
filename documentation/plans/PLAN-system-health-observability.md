# PLAN - System Health Observability (webhook smoke-test · audit coverage · daily digest)

**Status:** COMPLETE (2026-07-06), UNCOMMITTED. All 3 workstreams shipped. n8n workflows live (3 error branches + ping wf, published). BE + FE done. Tests: 41 pytest + 48 vitest green. Browser-verified live (dashboard drill-downs, audit date filter + derived descriptions + attribution, Settings→System Health tab, 0 console errors). Migrations 265 - 267. Post-review fixes applied: probe channel hidden from dashboard Integrations table; empty-roles warning softened to admin-fallback. Playwright persisted spec skipped (login creds unavailable) - MCP interactive verification done instead. Pending: user diff review + commit.
**Slug:** `system-health-observability`
**Author:** planning session 2026-07-06

## Goal

Make "is the system running properly today?" answerable without waiting for a user to
report a failure. Three linked workstreams:

1. **WS1 - n8n webhook smoke test + integration dashboard fixes.** Prove the attachment
   webhook round-trip daily (BE→n8n→MCP write→S3→callback) with zero new business data;
   fix the blind `integration_log_update` meta-log; add failed-row drill-down.
2. **WS2 - Audit coverage + attribution + drill-down.** Attribute portal/public-link
   writes to the contact (not "System"); audit currently-silent imports (DO/GRN, stock,
   order, packing list) at job granularity; human-readable descriptions for status
   changes; date-range filter + clickable tiles.
3. **WS3 - Proactive daily health digest + immediate anomaly alerts.** In-app + email to
   admins; three conditions alert off-cycle immediately, the rest roll into a daily digest.

## Locked decisions (user grill, 2026-07-06)

| Topic | Decision |
|-------|----------|
| Smoke-test depth | **REVISED → lightweight liveness ping** (not fixed-row upsert). User wants: (a) alert on real n8n failures (integration log body `status=failed`), (b) catch n8n death during quiet periods via a liveness ping. No full-flow simulation. |
| "System" actor label | **Contact-only fix** - resolve portal/public-link NULL-user writes to the contact name; the `system` principal (X-API-Key automation) stays "System". |
| Contact-attribution mechanism | Extend `audit_context` with optional `actor_contact_id`; portal/public routes set it from resolved contact; new nullable `audit_logs.contact_id`; display resolves `contact_id → name` before `user_id ? staff : "System"`. |
| Import audit granularity | **Coarse per-job** - one `log_audit()` event at each `process_*_import` boundary: `entity_type IMPORT 'label, N rows' uploader`. |
| Import scope | DO/GRN (PickingHeader), Stock/InboundShipment, Order import, Packing list/other, product/warehouse/SPO - i.e. all `process_*_import` fns. |
| Daily-health delivery | **Proactive** - in-app bell + email to superadmin/admin; recipient roles/tiers DB-configurable (system_settings pattern). |
| Immediate (off-cycle) alerts | n8n smoke-test fail · scheduled task failed/overdue · integration failure spike. (Audit volume floor = daily-only.) |

---

## WS1 - n8n webhook smoke test + integration dashboard fixes

### 1a. Kill the blind meta-log
`app/api/v1/integrations/logs.py:153-165` - the `/status` handler creates a second
`integration_log` row with hardcoded `status="success"` (channel `integration_log_update`).
It records only "n8n hit my callback endpoint," never the outcome, so the dashboard row is
always N/N/0-failed - structurally blind. The real outcome already lives on the original
`n8n` row (`update_integration_log(log_id, status=…)` at line 147).

**Change:** drop the meta-log create entirely (redundant + doubles log volume). If we want
to keep an audit of callback receipt, at minimum change `status="success"` → `status=update_data.status`
so a `failed` callback surfaces. **Recommend: drop.**

### 1b. Failed-row drill-down (dashboard)
`app/api/v1/system/health.py:173-200` `_integrations_health` produces the channel table.
FE: make each channel+failed cell link to the integration-log list filtered
`channel=<x> & status=failed & 24h`, showing `error_message` / `response_payload.error`.
Backend: confirm the integration-log list endpoint accepts `integration_channel`, `status`,
and a time-window filter; add if missing.

### 1c. n8n error-branch hardening - ✅ DONE (live, 2026-07-06)
The prod attachment workflow `system-upload-attachments` (n8n id `_NbFU3cCoEQwPSbvn14vV`)
already had 11 failed-callback nodes wired to most error outputs. Three gap nodes could fail
and produce NO explicit `status=failed` callback (workflow stopped silently → only caught by
the 10-min timeout). Fixed + published:
- `promotion-create` (terminal CRM insert) → `onError=continueErrorOutput` → new
  `integration-log-update-promotion-fail`.
- `download-packing-list` → `onError=continueErrorOutput` → new `integration-log-update-download-fail`.
- `analyze-packing-list` (Gemini) → error was dead-ending into `analyze_document_output_parser17`;
  re-pointed to new `integration-log-update-packinglist-ai-fail`.
All three POST the standard `{status:"failed", response_payload:{error:...}}` to the existing
`/status` endpoint. **Backstop unchanged:** `integration_log_retry` Pass 2
(`app/services/integration_service.py:830-862`) still marks any `sent` log >10min as `failed`
(`N8N_CALLBACK_TIMEOUT`) - covers total n8n death.

### 1d. Liveness ping - ✅ n8n side DONE (live, 2026-07-06)
New workflow `system-healthcheck-ping` (n8n id `FfmDkEWdt3Bian82`, personal project). Webhook
→ immediate `/status` success callback. No MCP, no S3, no data.
- **Webhook (prod):** `POST https://automate-sorento.foundryx.my/webhook/system-healthcheck-ping`
  body `{ "integration_log_id": "<id>" }` → echoes `{status:"success", response_payload:{healthcheck:true}}`.
- **Failure semantics:** if n8n is down, the CRM POST itself fails at send → the healthcheck
  log is marked `failed` immediately (send failure), NOT waiting 10 min. Near-instant liveness.

**BE side of 1c/1d - REMAINING (Phase 2):**
- **New scheduled task** `n8n_liveness_ping` (daily; register in `app/scheduler/task_scheduler.py`
  alongside `_handler_integration_log_retry`, seed via alembic like `072_seed_scheduled_tasks.py`).
  Creates a healthcheck integration_log (channel `n8n_healthcheck`, `business_table="__healthcheck__"`,
  sentinel `business_id`) and POSTs `{integration_log_id}` to the ping webhook URL above.
- **Sentinel hygiene:** exclude channel `n8n_healthcheck` / `business_table="__healthcheck__"`
  from real attachment listings + the upload-activity drawer.
- **Alerting** rolls into the WS3 watchdog: alert on ANY `n8n`-channel log → `status=failed`
  (covers explicit n8n error-callbacks AND the 10-min timeout) + `n8n_healthcheck` log failed/stale.

---

## WS2 - Audit coverage + attribution + drill-down

### 2a. Contact attribution ("System" → contact name)
Today: `user_id IS NULL` → display "System" (`app/api/v1/audit/audit_logs.py:56`). NULL comes
from (i) portal contact submissions (unauthenticated, audit context never set) and
(ii) public approval link (`app/api/v1/public/approval.py:61,68` explicit `user_id=None`).
The `system` principal (X-API-Key, no act-as) is a *separate* NULL source with no contact  - 
stays "System".

- **Migration:** add nullable `audit_logs.contact_id` (String/UUID) + index.
- **`app/audit_context.py`:** add optional `actor_contact_id` to the contextvar; getter/setter.
- **`app/services/audit_service.py`** `_session_before_flush` (~209-295): read
  `actor_contact_id` from context, write it onto auto-generated rows' `contact_id`.
- **Portal/public routes:** where a contact is resolved (PortalToken→contact / PR→contact),
  call `set_audit_context(..., actor_contact_id=<respond_contacts.id>)`. Public approval:
  pass the PR's contact into the explicit `log_audit(...)`.
- **Display** (`audit_logs.py:_user_display_names` + serializer): resolve
  `contact_id → RespondContact name` FIRST; else `user_id ? staff name : "System"`.
  - **Gotcha (CLAUDE.md):** `contact_id` stores `respond_contacts.id`, NOT `respond_io_id`.
    Resolve the display name via `RespondContact`.

### 2b. Coarse import auditing (currently 100% silent)
Confirmed silent: `PickingHeader` (DO/GRN) and `InboundShipment` (stock) lack `__audit_track__`;
`inventory_service` uses `bulk_insert_mappings` so even adding the flag would NOT fire the ORM
listener. Correct mechanism = **explicit `log_audit()` at the import-job boundary**, not the flag.

- **New helper** `log_import_audit(db, entity_type, label, row_count, user_id)` →
  writes `action="IMPORT"`, `description=f"{label}, {row_count} rows"`, `user_id`.
- **Hook at end of each** `process_*_import` in `app/tasks/import_tasks.py` (all take `user_id`):
  - `process_delivery_order_detail_import` (1921) → `entity_type="picking"` / DO
  - `process_grn_listing_import` (1446), `process_grn_lines_import` (1495) → `grn`
  - `process_stock_import` (82) → `inbound_shipment` / stock
  - `process_order_tracking_import` (249) → `order`
  - `process_product_import` (189) → `product` (safety net; per-row bulk may bypass ORM)
  - `process_spo_import` (826), `process_warehouse_import` (138), packing-list flow → as-is entity types
- One event per job, on success AND on partial/failed (record the counts). Worker task  - 
  **restart worker after editing `app/tasks/*`** (dev-session rule).

### 2c. Human-readable descriptions for status changes
Auto-tracked rows have `description=NULL`; the delta lives in `old_values`/`new_values` JSONB
but the list Description column shows "-". Derive a short description when a tracked status
field changes (e.g. `complaint: status pending → approved`). Keep it cheap - derive at
serialize time in the audit-list endpoint from the JSONB diff; no schema change.

### 2d. Drill-down + date filter
- **Add date-range filter** (`from`/`to` on `changed_at`) to `GET /api/v1/audit/`
  (`audit_logs.py:27-63`) - today it has entity/user/action but no date range, so
  "click the 07-02 bar" is impossible.
- **FE:** Audit Activity tile bars clickable → audit list scoped to that date; the
  Integrations failed cells → integration-log list (WS1b); "1 overdue" → scheduled-tasks
  list filtered overdue.

---

## WS3 - Daily health digest + immediate anomaly alerts

Reuse the health aggregation already in `app/api/v1/system/health.py` (email outbox, imports,
scheduled tasks, integrations, audit activity) as the data source - don't re-query.

### 3a. Digest (daily)
- **New scheduled task** `system_health_daily_digest` (daily, ~08:00 MYT). Builds the digest
  from the health summary + WS1 smoke-test result, sends **in-app notification + email** to
  superadmin/admin.
- **Recipients DB-configurable** - `system_settings` key (e.g. `health_digest_notify_roles`
  / tiers), Settings → System Health. Follow the `complaint_do_delivered_notify_tiers` pattern
  (DB → env → default). **Singleton gotcha:** add the new column to BOTH the GET dict builder
  AND `SystemSettingUpdate` (inheriting the field is not enough - CLAUDE.md).
- Digest content: n8n smoke result + last-OK age · integration failures by channel ·
  scheduled tasks (overdue / last-failed) · email queue failed · imports 24h · audit volume
  (with expected-floor note).

### 3b. Immediate alerts (off-cycle)
- **New scheduled task** `system_health_watchdog` (e.g. every 5-10 min). Evaluates only the
  three immediate conditions; alerts (in-app + email) with de-dup so it doesn't spam every tick:
  1. **n8n smoke-test fail** - latest `n8n_healthcheck` log `failed`, OR no healthcheck log
     in >25h (firing task itself broke).
  2. **Scheduled task failed/overdue** - any task `last_status="failed"` or overdue past its
     interval (mirrors the dashboard "1 overdue" / "last run failed").
  3. **Integration failure spike** - a channel's rolling failed count crosses a threshold
     (DB-configurable, default e.g. respond_io failed > N in window).
- **De-dup:** track last-alerted state per condition (system_settings or a small state table);
  re-alert only on transition to bad / still-bad after a cooldown, and on recovery.
- **Audit volume floor** = daily-digest only (weekend-aware), not immediate.

---

## Three-phase execution (per CLAUDE.md)

- **Phase 1 (FE prototype, mock data):** System Health tiles clickable → drill-down lists
  (audit by date, integration failures, overdue tasks); a "n8n webhook: last OK Xh ago" tile;
  digest/alert preview. Document the contract at the top of the health service file.
- **Phase 2 (BE wiring + tests):** migrations (`audit_logs.contact_id`, system_settings keys),
  audit_context extension, import-boundary audit helper + hooks, date-range filter,
  smoke-test task + n8n branch contract, digest + watchdog tasks. Tests land here  - 
  pytest (each new route/handler happy+auth+validation; watchdog condition logic),
  vitest (tiles/drill-down states), playwright (click bar → filtered list round-trip).
- **Phase 3 (`/code-review`):** convention + correctness pass before PR.

## Open verification items (resolve during Phase 2)
- Confirm portal-submission write path actually reaches an ORM flush (so `contact_id` from
  context lands) vs going through a service that commits without the tracked model dirty.
- Enumerate the exact packing-list import fn + entity_type for WS2b.
- Confirm the integration-log list endpoint's existing filter params (WS1b) before adding.
- Pick the immediate-alert de-dup store (system_settings JSON vs a dedicated `health_alert_state`
  table) - lean small table if we want per-condition timestamps.

## Non-goals
- Per-row import auditing (noise) - coarse only.
- Auditing chat/respond/stock-ledger movements.
- Testing real attachment linkage logic in the smoke test (fixed sentinel row only).
- Multi-tenant recipient routing (multi-tenant is still stubbed).
