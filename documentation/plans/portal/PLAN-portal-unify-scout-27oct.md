# PLAN: portal / system unification scout (27 Oct 2026)

Status: aligned (27 Oct 2026). Option (i), one CRM shell, accepted; QA to QE and D1 to D8 ruled
(section "Alignment"). Lanes P1 and P2 ready to spawn from the briefs below. Design lane, no
product code.
Track: scout. Lane PORTAL-UNIFY-SCOUT.

Design doc (the deliverable, self-contained HTML):
`documentation/plans/portal/portal-unify-scout-27oct.html`.

## Owner question (27 Oct 2026, verbatim)

> "our sign in has two places: portal and system. It works fine for forms like stock inquiry,
> purchase request, all these easy forms, but when it comes to project registration, quotation,
> and further flow down the road of project sales, the UI and function is gonna be complex and I
> don't want to replicate the function in portal and in system view, I want to maintain one."

## Findings (detail and file:line evidence in the HTML)

- Unified identity S0, S1 and S3 shipped; S2 (the portal on the `user_sessions` session) is not
  built (`PLAN-unified-identity-26sep.md`, slice S2).
- The backend services are mostly shared between the portal and the system. The duplication is in
  the FE screens (about 1,300 to 2,000 lines estimated) and in the two route surfaces in front of
  them (83 `get_portal_token` dependencies). Sales opportunity is a full FE mirror
  (1,136 portal lines vs 1,934 staff lines).
- Staff project reads are wide open by design (`app/services/project_service.py:407-408`). Putting
  salespeople on the staff API therefore needs a new server-side own-records read rule.
- On the portal, project sales covers registration only (#1849). Everything after Approve is
  staff-only.

## Recommendation

Option B: one login (finish S2) and one app with two shells. The portal URL and look stay as the
salesperson's entry. Project detail, quotation and the later steps are built once on the staff API,
mounted in a slim portal shell, with `projects.projects.view_own` enforced in the backend. The
simple forms stay as they are.

## Phases (one lane each)

1. P1 identity S2 (already planned and ruled), M, full track + security review.
2. P2 `projects.projects.view_own` read rule on every project-sales read, S to M, full track +
   security review.
3. P3 portal shell + "My projects" using the staff project detail components, M.
4. P4 quotation in the portal from the same editor, scoped per Q3, M to L.
5. P5 retire the sales opportunity mirror when it next needs a change (named trigger).

## Owner questions

Q1 salesperson reads only own + collaborator projects (rec: yes). Q2 project sales beyond
registration only for set-up users (rec: yes). Q3 portal quotation scope (rec: draft + lines +
send for approval; admin issues). Q4 salesperson never sees the CRM sidebar (rec: portal shell
only). Q5 P1 and P2 as two parallel lanes now (rec: yes).

## Owner answers (27 Oct 2026) and v2

- Q1 yes, Q2 yes.
- Q3: salespeople may use every quotation function built, issue and revision included, to cut
  admin work. v2 section 12 lists today's rules and decisions D1 to D8 (floors as the discount
  limit, floor coverage, who signs, self-approval, revision, terms, sign link, admin visibility).
- Q4: concern about building the CRM view and the portal view twice. v2 section 10: one route tree
  (`app/(protected)/project-sales/**`), the frame chosen in `app/(protected)/layout.tsx`
  (Demo1Layout or a new PortalFrame), permissions decide buttons, and guards (route allowlist
  vitest, ESLint bans on `@/lib/shell` and on portal imports of project-sales). v2 section 11
  compares (i) one shell with a role menu against (ii) two frames around the same pages, and
  recommends (ii).
- Q5: no lane starts until alignment.

## v3 (owner feedback on v2, 27 Oct 2026)

Owner: "I am fine with them seeing the sidebar just like CRM" (Q4), "how can we ensure same
behaviour for simple forms and project sales" (Q2), Q3 "all". v3 recommends option (i): set-up
salespeople sign in (`/signin` or their WhatsApp link, same code) to the CRM layout, the sidebar
trimmed by the `salesperson` role's permissions, every page the staff page. No blocker found.

- "Only theirs" is one backend rule (`*.view_own`) per module, landing before any grant (P2).
- Each simple form converges onto its existing staff screen (project registration, sample
  request, NPA, sales opportunity, stock inquiry, purchase request + sponsorship, complaint, price
  tag), then the portal form is retired once no contact without a user uses it.
- Phases: P1 WhatsApp link to CRM session (S), P2 view_own rule (M), P3 role + menu + "My work"
  home (S to M), P4 converge forms one lane each (M each), P5 quotation D1 to D8 (M), P6 retire
  portal forms per kind.
- Questions QA (retire portal gradually), QB (salesperson menu headings), QC (hide floor values and
  internal numbers), QD (salesperson registrations go to approval), QE (portal Conversation kind).

## Alignment (owner, 27 Oct 2026)

Verbatim: "ok, just make sure we don't reinvent the wheel and reuse as much as possible."

- Option (i) accepted: set-up salespeople use the CRM shell, sidebar trimmed by permissions.
- **Standing rule for every phase:** reuse existing staff screens, components and services; no
  parallel implementation. Every lane brief lists what it reuses (paths) and what is genuinely new.
- QA (a): retire the portal gradually; it stays for contacts without a user.
- QB (a): "MY WORK" and "REQUESTS" sidebar headings for the salesperson role (menu config only).
- QC: "this depends on their permission". Floor values and internal numbers follow an existing
  view permission granted per role or user; the "below floor" warning always shows (P5).
- QD (a): a salesperson's project registration on the staff form goes to Project Sales Admin.
- QE: "CRM already has conversation, just need to reuse the component and show only the
  conversation they can see". Reuse the CRM inbox `app/(protected)/sla-management/conversations`
  (BE `app/api/v1/sla/conversations.py`), scoped server-side in P2. No new page.
- D1 to D8 as recommended in v2 section 12.

## Lane briefs

### P1 PORTAL-UNIFY-P1: WhatsApp link to a CRM session (S)

Track: full (auth change; CLAUDE.md excludes auth from the small fix track). security-reviewer
required.

Goal: a contact linked to an eligible user who enters the WhatsApp code on the portal verify card
ends up with today's portal token (unchanged) AND a CRM `user_sessions` row
(`auth_method = portal_link`). A contact without a user sees byte-identical behaviour. Landing is
unchanged in P1 (`home_path_for_user` moves salespeople to the CRM in P3).

Reuse (no parallel implementation):
- `PortalService.verify_otp` (`sorento_crm_backend/app/services/portal_service.py:736-789`),
  unchanged: the card keeps calling `/public/portal/verify-otp` and gets its portal token.
- `mint_session(..., auth_method="portal_link")` (`app/services/user_session_service.py`;
  `portal_link` already allowed at `:36` and in `ck_user_sessions_auth_method`,
  `app/models/user_session.py`).
- `build_login_response` (`app/services/phone_signin_service.py:328`) and the eligibility rules of
  `find_eligible` (`:93`: ACTIVE, not integration, not trashed, linked contact).
- `PortalService.resolve_token` for the token lookup.
- NextAuth `phone-otp` provider (`sorento_crm_frontend/app/api/auth/[...nextauth]/auth-options.ts:193-237`):
  add a `portal_token` credential branch, same error handling. No new provider.
- `PortalVerifyCard.tsx:237` (after `verifyOtp` succeeds) calls `signIn('phone-otp', {portal_token,
  redirect: false})` only when `has_user`.
- The existing per-IP Redis rate-limit pattern in `app/api/v1/auth.py`.

Genuinely new: one route `POST /api/v1/auth/portal-link` (`{portal_token}` -> `LoginResponse`);
a `has_user` boolean on `slug-info` and `token-info` (`app/api/v1/public/portal.py`); the card
branch; portal Log out also calls NextAuth `signOut`.

Acceptance criteria:
1. Set-up contact: code on the card, then the portal works exactly as today AND a CRM API call with
   the session succeeds; one `user_sessions` row with `auth_method = portal_link`; audit actor is
   the user.
2. Contact without a user: no NextAuth call, no `user_sessions` row, network trace identical to
   today.
3. An admin "view as contact" token (`is_impersonation`) never mints a session.
4. Refused with one identical 401 body: token not found, revoked, expired, unverified, verified
   more than 120 s ago (compare with the same `_utcnow` that `verify_otp` stamps; do not compare
   against the DB-default `created_at`), contact without a user, user INACTIVE / BLOCKED / trashed / integration.
5. Portal Log out clears the portal token AND revokes the session row.
6. `has_user` is a boolean only; no user id, email or name leaks through slug-info / token-info.
7. agent-browser evidence at 375px and 1280px: the verify card is visually unchanged.
Tests: pytest per AC on the route; vitest on the PortalVerifyCard branch.

Risks: a verified portal token captured within 120 s could mint a session (equivalent to holding
the code); the security reviewer decides whether to make it one-time with a nullable unique
`user_sessions.portal_token_id` (that adds a migration). A shared device now also holds a CRM
session; harmless until P3 grants anything.

Do NOT touch: the 83 `Depends(get_portal_token)` portal routes; portal token lifetimes;
`/signin`; `home_path_for_user` (P3); `company_scope_resolver.py`; any portal form; the menu.

Pre-flight for crew (read-only, dev copy; feeds QA and P6): portal contacts active in the last 90
days with and without a linked user, and submissions per kind by each group:
```sql
WITH active AS (
  SELECT DISTINCT contact_id FROM portal_tokens WHERE created_at > now() - interval '90 days'),
linked AS (SELECT respond_contact_id AS contact_id FROM users
  WHERE respond_contact_id IS NOT NULL AND is_trashed = false)
SELECT (a.contact_id IN (SELECT contact_id FROM linked)) AS has_user, count(*)
FROM active a GROUP BY 1;
-- per kind: repeat with stock_inquiries / purchase_requests (request_type) / complaints /
-- sample_requests (source='portal') / new_product_applications (source='portal') /
-- price_tag_requests / sales.opportunities (source='portal', created_by_contact_id) on contact_id.
```

### P2 PORTAL-UNIFY-P2: "only theirs" on the server (M)

Track: full (RBAC). security-reviewer required. Backend only; grants the new permissions to NO
role (P3 grants).

Scope: the modules P3 grants first: projects (with every child route: quotations and quotation
documents, tasks, samples, sample requests, POs, sales orders, activity, documents),
opportunities, sample requests, new product applications, and the conversation inbox (QE).
Stock inquiries, purchase requests + sponsorship, complaints and price tag requests get their rule
in their own P4 lane with the same helper.

Reuse (no parallel implementation):
- `require_any_permission` (`app/dependencies.py:453`) to accept `VIEW` or `VIEW_OWN` on reads.
- `permission_slugs` (`app/api/v1/projects/_common.py:38`).
- Project ownership: `owner_user_id`, `project_service._is_collaborator` (`app/services/project_service.py:387`),
  and `ProjectSalesProfile.contact_id` (portal registrations, `project_registration_service.py:344-354`).
- Agents of a contact: `price_tag_request_service.sales_agents_for_contact` (`:109`) and
  `app/services/sales/portal_agent.py:24-33` (the portal opportunity scope, `portal_sales_opportunity.py:72-116`).
- Conversations: `portal_conversation_service._rows_query` / `list_for_agent` / `contact_in_scope`
  (`app/services/portal_conversation_service.py:39,135,155`) applied inside
  `app/api/v1/sla/conversations.py` when limited. FE inbox `app/(protected)/sla-management/conversations`
  untouched. `REPLY` stays its own permission (`conversations.py:191,271`).
- Precedents of the pattern: tickets (`app/services/tickets_service.py:68-76`), customer asks
  (`app/api/v1/sales/customer_asks.py:41-71`).
- Permission seeding pattern with `_has_*` guards: `alembic/versions/330_quotation_approval_gate.py`.

Genuinely new: `app/services/own_scope.py` (one helper: `is_limited(perms, view, view_own)` =
holds `view_own`, not `view`, not admin/superadmin; `me(db, user)` = user id, linked contact id,
agent ids; one filter per model); `*.view_own` slugs seeded by one migration (granted to nobody):
`projects.projects.view_own`, `sales.opportunities.view_own`, `projects.sample_requests.view_own`,
the NPA module's `view_own`, `sla_management.conversations.view_own`; a scoped project loader used
by every route that accepts `view_own` (`get_project_or_404`, `project_service.py:943`, has 57
callers: add a scoped sibling rather than changing all 57).

Columns per model ("me" = user id + linked contact id + agent ids):
projects `owner_user_id` / collaborator / profile `contact_id`; opportunities `sales_agent_id` in
agent ids; sample requests `salesperson_id` or `contact_id`; NPA `contact_id`; conversations: the
agents' customers.

Acceptance criteria:
1. Per module, a limited user's list holds only their rows (two salespeople, two contacts, rows
   for each, seeded in the test).
2. A foreign id returns 404 on the detail route and on EVERY child route. For projects the test
   enumerates `app.routes` under the project-sales router with a `{project_id}` path parameter and
   asserts 404 for a foreign project on each.
3. Writes (edit, delete, child creates) on foreign rows return 404.
4. Holders of `VIEW` (staff), admin and superadmin get identical results to before (regression
   assertions), and a user holding both `VIEW` and `VIEW_OWN` behaves as `VIEW`.
5. Conversations: list, page, search, comments, window, media limited to their agents' customers;
   foreign `contact_ref` 404; reply still needs `REPLY`.
6. Cross-cutting readers closed for a foreign id: form comments (`app/api/v1/form_comments.py:59`),
   activities (`app/api/v1/activities`), downloads/exports (`app/api/v1/downloads`), AI assistant
   record context (`app/api/v1/assistant/record_context.py`, `ai_assistant_service.py:1035-1047`),
   global search (`app/services/list_query_search_service.py`); confirm none of the P2 models is a
   generic list-query resource (`app/services/list_query_registry.py`).
7. Linked contact null: the limited user sees only rows keyed on their user id.
8. One migration, single alembic head, no role grant, no FE change.

Risks: a child route missed means a leak (AC-2's route enumeration is the mitigation); OR filters
on large tables (check indexes exist on each column, add only where missing); company scope still
applies on top (unchanged).

Do NOT touch: the wide-open read for `VIEW` holders (`project_service.py:407-408`); portal routes
(`app/api/v1/public/*`); `company_scope_resolver.py`; the menu and every FE file (P3); role grants
(P3); quotation issue and approval logic (P5).

### P5 PORTAL-UNIFY-P5: quotation for salespeople (M), carries QC

Reuse: the staff quotation pages and services as they are (`app/api/v1/projects/quotation_documents.py`,
`project_quotation_approval_service.py`, `project_quotation_service.revise`), `project_notify_service`
for D8 (recipients = `MANAGEMENT_PERMISSION`, `:33`), the existing Price Floors page
`/project-sales/price-floors` for D2's system-level floor (data, set by the owner or an admin).

QC (owner: "this depends on their permission"): no role-based hiding.
- Floor values (`floor_value_applied`, `floor_level_applied`; `project.types.ts:787-790`) are
  returned and shown only to holders of `projects.projects.view_all_financials`, the existing
  "management" permission (`app/services/project_notify_service.py:33`). First task: confirm the
  slug exists as a permission row; no migration in `alembic/versions` seeds it, so if it is absent,
  seed that same slug rather than invent a new one. `is_below_floor` and the warning always show.
- Internal consignment and PO numbers on sample requests (`SampleRequestDetail.tsx:557-560`) follow
  `projects.sample_requests.process` (existing, `app/api/v1/projects/sample_requests.py:32`).
- The serializer drops a gated field (not only the FE), so the API never returns it to a
  non-holder.

D3 signer from the user record (reuse `QuotationSignDialog.tsx`); D4 refuse approve/reject by the
requester (`project_quotation_approval_service.py:344` `requester_id`, `:424-461`); D6 terms and cover
letter editable only by `projects.projects.manage` holders; D5, D7 need no code.
