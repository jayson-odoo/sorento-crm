# PLAN: PORTAL-P3-ROLE-MENU, salesperson role + trimmed CRM sidebar (28 Oct 2026)

Status: Plan. Behaviour card filed to crew (`crew report --ask`, 28 Oct); design below is built on the
recommendations and waits on the owner's answers to Q1-Q5 before code.
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

## Design (on the recommendations; revise when the answers land)

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
| Projects | PipelineClient + P2 guard | `project-sales/pipeline`, `app/api/v1/projects/_own_scope.py` |
| Opportunities | SalesOpportunitiesView | `sales/opportunities`, `app/api/v1/sales/opportunities.py:42` |
| Conversations | ConversationsInbox (QE) | `sla-management/conversations`, `app/api/v1/sla/conversations.py:49` |
| Customer asks | existing page, existing grant | `sales/customer-asks` |
| Sample requests | SampleRequestsList | `project-sales/sample-requests`, `sample_requests.py:77-83` |
| NPA | NewProductApplicationsList | `procurement-management/new-product-applications` |
| Landing | home_path_for_user, LoginResponse.home_path | `phone_signin_service.py:302`, `app/schemas/auth.py:29` |
| Grant pattern | sat_0001 role grant | `alembic/versions/sat_0001_stock_ask_done.py:104-114` |
| Route sweep | P2 allowed-routes test | `tests/portal_p2_allowed_routes.txt` |

New: one migration (grants), one `MenuItem` field + filter line, the menu block, the card's homePath
read, the slice-2 guard + its allowlist.

## Acceptance criteria

`portal-p3-role-menu-acceptance-criteria.md`.
