# PLAN - user-management read gates

**Status:** In progress. Phase 2 (backend + tests) plus the frontend work the gates forced: the
three consumers moved onto the `/settings/app-config` projection and its cache-invalidation fix,
the menu / user-detail-tab permission alignment (`menu.config.tsx`, `users/[id]/layout.tsx`), the
`TraceSettingsCard` load-failure hardening, and the deletion of `lib/db.ts`. No Phase 1 prototype.
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

### Gated after escalation (Q1-Q3 decisions, see below)

| # | Route | Returns | Slug applied |
|---|---|---|---|
| 14 | `GET /contacts/` | full respond-contact directory (names, phone numbers) | `user_management.contacts.view` |
| 15 | `GET /contacts/{contact_id}` | one contact | `user_management.contacts.view` |
| 16 | `GET /contacts/cs-routing/candidates` | tier-1 CS team member roster | `user_management.contacts.view` |
| 17 | `GET /contacts/cs-routing/fields` | routable predicate field metadata | `user_management.contacts.view` |
| 18 | `GET /contacts/{contact_id}/cs-routing` | a salesman's CS-PIC pins | `user_management.contacts.view` |
| 19 | `GET /contacts/{contact_id}/market-segments` | a contact's segment codes | `user_management.contacts.view` |
| 20 | `GET /contacts/{contact_id}/attachment-types` | document types a contact may retrieve | `user_management.contacts.view` |
| 21 | `GET /contacts/{contact_id}/access-agents` | which agents may see this contact | `user_management.contacts.view` |
| 22 | `GET /settings/` | full settings blob (n8n webhook URLs, SMTP, roles list) | `user_management.settings.view` |
| 23 | `GET /contact-access-types/` | active access-type catalog | `user_management.reference_data.view` |
| 24 | `GET /market-segments/` | market segment catalog | `user_management.reference_data.view` |

Plus one new route, `GET /settings/app-config`, authenticated but deliberately ungated - the narrow
projection that keeps the procurement consumers working once row 22 is gated.

### Gated after an independent review found the scope hole (rows 25-26)

| # | Route | Returns | Screens today | Screen gate today | Slug applied |
|---|---|---|---|---|---|
| 25 | `GET /system-logs/` | the whole system audit log - event, description, entity id/type, IP address, and the acting user's name/email/avatar | `/user-management/logs` | `logs.view` | `user_management.logs.view` |
| 26 | `GET /system-logs/users/{user_id}` | the same, for one user (it delegates straight to row 25) | `/user-management/users/[id]` activity panel | `users.view` | `user_management.logs.view` |

No new slug and no migration: `user_management.logs.view` is already in
`permission_registry.py` and is already the `permission:` on the `/user-management/logs` menu entry,
so the dependency simply makes the menu's claim true. `POST /system-logs/` in the same file is left
alone - writes are issue #174.

**Why these two were missed, which matters more than the two routes.** The structural coverage test
in work item 4 exists precisely to catch this, and could not: its `_IN_SCOPE_MODULES` was a
hardcoded set of the seven module names this plan's audit table walked, and `system_logs.py` is an
eighth. A sweep that only looks where someone remembered to point it inherits the failure mode of
the per-route tests it backstops. The scope is now the whole `app.api.v1.user_management` package,
matched on the module path prefix, so a router file added tomorrow is in scope with nothing to
update. See UAC Item 7.

That widening pulls in four more genuinely ungated GETs, all self-scoped, all added to the
allowlist with their filter recorded (see the exceptions table below), and twelve already-gated
reads in `users.py` / `roles.py` / `permissions.py` - so the gated-path exact set goes 24 -> 38.

### Documented exceptions - deliberately NOT gated

| Route | Returns | Why not gated |
|---|---|---|
| `GET /quick-access/` | the caller's own pinned menu entries | Self-scoped: the query filters `user_id == current_user["id"]`, so it discloses nothing about anyone else - the same family as `GET /users/me` and `GET /users/me/permissions`, which are also `get_current_user`. It also fires on every page load for every user from the app shell (`quick-access-block.tsx:34`, `menu-item-pin-button.tsx:24`), and in both components the `useQuickAccess()` call sits ABOVE the permission bail-out, so a gate would 403 on every page render for every user without pin/unpin. The sibling POST/PATCH/DELETE are correctly gated on `menu.quick_access.pin` / `.unpin`; the read needs no equivalent. |
| `GET /contacts/{contact_id}/companies` | companies granted to a contact | Already gated, in the handler body: it calls `_require_superadmin(db, current_user)` before doing anything. Adding a dependency would be a second, weaker gate. Covered by a test so the in-body check cannot be dropped unnoticed. |
| `GET /users/me` | the caller's own profile | Self-scoped: reads `current_user["id"]`. Same family as `/quick-access/`. |
| `GET /users/me/permissions` | the caller's own effective permission slugs | Self-scoped: reads `current_user["id"]`. It is what the frontend RBAC layer runs on, and it discloses only what the caller could discover by clicking around. |
| `GET /impersonation/current` | the caller's own active impersonation session, if any | Self-scoped: filters `ImpersonationSession.admin_user_id == real_user["id"]` and `ended_at IS NULL`. It takes `get_real_user`, not `get_current_user`, so an impersonated session cannot read it as somebody else either. |
| `GET /contact-impersonation/current` | the caller's own active contact-impersonation session, if any | Self-scoped, same shape: `ContactImpersonationSession.admin_user_id == real_user["id"]` + `ended_at IS NULL`, on `get_real_user`. |
| `GET /settings/app-config` (new) | `currency`, `currency_format`, and the four default-approver id/email fields | Authenticated-only by design. It is the projection that lets the procurement consumers keep working now that the full blob is gated, so a permission on it would defeat its own purpose. What makes that safe is the pydantic `response_model`: six declared fields, and anything not declared is dropped on serialization rather than leaking because a dict builder grew a line. Its test seeds the SMTP, n8n webhook and health-notify fields with recognisable values first, so it proves suppression rather than passing on an empty row. |

### Q1-Q3 - escalated, decided, and now gated in this PR

These three groups each had a frontend caller running under a role holding no candidate slug, so
there was no mechanical answer and the grant set was a product call rather than an engineering one.
They were escalated rather than guessed. **All three came back "gate them"**, with the grant sets
below. The problem statements are kept verbatim because they are the reasoning the decision was
made against.

Resolution summary:

- **Q1 - gate the 8 contacts GETs.** New slug `user_management.contacts.view`, granted to `admin`,
  `superadmin`, `director`, `warehouse_manager` and the three `integration_*` roles. The orphan
  `user_management.contacts.edit` row found in the prod DB is **left in place, not deleted**, and is
  flagged in the PR body: it has no repo reference and no grant path, and removing a live permission
  row is not this PR's call to make.
- **Q2 - gate `GET /settings/` on `user_management.settings.view`, and add a narrow projection**
  `GET /settings/app-config` (authenticated, no permission) carrying exactly `currency`,
  `currency_format` and the four default-approver id/email fields. The three procurement consumers
  move onto it in this PR, so `purchasing_manager` and `project_sales_manager` keep working with no
  silent degradation. Nothing sensitive is in the projection, and its `response_model` is what makes
  that enforceable rather than aspirational.
- **Q3 - gate both reference reads on a new low-privilege slug** `user_management.reference_data.view`,
  granted to every role that already holds a view permission for one of the consuming screens
  (`forms.forms.view`, `marketing.promotions.view`, `master_data.brands.view`,
  `master_data.products.view`, `resource.attachments.view`, `resource.attachment_directories.view`,
  `resource.attachment_types.view`). That resolves to `admin`, `superadmin`, `director`,
  `warehouse_manager`, `warehouse_executive`, `marketing_manager`, `marketing_executive`,
  `purchasing_manager`, `purchasing_executive` and the three `integration_*` roles. The migration
  derives that set in SQL from the seven slugs rather than hardcoding role names, so an install with
  a different role set gets the right answer. Net effect: the two catalogs are no longer readable by
  any authenticated caller, and no consuming screen breaks.

Review follow-up on that derivation: the consumer list is now NINE slugs, not seven -
`user_management.contacts.view` and `user_management.access_agents.view` were added, because the
in-package screens read the same two catalogs (the contact detail page's market-segment section and
its edit dialog, the access-agents member segment editor). `contacts.view` is granted by this very
migration, so the derivation must stay ordered after that grant and inside the same transaction;
a test pins that direction. The review that raised this also claimed a concrete stranded role, and
that half was wrong: on the live database all six grantees of `contacts.view` (admin, director,
warehouse_manager and the three `integration_*`) already hold all seven original consumer slugs and
therefore already derived `reference_data.view`. The "director" it cited is the migration test's
synthetic fixture role, seeded holding no consumer slug precisely to prove the negative direction of
the derivation. The change is made on the structural argument - the stated rule is "every role that
can open a consuming screen", and two consuming screens were missing from the list - not because
anyone was stranded.

One correction the Q2 investigation turned up: of the "three consumers" that made gating
`GET /settings/` risky, only two were ever functional. `hooks/use-excel-accept.ts` reads
`settings.excel_upload_accept_extensions`, which **is not a column on the `SystemSetting` model and
never has been**, and the hook already returns `DEFAULT_ACCEPT` on any non-2xx. Review then took that
one step further: `AppConfigResponse` pins six fields, so pydantic drops the key before it can reach
the client - the read cannot succeed by construction, not by accident. The fetch is therefore gone
and the hook returns the constant; behaviour is unchanged, the column is still not added, and the
projection is still not widened. Making the extensions configurable needs a column first.

Two consumer screens read a route gated on a slug outside their own screen's gate, and they are
treated differently on purpose. The AI Agents detail screen (`access_agents.view`) renders
`MemberMarketSegmentEditor`, which reads `GET /teams/{team_id}/members/{user_id}/market-segments`
(`teams.view`); it is left exactly as it is, because every role holding `access_agents.view` on the
live database also holds `teams.view` (admin, director, warehouse_manager and the three
`integration_*`), so the panel works for every role that can reach the screen - that pairing is
UAC1.4 in the acceptance criteria, and hiding a working panel would be inventing a problem. The user
detail page's Activity Logs tab is the opposite case: it reads `GET /system-logs/users/{user_id}`
(`logs.view`), which a role holding only `users.view` does not have, so the tab is rendered only
when the caller holds `logs.view` rather than always erroring on click. Neither gate is widened.

The two catalogs are gated on different slugs and the sidebar has to match route by route, not
screen by screen: `/user-management/market-segments` reads `GET /market-segments/`
(`reference_data.view`), while `/user-management/contact-access-types` reads
`GET /contact-access-types/all` - the admin variant, gated on `access_agents.view`, not the
`reference_data.view` catalog read. The menu entries carry those two slugs respectively.

| Q | Routes | The problem as escalated |
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
   `tests/test_external_permission_coverage.py`: every GET in the `app.api.v1.user_management`
   package carries a permission dependency or sits in a commented exception allowlist. This is what
   stops route 14 from repeating route 1's history. (Scoped to seven named modules at first, which
   is how rows 25-26 slipped through; it is a package-prefix match now.)
4. Two exception tests: quick-access self-scoping, and the contacts/companies superadmin check.

## Behaviour changes beyond the 403

- **A fifth, dead frontend reader of the full blob was found and deleted.**
  `sorento_crm_frontend/lib/db.ts` held `getSettings()`, which read the full settings endpoint. It
  had zero callers, as did its only sibling export `isUnique`, so the whole 44-line module went
  rather than half of it. Verified before deleting: no import of `lib/db`, `./db` or any specifier
  ending in `/db` anywhere in the frontend, and neither of its own imports (`SystemSetting`,
  `apiFetch`) was orphaned by the removal. `tsc --noEmit` output is byte-identical before and after
  (26 pre-existing errors in unrelated scm/products/prompts files, unchanged), and `lib/` lost 3
  pre-existing `no-unused-vars` errors that lived in the deleted file.
- **All 24 gated routes now reject `X-API-Key` principals.** `require_permission` wraps
  `get_current_user`, not `get_current_user_or_api_key`, so an automation calling these paths with
  a key rather than a bearer token gets 401 where it previously got 200. Verified safe: no caller
  exists in `sorento_crm_mcp/`, in backend internal HTTP calls, or in any n8n workflow or doc -
  the only repo references to these paths are frontend callers, tests, and two URL-string builders
  (`respond_sync_handler.py:106`, `ai_assistant_service.py:3217`). It also matches the `users.py`
  precedent, where the gated reads use the same dependency. Named here because it is a real
  behaviour change that the audit table's slug column does not convey. Routes that genuinely need
  key access use `require_permission_with_api_key`; none of these 24 do.
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

## Simplicity audit

Checked against the standing principle: build the simplest thing that solves the problem end to
end; no new abstraction, indirection or knob unless the direct path is proven inadequate and the
proof is nameable. Three pieces of this PR add something, and each has to earn it:

- **`user_management.reference_data.view` (new slug).** The direct path was reusing
  `user_management.access_agents.view`, which the external surface already maps this resource to.
  Proven inadequate: `marketing_manager` and `marketing_executive`, 18 users, hold zero
  `user_management.*` grants, and the catalog is read by ~10 screens across promotions, forms,
  files, trash, attachments, brands and products. That slug would 403 all of them. The proof is the
  role-grant query, not a preference.
- **`GET /settings/app-config` (new route).** The direct path was gating `GET /settings/` and
  accepting the consequences. Proven inadequate: `useCurrencyFormat` and `PurchaseRequestDetail`
  read it from screens gated on `procurement.purchase_requests.view`, held by roles with no
  settings grant, so the PR-detail default approver would silently vanish. Kept as narrow as it can
  be: six fields, pinned by a `response_model` rather than a hand-built dict, no config, no knob.
- **The structural coverage test.** Not new machinery: it copies the shape of the existing
  `tests/test_external_permission_coverage.py`. It exists because this PR is itself the second
  round of "someone missed a route" (PR #168 was the first), so the failure mode is proven, not
  hypothetical.

Deliberately NOT added, having considered them: no per-resource permission helper, no decorator
wrapper over `require_permission`, no settings-projection config, no feature flag to stage the
gates, and no "floor" of admin roles hardcoded into the reference-data grant (an earlier draft had
one; it was removed because deriving the set in SQL already covers every install that has a role
able to open the consuming screens).

Deleted rather than kept: `sorento_crm_frontend/lib/db.ts`, a 44-line module whose two exports
(`isUnique`, `getSettings`) both had zero callers repo-wide. `getSettings` read the full settings
blob this PR just gated, so leaving it would have left a dead reader of a newly gated endpoint
looking like a live consumer somebody missed.

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
