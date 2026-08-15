# PLAN - user-management read gates

**Status:** In progress. Phase 2 (backend + tests) only; no Phase 1, no frontend change.
**UAC:** `documentation/plans/security/user-management-read-gates-acceptance-criteria.md`
**Classification:** CORE (`user_management` is base-platform; not an installable module).
**Branch:** `fm/user-management-read-gates-audit`
**Follows:** PR #168 (`GET /users/respond-users`), PR #152 (`POST /users/{id}/sync-respond`) - same
defect class, one route each.

## The defect

`Depends(get_current_user)` proves a session exists. It proves nothing about role. Sibling routes
in the same package have used `Depends(require_permission("<module>.<resource>.<action>"))` since
migration 061, so the pattern is not in question - these routes were simply missed.

Two facts make this worse than it reads:

1. **Menu `permission:` is cosmetic.** `config/menu.config.tsx` keys hide the sidebar link only.
   There is no `middleware.ts` in the frontend and no `RequireAccess` under
   `app/(protected)/user-management/**` (that component is used only by `system-management/*`).
   Every one of these pages renders and fires its fetches on a direct URL. The backend dependency
   is the entire gate.
2. **Two doors are permission-free by construction.** `/user-management/contacts` has no menu
   entry at all and is linked from the global topbar Apps dropdown
   (`app/components/partials/topbar/apps-dropdown-menu.tsx:33`), rendered for every authenticated
   user with no filter. `/user-management/contact-access-agents` has a menu entry with no
   `permission:` key and renders the same `ContactsList`. Between them, nine of the routes below
   are reachable by any logged-in account.

Live role grants (prod-copy DB, read-only query): only `admin`, `director`, `warehouse_manager`
and the three `integration_*` roles hold any `user_management.*.view`. `customer_service`,
`marketing_manager`, `marketing_executive`, `purchasing*`, `project_sales*` and
`warehouse_executive` hold none - and they account for most of the 125 users with role
assignments. So the exposure is real users, not a theoretical principal.

## Audit table

Slug column reads `-` where the route is not gated in this PR. "Screen gate today" is the menu
`permission:` on the entry that reaches the screen, which as established is advisory only.

### Gated in this PR

| # | Route | Returns | Screens today | Screen gate today | Slug applied |
|---|---|---|---|---|---|
| 1 | `GET /teams/` | all teams | `/user-management/teams`; access-agent form + detail | `teams.view`; `access_agents.view` | `user_management.teams.view` |
| 2 | `GET /teams/{team_id}` | one team | `/user-management/teams/[id]` | `teams.view` | `user_management.teams.view` |
| 3 | `GET /teams/{team_id}/members` | staff roster of a team | `/user-management/teams/[id]` | `teams.view` | `user_management.teams.view` |
| 4 | `GET /teams/{team_id}/members/{user_id}/market-segments` | member's segment codes | `/user-management/access-agents/[id]` (`MemberMarketSegmentEditor`) | `access_agents.view` | `user_management.teams.view` |
| 5 | `GET /access-agents/` | agent inventory | `/user-management/access-agents`, `[id]`, **and `/user-management/contacts/[id]`** (`ContactAccessAgentsTable`, `limit=1000`) | `access_agents.view`; **none** on contacts | `user_management.access_agents.view` |
| 6 | `GET /access-agents/contact-access` | whole agent-to-contact matrix | none live (two orphaned components under the permission-free `contact-access-agents` route) | none | `user_management.access_agents.view` |
| 7 | `GET /access-agents/neighbours` | prev/next id + total | `/user-management/access-agents/[id]` | `access_agents.view` | `user_management.access_agents.view` |
| 8 | `GET /access-agents/{agent_id}` | one agent | `/user-management/access-agents`, `[id]` | `access_agents.view` | `user_management.access_agents.view` |
| 9 | `GET /access-agents/{agent_id}/teams` | assignments + team member names/emails/respond ids + round-robin state | `/user-management/access-agents`, `[id]` | `access_agents.view` | `user_management.access_agents.view` |
| 10 | `GET /access-agents/{agent_id}/field-access` | per-field allow/deny ACL + per-contact overrides | `/user-management/access-agents/[id]` **and `/user-management/contacts/[id]`** (`ContactFieldAccessDialog`) | `access_agents.view`; **none** on contacts | `user_management.access_agents.view` |
| 11 | `GET /access-agents/{agent_id}/contact-access` | one agent's contact grants | `/user-management/access-agents/[id]` | `access_agents.view` | `user_management.access_agents.view` |
| 12 | `GET /contact-access-types/all` | full catalog incl. inactive | `/user-management/contact-access-types` | **none** | `user_management.access_agents.view` |
| 13 | `GET /contact-access-types/{code}` | one type | none (dead service export) | n/a | `user_management.access_agents.view` |

**Why `access_agents.view` for rows 12-13.** Not invented: `app/api/v1/external/permissions.py:134`
already maps the `contact-access-types` external endpoint to `user_management.access_agents.view`.
The same resource keeps the same slug on the internal surface.

**Why `teams.view` for row 4.** It is teams data (`/teams/{id}/members/{uid}/...`), read from an
access-agents screen. Gating on the resource rather than the calling screen is what rows 1-3 do,
and it is safe here: every role that currently holds `access_agents.view` also holds `teams.view`
(admin, director, warehouse_manager, the three `integration_*` roles). Rows 5 and 10 are the mirror
case and are gated on `access_agents.view` for the same reason - they return access-agent data,
and the fact that an ungated screen happens to call them is the ungated screen's defect, tracked
as Q1 below, not a reason to leave ACL rows world-readable.

### Documented exceptions - deliberately NOT gated

| Route | Returns | Why not gated |
|---|---|---|
| `GET /quick-access/` | the caller's own pinned menu entries | Self-scoped: the query filters `user_id == current_user["id"]`, so it discloses nothing about anyone else - the same family as `GET /users/me` and `GET /users/me/permissions`, which are also `get_current_user`. It also fires on every page load for every user from the app shell (`quick-access-block.tsx:34`, `menu-item-pin-button.tsx:24`), and in both components the `useQuickAccess()` call sits ABOVE the permission bail-out, so a gate would 403 on every page render for every user without pin/unpin. The sibling POST/PATCH/DELETE are correctly gated on `menu.quick_access.pin` / `.unpin`; the read needs no equivalent. |
| `GET /contacts/{contact_id}/companies` | companies granted to a contact | Already gated, in the handler body: it calls `_require_superadmin(db, current_user)` before doing anything. Adding a dependency would be a second, weaker gate. Covered by a test so the in-body check cannot be dropped unnoticed. |

### Deferred - needs a decision above the implementation seat

Listed here rather than gated, per the brief's rule against silently widening a grant. Each has a
frontend caller running under a role that lacks any candidate slug, so there is no mechanical
answer.

| Q | Routes | The problem |
|---|---|---|
| Q1 | `GET /contacts/` and the 7 other `contacts` GETs (`/{id}`, `/{id}/cs-routing`, `/cs-routing/candidates`, `/cs-routing/fields`, `/{id}/market-segments`, `/{id}/attachment-types`, `/{id}/access-agents`) | There is no `user_management.contacts.view` slug in `app/rbac/permission_registry.py` - the contacts resource only has `.portal_link`. (The prod DB additionally carries an orphan `user_management.contacts.edit`, created 2026-08-14, with no reference anywhere in the repo - not usable as precedent.) Registering a new slug is mechanical; deciding who gets granted it is not. Migration `298_external_integration_permissions` is explicit that a new permission reaches no existing role automatically, so the grant set must be chosen deliberately or the feature 403s for everyone but admin. Today the screen is reachable by all 125 assigned users via the topbar Apps dropdown, so "grant it to whoever uses it now" is not an answer. |
| Q2 | `GET /settings/` | Leaks `n8n_attachment_webhook_url`, `n8n_crm_chat_outbound_webhook_url`, `n8n_stock_inquiry_revise_webhook_url` (bearer-capability URLs), SMTP host/port/username/from, both default-approver names + emails, `health_notify_role_ids`/`_user_ids`, and every role id and name. `smtp_password` is correctly withheld. But gating on `user_management.settings.view` is not a pure narrowing: `hooks/useCurrencyFormat.ts`, `hooks/use-excel-accept.ts` and `PurchaseRequestDetail.tsx:316` read it from procurement screens gated on `procurement.purchase_requests.view`. The first two degrade silently to defaults; the PR-detail approver default would disappear. |
| Q3 | `GET /contact-access-types/` and `GET /market-segments/` | Cross-module reference reads. `contact-access-types/` is consumed by ~10 screens across marketing (promotions), forms, resource-management (files, trash, attachments), and master-data (brands, products) - `marketing_manager` and `marketing_executive`, 18 users between them, hold zero `user_management.*` grants, so any `user_management.*` slug breaks those screens. `market-segments/` has no registered slug of its own and is read from the contacts detail screen covered by Q1. |

### Out of scope - follow-up issue

The same seven files contain 40 WRITE routes (POST/PUT/PATCH/DELETE) on bare
`get_current_user`, including every `settings` mutation, all team and team-member mutation, all
access-agent and field-access mutation, and contact create/update/delete/bulk-delete. This PR is
read-gates only, per its brief. Full list and suggested slugs filed as **issue #174**, referenced
from the PR body.

## Approach

1. Swap `Depends(get_current_user)` for `Depends(require_permission("<slug>"))` on rows 1-13.
   Import `require_permission` where the file does not already import it (`teams.py`,
   `access_agents.py`, `contact_access_types.py` currently import only `get_current_user`).
   No handler body changes, no schema changes, no migration - every slug applied already exists in
   `permission_registry.py` and is already granted to the roles whose screens call these routes.
2. Per-route pytest: one 403 (caller lacking the slug) and one 200 (caller holding it), following
   `tests/test_user_respond_users_permission.py` from PR #168 - override `get_db` and
   `get_current_user`, monkeypatch `UserPermissionService.check_user_has_permission` against an
   `allow` set, Postgres `blank_session()` for the DB.
3. One structural coverage test over the mounted router, modelled on
   `tests/test_external_permission_coverage.py`: every GET in the seven files carries a permission
   dependency or sits in a commented exception allowlist. This is what stops route 14 from
   repeating route 1's history.
4. Two exception tests: quick-access self-scoping, and the contacts/companies superadmin check.

## Behaviour changes beyond the 403

- **The 13 gated routes now reject `X-API-Key` principals.** `require_permission` wraps
  `get_current_user`, not `get_current_user_or_api_key`, so an automation calling these paths with
  a key rather than a bearer token gets 401 where it previously got 200. Verified safe: no caller
  exists in `sorento_crm_mcp/`, in backend internal HTTP calls, or in any n8n workflow or doc -
  the only repo references to these paths are frontend callers, tests, and two URL-string builders
  (`respond_sync_handler.py:106`, `ai_assistant_service.py:3217`). It also matches the `users.py`
  precedent, where the gated reads use the same dependency. Named here because it is a real
  behaviour change that the audit table's slug column does not convey. Routes that genuinely need
  key access use `require_permission_with_api_key`; none of these 13 do.
- **`teams.py` had malformed indentation on exactly the four lines this PR targets** (six spaces
  before `current_user:` instead of four, on all four GET handlers, and on its write handlers too).
  A small tell that these handlers were hand-edited and skipped when the rest of the package was
  gated. The four GET lines are normalised because they were being rewritten anyway; the write
  handlers' identical quirk is left alone as out of scope.

## Test baseline (measured, not assumed)

The suite is not green on this branch to begin with, so the coder measured the baseline by
stashing the change, re-running, and re-applying:

- **8 failures pre-date this change** and are not ours: 5 `test_market_segment_routing.py::test_next_assignee_*`
  failing on `Permission required: integration.assignment.resolve`, plus
  `test_team_members_endpoint_segment_filter`, `test_team_members_response_shape_unchanged` and
  `test_next_assignee_regression_no_contact_id` failing on `user_management.teams.view` - all from
  the already-gated **external** router, whose fixture grants no permissions at all. Out of scope
  here; fixing them would muddy the diff.
- **8 failures are caused by these gates**, all fixture-side: the 7 in
  `test_agent_field_access_endpoint.py` and `test_market_segment_routing.py::test_member_segment_assignment_endpoints`.
  Each overrides `get_current_user` but never stubs `UserPermissionService.check_user_has_permission`,
  so the new dependency denies. Repaired by granting the slug in the fixture - never by loosening a gate.

## Risks

- **A gate lands on a route whose only live caller is an ungated screen** (rows 5 and 10, called
  from `/user-management/contacts/[id]`). Accepted deliberately: those routes return the access
  control matrix itself. The consequence is that the contacts detail page shows an empty or
  errored agents table for a user without `access_agents.view` - which is the correct outcome and
  is exactly what Q1 exists to resolve properly.
- **403 does not log the user out.** `lib/api.ts:193` is explicit that an RBAC 403 from one
  endpoint never clears the session, so the failure mode is a toast or an empty grid, not a
  logout loop.
- **No migration, so no head to merge.** `alembic heads` must still read a single head at the end.
