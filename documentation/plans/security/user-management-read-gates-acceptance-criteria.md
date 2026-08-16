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

## Item 6 - escalated groups Q1-Q3, decided and now IN this PR

The four route groups below were escalated rather than guessed, because each had a frontend caller
under a role holding no candidate slug. The decision came back "gate them", with the grant sets
recorded in the plan. These ACs cover that second wave.

### Item 6a - Q1, the contacts directory

UAC6a.1 - `user_management.contacts.view` is registered in `app/rbac/permission_registry.py`.
UAC6a.2 - **Given** a caller WITHOUT it, **when** it calls any of the 8 contacts GETs (`/`,
`/{id}`, `/cs-routing/candidates`, `/cs-routing/fields`, `/{id}/cs-routing`,
`/{id}/market-segments`, `/{id}/attachment-types`, `/{id}/access-agents`), **then** each returns
403 naming the slug; **with** it, each returns 200.
UAC6a.3 - A migration registers the slug AND explicitly grants it to `admin`, `superadmin`,
`director`, `warehouse_manager` and the three `integration_*` roles. Registering without granting
is the failure mode migration 298's docstring warns about, so the grant is the AC, not the
registration.
UAC6a.4 - The migration is idempotent, skips a role absent from the database with a log line rather
than crashing, and leaves `alembic heads` reporting exactly ONE head. Revision id is <= 32 chars.
UAC6a.5 - `GET /contacts/{contact_id}/companies` is NOT given a dependency; it keeps its in-body
`_require_superadmin` gate (UAC5.2 still holds).
UAC6a.6 - The orphan `user_management.contacts.edit` row in the prod DB is **not deleted** and is
flagged in the PR body.

### Item 6b - Q2, settings

UAC6b.1 - **Given** a caller WITHOUT `user_management.settings.view`, **then** `GET /settings/`
returns 403; **with** it, 200 and the body is unchanged from today.
UAC6b.2 - `GET /settings/app-config` returns 200 for a caller holding ZERO permissions.
UAC6b.3 (REG - SECURITY) - **Given** a `system_settings` row seeded with recognisable non-null
values in `smtp_*`, the three `n8n_*` webhook URLs and the health notify id fields, **when**
`/app-config` is read, **then** the response keys are EXACTLY the six documented fields and none of
those sensitive keys appear. Seeding the sensitive values first is what makes this prove
suppression rather than pass on an empty row.
UAC6b.4 - `/app-config` answers correctly when no `system_settings` row exists.
UAC6b.5 (REG) - The three procurement consumers move onto `/app-config` and keep working for
`purchasing_manager` / `project_sales_manager`: currency formatting still renders, the PR-detail
default approver is still offered when sending an approval link, and the Excel accept hook still
yields its default. No silent degradation.
UAC6b.6 - Every moved consumer is **rekeyed** off `['system-settings']`. That key is shared with
the settings admin layout, which still fetches the full blob; leaving a moved consumer on it would
let react-query serve one shape where the other is expected.
UAC6b.7 - `hooks/use-excel-accept.ts` behaviour is byte-identical: it reads a field that is not a
column on `SystemSetting` and never has been, so it has always returned `DEFAULT_ACCEPT`. The field
is NOT added to the projection or the model.

### Item 6c - Q3, reference data

UAC6c.1 - `user_management.reference_data.view` is registered.
UAC6c.2 - **Given** a caller WITHOUT it, **then** `GET /contact-access-types/` and
`GET /market-segments/` return 403; **with** it, 200.
UAC6c.3 - The same migration grants it to every role holding at least one of
`forms.forms.view`, `marketing.promotions.view`, `master_data.brands.view`,
`master_data.products.view`, `resource.attachments.view`, `resource.attachment_directories.view`,
`resource.attachment_types.view` - **derived in SQL from those slugs**, not hardcoded by role name.
UAC6c.4 (REG) - The ~10 consuming screens outside user-management (promotions, forms, files, trash,
attachments, brands, products) keep working for `marketing_manager` and `marketing_executive`, who
hold zero `user_management.*` grants otherwise. This is the whole reason the slug is new and
low-privilege rather than reusing `access_agents.view`.

### Item 6d - coverage stays honest

UAC6d.1 - `_EXCEPTION_ALLOWLIST` in the structural test ends as exactly three entries -
`GET /quick-access/`, `GET /contacts/{contact_id}/companies` and `GET /settings/app-config` - and
the gated-path assertion is updated from 13 to the new exact set of 24. No assertion is weakened to
make it pass. The allowlist is itself pinned by a set-equality test, so "one entry left and another
joined" cannot net out green. (Drafted as two entries before the Q2 projection route existed;
`app-config` is the third by UAC6d.2.)
UAC6d.2 - `GET /settings/app-config` is either gated or allowlisted with its reason, like every
other GET in scope - a new ungated route must not be introduced by the fix for an ungated route.

UAC6.1 (superseded) - the four groups above are no longer deferred; they are gated here.
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
