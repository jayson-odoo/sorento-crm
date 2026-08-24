# PLAN - module access gates + sidebar reorganisation

**Status:** Planned, not started. Grilled 2026-08-24 with the user; decisions recorded below.
**UAC:** `documentation/plans/security/module-access-gates-acceptance-criteria.md`
**Classification:** CORE (sidebar, `RequireAccess`, query error handling) + per-module wiring for
`scm`, `projects`, `dealer_kit`, and the Ideas embed.
**Branch:** `fix/module-access-gates` (worktree `.claude/worktrees/module-access-gates`).
**Follows:** `PLAN-user-management-read-gates.md` (same defect class: menu `permission:` is
cosmetic, only the backend gates). `PLAN-permission-gating.md` (the 410-route backend sweep).

## The user's ask

1. Supply Chain, Project Sales, Ideas and Dealer Kit must be invisible AND unreachable to a user
   whose role holds no permission for them. Sidebar hides the module; a typed URL lands on the
   existing `AccessDenied` page ("You don't have access to this page", shield, "Back to
   dashboard"), not on a page shell that toasts `Permission required: scm.dashboard.view` once per
   query.
2. Move Fulfilment Planning, Plans, Order Inquiries, Planning changes and Forecast & Reports from
   Project Sales to Supply Chain.
3. The sidebar is too long (20 groups, ~140 flat leaves). Regroup under upper-case section
   headings and fold long groups into sub-groups.

Decisions taken with the user:

- The four modules are not live, so role assignment of the new/changed slugs is out of scope.
  Seeds grant `superadmin` + `admin` only; the customer assigns the rest in Roles.
- "Planning changes" moves with the other four (it is planning, not pipeline).
- "Project Sales Admin" (Purchase Requests, Sponsorship Forms) folds into a single Forms group.
  Not confirmed explicitly; flagged here so it can be reverted in review with one edit.
- Section headings render as upper-case labels (`AccordionMenuLabel`); accepted.
- Separate PR from the SCM fixes lane. Touches four modules and the shell, not SCM logic.

## What is true today (audit 2026-08-24)

| Module | Sidebar | Page guard | Backend | Deep URL without permission |
| --- | --- | --- | --- | --- |
| SCM `/scm` | `moduleKey: scm` + per-leaf slug | none (0/13 pages) | `require_permission*` on all 20 route files | shell renders, every query 403s, one red toast per query |
| Project Sales | `moduleKey: projects` + per-leaf slug | `RequireAccess` on 27/33; Series, Price Floors and their detail pages unguarded; every guard checks `projects.projects.view` even where the nav slug is `projects.types.view` | strong | denied page on guarded routes, toasts on the six |
| Ideas `/ideas` | no slug, no moduleKey, visible to everyone | none | `get_current_user` only (`integrations/ideation_embed.py:39-42`); no `ideas`/`ideation` view slug exists | renders and works for any logged-in user |
| Dealer Kit | no slug, no moduleKey, visible to everyone (comment at `menu.config.tsx:428-435` says "wait for seeds"; migration 309 already seeded the module row + six slugs, comment is stale) | none (0/12 pages) | strong (`dealer_kit.*`; `selections.py` ownership-only by design) | shell + toasts `Permission required: dealer_kit.page.view` |

Cross-cutting facts that shape the fix:

- No `middleware.ts`, no route-to-permission registry. The only generic route guard is
  `app/components/module-route-guard.tsx` (module-level via `lib/route-module-map.ts`, which lists
  `/scm` but not `/project-sales`, `/dealer-kit`, `/ideas`).
- `RequireAccess` (`app/components/common/RequireAccess.tsx`) already renders `AccessDenied`
  before children mount, so a guarded page fires no queries and produces no toasts. It is the
  right primitive; it is simply not applied.
- The toast is the global `QueryCache.onError` in `providers/query-provider.tsx:18-45`, which
  shows `error.message` (the raw FastAPI `detail`) once per failed query.
- `dealer_kit.*` slugs live only in migration 309, not in `app/rbac/permission_registry.py`, so a
  create_all database (CI) has none of them. SCM already fixed this for itself
  (`permission_registry.py:557-562` explains why).
- `sidebar-menu.tsx` splits the menu at the item titled `User Management` to insert
  `<QuickAccessBlock/>`; the heading filters pass every heading through unfiltered, so a section
  whose groups are all hidden would leave an orphan label.
- `config/menu.config.test.ts` already asserts on the "Planning changes" entry; it must be updated
  to the new location, not deleted.

## Design

Simplest thing that works: no middleware, no registry. One `RequireAccess` per module subtree,
one slug for Ideas, config edits for the sidebar, one dedupe in the toast path.

### Slice 1 - Ideas gets a permission (backend first, test first)

- `app/rbac/permission_registry.py`: add `ideation.board.view` ("View the Ideas board") under a
  new `ideation` group, next to the existing `integration.ideation.submit`.
- Migration `NNN_ideation_board_view_perm.py`: insert the slug if absent; grant to `superadmin`
  and `admin` role rows if present. Idempotent, CI-safe (no data assumed).
- `app/api/v1/integrations/ideation_embed.py`: swap `Depends(get_current_user)` for
  `Depends(require_permission("ideation.board.view"))` on the mint route(s). The route stays
  outside `MODULE_GUARD_STRICT` (no module row; not adding one).
- Test: `tests/test_ideation_embed_permission.py` - user without the slug gets 403 with
  `Permission required: ideation.board.view`; user with it gets past the permission dependency
  (the upstream call is mocked or the dormant-config 404 is accepted as "past the gate").

### Slice 2 - Dealer Kit registry parity

- `permission_registry.py`: add the six `dealer_kit.*` slugs with the labels migration 309 uses,
  so create_all databases carry them. Test asserts registry and migration agree on the slug set.
- `lib/route-module-map.ts`: add `/dealer-kit -> dealer_kit`, `/project-sales -> projects`.
  `/ideas` has no module; leave it out.

### Slice 3 - Page guards, one layout per subtree

Client layouts wrapping `children` in `RequireAccess`:

| File | Slug |
| --- | --- |
| `app/(protected)/scm/layout.tsx` | `scm.dashboard.view` |
| `app/(protected)/dealer-kit/layout.tsx` | `dealer_kit.page.view` |
| `app/(protected)/ideas/layout.tsx` | `ideation.board.view` |
| `app/(protected)/project-sales/layout.tsx` | `projects.projects.view` (keeps the 27 page-level guards working; they become redundant, leave them) |

Per-leaf tightening on top, page-level `RequireAccess` where the nav slug differs from the
subtree slug:

- `/scm/policies` -> `scm.policy.manage`
- `/scm/reorder`, `/scm/loading-plan`, `/scm/incoming`, `/scm/simulation` -> `scm.reorder.run`
- `/project-sales/series`, `/project-sales/series/[seriesId]`, `/project-sales/price-floors`,
  `/project-sales/price-floors/[ruleId]`, `/project-sales/setup/**` -> `projects.types.view`
- `/project-sales/parties/**` -> `projects.parties.view`

The moved SCM pages (Fulfilment Planning, Plans, Order Inquiries, Planning changes, Forecast &
Reports) keep their `/project-sales/*` paths and `projects.projects.view` slug in this PR. Moving
the route folders is a separate, mechanical change; the ask is about the menu.

`RequireAccess` and the sidebar both fail open while permissions load (loader vs. full menu);
`useHasPermission` fails closed. Leave as is. The loader hides the page until resolution, so
nothing leaks, and the sidebar flash is cosmetic. Recorded so a reviewer does not re-open it.

Tests (vitest): each new layout renders `AccessDenied` and no child when the slug is absent, the
child when present. Mock `usePermissions`.

### Slice 4 - Denied UX for anything still unguarded

`providers/query-provider.tsx` `QueryCache.onError`: when the error is a 403 whose message starts
with `Permission required:` / `One of these permissions required:`, show ONE toast with id
`permission-denied` and copy "You don't have permission to view this. Ask an administrator." The
sonner `id` dedupes the stack. Other errors unchanged. `extractApiError` already returns the
detail string; the status is read off the thrown error where available, else the prefix match is
enough. Test: three concurrent 403s produce one toast; a 500 still produces its own.

### Slice 5 - Sidebar reorganisation (`config/menu.config.tsx`, `MENU_SIDEBAR` only)

Paths do not change. Every leaf keeps its `permission` / `permissionsAny` / `superadminOnly`;
every group keeps its `moduleKey`. Only titles, nesting and section headings change.

```
OVERVIEW
  Dashboards
  Ideas                                  permission: ideation.board.view
SALES
  Project Sales            (projects)    Pipeline, Leads, Awaiting Acceptance, My Tasks,
                                         Stock Claims, AutoCount Differences, Parties
                                         Configuration > Setup, Series, Price Floors
  Delivery Orders          (order)       Delivery Orders, Delivery Order Status, Customers
  Marketing                (marketing)   Promotions > (as is), Campaigns
SUPPLY CHAIN
  Supply Chain             (scm)         Dashboard
                                         Planning > Reorder Planning, Loading Plan, Simulation,
                                                    Market Signals, Policies
                                         Project Demand > Fulfilment Planning, Plans,
                                                    Order Inquiries, Planning changes,
                                                    Forecast & Reports   (moved; slugs unchanged)
                                         Orders > Sales Orders, Purchase Orders,
                                                    Proforma Invoices, Incoming Containers
  Procurement              (procurement) as is
  Inventory                (inventory)   as is
CATALOGUE
  Products                 (product)     Products > All Products, Product Attachments
                                         Specifications > Product Specifications,
                                                    Spec Verification, Flyer Spec Proposals
                                         Reference Data > Product Categories, Brands,
                                                    Units of Measure, Certificates
  Dealer Kit               (dealer_kit)  Catalogue Pages, Editions
                                         Library > Product Collections, Tile Designs,
                                                    Brochure Images, Flyers, Bundles
                                         Room Designer > Room Designer, Design Summary
CUSTOMER SERVICE
  Customer Service         (sla)         Conversations, My Team Tasks, KPI Dashboard,
                                         Message Snippets
                                         Complaints > Complaints, Root Causes, Resolutions
                                                    (moduleKey complaints on the sub-group)
                                         SLA > SLA Policies, Conversation SLA Tracking,
                                                    Form SLA Tracking, Form SLA Configuration,
                                                    SLA Event Logs
WORKSPACE
  Forms                                  Forms (forms), Definitions (workflow_forms),
                                         Purchase Requests, Sponsorship Forms (procurement)
                                         (moduleKey per leaf, not on the group)
  Files                    (resources)   Files, Trash, Attachment Types
ADMINISTRATION
  Users & Access           (base)        People > Administrative Users, Internal Users, Teams,
                                                    Sales Agents, Onboarding Requests
                                         Access > Roles, Permissions, AI Agents,
                                                    Contact Access Types
                                         Market Segments, Account, Logs, Settings
  System                   (base)        Platform > Companies, App Store, Module bundles
                                         Operations > Import Jobs, Import Logs,
                                                    Tracking Validation, Audit Logs,
                                                    System Health, Activity Timeline,
                                                    Scheduled Tasks, API Call Log
                                         Messaging > Integrations, Integration Logs,
                                                    WhatsApp Templates, Email Outbox,
                                                    Respond Outbox, Chat History,
                                                    Email Event Configs, Email Templates,
                                                    Respond.io Workspaces, Respond.io Contacts
                                         Configuration > Automation, Work Calendar,
                                                    Running Numbers, Status Graphs, Lookup Sets
                                         AI Assistant > (as is)
```

Dealer Kit gains `moduleKey: 'dealer_kit'` and `permission: 'dealer_kit.page.view'` on every
leaf; the stale comment goes. Ideas gains `permission: 'ideation.board.view'`.

`sidebar-menu.tsx` changes:

- Split point for `<QuickAccessBlock/>` becomes the `ADMINISTRATION` heading, not the
  `User Management` title (which no longer exists).
- After permission / superadmin / module filtering, drop any heading that is not followed by at
  least one non-heading item before the next heading. Add this as a fourth pure filter next to
  the three existing ones; unit-test it.
- Verify `filterMenuByModule` recurses into sub-groups so a `moduleKey` on a nested sub-group
  (Complaints under Customer Service) hides that sub-group only.

Other consumers of `MENU_SIDEBAR` to check, not rewrite: `breadcrumb.tsx` and `toolbar.tsx`
(path lookup; deeper nesting just adds a crumb), `search-dialog.tsx` and
`lib/universal-search.ts` (flatten leaves; verify headings are skipped), `quick-access-block.tsx`
(pinned items by path; unaffected), `MENU_SIDEBAR_COMPACT` (demo10, not mounted; leave alone).
`config/menu.config.test.ts` updated for the new location of "Planning changes".

## Order of work

Phase 1 (FE mock) is skipped: there is nothing to mock, every screen already exists. Straight to
Phase 2 test-first per slice, in the order 1, 2, 3, 4, 5. Slice 5 last because it is the largest
diff and the easiest to review in isolation.

## Verification

agent-browser, dev server, two accounts:

1. Superadmin: every section and group visible, every moved leaf reachable from the sidebar,
   headings upper-case, Quick Access sits just above ADMINISTRATION.
2. A role with NONE of `scm.*`, `projects.*`, `dealer_kit.*`, `ideation.*`: SUPPLY CHAIN section
   shows only Procurement/Inventory (or is absent if the role has neither), no Project Sales, no
   Dealer Kit, no Ideas, no orphan headings. Typed `/scm`, `/scm/policies`, `/project-sales/series`,
   `/dealer-kit/editions`, `/ideas` each show `AccessDenied`, zero toasts, and "Back to
   dashboard" lands on `/`.
3. Same role, typed `/scm/proforma-invoices/<id>` (a detail route with no menu entry): denied.

## Out of scope, named so nobody re-litigates

- Same treatment for inventory, order-management, marketing, procurement, complaints, master-data,
  forms (zero `RequireAccess` each). Same fix, separate PR per module owner.
- `MODULE_GUARD_STRICT` (off by default; the permission deps are the real gate).
- Moving the five planning route folders under `/scm`.
- Role assignment for any slug.
