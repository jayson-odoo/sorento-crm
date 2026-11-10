# SCOUT: every history we keep, every screen that shows it (STANDARD-HISTORY, Part B step 1)

Scouted at `4f68e602` (main, 10 Nov 2026). Read-only; no code. `BE/` = `sorento_crm_backend/`,
`FE/` = `sorento_crm_frontend/`. Plan: `PLAN-standard-history-10nov.md`.

## 1. Sources we keep

### audit_logs (the backbone, `PLAN-audit-standard-26sep.md`)

- Model `BE/app/models/audit.py:32-105`; append-only (triggers block UPDATE / DELETE / TRUNCATE,
  :158-206); failed writes land in `audit_trail_gaps` (:209-236).
- Columns: `entity_type`, `entity_id`, `action`, `changed_at`, `old_values` / `new_values`
  (JSONB), `description`, `event`, `reason`, `source`, `trace_id`, `correlation_id`,
  `root_entity_type` / `root_entity_id`, actor: `actor_type`, `user_id`, `real_user_id`
  (impersonation), `contact_id`, `integration_id`, `auth_method`, `session_id`, `job_id`, ip,
  user agent; `company_id` of the changed record.
- Automatic capture: `register_audit_listeners` (`BE/app/services/audit_service.py:1313`, called
  at `BE/app/main.py:353`). Default ON for every model; 103 models opt out with `__audit_skip__`;
  21 set `__audit_parent__` so child rows roll up (`audit_service.py:93-122`).
- Explicit writes: `log_audit` (`audit_service.py:246`), `record` (:399), `@audit_event` (:434),
  `log_import_audit` (:498). About 60 explicit entity types (complaint, stock_inquiry, customer,
  purchase_request, product, order_line, ticket, project_order_inquiry_rows,
  project_so_supply_decisions, price_tag_request, impersonation_session, automation_run, ...).
- "On behalf of": `BE/app/services/audit_actor_label.py:11-13, 36-51` ("<admin> on behalf of
  <target>"); sessions in `BE/app/models/impersonation.py:18, 41`.
- **The OI case.** Order inquiry rows are `__audit_skip__` (`BE/app/models/project_so.py:1003`),
  so the explicit batch rows are their only trail: Confirm
  `BE/app/services/project_order_inquiry_service.py:9678-9688`, Unconfirm `:9849-9866`. Each is ONE
  row, `entity_id = first row id`, `new_values.row_ids = every row`, `old_values.rows = prior
  states`, no `root_entity_*` (defaults to the row itself, `audit_service.py:334-335`). A reader
  filtering by `entity_id` sees the press on 1 row of 9; nothing ties it to the OI.

### Domain trails (not in audit_logs)

| Trail | Table / model | Written by | Read by |
|---|---|---|---|
| Supply decisions (Decisions tab) | `so_supply_decisions` `project_so.py:1631`, drafts :1756, `order_inquiry_raises` :971 | decision service | `GET /sales-order-lines/{id}/decision-trail` `BE/app/api/v1/projects/order_inquiries.py:1626-1647`, `BE/app/services/decision_trail_service.py:126-300` |
| Reserve events (Reserve tab) | `order_inquiry_reserve_events` `project_so.py:1536` | `order_inquiry_reserve_service.py:1635` | `order_inquiries.py:1602-1623` |
| OI rows Now / Before (Rows tab) | cancelled `order_inquiry_rows` + `previous_qty`, `previous_delivery_date`, `ack_*`, `rejected_*` (`project_so.py:1066-1108`) | OI services | `GET /order-inquiries?include_history=true` (`order_inquiries.py:290, 448-475`), folded in `FE/.../_shared/lib/orderInquiryLineFold.ts:341-369` |
| Planning changes | `planning_change_batches` / `_rows` `BE/app/models/planning_change.py:94, 134` | planning | `BE/app/services/planning_history_service.py:209, 332` |
| Pending actions (deferred delete / unlink) | `sla_form_actions` `BE/app/models/sla.py:431`, registry `BE/app/services/record_actions.py` | `form_action_service.py:117-160` also writes an audit row on the source record | `BE/app/api/v1/system/pending_actions.py:789, 881, 908` |
| Emails | `email_outbox` `BE/app/models/email_outbox.py:18` | outbox | `BE/app/api/v1/system/email_outbox.py:64` |
| Notifications | `notifications` / `notification_deliveries` `BE/app/models/notification.py:11, 47` | notifier | planning history only (`planning_history_service.py:434-446`) |
| Integration / Respond.io | `integration_log` `BE/app/models/integration.py:115`, `chat_histories` `BE/app/models/chat_history.py:22` | integrations | `BE/app/api/v1/integrations/logs.py:65`, `system/respond_outbox.py:89`, `system/chat_history.py:42` |
| Automation / scheduled runs | `automation_runs` `BE/app/models/automation.py:84`, `scheduled_task_runs` `scheduled_task.py:38` | runners | `system/automation.py:168`, `system/scheduled_tasks.py:167` |
| Imports | `import_logs` `BE/app/models/import_log.py:10` | importers | `system/import_logs.py:16` |
| Downloads | `user_downloads` `BE/app/models/download.py:27` | download service | `downloads/downloads.py:27` (own rows) |
| Logins | `user_sessions` `BE/app/models/user_session.py:28` | auth | `auth.py:473` (own sessions) |
| Activities | `activity_events` `BE/app/models/activities.py:26` | activities | `activities/activities.py:36` |
| Versions | `po_versions`, `delivery_schedule_versions`, `quotation_versions`, `certificate_revisions`, `portal_form_revisions` (`portal.py:76`), `tag_template_version`, `workflow_form_versions`, `page_version`, `ai_prompt_versions` | each domain | each domain |

## 2. Screens that show history today

| Screen | File | Reads | Filters | Gate |
|---|---|---|---|---|
| System > Audit Logs | `FE/app/(protected)/system-management/audit-logs/components/AuditLogsList.tsx` | `GET /audit/logs/` | entity, action, user, date, search (:355-425) | superadmin |
| System > Activity | `FE/app/(protected)/system-management/activity/components/ActivityTimeline.tsx` | `GET /audit/activity` (`BE/app/api/v1/audit/activity.py:21`) | entity, action, user, dates, trace | superadmin / `require_audit_admin` |
| Per-record Audit Trail | `FE/components/audit/AuditTrail.tsx:81` | `GET /audit/logs?include_children=true` | none | record view permission, `_PER_RECORD_VIEW_PERMISSION` `BE/app/api/v1/audit/audit_logs.py:27-41` |
| ... used on | spec registry `SpecKeyRecordDetail.tsx:250`, PO `PurchaseOrderDetail.tsx:1415`, complaint `ComplaintDetail.tsx:1405`, stock inquiry `StockInquiryDetail.tsx:1304`, PR `PurchaseRequestDetail.tsx:1624`, sample request `SampleRequestDetail.tsx:880`, product `ProductDetail.tsx:669`, NPA `NewProductApplicationDetail.tsx:658` | | | |
| OI line History | `FE/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryLineHistoryDialog.tsx` | decision trail, reserve history, `include_history` | none | OI view / acknowledge / reserve |
| SO History drawer | `FE/app/(protected)/project-sales/fulfilment-planning/components/PlanningHistorySheet.tsx:322-592` | `GET /fulfilment-planning/history` (`fulfilment_planning.py:716-739`) | SO, Product, Line, Event, User, dates (:509-551) | planning admins only (:637) |
| OI status pill tooltip | `FE/.../_shared/components/OrderInquiryLineStatusPill.tsx:81` (`orderInquiryAck.ts:86-92`) | row fields | none | none |
| Download history | `FE/components/my-downloads/EntityDownloadsButton.tsx:61` | `/downloads` | none | own |
| Contact chat | `FE/app/(protected)/user-management/contacts/[id]/components/ContactChatHistorySection.tsx` | `/chat-history/thread` | none | `system.chat_history.view` |
| Others | `ContainerRequestHistory.tsx`, `CostPriceHistoryTab.tsx`, `ListPriceHistoryDialog.tsx`, `ProductPurchaseHistoryTab.tsx`, `CertificateRevisionTimeline.tsx`, dealer-kit `VersionHistory.tsx`, `TaskHistoryDialog.tsx`, `PackingListTimelineTab.tsx`, `SoLineHistoryBody.tsx` | own routes | mostly none | own |

**No history screen at all:** OI header (Confirm / Unconfirm / Link / Reject presses), sales
order header outside the planning-admin drawer, contacts and dealer access (only System > Audit
Logs, superadmin), customers, price tags, users, logins (own sessions only).

## 3. Building blocks that exist

- Drawer: `FE/components/ui/sheet.tsx` (as `PlanningHistorySheet.tsx`).
- Timeline: `FE/components/common/EventTimeline.tsx` (`TimelineEvent` :28, `EventTimeline` :82).
- Audit rendering: `FE/components/audit/AuditTrail.tsx`, `FE/lib/audit-fields.ts` (field labels,
  `old -> new`, bookkeeping skip list, resubmit headings), `FE/lib/audit-actor.ts` (`actorDisplay`,
  on behalf of).
- Filters: `FE/components/common/SearchableMultiSelect.tsx`, `FE/components/ui/date-range-picker.tsx`,
  `FE/components/common/ListSearchInput.tsx`.
- Row lists: `FE/components/ui/data-grid*.tsx`.
- Pills: `FE/components/ui/badge.tsx`, `FE/components/common/StatusPill.tsx`.
- Dates: `FE/lib/helpers.ts` `formatDateInMalaysia` :325 (dd/mm/yyyy), `formatDateTimeInMalaysia` :446.

## 4. Permission and company scoping today

- `_authorize_log_read` (`BE/app/api/v1/audit/audit_logs.py:68-90`): admin, or the record type's
  view permission + an `entity_id`; non-admins need an active company; IP hidden for non-admins
  (:362-365).
- `list_audit_logs` (`audit_service.py:543-611`) filters through `admin_listing_company_filter`
  (`BE/app/services/company_scope.py:250`), which is NOT fail-closed (company rows + NULL-company
  rows). `_authorize_po_history` (`audit_logs.py:101-118`) adds a check on the record's own
  company: the pattern to copy.
- #2295 redaction: `redact_foreign_icon_ids` (`BE/app/services/dealer_kit/asset_service.py:699-724`)
  strips other companies' ids from the returned copy, applied at `audit_logs.py:329-332` and
  `activity_service.py:449-452`.
