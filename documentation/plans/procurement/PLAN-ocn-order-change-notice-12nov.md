# PLAN: Order Change Notice (OCN) on the purchase request engine

Status: Slice 1 hand test (13 Nov): built, reviewed (reviewer 3 rounds, security 3 rounds), kill-tested, browser-passed;
waiting for the owner's hand test. Merges after #2383 (PROJECT-RELATED-RECORDS). Size L, full track (migration, new SLA
rows, RBAC slugs).
Lane OCN-ORDER-CHANGE-NOTICE. Card: `CARD-ocn-order-change-notice-12nov.md`. UAC:
`ocn-order-change-notice-acceptance-criteria.md`. Mock: `documentation/mockups/ocn/index.html`.
Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`. Read from main aa824637.

## Decisions (fixed)

- The OCN is the existing `projects.order_change_notices` row (`models/project_so.py:668`), extended.
  Its own service + router, following the NPA template (`services/new_product_application_service.py`,
  `api/v1/procurement/new_product_applications.py`: module functions `fn(db, row, *, actor, ...)` that
  flush and return the SLA event; router `_move` = lock-load, view check, handling lock, move, commit,
  notify + emit, commit).
- Lifecycle mirrors the PR exactly (columns AND values, so the shared rules and the deferred-action
  column captures carry over): `status` draft / submitted / resubmitted / approved / rejected /
  processed_by_cs (shown "Done") / voided; `approval_status` NULL / pending / approved / rejected /
  voided; `approved_at`, `approved_by`, `approval_comments`, `rejected_by_id`,
  `requested_approval_by_user_id`, `voided_by`, `voided_at`, `void_reason`, `revision_no`.
  Moves and SLA events: submit (`submit`), send for approval (`send_for_approval`), send back
  (`reject_submitted`), approval decision (`approved` / `approval_rejected`), done (`resolved`), void
  (`voided`), revise (approved or rejected -> draft, bumps `revision_no`, clears the approval stamp, voids the open stages, emits nothing; the next Submit emits `submit` again; like `npa.revise` :540).
- Routes: `/api/v1/procurement/order-change-notices` (module `procurement`, like PR/SF; the menu sits in
  Project Sales Admin which is module `procurement`). Project panel route
  `/api/v1/project-sales/projects/{project_id}/order-change-notices` (sponsorships shape,
  `api/v1/projects/samples_pos.py:502`). FE pages `/procurement-management/order-change-notices`.
- Permissions `procurement.order_change_notices.{view, view_own, create, edit, delete, approve, report}`;
  grants copied from the matching PR slug holders (`view`<-`purchase_requests.view`,
  `edit`<-`purchase_requests.send_for_approval`, `approve`<-`purchase_requests.approve`, etc.) +
  admin/superadmin, ids prefixed `ocn-` (npasla_0001 pattern).

## Shared once, never copied (owner rule)

| Piece | Today | Change |
|---|---|---|
| Numbering | `ProjectSODeltaService._next_ocn_number` (`project_so_delta_service.py:1465`), no company_id | one module function `next_ocn_number(db, company_id)` used by the delta service and the OCN service; passes `company_id`; rule `OCN{yy}-` 4 digits yearly seeded |
| Approval stage + default approver | `_is_approval_stage` / `_form_default_approver_user_id` hard-code PR/SF (`form_sla_service.py:910-933`) | one dict `{type: settings column}`; new `system_settings.order_change_notice_default_approver_user_id` + settings API fields |
| Deferred actions | five `pr.*` `_declare` calls (`form_actions.py:168-279`) | helper `_declare_approval_chain(prefix, entity_types, getter, service, id_key)` called for `pr.*` and `ocn.*` |
| PR rules | `_refuse_if_voided` :8128, `assert_decidable` :10574, `decision_comments` :10587, `_VOID_BLOCKED_STATUSES` :8123, finalize-from :7984 | lifted to module-level functions taking a row; PR methods call them; OCN calls them |
| Revision fence | `_TARGETS`/`_LABELS` (`revision_fence.py:99-132`) | add OCN target + seeded enabled `portal_revision_configs` row |
| Form comments | 4 dicts + `_load_row` else-branch (`form_comment_service.py:38-138`) | add kind + explicit branch; router `_MODULE` |
| SLA lockstep lists | `FORM_SLA_TYPES`, `schemas/sla.py:656`, `_ENTITY_NUMBER_SOURCE`, `_STAGE_ACTION_LABELS`, `_form_detail_link`, `_FE_RECORD_ROUTES`, `SOURCE_TYPE_READERS`, FE `formSLAService.ts`, `FormSLAConfigDialog.tsx`, `MyPendingSLAWidget.tsx` | add `order_change_notice` |
| Audit / History | `__audit_track__` on, no `__audit_entity_type__` | set `order_change_notice`; add to `_PER_RECORD_VIEW_PERMISSION` (`api/v1/audit/audit_logs.py:27`); FE `AuditTrail` |
| Amendment link | `_persist_amendment` always drafts (`:705`); publish checks `approver_id` (`:791`) | optional `ocn_id` pick (same project, unlinked, not terminal); publish requires `approval_status == approved` and not voided; `project_po_progress_service.py:587` and `get_amendment` read the new fields |

Full engine map with file:line: `documentation/plans/procurement/evidence/ocn-pr-lifecycle-contract.md`.

## Migration (one revision, `ocn_0001_order_change_notice`, down = current head at commit time)

Additive and idempotent: OCN columns (`ADD COLUMN IF NOT EXISTS`), `project_id` nullable + FK
re-created ON DELETE SET NULL, `projects.order_change_notice_lines` (UUID id), lookup
`projects.order_change_types` (seed 4 rows with risk + guide text), `system_settings` columns
(`order_change_notice_require_project` bool default false, `order_change_notice_default_approver_user_id`),
numbering rule, permissions + grants, SLA policy `ORDER_CHANGE_NOTICE` (tiers copied from
PURCHASE_REQUEST) + 3 `form_sla_configs` rows copied from the PR rows, `portal_revision_configs` row.
The table has 0 rows on the 12 Nov prod clone, so no backfill.

## Slices

1. **This PR (#2384):** BE (migration, model, service, routers, shared extractions, amendment link,
   project list) then FE (menu, list, form in the sample-request document shell, detail with tabs,
   amendment dialog picker) + user guide.
2. **`OCN-ORDER-CHANGE-NOTICE B`** (new branch + PR): portal kind, public approval / view link, PDF,
   assistant / MCP, report.

## Test list (tester writes these red first)

BE pytest (Postgres, `tests/_pg_fixture.py`): UAC A1-A7, B1-B11, C1-C4, D1-D4, E1-E4, F1-F2; plus the
global guards `test_schema_uuid_id_principle.py`, `test_list_pagination_limit.py`,
`test_form_sla_types_consistency.py`, `test_form_action_route_wiring.py` (OCN router in `ROUTE_FILES`),
an OCN sort-keys test (pattern `test_portal_p4_npa_sort_keys.py`), and a PR regression (PR moves still
behave identically after the shared extraction). FE vitest: list columns/sort/filters, form shell +
Save as draft / Submit, detail main button per status, menu entry.

## Follow-ups recorded (not in this lane)

- Upload helper shared with complaints and stock inquiries trusts the browser content type and has no virus scan
  (security L6); applies to every caller, so it gets its own lane.
- Linking a project ignores the "own projects only" limit (security L4), same as purchase requests and complaints today.
- `apply_decision` writes an aware timestamp into a naive column (review m6), pinned PR behaviour; fix with the PR pin.
- iOS long-press can open the Unlink menu on the wrong file (shared PurchaseOrdersPanel pattern).
- The purchase request customer lookup (`api/v1/procurement/purchase_requests.py:142`) checks no permission: any staff
  user who is not own-scope-limited can list up to 1000 customers (security review round 4, outside this lane).
- Salesperson breadcrumb on the notice pages reads the staff group (same as purchase requests reached from My requests).
- Shared picker clear button fires on touch-down; a scroll starting on it may clear a value on phones (crew note, unverified).
- Main-only test failures seen while testing, not from this lane: `test_every_route_a_limited_user_reaches_is_pinned`
  (#2173 AutoCount routes unpinned) and one passkey audit test (#2375).
- Slice 2 (`OCN-ORDER-CHANGE-NOTICE B`): portal kind, public approval / view link, PDF, assistant actions (the list is
  already registered for reading), report, Revisions tab with portal revisions.
