# PLAN - RBAC-gate the My Pending / My Team task buttons

**Status:** Draft → ready for implementation
**Owner:** jayson
**Scope:** `MyPendingSLAWidget.tsx` (both tabs: *My Pending* + *My Team*) action buttons → per-action permission slugs, FE show/hide + BE enforce.

## Goal

Every action button in the My Pending / My Team dashboard widget is independently
RBAC-controlled: hidden on the FE when the user lacks the slug, AND rejected (403)
on the BE. Dedicated per-action slugs so each button can be granted per role
independently. Close the two current auth holes (Resolve, Escalate are unguarded).

## Buttons in scope

| Button | Tab | FE call | BE route today | BE guard today |
|--------|-----|---------|----------------|----------------|
| Extend | My Pending | `POST /{id}/extend` | `extend_sla_tracking` (614) | assignee-only (`_assert_can_extend`) ✅ |
| Reassign | both | `POST /{id}/reassign` | `reassign_sla_tracking` (428) | team-visibility (`can_user_act_on_tracking`) ✅ |
| Resolve | My Pending | `PUT /{id}` `{is_resolved:true}` | `update_sla_tracking` (1153) | **none** ❌ (shared w/ n8n) |
| Escalate | My Pending | `POST /{id}/escalate` | `escalate_conversation_sla_tracking` (1018) | **none** ❌ |
| Takeover | My Team | `POST /{id}/takeover` | takeover route | team-visibility (service) ✅ |

Takeover Cancel/Reject are takeover sub-actions → gate under the same `takeover` slug.

## New permission slugs (5)

Added to `app/rbac/permission_registry.py`, SLA Management section (after `test_override`):

```
sla_management.conversation_sla_tracking.extend
sla_management.conversation_sla_tracking.reassign
sla_management.conversation_sla_tracking.resolve
sla_management.conversation_sla_tracking.escalate
sla_management.conversation_sla_tracking.takeover
```

**Seeding:** `sync_permissions(db)` runs at startup (`app/main.py:211`), idempotent
 -  new slugs auto-create on next boot. **No Alembic migration needed** for the perm
rows. Roles get the slugs via the existing Roles UI; `superadmin`/`admin` bypass all
checks (`require_permission` short-circuit).

## Backend changes - `app/api/v1/sla/sla_tracking.py`

Pattern for routes that keep `current_user` (need the actor id) AND add a perm gate:
add a second dependency param `_perm: dict = Depends(require_permission("<slug>"))`.
Both resolve through cached `get_current_user`.

1. **extend** (614): add `_perm = Depends(require_permission("…extend"))`. Service
   already enforces assignee. ✅ done.
2. **reassign** (428): add `_perm = Depends(require_permission("…reassign"))`. Service
   already enforces team-visibility. ✅ done.
3. **escalate** (1018): add `_perm = Depends(require_permission("…escalate"))` **AND**
   insert an actor check in the route body before escalating:
   ```python
   if not service.can_user_act_on_tracking(current_user["id"], tracking):
       raise handle_not_found("Conversation SLA tracking", tracking_id)
   ```
   (route currently has no actor check at all). Keep `current_user=Depends(get_current_user)`.
4. **takeover** route: add `_perm = Depends(require_permission("…takeover"))`.
   Cancel/reject takeover routes: gate under the same `…takeover` slug.
5. **resolve** - do NOT touch `PUT /{id}` first (n8n integration uses it via API key).
   Add a dedicated endpoint:
   ```python
   @router.post("/{tracking_id}/resolve", response_model=ConversationSLATrackingResponse)
   async def resolve_sla_tracking(
       tracking_id: UUID,
       current_user: dict = Depends(get_current_user),
       _perm: dict = Depends(require_permission("…resolve")),
       db: Session = Depends(get_db),
   ):
       service = ConversationSLATrackingService(db)
       tracking = service.get_tracking(str(tracking_id))
       if not tracking:
           raise handle_not_found("Conversation SLA tracking", tracking_id)
       if not service.can_user_act_on_tracking(current_user["id"], tracking):
           raise handle_not_found("Conversation SLA tracking", tracking_id)
       updated = service.update_tracking(str(tracking_id),
                   ConversationSLATrackingUpdate(is_resolved=True))
       return build_conversation_sla_tracking_response(db, updated)
   ```
   Route-shadowing: declare `/{tracking_id}/resolve` BEFORE the parametric
   `PUT /{tracking_id}` is irrelevant (different method), but keep it next to the
   other `/{tracking_id}/*` POSTs for consistency.
   **Defense-in-depth on PUT (secondary):** in `update_sla_tracking`, when the
   principal is a real user (NOT the api-key/system principal) and the payload flips
   `is_resolved`, require the `…resolve` slug; api-key principal (n8n) bypasses.
   Coder to confirm how `get_current_user_or_api_key` marks the api-key principal
   before implementing this guard - if non-trivial, ship the dedicated route only and
   note the residual PUT exposure.

## Frontend changes - `MyPendingSLAWidget.tsx`

```ts
import { useHasPermission } from '@/hooks/usePermissions';
const SLUG = 'sla_management.conversation_sla_tracking';
const canExtend   = useHasPermission(`${SLUG}.extend`);
const canReassign = useHasPermission(`${SLUG}.reassign`);
const canResolve  = useHasPermission(`${SLUG}.resolve`);
const canEscalate = useHasPermission(`${SLUG}.escalate`);
const canTakeover = useHasPermission(`${SLUG}.takeover`);
```

- Escalate button (550): wrap `{canEscalate && (…)}`.
- Resolve button (565): wrap `{canResolve && (…)}`.
- Extend (`<ExtendDueButton/>`, 584): `{!isTeam && canExtend && (…)}`.
- Reassign (597): `{!tk && canReassign && (…)}`.
- Takeover (533) + Cancel(500)/Reject(513): wrap in `{canTakeover && …}`.
- Switch `resolveConversationSLATracking` service to `POST /{id}/resolve`.

If a row's whole action cluster collapses to empty for a user, that's fine (read-only).

## Tests (Phase 2 - land here, not deferred)

- **pytest** (`tests/`): for each of the 5 routes - 200 with perm + valid actor;
  403 without perm; 404/403 when acting on a tracking outside visible scope. Plus
  resolve: api-key PUT still works (n8n path unbroken).
- **vitest**: `MyPendingSLAWidget` renders each button only when the matching
  `useHasPermission` is true (mock the hook). Empty-cluster row renders cleanly.
- **playwright** (optional): grant a role only `…resolve`, confirm only Resolve shows.

## Out of scope

- Form-SLA rows (`is_form_sla`) already hide Escalate/Resolve in the widget; their
  actions live on the form detail pages with their own perms.
- The route-level page gate (`conversation_sla_tracking.view`) is unchanged.
```