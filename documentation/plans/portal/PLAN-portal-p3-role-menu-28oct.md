# PLAN: PORTAL-P3-ROLE-MENU, salesperson role + trimmed CRM sidebar (28 Oct 2026)

Status: Build, slice 1. Owner answered the card 28 Oct ~08:40; design v2 below.
Track: full (RBAC grant + landing change + API guard), security review required. Size M, LEAD pattern.
Lane PORTAL-P3-ROLE-MENU.

Source: scout `PLAN-portal-unify-scout-27oct.md` (PR #1894, v3 + alignment), P1 #1908 (`portal_link`
session), P2 #1911 (`*.view_own`, `app/services/own_scope.py`). Both merged and live.

## Goal

A salesperson who signs in from the portal link, or at `/signin`, lands in the CRM shell. The sidebar
is the existing permission-driven menu, trimmed to what the `salesperson` role holds, under MY WORK /
MY REQUESTS headings. Contacts without a CRM user keep today's portal byte for byte. Existing staff:
no change.

## Who

"Salesperson" = ACTIVE user holding the existing protected role `salesperson`
(`alembic/versions/identity_0001_s0_model.py:46-49`), with a linked WhatsApp contact. The role already
holds `sales.customer_asks.view/edit` (`sat_0001_stock_ask_done.py:54`). No new role.

## Owner answers (28 Oct ~08:40, relayed by crew)

- Q1: landing = the contact's FAVOURITE portal form; none -> the first portal form page (Stock Inquiry).
- Q2 (b+): in the CRM a salesperson can do whatever they can do in the portal (create/submit too).
- Q3: one sidebar item PER request form kind, not one "Request forms" link.
- Q4: **known gap, accepted 28 Oct.** Any CRM session reads the sign-in-only GETs (e.g.
  `procurement/stock_inquiries.py:56`, `procurement/purchase_requests.py:55`,
  `order_management/customers.py:25`, `procurement/suppliers.py:39`, `incoming_stock.py:231`,
  `procurement/grn.py:28`, `inventory/stock.py:238`). No fail-closed guard in this lane.
- Q5 (b): WhatsApp deep links open the CRM page once live.
- Re-plan: Q2/Q3/Q5 pull the form-in-CRM work (scout P4) forward; reuse the existing portal form
  components inside the CRM shell, do not rebuild them. Slice 1 = landing + sidebar first.

## Design v2 (on the owner answers)

"Salesperson view" = ACTIVE user holding role `salesperson` whose every role is in
{salesperson, portal_user}, with a linked contact. One predicate in `phone_signin_service.py`, used
by `home_path_for_user` and `/users/me`. A user with any other role is staff (full staff menu and
landing): the mixed-user edge case.

Sidebar for a salesperson (existing SidebarMenu + applyMenuAccess, two new MenuItem fields:
`audience: 'salesperson' | 'staff'` and `portalKind`):

- MY WORK: Projects `/project-sales/pipeline` (staff page, `projects.projects.view_own`, P2 guard);
  Conversations `/sla-management/conversations` (staff inbox, `sla_management.conversations.view_own`,
  QE); Customer Asks `/sales/customer-asks` (staff page, grant exists since sat_0001).
- MY REQUESTS: one item per portal kind the contact may use (server list, portal order): Stock
  Inquiry, Complaint, Purchase Request, Sponsorship Form, Project Registration, Sample Request, New
  Product Application, Price Tag Request, Sales Opportunity. Each opens `/my-requests?type=<kind>`,
  which renders the EXISTING portal component inside the CRM shell, calling the same portal API with
  the same portal token, so the salesperson can do exactly what the portal lets them (Q2 b+) and
  nothing more. Portal kinds `customer_asks` and `conversation` are covered by MY WORK.

Grants: migration `pp3_0001_salesperson_grants` (copies `sat_0001_stock_ask_done.py:104-114`):
`projects.projects.view_own`, `sla_management.conversations.view_own`. Nothing else: the forms
run on portal rules, not on staff permissions.

Landing (Q1): `home_path_for_user` sends a salesperson to `/my-requests`; the embedded
PortalLanding already opens the starred default tab (localStorage
`sorento.portalDefaultTab.<contact_id>`, PortalLanding.tsx:316-328), else Stock Inquiry. The
favourite is per device (no server field); same browser as the portal = same favourite.

## Slices

1. Landing + sidebar (owner sees it first). BE: grants migration; salesperson predicate;
   `/users/me` gains `salesperson: {portal_kinds, portal_slug} | null`; `home_path_for_user` ->
   `/my-requests`. FE: menu block + filter fields; page gates take `[.view, .view_own]`
   (`project-sales/layout.tsx:7` + its pages, `sla-management/conversations/page.tsx:24`);
   `app/(protected)/my-requests/**` mirrors the portal slug tree (landing, `[type]/new`,
   `[type]/[id]`, price tag, sample request, NPA, sales opportunity) by rendering the portal
   components; one base switch in `portal-paths.ts` so their hardwired links stay under
   `/my-requests`; PortalLanding's own header/log-out hidden inside the CRM; the verify card follows
   `session.user.homePath` when it is a CRM path.
2. Deep links (Q5 b): a salesperson opening a WhatsApp link `/portal/c/{slug}/{kind}/{id}` (or
   `?type=`) lands on the same suffix under `/my-requests` (verify card and slug-page guard).
3. `/signin` salesperson with no portal token on that device: `/my-requests/verify` renders the
   existing PortalVerifyCard (WhatsApp code once per device), slug from `/users/me`. No new
   token-minting route.

## Round 6: admin impersonation (owner ruling 28 Oct ~11:50)

Owner: "Impersonation also need to have same views" (option b). Contacts > "Impersonate in portal" on a
contact whose linked user is a salesperson starts the EXISTING CRM user impersonation of that user plus the
EXISTING contact-impersonation portal token, then opens `/my-requests`; Exit ends both. Contacts without such a
user keep today's portal impersonation. UAC P3-23..P3-28.

## Not in this lane

- Fail-closed API guard (Q4, accepted gap above).
- A server-side favourite (needs a column; trigger: owner asks for it across devices).
- Staff permissions for the request forms (they run on portal rules).

## Design v1 (superseded by the answers above; kept for the record)

1. Grant (Q2 a): migration `pp3_0001_salesperson_view_own`, insert-only, copies
   `sat_0001_stock_ask_done.py:104-114`: role `salesperson` gets the five slugs seeded by
   `pp2_0001_view_own_perms.py:26-56`. Downgrade deletes exactly those five pairs.
2. Landing (Q1 a): `home_path_for_user` (`app/services/phone_signin_service.py:302-333`) sends a
   salesperson to `/project-sales/pipeline` instead of the portal. Everyone else unchanged.
3. Portal verify card: after `openCrmSession`, read `session.user.homePath`
   (`portal-client.ts:938-965`, `auth-options.ts:250,304,332`); a CRM path wins for a plain link;
   anything else (no user, no role, session failed, deep link per Q5 a) goes where it goes today.
4. Menu: a MY WORK / MY REQUESTS block in `config/menu.config.tsx`, same routes, each item gated on
   its `view_own` slug and hidden when the user holds that module's `.view` (one new `MenuItem`
   field in `config/types.ts`, one line in `lib/menu-access-filter.ts`). Q3 a adds "Request forms"
   to the user's portal page.
5. FE page gates accept `[.view, .view_own]`: `app/(protected)/project-sales/layout.tsx:7` and the
   pipeline / sample-requests pages; `sla-management/conversations/page.tsx:24`. Buttons keep their
   existing slugs.
6. API guard (Q4 a), slice 2: a user whose every role is in {salesperson, portal_user} gets 403 on
   any `/api/v1` route outside an allowlist; a test sweeps every registered route (P2 pattern,
   `tests/portal_p2_allowed_routes.txt`).

## Reuse (owner 27 Oct: "don't reinvent the wheel")

| Need | Reused | Path |
| --- | --- | --- |
| Shell | Demo1Layout | `app/(protected)/layout.tsx` |
| Sidebar + trimming | SidebarMenu, applyMenuAccess, orphan headings | `app/components/layouts/demo1/components/sidebar-menu.tsx:33`, `lib/menu-access-filter.ts:64-89` |
| Projects | PipelineClient + P2 guard | `app/(protected)/project-sales/pipeline`, `app/api/v1/projects/_own_scope.py` |
| Conversations | ConversationsInbox (QE) + P2 scope | `app/(protected)/sla-management/conversations`, `app/api/v1/sla/conversations.py:49` |
| Customer asks | existing page, existing grant | `app/(protected)/sales/customer-asks`, `sat_0001_stock_ask_done.py:54` |
| Request landing + lists | PortalLanding (SubmissionList, MyTargetPanel, default-tab star) | `app/(auth)/portal/components/PortalLanding.tsx` |
| Request forms + details | SubmissionForm, PriceTagRequestForm, SampleRequestForm, NewProductApplicationForm, SalesOpportunityPortalForm/Detail | `app/(auth)/portal/**/components/` |
| Portal API + token | portalFetch, `sorento.portalToken`, every `/public/portal/*` rule | `app/(auth)/portal/lib/portal-client.ts`, `app/api/v1/public/*` |
| Kinds + visibility | LANDING_KINDS, `/public/portal/me` visible_form_types, portal_form_visibility_service | `lib/portal-form-kinds.ts`, `app/services/portal_form_visibility_service.py:53-115` |
| Links | portal-paths builders (one base switch) | `app/(auth)/portal/lib/portal-paths.ts:41-105` |
| Verify | PortalVerifyCard + P1 session link | `app/(auth)/portal/components/PortalVerifyCard.tsx` |
| Landing | home_path_for_user, LoginResponse.home_path | `app/services/phone_signin_service.py:302`, `app/schemas/auth.py:29` |
| Grant pattern | sat_0001 role grant | `alembic/versions/sat_0001_stock_ask_done.py:104-114` |

New: one migration (two grants), the salesperson predicate + `/users/me` field, two MenuItem fields +
filter lines, the menu block, the `/my-requests` route files (thin wrappers), the portal-paths base
switch, the verify card's homePath read.

## Acceptance criteria

`portal-p3-role-menu-acceptance-criteria.md`.
