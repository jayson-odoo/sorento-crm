Summary (15 lines):
1. **PR lifecycle.** The PR uses two columns: `status` (draft → submitted/resubmitted → approved/rejected → processed_by_cs/closed, plus voided) and `approval_status` (empty → pending → approved/rejected, plus voided). Every move is a `PurchaseRequestService` method that commits, then sends best-effort notifications, then calls `emit_form_event`.
2. **SLA event names:** `submit`, `send_for_approval`, `reject_submitted`, `approved` / `approval_rejected`, `resolved`, `voided`. A revise voids the open stages and re-emits the restart stage's start event.
3. **Deferred actions:** `pr.send_for_approval`, `pr.reject_submitted`, `pr.approval_decision` and `pr.finalize` are routed through `dispatch_or_defer`. `pr.void` is registered, but the void route never dispatches it; it calls `void_request` directly.
4. **Revision fence:** every PR write route mounts `require_current_revision("purchase_request","request_id")`. The fence only arms when the type has an enabled `portal_revision_configs` row and the table has `revision_no`.
5. **Already generic (no edit needed):** `emit_form_event`, `assert_can_act_on_form`, `dispatch_or_defer`, `FormActionService`, `grace_seconds_for`, `notify_form_voided_in_app`, NumberingService, audit hooks. None of these name an entity type.
6. **Type-keyed lists the OCN must join:** `FORM_SLA_TYPES` and its lockstep copy `schemas/sla._FORM_SLA_TYPES`, `_ENTITY_NUMBER_SOURCE`, `_STAGE_ACTION_LABELS`, `_form_detail_link`, `_FE_RECORD_ROUTES`, `SOURCE_TYPE_READERS`, `_PER_RECORD_VIEW_PERMISSION` (audit), `form_action_undo._entity_status`, fence `_TARGETS`/`_LABELS`, and the four form-comment dicts.
7. **Hard-coded PR/SF logic to make a lookup table:** `_is_approval_stage` and `_form_default_approver_user_id` (plus a new `system_settings` column for the OCN default approver), and the form-comment `_load_row` else-branch, which falls through to `PurchaseRequestHeader`.
8. **PortalRevisionService.revise cannot be reused.** It is tied to a portal token and a contact. NPA's revise is its own move, and the OCN should follow NPA. The restart helpers `_restart_stage` and `_restart_flow` are keyed by type only and can be reused.
9. **Own-scope:** `REQUEST_KINDS` and `MODULE_REQUEST_KINDS` need nothing unless the OCN gets a `view_own` slug. Under `/project-sales`, `project_own_scope_guard` already covers `/projects/{project_id}/...` routes. Any `/{ocn_id}` route needs a new `_ANCHORS` resolver.
10. **NPA template:** module-level functions take `(db, app, *, actor, ...)`, only `flush()`, and return an event name. The router's `_move` does load (row lock) → view check → handling lock → move → `_done` (commit → `notify` emits the SLA event → commit). Company scoping comes from `CompanyScopedMixin` plus the session scope.
11. **Lists:** NPA and SR return plain dicts with `le=200` and do not use `list_query_registry`. The pagination test only scans files containing `response_model=ListResponse[`; those must use `le=MAX_PAGE_LIMIT`. The "every column sorts" rule is pinned by the per-form `test_portal_p4_*_sort_keys.py` tests.
12. **Project sponsorships route:** `GET /api/v1/project-sales/projects/{project_id}/sponsorships` returns `ListResponse[ProjectSponsorshipResponse]` (11 fields) inside a single-page envelope. Auth is `require_any_permission([projects.projects.view, view_own])` plus the project own-scope guard.
13. **Amendment link:** `_persist_amendment` always builds a new OCN (`project_so_delta_service.py:728-747`); that is where an optional `ocn_id` would be accepted. `publish_amendment` only checks `ocn.approver_id` (`:791`), and nothing in the codebase ever sets `approver_id`. Once the OCN has a status, the check should become `ocn.approval_status == "approved"` (status not voided). `project_po_progress_service.py:587` reads `approver_id` too.
14. **Migrations:** `npasla_0001` copies the stock-inquiry stage rows per team set (policy, agent and flags, guarded by NOT EXISTS) and copies role grants from existing slugs under `npasla-` ids. `npa_0001` inserts permissions with WHERE NOT EXISTS, copies `create` from `procurement.stock_inquiries.edit`, and grants everything to admin and superadmin.
15. **Single alembic head:** `acqs_0001_project_ac_write` (revises `passkey_0001_user_passkeys`). I computed it by parsing all 1108 revision files, because `alembic heads` would not run without environment settings. The OCN model today has no status, revision or void columns (`models/project_so.py:668-704`).

---

# Full report

All paths are under `/home/user/sorento-crm/sorento_crm_backend/` unless marked FE (`/home/user/sorento-crm/sorento_crm_frontend/`).

## 1. PR status machine (service `app/services/procurement_service.py`, router `app/api/v1/procurement/purchase_requests.py`)

The router is mounted at `/api/v1/procurement/purchase-requests`. Two router-level dependencies apply to every route: `require_module_enabled_with_api_key("procurement")` (`app/api/v1/__init__.py:93-96`) and `purchase_request_own_scope` (`app/api/v1/procurement/__init__.py:34-39`).

**Status values**
- `status`: `draft`, `submitted`, `resubmitted` (from `submission_status.py:18-19`), `approved`, `rejected`, `processed_by_cs`, `closed`, `voided`.
- `approval_status`: NULL / `""` / `draft`, `pending`, `approved`, `rejected`, `voided`.
- The restart-stage mapping is in `portal_revision_service.py:75-84`.
- Edits can never move the status: `_pop_status_or_refuse_move` (`procurement_service.py:104-150`) returns 422 and lists the allowed actions from `_REQUEST_STATUS_ACTIONS` (`:169`).

| Action | Route (perm dependency) | Fence | Precondition | Writes | SLA event | Deferred key | Notifications |
|---|---|---|---|---|---|---|---|
| create (staff) | POST `/` :302, `get_current_user` (no slug) | none | n/a | status=`draft`, source=`manual` (:9701-9702); number from `NumberingService.get_next_number(request_type, date)` (:9711-9718); `assert_linkable_project` (:9728) | none | none | none (view token only, :9761-9765) |
| create (external/n8n) | `create_external_request` :8675 | n/a | n/a | status=`draft`, source=`external` (:8745-8746) | `submit` (:8794-8804) | none | `_notify_team_on_external_pr_created` (:8778, def :8970) |
| submit (portal) | `PortalService.submit_draft` (`portal_service.py:1158`) | own guard (C5) | status in (draft, rejected) or approval_status=rejected (:1257-1263) | status=`submitted`/`resubmitted` (:1265-1267), `submitted_at` (:1271), clears approval fields on a resubmit (:1272-1279); history `_record_submission_history` → `PortalRevisionService.record_submission` (:1288, :1363-1395) | `submit` (:1342-1352) | none | `_post_submit_notify` → `_notify_team_on_external_pr_created` (`portal_service.py:2078-2095`) |
| update | PUT `/{request_id}` :321, `get_current_user` | yes :324 | status may not move (:9793-9798) | header fields + replaced lines (:9820-9842) | none | none | none |
| update-and-reply | POST `/{id}/update-and-reply` :346, `get_current_user` + `assert_can_act_on_form` :362 | yes :349 | same guard (:9888-9893) | fields; Respond.io send | none | none | `send_text_or_template`, `enqueue_crm_chat_outbound_webhook` (:9955-9998) |
| send_for_approval | POST `/{id}/set-pending-approval` :423, `require_permission_with_api_key("procurement.purchase_requests.send_for_approval")` :431; `assert_can_act_on_form` :441 | yes :426 | not voided (`_refuse_if_voided` :10085); approval_status ≠ rejected (:10087-10091); no-op guard when already pending (:10098) | approval_status=`pending`, clears approved_at/by/signature/comments, sets requested_approval_by_user_id (:10099-10105) | `send_for_approval`, only if it was not already pending (:10111-10123) | `pr.send_for_approval` (`form_actions.py:201-221`), payload `{actor_user_id}` (router :450-452) | `_notify_contact_on_pending_approval` (:10131, def :10141) |
| reject_submitted | POST `/{id}/reject-submitted` :473, same slug :482; lock :486 | yes :476 | reason required (:10177-10179); not voided (:10182); approval_status in (None, "", draft) (:10184-10188) | approval_status=status=`rejected`, approval_comments, approved_at, approved_by (display name), rejected_by_id (FK-guarded), requested_approval_by_user_id (:10190-10211) | `reject_submitted` (:10225-10236) | `pr.reject_submitted` (`form_actions.py:223-245`) | `_notify_contact_on_approval_rejected` (:10214, def :7922) |
| approval_decision | POST `/{id}/approval-decision` :526, `require_permission_with_api_key("procurement.purchase_requests.approve")` :535; lock :542 | yes :529 | `assert_decidable`: not voided and approval_status == pending (:10574-10584); `decision_comments` requires a reason on reject (:10587-10598) | `_apply_approval_decision`: approval_status=status=action, approved_at, approved_by, rejected_by_id (on reject), signature, comments (:10656-10677) | `approved` / `approval_rejected` (:10712-10723) | `pr.approval_decision` (`form_actions.py:168-195`), event chosen at router :557 | `_notify_requester_on_approved` / `_notify_requester_on_rejected` (:9198/:9240); `_notify_contact_on_approval_approved` / `_rejected` (:7952/:7922); `_dispatch_approval_automation` (:9282, called :10727-10734 after the SLA event) |
| (public link) | `create_approval_token` :10240 sets approval_status=`pending` (:10273) with **no SLA event**; `submit_approval` :10600 → the same `_apply_approval_decision` | - | not voided (:10253, :10628) | | as above | - | as above |
| process | POST `/{id}/process` :595, `require_permission("procurement.purchase_requests.process")` :604; lock :612 | yes :598 | `_finalize_request`: status == `approved` (`_CS_FINALIZE_FROM_STATUSES` :7984); idempotent when already at the target (:8050-8051) | status=`processed_by_cs` (:8073-8075) | `resolved` (:8102-8115) | `pr.finalize` (`form_actions.py:247-264`), payload new_status | `_send_purchase_request_contact_message` (:8088) |
| close | POST `/{id}/close` :638, `require_permission("procurement.purchase_requests.close")` :647; lock :655 | yes :641 | same as process | status=`closed` | `resolved` | `pr.finalize` | same |
| void | POST `/{id}/void` :681, `get_current_user` with an in-handler slug check `procurement.purchase_requests.void` (:706-708); **no handling-lock call** | yes :684 | reason of at least 3 chars (:8150-8154); status not in `_VOID_BLOCKED_STATUSES` {voided, rejected, closed, processed_by_cs} (:8123-8125) and approval_status ≠ rejected (:8158) | status=`voided`; approval_status=`voided` if it was pending; voided_by/at/reason (:8165-8174) | `voided`, emitted **after** the notify (:8178-8200) | `pr.void` is registered (`form_actions.py:266-279`) but **not used** (router :713 calls `void_request` directly) | `_notify_request_voided` (:8204) → `form_void_notify.notify_form_voided_in_app` + WhatsApp |
| revise (portal contact) | `PortalRevisionService.revise` (`portal_revision_service.py:1677`) | mandatory `expected_revision_no` (:1701-1712) | `resolve_policy(...).allowed` (:1715-1717); reason required (:1721-1725) | applies the payload; invalidates the approval fields (`_REQUEST_INVALIDATED` :220-226); revision_no+1, last_revised_at (:1802-1804); status = `_request_status_for_stage(restart)` (:1830) | `void_active_for_source` (:1836), then `_restart_flow` emits the start event (:1988-2008) | none | `_notify_voided_handlers` (:1864, def :2012) |
| delete | DELETE `/{id}` :748, `get_current_user` | yes :751 | none | hard delete (:10035-10040) | none | none | none |

**Audit and history**
- Automatic row audit: `PurchaseRequestHeader.__audit_track__ = True` and `__audit_entity_type__ = "purchase_request"` (`app/models/procurement.py:1127-1128`).
- Explicit `log_audit` for line changes on the external update (`procurement_service.py:8889-8901`).
- Portal history rows go to `portal_form_revisions` (record_submission / record_initial, `portal_revision_service.py:1026-1100`).
- SLA event logs come from `FormSLAOrchestrator._write_event_log` (`form_sla_service.py:1602`).
- FE reads it through `<AuditTrail entityType="purchase_request">` (FE `app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestDetail.tsx:1624`) → `GET /api/v1/audit/logs?entity_type=&entity_id=` (FE `services/auditService.ts:18`). Non-admin readers are gated by `_PER_RECORD_VIEW_PERMISSION` (`app/api/v1/audit/audit_logs.py:27-42`).

## 2. What is PR-bound vs generic, and the smallest change for a second type

**PurchaseRequestService methods**
- Rules that can be lifted into a shared module (they only read `status` / `approval_status`):
  - `_refuse_if_voided` (:8128)
  - `assert_decidable` (:10574)
  - `decision_comments` (:10587, already a staticmethod)
  - `_VOID_BLOCKED_STATUSES` (:8123)
  - `_CS_FINALIZE_FROM_STATUSES` / `_CS_FINALIZE_STATUSES` (:7984-7985)
  - the already-pending no-op guard (:10098)
  - the write sets of `set_pending_approval`, `reject_submitted` and `_apply_approval_decision`
- Smallest share: move these to module-level functions that take `(row)`, and have the PR methods call them, so the logic is not copied.
- PR-bound parts:
  - `get_request`
  - `request_type` as the entity type
  - the Respond.io contact messages (`_send_purchase_request_contact_message` :7707 and every `_notify_contact_*`)
  - email templates `purchase_request_requester_*` (:9219, :9261)
  - the automation context (:9310-9344)
  - the PR-specific `_resolve_actor_display_name` UUID handling (:7844)
- The OCN must provide its own notify hooks. Its column names must match the PR's (`approval_status`, `approved_at`, `approved_by`, `approval_comments`, `rejected_by_id`, `requested_approval_by_user_id`, `voided_by` / `voided_at` / `void_reason`, `status`, `revision_no`) so the shared rules and the form_actions column captures carry over. Today the OCN has none of these columns except `approved_at` (`models/project_so.py:694-697`).

**Revision fence** (`app/services/revision_fence.py`)
- Generic: `require_current_revision(target, id_param)` (:214) and `assert_revision_current` (:165).
- Smallest change:
  - add an `ORDER_CHANGE_NOTICE` key to `_TARGETS` (:99-123): `_FenceTarget(load_model=<OrderChangeNotice>, entity_types=("order_change_notice",), resolve_entity_type=lambda r: "order_change_notice")`.
  - add `"order_change_notice": "order change notice"` to `_LABELS` (:127-132).
  - add a `revision_no` column on the OCN (read at :194).
  - seed an enabled `portal_revision_configs` row (`_revisable_types` :143-162; the model at `models/portal.py:141-166` fails closed when the row is missing).
- That row cannot be toggled in the UI: `REVISABLE_PORTAL_FORM_TYPES` comes from the portal-grantable types (`app/api/v1/forms/revision_configs.py:46-63`). It has to be seeded by the migration.

**form_action_registry / form_actions**
- Registry generic: `register` refuses duplicate keys (`form_action_registry.py:76-80`).
- `_declare` (`form_actions.py:103-159`) is generic. Its getter only receives `(db, payload)` (:124-137), so one key cannot serve two tables unless the payload names the table.
- Smallest change:
  - add an `_ocn_service` accessor and `_get_ocn(db, p)` next to `_pr_service` / `_get_request` (:37-56).
  - wrap the five PR `_declare` calls (:168-279) in a helper `_declare_approval_chain(prefix, entity_types, getter, service, id_key)` and call it twice (`pr.*` with `PR_TYPES`, `ocn.*` with `("order_change_notice",)`). Same columns and the same runner method names.
  - add the OCN router file to `ROUTE_FILES` in `tests/test_form_action_route_wiring.py:19-24`.
- `dispatch_or_defer` (`form_action_dispatch.py:21-72`) and `grace_seconds_for` (`form_action_grace.py:89-131`, per-stage `grace_seconds`, then the global `system_settings.form_sla_grace_seconds`) are generic.
- Undo:
  - add the OCN model to `form_action_undo._entity_status` (`form_action_undo.py:81-87`).
  - `form_action_notify._notify_contact` has no OCN branch and logs-and-skips (:231-330). That is fine for a form with no contact.
  - the undo routes check `FORM_SLA_TYPES` (`app/api/v1/sla/form_actions.py:50-54`).

**form_comment_service** (`app/services/form_comment_service.py`)
- Add `order_change_notice` to:
  - `FORM_COMMENT_KINDS` (:38-44)
  - `VIEW_PERMISSION` (:46-52)
  - `_LABELS` (:58-64)
  - `_NUMBER_ATTR` = `ocn_number` (:65-71)
- Add an explicit `_load_row` branch (:125-138). Today the else-branch assumes `PurchaseRequestHeader` and filters by `request_type == kind`.
- Router `_MODULE` (`app/api/v1/form_comments.py:31`) defaults to `procurement`; add `"order_change_notice": "projects"`.
- `_notify_submitter` returns `"no_whatsapp"` when there is no `respond_inbox_url` (:612-614), which is safe. `_require_open` reads `status` / `portal_draft_at` through getattr (:148-153).

**PortalRevisionService** (`app/services/portal_revision_service.py`)
- The `RevisionAdapter` (:115-172) and `ADAPTERS` (:743-749) are for portal submissions. `revise()` goes through `fetch_owned(token, …)`, which filters `contact_id == token.contact_id` (:1536-1539), so it does not fit an office-only OCN.
- The same conclusion was reached for NPA (`revision_configs.py:45-46`).
- Reusable as-is, keyed by type only:
  - `FormSLAOrchestrator.active_trackers_for_source` / `void_active_for_source` (`form_sla_service.py:515-560`)
  - `PortalRevisionService._restart_stage(type)` (:1926-1932), which works with no config row (falls back to the stage whose start event is `submit`)
  - `_restart_flow` (:1988-2008)
- Recommendation: OCN revise as its own move, shaped like `npa.revise` (`new_product_application_service.py:540-571`).

**form_sla_service** (`app/services/form_sla_service.py`)
- `FORM_SLA_TYPES` (:34-53) must gain the key, in lockstep with `app/schemas/sla.py:656-668`. Pinned by `tests/test_form_sla_types_consistency.py:38-48`, and also gates `_open_form_trackers` (:499-501).
- `_ENTITY_NUMBER_SOURCE` (:143-156): add `("projects.order_change_notices", "ocn_number", True)` if you add `revision_no`, otherwise `False`. It must be schema-qualified, the same way `sample_request` is (:152). It is also used by `_load_form_field_values_strict` (:1161-1174).
- `_STAGE_ACTION_LABELS` (:229-260): one entry per OCN `(type, team_set_code)`.
- `_form_detail_link` (:275-295): add the OCN FE path. The fallback at :295 would build `/order-change-notice/{id}`, which is wrong.
- `_FE_RECORD_ROUTES` (:1490-1493) must match FE `MyPendingSLAWidget.ENTITY_ROUTES` (FE `app/(protected)/sla-management/conversation-sla-tracking/components/MyPendingSLAWidget.tsx:89`).
- `_is_approval_stage` (:910-918) hard-codes `("purchase_request","sponsorship_form")`. Smallest change: one module constant shared with the next item.
- `_form_default_approver_user_id` (:920-933) is an if/elif. Smallest change: a dict `{type: settings column}`, plus:
  - a new column `system_settings.order_change_notice_default_approver_user_id`, next to `models/user.py:578-587`.
  - the settings API fields (`app/api/v1/user_management/settings.py:94-95, 280-283, 340-341, 422-423`).
- `_routing_contact_id` (:1239-1269) and `_computed_request_values` (:1172-1197) are PR/SI-only. An OCN returns None, so no CS pin applies.
- `emit_event` takes `company_id` (:378-396). Pass the OCN's own `company_id`, as NPA does (`new_product_application_service.py:1858-1867`).

**SOURCE_TYPE_READERS** (`app/api/v1/sla/sla_tracking.py:67-87`)
- Add `"order_change_notice": [<ocn view slug>]`.
- `_require_source_visible` (:111-122) only checks NPA. The OCN is company-scoped too, so add the same scoped-load check.

**Handling lock** (`app/services/handling_lock_service.py`)
- Generic: `assert_can_act_on_form(db, id, actor, *, source_entity_type=…)` (:156-188), limited to `FORM_SLA_TYPES` (:149).
- It is enabled per type by the CSV `system_settings.handling_lock_enabled_types` (:47-68), validated against `FORM_SLA_TYPES` (`settings.py:1021-1030`).
- No code change beyond `FORM_SLA_TYPES`. Pass `source_entity_type`, as NPA does (`new_product_applications.py:297-299`).

**Audit**
- The OCN has `__audit_track__ = True` (`models/project_so.py:676`) but no `__audit_entity_type__`, so rows are written as `order_change_notices` (`audit_service.py:125-126`).
- Smallest change:
  - add `__audit_entity_type__ = "order_change_notice"`, or use the table name consistently on the FE.
  - add that key to `_PER_RECORD_VIEW_PERMISSION` (`audit_logs.py:27-42`).
  - FE: `<AuditTrail entityType="…" entityId=…/>` (FE `components/audit/AuditTrail.tsx:79-80, 256-258`).

**Own-scope**
- `own_scope.REQUEST_KINDS` (:55-69) and `MODULE_REQUEST_KINDS` (:76-81) are only needed if a `view_own` slug is introduced. Without one, nothing changes.
- If the OCN routes live under `/project-sales`, `project_own_scope_guard` (`app/api/v1/projects/_own_scope.py:249-273`, mounted at `app/api/v1/__init__.py:112-121`) already covers `/projects/{project_id}/…` through the `("projects","project_id")` anchor (:119).
- Any `/order-change-notices/{ocn_id}` route is refused to limited users until an `_ANCHORS` entry with a resolver to `OrderChangeNotice.project_id` is added (:117-130).
- `_request_own_scope.py` (`_PREFIX` / `_KINDS` / `_READS`, :50-83) does not apply unless the OCN is mounted under procurement.

**permission_registry** (`app/rbac/permission_registry.py`)
- PR slugs: `_crud("procurement","purchase_requests",…)` (:281) plus `send_for_approval` / `approve` / `process` / `close` / `void` (:283-296); `view_own` at :1138-1141.
- There are no OCN slugs today. Add entries via `PERMISSION_REGISTRY.extend([...])`. `sync_permissions` (:1012-1034) only inserts.
- The module gate is prefix-based (`app/modules/runtime/permission_module_map.py:7-27`): a `projects.*` slug is tied to the projects module.

**NumberingService** (`app/services/numbering_service.py:14-94`)
- Generic, and supports `company_id` and `commit_rule=False`.
- The OCN already numbers through `ProjectSODeltaService._next_ocn_number` (`project_so_delta_service.py:1465-1486`): doc_type `order_change_notice` (:88), fallback `OCN-` + 6 digits (:89-90).
- It does **not** pass `company_id` (:1468-1470), even though the uniqueness constraint is `(company_id, ocn_number)` (`models/project_so.py:700-701`).
- Smallest share: make it a module-level function used by both the delta service and the OCN service, and pass `company_id`.

## 3. NPA template (`app/services/new_product_application_service.py`, `app/api/v1/procurement/new_product_applications.py`)

- **Constants:**
  - `ENTITY` (:47)
  - permission slugs (:49-53)
  - statuses (:55-64), labels (:66-75)
  - status groups `EDITABLE`, `AWAITING_REVIEW`, `WITH_PURCHASING`, `LOCKED` (:79-83)
  - `SLA_EVENTS` (:1830)
- **Actor:** the `Actor` dataclass (:95-106) and `actor_from_slugs` (:109-120). The router's `_actor` adds `own_contact_id` for `own_only` users (router :42-49).
- **Loading:** `get_for(db, id, *, contact_id=None, for_update=False)` validates the UUID, then `with_for_update(of=Model)`, else 404 (:365-383).
- **Moves:** each is `fn(db, app, *, actor, reason=None) -> Optional[str]`. It checks the role (403 `_forbidden`), then the state (409 `_conflict(..., code)`), validates input (422 `_invalid(field, msg)`), assigns columns, calls `db.flush()` and returns the event name. Examples: `submit` :428-443, `approve` :479-488, `reject` :491-503, `revise` :540-571 (bumps `revision_no`, clears the stage output, `_void_sla`), `cancel` :574-587.
- **SLA:**
  - `_void_sla` (:1833-1850) calls `FormSLAOrchestrator(db).void_active_for_source(ENTITY, id, reason=…, void_reason="withdrawn")` inside the move's own transaction.
  - `_emit_sla` (:1853-1871) calls `emit_form_event(..., company_id=str(app.company_id))` and rolls back if the session is no longer active.
- **Transaction pattern** (router):
  - `_move` (:302-312): `_load(for_update=True)` → `_actor` → `assert_can_view` → `_gate` (`assert_can_act_on_form(..., source_entity_type=svc.ENTITY)` for stage-work functions only, `_STAGE_WORK` :282-299) → `event = fn(...)` → `_done`; `db.rollback()` on any exception.
  - `_done` (:78-85): `db.commit()`, then `svc.notify(db, app, event, actor_id)`, then `db.commit()`, then `serialize_detail`.
  - So the SLA event is emitted after the move commits, and `notify` (:1943-2001) runs `_emit_sla` → `_team_notice` → per-user `NotificationService.create_with_channel_preferences`, all best-effort.
- **Company scoping:**
  - The model uses `CompanyScopedMixin` (`app/models/new_product_application.py:51`) and overrides `company_id` as NOT NULL (:59-61).
  - The mixin (`app/models/base.py:112-147`) is auto-filtered by `do_orm_execute` and auto-stamped by `before_insert` (`app/services/company_scope.py:393, 450`), using the scope set on the session (`set_company_scope` / `get_company_scope` / `company_scope` contextmanager, `base.py:62-108`).
  - The acting company for a write comes from `acting_company_id(db)` (`app/api/v1/projects/_common.py:11-25`).
  - Numbering is a `before_insert` listener under a per-company advisory lock (`new_product_application.py:268-295`). For the OCN, use NumberingService instead.
- **Note:** NPA does not mount `require_current_revision` and does not use `dispatch_or_defer`; the npasla migration says so (:14). The OCN would be the first type with both fence and deferral outside PR/SI/CX/TK.

## 4. List endpoint pattern

- **NPA list:** `GET ""` (router :138-164) takes `status` (multi, via `multi_values`), `q`, `stock_inquiry_id`, `applicant_id` (`multi_uuids`), `page`, `limit` (`le=200`), `sort`, `dir`, and returns `{items,total,page,limit}`.
  - Service `list_for` (:1422-1503): visibility clause `_visible` (:1391-1399), `_SORTS` map with scalar subqueries for derived columns (:1402-1419), SLA person-name and print-count sorts via `StockInquiryService._sla_person_name_sort` / `_print_count_sort(..., ENTITY, Model)` (`procurement_service.py:5761, 5790`), `.nulls_last()` plus a tie-breaker (:1479-1485), batched `_attach_sla_handlers` / `_attach_print_counts` (`procurement_service.py:5829, 5809`).
- **SR list:** same shape (`app/api/v1/projects/sample_requests.py:135-193`, `le=200`, `LIST_SORTS` in `sample_request_service.py:1272`).
- **PR list:** returns `ListResponse` with `le=MAX_PAGE_LIMIT` (router :56-100). Its `sort_map` with an id tie-breaker is at `procurement_service.py:9466-9490`, and its multi-select OR filters at :9426-9464.
- **Multi-select helpers:** `app/utils/multi_value.py` (`multi_values` :26, `multi_uuids` :60, `multi_choices` :71). Comma or repeated values, at most `MAX_FILTER_VALUES = 200` (:17), otherwise 422.
- **list_query_registry** (`app/services/list_query_registry.py:95-213`) is **not** used by NPA, SR or PR. It is for list-query export/metadata resources (orders, products, tickets…). Adding an OCN there is only needed if you want that export.
- **`tests/test_list_pagination_limit.py`:** `MAX_PAGE_LIMIT == 1000` (:25-27). In any `api/v1` file containing `response_model=ListResponse[`, every `limit: int = Query(...)` without `description=` must not have `le` below 1000 (:37-59). If the OCN router uses `ListResponse`, use `le=MAX_PAGE_LIMIT`.
- **Server-side sort on every column:** pinned per form, e.g. `tests/test_portal_p4_npa_sort_keys.py:39-53`. Asc and desc must differ, be exact reverses, and follow the value order rather than the created_at fallback. Write the same kind of test for the OCN.
- **`tests/test_schema_uuid_id_principle.py`:** every mapped table needs a `UUID` `id` primary key unless it is in `EXEMPTIONS` (:43-97, :143-154). The key is schema-qualified (`projects.x`, :126-140). The OCN already complies (`models/project_so.py:678`). Any new child table (e.g. OCN lines) must too.

## 5. GET /projects/{id}/sponsorships

- **Full path:** `/api/v1/project-sales/projects/{project_id}/sponsorships` (`app/api/v1/projects/samples_pos.py:502-523`).
- **Auth:**
  - `require_any_permission(READ)` with `READ = ["projects.projects.view","projects.projects.view_own"]` (:54-58, :508). It is session-only (`get_current_user`, `dependencies.py:523-530`), and admin/superadmin bypass it.
  - Router-level: module `projects` plus `project_own_scope_guard` (`app/api/v1/__init__.py:112-121`).
  - The handler then runs `validate_uuid_path` and `projects.get_project_or_404`.
- **Response:** `ListResponse[ProjectSponsorshipResponse]` built by `_envelope` (:63-68): `{"data":[...], "pagination":{"total":n,"page":1,"limit":max(n,1)}, "empty": not data}`, plus the `ListResponse` defaults `fallback_used`, `resolved_entities`, `lookup_companies`, `summary` (`schemas/common.py:47-70`).
- **Item fields** (`schemas/projects.py:1855-1874`): `id`, `request_number`, `request_date`, `status`, `approval_status`, `customer_name`, `project_title`, `sponsor_subject`, `sponsor_subject_other`, `total_project_value` (Decimal), `purpose`.
- **Data:** `sponsorship_link_service.list_sponsorships` (:152-183) filters `project_id` and `request_type='sponsorship_form'`, ordered by `request_date desc nulls last`. There is no pagination or sort param.

## 6. Amendment link (`app/services/project_so_delta_service.py`)

- **`_persist_amendment`** (:705-754): creates the `SOAmendment` (status `proposed`, :715-726), then always creates a new `OrderChangeNotice` (:728-746) and sets `amendment.ocn_id` (:747).
  - Callers: `create` (:584-639, route `app/api/v1/projects/sales_orders.py:851-876`, body `AmendmentCreateRequest` at `schemas/project_sales_order.py:443-446`) and `create_area_date_amendment` (:641-703).
  - Where to accept an existing OCN: add `ocn_id: Optional[str] = None` to `_persist_amendment` and thread it through `create`, `create_area_date_amendment` and `AmendmentCreateRequest`.
  - When it is given: load the OCN under the company scope; require the same `project_sales_order_id` / `company_id` and a non-terminal status; refresh its `change_table_json` from `delta` (same keys as :737-742); set `amendment.ocn_id`. Otherwise keep the current create path.
  - `AmendmentCreateResponse` already returns `ocn_id` / `ocn_number` (`schemas/project_sales_order.py:515-519`).
- **`publish_amendment`** (:758-855):
  - Today it checks `if ocn is None or not ocn.approver_id` → 409 `amendment_ocn_unapproved` (:791-799), and stamps `approved_at` if empty (:823-824).
  - Nothing in `app/` assigns `OrderChangeNotice.approver_id` (only reads: :791, :945; `project_po_progress_service.py:587`).
  - Once the OCN has the PR lifecycle, replace the check with `ocn.approval_status == "approved"` and `ocn.status != "voided"` (mirroring `assert_decidable`'s columns, `procurement_service.py:10578`), and drop the `approved_at` stamp, because the decision already sets it.
  - Also update `project_po_progress_service.py:585-588`, which treats `approver_id` as "review started, keep it", and `get_amendment`, which serializes the approver from `approver_id` (:943-971).
  - Draft wipe: `project_so_draft_service.py:2280-2285` deletes notices by SO / ocn ids.

## 7. Migrations

- **`alembic/versions/npasla_0001_seed_configs.py`** (revision `npasla_0001_seed_configs`, down `lpcui_0001_list_price_changed`, :35-36):
  - Copies form_sla_configs per stage (:41-62): `INSERT … SELECT gen_random_uuid(), '<type>', '<stage>', si.policy_id, si.agent_code, si.team_set_code, '<start>', <respond>, '<resolve>', si.is_active, si.notify_assignee, si.notify_on_escalation …` from the source type's row with the same team set, `NOT EXISTS` for the target type and team set, `ORDER BY is_active DESC, created_at ASC LIMIT 1`. It reuses the policy by `policy_id`; it does not clone the policy row. `grace_seconds` is not copied.
  - Copies role grants from source slugs (:99-126) using ids `npasla-` || md5(role:perm) with `NOT EXISTS` / `ON CONFLICT DO NOTHING`. The downgrade deletes by id prefix (:127, :138-147).
  - For the OCN: copy the `purchase_request` rows. Their chain shape is submit → send_for_approval → approved, with resolves `send_for_approval,reject_submitted,voided` / `approved,approval_rejected,voided` / `resolved,voided` (`tests/test_forms_chain_purchase_request.py:59-65`).
- **`alembic/versions/npa_0001_new_product_apps.py`** (revision `npa_0001_new_product_apps`, down `lean_0001_parser_reasoning`, :19-20):
  - `_PERMS` tuple (:24-45).
  - `INSERT INTO user_permissions … WHERE NOT EXISTS (slug)` (:134-144).
  - Copies the `create` grant from the holders of `procurement.stock_inquiries.edit` (:146-165).
  - Grants every slug to roles `superadmin` and `admin` (:47, :167-185).
  - The downgrade deletes the grants and then the permissions (:188-198).
- **Current single alembic head:** `acqs_0001_project_ac_write` (`alembic/versions/acqs_0001_project_ac_write.py:15-16`, revises `passkey_0001_user_passkeys`). I found it by parsing the revision / down_revision of all 1108 files; `alembic heads` would not start here because required settings were missing. Revision ids must stay at 32 characters or fewer (`npasla_0001:34`).
- Per `CLAUDE.md`, the shared local database converges through `create_all`. Write the OCN's new columns as additive and idempotent (`ADD COLUMN IF NOT EXISTS`).