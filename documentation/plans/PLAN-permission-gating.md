# PLAN - Permission gating across every route and every affordance

> Status: DRAFT 2026-08-10. Raised during the Form SLA Undo plan review as *"if the user is not
> allowed permission to delete, the button should be hidden - do a sweep on the entire system"*,
> then widened by the user on 2026-08-10: **"I want this delivery to cover all cause this is a
> security risk."**
>
> Decisions locked:
> 1. Backend enforcement and frontend hiding ship **together, in one delivery**.
> 2. Scope is **all verbs, reads included** - not delete, not writes only.
> 3. ~~This delivery goes before Form SLA Undo.~~ **Reversed by the user on 2026-08-10: Form SLA
>    Undo is built first** (`PLAN-form-sla-undo.md`). This plan stays fully specified and ready to
>    start; nothing about its content changes, only when it starts. The gap it describes remains
>    open in the meantime.
> 4. **Write implies read.** Holding `<resource>.add`, `.edit` or `.delete` satisfies a
>    `<resource>.view` check. Implemented as an implication inside
>    `UserPermissionService.check_user_has_permission`, NOT by writing three extra grant rows per
>    role - so the rule holds for roles created later without anyone remembering it.

## Permission implication

`check_user_has_permission(user, "x.y.view")` returns true when the user holds any of
`x.y.view`, `x.y.add`, `x.y.edit`, `x.y.delete`. One place, cached the same way the current check
is, and it removes a large slice of the P4 grant migration: any role that can already maintain a
resource needs no new grant to read it.

Scope of the rule: **within one resource only**. It says nothing about a user who holds no
permission on the resource at all - which is exactly the cross-feature lookup case below.

## The finding

Two scans over `sorento_crm_backend/app/api/v1` and `sorento_crm_frontend/app`.

### Backend - routes by guard

| Verb | Total | `require_permission` | superadmin | **auth only** | no recognised guard | token / api-key |
|---|---|---|---|---|---|---|
| GET | 380 | 119 | 6 | **181** | 63 | 11 |
| POST | 314 | 121 | 3 | **110** | 75 | 5 |
| PUT | 88 | 27 | 3 | **48** | 9 | 1 |
| PATCH | 26 | 15 | 0 | **10** | 1 | 0 |
| DELETE | 107 | 38 | 3 | **61** | 3 | 2 |
| **Total** | **915** | **320** | **15** | **410** | **151** | **19** |

**410 routes require login and check nothing else.** 229 of them are writes.

Verified by reading, not inferred:

- `order_management/orders.py:913` `delete_order` - `Depends(get_current_user)` only, no
  router-level dependency, hard delete.
- `complaints/complaints.py:348` `bulk_delete_complaints` - same shape.
- `order_management.orders.delete` exists in the registry **and is enforced on a different route
  in the same file** (line 900). This is inconsistency, not a missing concept. 58 delete slugs and
  313 permissions already exist.

### Frontend - affordances by gate

| Affordance | Files with the UI | Gated on `*.<verb>` | Ungated |
|---|---|---|---|
| add | 107 | 0 | **107** |
| edit | 101 | 1 | **100** |
| export | 17 | 0 | **17** |
| delete | 171 | 2 | **163** |

`useHasPermission` is used 78 times, but on page-level and feature-level gates - almost never on a
CRUD affordance.

### What the numbers do NOT say

Both caveats matter more now that scope is "everything", because over-reading them turns a real
problem into an inflated one.

- **"No recognised guard" (151) is not a hole count.** Sampling the 75 POSTs in that column:
  `login`, `signup`, `reset_password`, `verify_email`, `external/` API-key routes, and portal
  routes whose token dependency the scan did not name (`submit_draft_via_token`). Most are
  correctly public. This column needs triage, not enforcement.
- **"Auth only" (410) over-counts.** Some routes are correctly **ownership-scoped** rather than
  permission-scoped. Five were verified that way among the deletes: two portal-token routes,
  own-session revoke, coverage self-unsubscribe, own column config. The fraction across the other
  405 is unknown until triaged.

So the honest statement is: **410 routes have no permission check, an unknown but minority share
of which are legitimately scoped another way.** Triage is the first real work item, not the fix.

## The thing that will bite: enforcing reads

Writes are the easy half. Every write has an obvious owning resource and an obvious slug.

Reads do not. 181 auth-only GETs include the endpoints that feed **cross-feature dropdowns and
lookups**. A user whose job is complaints still has to read products, customers, warehouses and
users to fill a select. Requiring `master_data.products.view` on the products GET would 403 every
product dropdown for every role that was never granted products explicitly - which is most of
them, because until now nobody needed the grant.

Enforcing reads naively does not produce a locked-down system. It produces an application where
half the forms cannot be filled in, and the failure is diffuse and hard to attribute.

This is why the rollout below is shadow-first. **Do not skip it to save time.** The alternative is
discovering the grant gaps in production, one broken dropdown at a time.

### This is already happening, and the codebase already disagrees with itself

27 lookup-shaped GET endpoints (`/select`, `/options`, `/lookups/*`). Ten require the owning
module's `.view`; ten are authenticated-only; seven are portal or other. The same endpoint shape,
both answers:

| Gated on the owning `.view` | Authenticated only |
|---|---|
| `user_management/users/select` | `master_data/products/select` |
| `master_data/brands/select` | `order_management/customers/select` |
| `master_data/categories/select` | `procurement/suppliers/select` |
| `complaints/complaint_root_causes/select` | `system/companies/select` |
| `complaints/complaint_resolutions/select` | `lookup/{set_key}/options` |

`GET /user-management/users/select` requires `user_management.users.view`
(`users.py:132`) and is consumed from at least twelve screens outside user management -
`ComplaintsList`, `TicketWatchersSection`, `FormSLATrackerDetail`,
`ConversationSLATrackingDetail`, `IntegrationFormDialog`, `AuditLogsList`,
`AttachmentsInFolderPanel`, `RecipientPicker`, `CompanyAccessDialog` and others.

So a complaints-only role either already holds a User Management permission it has no business
holding, or that assignee dropdown is already empty for them. The cross-feature read problem is
not a prediction about enforcement - it is a live inconsistency that enforcement would spread to
every other lookup.

## Approach

### P0 - triage every route (the actual work)

Classify all 915 routes into exactly one bucket, recorded in a checked-in manifest so the decision
survives review and the CI test can read it:

| Bucket | Meaning | Action |
|---|---|---|
| `perm` | Acts on a shared resource | Add `require_permission("<module>.<resource>.<verb>")` |
| `perm_api` | Same, but a machine caller legitimately uses it | `require_permission_with_api_key` |
| `own` | Scoped to the caller's own rows | Leave, add a one-line comment saying why |
| `token` | Portal / approval-token ownership | Leave, comment |
| `public` | Unauthenticated by design (login, signup, reset) | Leave, comment |
| `lookup` | Cross-feature reference read | **Decided: same as `perm`.** Require the owning module's `.view`, and grant those slugs broadly enough that dropdowns keep working |

**Lookup decision (user, 2026-08-10): require the owning slug everywhere.** No `reference.lookup.view`
shortcut and no auth-only exception. All 27 lookup-shaped endpoints get the owning module's
`.view`, which makes the ten currently-auth-only ones consistent with the ten already gated.

Consequence to carry into P4, stated because it is the cost of this choice: **the same slug gates
the lookup, the list and the detail page.** Granting `master_data.products.view` to a complaints
role so its product dropdown works also lets that role open the full products list, detail and
export. Menu configuration still controls whether the page appears in navigation, but the route is
reachable by URL. If that coupling is unwanted later, the fix is finer-grained slugs
(`<resource>.lookup` distinct from `<resource>.view`), not a change to this rule - and that is a
registry change, so it is cheaper to decide before P4 than after.

This bucket is therefore no longer a product decision at triage time; it is mechanical. The
product decision moved to P4: **which roles get which view slugs**, and that list is now larger
than it would have been under the shared-slug option.

Slugs mostly exist already - `_crud()` in `permission_registry.py` emits
`{module}.{resource}.{view,add,edit,delete}` for every registered resource, so this is
classification work, not naming work.

### P1 - shadow mode, then enforce

Add the dependency everywhere in P0's `perm` bucket, but behind a mode flag:

- `PERMISSION_ENFORCEMENT=shadow` - evaluate the check, **allow the request either way**, and write
  a row to a new `permission_denial_log` (route, method, slug, user, role slugs, timestamp) when it
  would have denied.
- `PERMISSION_ENFORCEMENT=enforce` - the check bites.

`api_call_log` cannot be reused for this: its middleware only logs `_LOGGED_PREFIX` paths or
`X-Source`-tagged calls, so ordinary in-app traffic never reaches it. A purpose-built table is
simpler than widening that middleware.

Run shadow on real traffic, then read the log as a work list: every distinct (role, slug) pair in
it is either a grant to make or a route classified into the wrong bucket. Fix until the log goes
quiet, then flip to enforce. Flipping is one env var, and reverting is the same var - which is the
property that makes this safe to ship.

**Reads and writes can flip independently.** Recommended: enforce writes first, keep reads in
shadow a while longer, because reads are where the dropdown breakage lives.

### P2 - the standing invariant

A test that walks the FastAPI route table and asserts every route either declares a permission
dependency or appears in the P0 manifest with a bucket and a reason. A new ungated route then
fails CI instead of waiting for the next sweep. This is the part that stops the problem coming
back, and it is cheap relative to P0.

### P3 - frontend

Not 390 hand edits. A shared gate:

- `useCan(verb, resource)` over the existing `useHasPermission`.
- Teach the **shared surfaces** to accept a resource slug and render nothing without the right
  verb: `ConfirmDeleteDialog`, the DataGrid row-actions menu, the bulk-action toolbar, the "Add"
  toolbar button, the export button.
- Sweep the remainder file by file, list-page first.

**Hidden, not disabled.** An action you cannot perform is not shown - a disabled button with no
explanation just generates support tickets.

The frontend can only be finished after P0, because the gate needs each screen's resource slug -
the same classification the backend needs.

### P4 - grants

Before enforcement flips, the roles already doing the work must hold the slugs. Two inputs:
the shadow log (what is actually being called, by whom) and the menu configuration (what each role
is already shown). Where those disagree, the shadow log wins - the menu says what someone can see,
not what they do.

## Cost, stated plainly

915 route decisions, ~390 frontend files, a new table, a middleware mode, a CI test and a grant
migration. The mechanical parts are small; **P0 triage and P4 grants are the bulk of it**, and
neither can be rushed without producing the broken-dropdown outcome.

If that is too large to take in one delivery, the natural split that preserves the security
outcome is: enforce **all writes** first (229 routes, unambiguous slugs), keep **reads in shadow**
across the same delivery, and flip reads once the log is quiet. That is still "cover all" - it
covers every route - it just does not flip every switch on the same day.

## Risks

1. **Enforcing reads breaks cross-feature lookups.** The dominant risk. Mitigated by the `lookup`
   bucket in P0 and by reads staying in shadow longer than writes.
2. **Machine callers.** The `X-API-Key` principal has no RBAC grants and depends on
   `EXTERNAL_API_KEY_ACT_AS_USER_ID`. Every machine-reachable route needs
   `require_permission_with_api_key` and the act-as user needs the slug, or n8n and MCP break
   silently. Note the existing warning on that helper: do not put it on a write endpoint without
   the second real-user gate that the AI-assistant layer applies.
3. **Admin lockout - resolved.** `check_user_has_permission` (`user_service.py:1107`) returns True
   for `superadmin` and `admin` before consulting role permissions, so enforcement cannot lock
   admins out. Verified, not assumed.
4. **A wrong bucket is invisible.** A route misfiled as `own` keeps a real hole open while looking
   handled. The manifest must carry a reason per route so review can challenge it, and `own`
   entries deserve the closest reading.
5. **RBAC cache.** `check_user_has_permission` caches for `RBAC_CACHE_TTL_SECONDS` (default 30s).
   A grant made during rollout takes up to that long to take effect - fine, but say so in the
   runbook so nobody concludes the grant failed.

## Open

- Confirm the split: flip writes and reads together, or writes first with reads in shadow?
  Recommended: the latter.
- How long shadow mode runs before the first flip.
- Whether `<resource>.lookup` should be split from `<resource>.view` in the registry, given the
  coupling noted in P0. Cheaper to decide before P4 than after.
- Does this delivery also cover the frontend's page-level menu gating, or only the in-page
  affordances?
