# UAC - module access gates + sidebar reorganisation

Plan: `PLAN-module-access-gates.md`. Each criterion names how it is proven.

## A. Sidebar visibility

- A1. A user with no `scm.*`, `projects.*`, `dealer_kit.*` or `ideation.*` permission sees no
  Supply Chain group, no Project Sales group, no Dealer Kit group and no Ideas entry.
  (vitest on the sidebar filters + agent-browser with a stripped role)
- A2. A user holding only `scm.dashboard.view` sees Supply Chain with Dashboard, Orders and the
  Project Demand leaves whose slug is `projects.projects.view` hidden; Planning hidden except
  nothing (all Planning leaves need `scm.reorder.run` or `scm.policy.manage`). (vitest)
- A3. A section heading never renders without at least one visible group under it. (vitest)
- A4. Superadmin sees all six headings in order: OVERVIEW, SALES, SUPPLY CHAIN, CATALOGUE,
  OPERATIONS, ADMINISTRATION, upper-case. (agent-browser)
- A5. Fulfilment Planning, Plans, Order Inquiries, Planning changes, Forecast & Reports appear
  under Supply Chain > Project Demand and nowhere under Project Sales. Their hrefs are unchanged.
  (vitest on `MENU_SIDEBAR`, replaces the existing "Planning changes" assertion)
- A6. Every leaf path present in `MENU_SIDEBAR` before this change is present after it, with the
  same `permission` / `permissionsAny` / `superadminOnly` value. (vitest snapshot of the flattened
  `{path, permission}` set, diffed against a committed fixture of the pre-change set)
- A7. Quick Access renders between the OVERVIEW section and the SALES heading (top of
  sidebar, after Dashboards and Ideas). (agent-browser)
- A8. Universal search and the breadcrumb still resolve a nested leaf (e.g. Room Designer, Lookup
  Sets) to its title. (agent-browser)

## B. Deep URL access

- B1. Without the module's view slug, each of `/scm`, `/scm/policies`, `/scm/sales-orders/<id>`,
  `/project-sales/pipeline`, `/project-sales/series`, `/project-sales/price-floors/<id>`,
  `/dealer-kit`, `/dealer-kit/editions`, `/ideas`, `/ideas/<id>` renders `AccessDenied` and
  issues zero data requests. (vitest per layout; agent-browser spot check with network count)
- B2. `AccessDenied` shows the shield, "You don't have access to this page", the administrator
  line, and "Back to dashboard" navigates to `/`. (agent-browser)
- B3. With `scm.dashboard.view` only, `/scm/policies` is denied (`scm.policy.manage`) while `/scm`
  loads. (vitest)
- B4. With `projects.projects.view` only, `/project-sales/series` is denied
  (`projects.types.view`) while `/project-sales/pipeline` loads. (vitest)
- B5. No red toast appears on any denied route. (agent-browser)

## C. Backend

- C1. `POST/GET` on the Ideas embed mint route returns 403 `Permission required:
  ideation.board.view` for a user without the slug, and passes the permission dependency with it.
  (pytest)
- C2. `ideation.board.view` exists in `permission_registry.py` and the migration seeds it
  idempotently; the migration grants it to `superadmin` and `admin` when those roles exist and
  does nothing otherwise. (pytest on a create_all DB + on a DB with the roles)
- C3. The six `dealer_kit.*` slugs in `permission_registry.py` equal the set migration 309 seeds.
  (pytest)
- C4. `alembic heads` is a single head on the branch. (CI)

## D. Denied toast dedupe

- D1. Three queries on one page failing 403 with `Permission required: ...` yield exactly one
  toast, text "You don't have permission to view this. Ask an administrator." (vitest on the
  QueryCache onError)
- D2. A 500 on the same page still yields its own toast with the server detail. (vitest)

## E. Hygiene

- E1. `lib/route-module-map.ts` maps `/project-sales -> projects` and `/dealer-kit -> dealer_kit`;
  `moduleKeyForPath('/dealer-kit/editions') === 'dealer_kit'`. (vitest)
- E2. No new Playwright spec. Evidence run recorded per
  `documentation/agents/browser-verification.md`.
- E3. `npm run lint`, `npx vitest run`, backend pytest for the touched tests all green.
