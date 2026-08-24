# PLAN - HoD coverage + coverage on the dashboard

**Status:** Draft → Phase 1 (FE prototype) next
**Owner:** jayson
**Related:** PLAN-team-coverage-and-reassignment.md (existing self-service coverage), PLAN-sla-pending-task-button-rbac.md (per-action SLA RBAC just shipped)

## Problem

Two gaps:
1. Coverage management lives at `/account/notifications` - separate from where staff
   actually work (the dashboard `app/(protected)/page.tsx`, which renders
   `MyPendingSLAWidget`). Users want **one page** to run tasks + coverage.
2. Coverage is **self-service only** - the API hardcodes `current_user["id"]` as the
   coverer (`subscriber_id`). A Head-of-Dept cannot set up coverage **for** team
   members (assign A to cover B). Today the only flow is "I cover for X".

## Confirmed decisions (from user)

1. **HoD = parent-team member + permission.** No team-lead schema. A user who is a
   member of a *parent* team already sees + can act on descendant-team members
   (scope-B, `_visible_member_ids`). Gate the cross-user assignment with a NEW slug
   `notifications.coverage.manage_team`. (`superadmin`/`admin` bypass.)
2. **Path (b) "ask the member to do it themselves" = existing self-service.** No
   in-app request/accept handshake. Only build path (a): HoD direct-assign.
3. **Direct-assign is active immediately + notifies the coverer.** Coverer A gets
   "You're now covering B until <date>" and can remove it themselves later. No accept
   step.

## Existing model (unchanged shape)

`NotificationSubscription` (`app/models/notification.py`):
`subscriber_id` (coverer) · `target_user_id` (covered) · `redirect_assignments`
(auto-assign vs notify-only) · `expires_at` · `is_active`. Unique active per
`(subscriber_id, target_user_id)`. Routing hooks already handle both modes
(`active_coverer_for` redirect, `fan_out_coverage_copies` notify) - **no change to
routing logic needed**; HoD-created rows flow through the same machinery.

## Backend changes

### Schema
- Add `created_by_id` (nullable FK `users.id`, SET NULL) to `notification_subscriptions`
  - audit trail: distinguishes self-created (`= subscriber_id` or NULL) from
  HoD-assigned (`= the HoD`). Alembic migration required.

### Permission
- `notifications.coverage.manage_team` → `permission_registry.py`. Auto-seeded at
  startup (`sync_permissions`).

### Service - `coverage_subscription_service.py`
- `subscribe(...)` gains optional `subscriber_id` (the coverer) + `created_by_id`.
  - When the coverer == actor → current self-service path (unchanged).
  - When coverer != actor → caller must have already passed the permission gate.
    Validate **both** coverer and covered ∈ actor's `_visible_member_ids(actor)`.
    Stamp `created_by_id = actor`. Then notify the coverer (best-effort, never raises).
- `list_team_subscriptions(actor_id)` → all active rows where coverer OR covered ∈
  `_visible_member_ids(actor)`. Returns coverer name, covered name, mode, expiry,
  `created_by` label. (For the HoD management view.)
- `deactivate_by_id(subscription_id, actor_id, can_manage)` → deactivate a specific
  row when the actor owns it (coverer == actor) OR `can_manage` and both endpoints ∈
  scope-B.

### Routes - `app/api/v1/notifications/coverage.py`
- `POST /` - extend `_SubscribeRequest` with optional `subscriber_id`. If present and
  != current_user → `Depends(require_permission("notifications.coverage.manage_team"))`
  via a branch (or a second route `POST /assign`). Cleanest: dedicated
  **`POST /assign`** gated by the slug, body `{coverer_id, target_user_id, expires_at?,
  redirect_assignments}`. Keeps the self-service `POST /` untouched.
- `GET /team` - `require_permission("…manage_team")`. Team coverage list.
- `DELETE /manage/{subscription_id}` - deactivate by id (owner or manage_team + scope).

Keep existing `GET /`, `POST /`, `DELETE /{target_user_id}` for self-service.

## Frontend changes

### Move/surface coverage on the dashboard (`app/(protected)/page.tsx`)
- Add a **Coverage** card beside/under `MyPendingSLAWidget`. Reuse the logic in
  `account/notifications/components/coverage-section.tsx` (lift shared bits into a
  shared component rather than duplicate - see CLAUDE.md "don't duplicate panels").
- Section 1 **My coverage** (self-service) - the existing picker + list, as-is.
- Section 2 **Team coverage** (only if `useHasPermission('notifications.coverage.manage_team')`):
  - Assign form: pick **Coverer** + **Covered** (both from scope-B users) + mode
    toggle + optional until → `POST /assign`.
  - List of team coverages with "assigned by" + revoke (`DELETE /manage/{id}`).
- Keep `/account/notifications` coverage section too (or link to the dashboard) - TBD,
  default keep both pointing at the same shared component.

### Services / hooks
- Extend `coverageService.ts` + `useCoverage.ts`: `assignCoverage()`,
  `useTeamCoverage()`, `useAssignCoverage()`, `useRevokeCoverageById()`.

## Tests (Phase 2)
- **pytest:** `POST /assign` - 200 as HoD for in-scope coverer+covered; 403 without
  `manage_team`; 422/404 when either user out of scope; self-service `POST /` still
  works; coverer gets notified (assert notification row). `GET /team` scope. `DELETE
  /manage/{id}` owner vs HoD vs forbidden.
- **vitest:** dashboard Coverage card - Team section hidden without the slug; assign
  form posts the right payload; list renders.
- **playwright:** as a HoD, assign A→cover→B from the dashboard, assert the
  `/api/v1/notifications/coverage/assign` call + the row appears.

## Out of scope
- Team-lead designation column. Transitive coverage chains (still one-hop).
- In-app request/accept handshake (path b stays self-service).
```