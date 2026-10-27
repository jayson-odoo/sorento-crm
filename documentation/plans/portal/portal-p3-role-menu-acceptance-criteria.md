# UAC: PORTAL-P3-ROLE-MENU (28 Oct 2026)

Plan: `PLAN-portal-p3-role-menu-28oct.md`. Built on the behaviour-card recommendations (Q1 a, Q2 a,
Q3 a, Q4 a, Q5 a); any differing owner answer revises the affected rows before code.

"Salesperson" = ACTIVE user, role `salesperson`, linked WhatsApp contact that is an active sales agent.
"Staff" = any user holding no `salesperson` role.

## Grant

- P3-01 After the migration, role `salesperson` holds exactly its previous slugs plus
  `projects.projects.view_own`, `sales.opportunities.view_own`, `projects.sample_requests.view_own`,
  `procurement.new_product_applications.view_own`, `sla_management.conversations.view_own`.
- P3-02 The migration grants nothing to any other role; running it twice adds no row; downgrade removes
  exactly those five pairs and nothing else.

## Landing

- P3-03 Salesperson password or phone sign-in with no callbackUrl: `home_path` = `/project-sales/pipeline`.
- P3-04 Staff (any non-salesperson, incl. admin, superadmin, agent-linked staff): `home_path` unchanged.
- P3-05 User linked to a contact without the role (e.g. `portal_user` only): `home_path` unchanged (portal).
- P3-06 Portal verify card, plain link, contact linked to a salesperson: after the code the browser
  opens `/project-sales/pipeline` in the CRM shell.
- P3-07 Portal verify card, contact without a CRM user: same requests and same destination as today.
- P3-08 Portal verify card, linked user without the role, or the CRM session fails (inactive, trashed,
  exchange 401): lands on the portal exactly as today.
- P3-09 Deep link to one request (portal-paths.ts:41-51): opens that portal page as today, salesperson or not.

## Sidebar

- P3-10 Salesperson sees headings MY WORK (Projects, Opportunities, Conversations) and MY REQUESTS
  (Customer Asks, Sample Requests, New Product Applications, Request forms), in that order, and no other
  item except those already shown to them today by an existing grant.
- P3-11 Request forms opens the salesperson's own portal page.
- P3-12 Staff sidebar is identical to today for every staff fixture (admin, superadmin, a role with
  `projects.projects.view`, a role without it): no MY WORK / MY REQUESTS heading.
- P3-13 Mixed user (salesperson role + a staff role holding `sales.opportunities.view` only): Opportunities
  shows in its staff group, not under MY WORK; Projects shows under MY WORK.
- P3-14 A heading with no visible item under it does not render.
- P3-15 Usable, not clipped, at 375 px (mobile header menu) and 1280 px.

## Pages

- P3-16 Salesperson opens Projects, Sample Requests, Conversations: the page renders (no AccessDenied)
  and lists only their own rows (P2 rules).
- P3-17 Salesperson sees no Add / Create / Edit / Approve / Delete / Reply button on any of the six pages.
- P3-18 Staff holding `.view` see the same pages and buttons as today.

## Server refuses what is hidden (slice 2)

- P3-19 Salesperson-only user (every role in {salesperson, portal_user}): every registered `/api/v1`
  route outside the allowlist answers 403, including stock inquiries, purchase requests, customers,
  suppliers, incoming stock, GRN, stock and every staff module list.
- P3-20 Every route the six pages and the shell call (auth, me, permissions, modules, notifications,
  column config, the pages' own lists, details and pickers) answers as today for that user.
- P3-21 Staff, admin, API-key callers and mixed users are never touched by the guard.
- P3-22 A route added later is refused for salesperson-only users until added to the allowlist (sweep test).
