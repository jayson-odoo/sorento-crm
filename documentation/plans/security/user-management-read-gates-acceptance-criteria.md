# UAC - user-management read gates

**Status:** Acceptance contract for `PLAN-user-management-read-gates.md`. Written BEFORE
implementation. Follow-up to PR #168 (`GET /users/respond-users`), which fixed one route of
the same defect class.

Legend: each criterion is **Given / When / Then**, testable. **REG** = explicit regression guard.

There is no `Journey` section here on purpose. This is not a feature: no screen changes, no new
user-facing step, no data model. It is a permission dependency added to routes that already
exist and already serve the same screens. PRINCIPLES.md step 0 asks the journey to precede the
schema so the schema serves the user; nothing here proposes either. The equivalent framing is
the threat statement below, and every AC traces to it.

**Threat statement.** Every GET in the seven routers listed in the plan is `Depends(get_current_user)`
only. `config/menu.config.tsx` `permission:` keys hide sidebar links but do not guard routes -
there is no `middleware.ts` and no `RequireAccess` anywhere under `app/(protected)/user-management/`
- so the backend dependency is the only real gate. Any authenticated session, including a role
holding zero `user_management.*` permissions, can read the full contact directory (names, phone
numbers), the staff team rosters, the agent-to-contact access matrix, per-field ACL rows, and the
system settings blob (n8n webhook URLs, SMTP host/username, every role id and name).

---

## Item 1 - teams router read gates

UAC1.1 - **Given** a caller WITHOUT `user_management.teams.view`, **when** it calls
`GET /api/v1/user-management/teams/`, **then** the response is 403 and the detail names the slug.
UAC1.2 - **Given** a caller WITH `user_management.teams.view`, **when** it calls the same route,
**then** the response is 200 and carries the team list.
UAC1.3 - UAC1.1 and UAC1.2 hold identically for `GET /teams/{team_id}`,
`GET /teams/{team_id}/members`, and `GET /teams/{team_id}/members/{user_id}/market-segments`.
UAC1.4 (REG) - **Given** the live role grants, **then** every role that holds
`user_management.access_agents.view` also holds `user_management.teams.view` - so the team
dropdown on `/user-management/access-agents` and `MemberMarketSegmentEditor` on
`/user-management/access-agents/[id]`, both of which read teams data, keep working. A test
asserts the two slugs are registered so the pairing is checkable, not assumed.

## Item 2 - access-agents router read gates

UAC2.1 - **Given** a caller WITHOUT `user_management.access_agents.view`, **when** it calls any of
`GET /access-agents/`, `/access-agents/contact-access`, `/access-agents/neighbours`,
`/access-agents/{agent_id}`, `/access-agents/{agent_id}/teams`,
`/access-agents/{agent_id}/field-access`, `/access-agents/{agent_id}/contact-access`,
**then** each returns 403 naming the slug.
UAC2.2 - **Given** a caller WITH the slug, **when** it calls each of those seven routes, **then**
each returns 200 with its documented body.
UAC2.3 - **Given** `GET /access-agents/{agent_id}/field-access`, **then** the 403 fires BEFORE any
field-access row is read, so a denied caller learns nothing about which fields exist.

## Item 3 - contact-access-types admin reads

UAC3.1 - **Given** a caller WITHOUT `user_management.access_agents.view`, **when** it calls
`GET /contact-access-types/all` or `GET /contact-access-types/{code}`, **then** 403.
UAC3.2 - **Given** a caller WITH the slug, **then** both return 200.
UAC3.3 (REG) - `GET /contact-access-types/` (the active-only catalog) is NOT gated by this item -
see the documented exceptions. A test asserts it still answers 200 for a caller holding no
`user_management.*` permission at all, so the exception cannot rot into an accidental gate.

## Item 4 - structural coverage

UAC4.1 - **Given** the mounted user-management router, **when** the coverage test enumerates every
GET route in the seven files in scope, **then** each either carries a `require_permission` /
`require_any_permission` dependency, or appears in an explicit, commented exception allowlist.
UAC4.2 - **Given** a new ungated GET added to any of those routers tomorrow, **then** UAC4.1 fails.
This is the point of the item: a per-route test only covers routes someone remembered.
UAC4.3 - **Given** the exception allowlist, **then** each entry carries the reason inline, and the
list is short enough to read.

## Item 5 - documented exceptions (no code change, must stay true)

UAC5.1 - `GET /quick-access/` stays `Depends(get_current_user)`. **Given** any authenticated user,
**then** it returns only that user's own rows (`user_id == current_user["id"]`) - same self-scoped
family as `GET /users/me`. A test asserts user A's pins are not visible to user B.
UAC5.2 - `GET /contacts/{contact_id}/companies` needs no new dependency: it already calls
`_require_superadmin` in the handler body. A test asserts a non-superadmin gets denied.

## Item 6 - deferred, NOT in this PR

UAC6.1 - The `contacts` router GETs, `GET /settings/`, `GET /market-segments/` and
`GET /contact-access-types/` are named in the PR body with the concrete screen and role that
blocks a mechanical answer, and are NOT silently gated or silently widened.
UAC6.2 - The 40 ungated WRITE routes in the same seven files are recorded as a follow-up issue,
with the list, and referenced from the PR body. This PR is read-gates only. **Filed as issue #174.**

---

## Cross-cutting

- **Tests are Postgres-only** (`tests/_pg_fixture.py`), never sqlite, per PRINCIPLES.md. Each test
  seeds its own chain with a marker prefix; nothing is borrowed with `LIMIT 1` off an existing
  table, because CI's database is empty.
- **No frontend change in this PR.** Every gated route's live callers were mapped caller-by-caller
  (see the plan's audit table). All sit on screens whose menu entry already carries the matching
  slug, with two deliberate exceptions - `GET /access-agents/` and
  `GET /access-agents/{id}/field-access` are also called from the permission-free
  `/user-management/contacts/[id]` screen. Those two are gated anyway, because they return the
  access-control matrix; the ungated screen is Q1 in the plan, not a reason to leave ACL rows
  world-readable.
- Full `pytest` green in CI. `alembic heads` stays at a single head.
