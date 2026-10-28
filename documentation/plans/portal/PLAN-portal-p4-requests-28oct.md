# PLAN: PORTAL-P4-REQUESTS, MY REQUESTS opens the staff pages with server-side "only theirs" (28 Oct 2026)

Status: Plan. Behaviour card v1 filed to the owner (`CARD-portal-p4-requests-28oct.md`, ee46e8131d); no code before
the answers. Track: full (RBAC + permission slugs migration + new write surface), security review required. Size L,
LEAD pattern. Lane PORTAL-P4-REQUESTS. Stacked on PR #1944 (PORTAL-P3-ROLE-MENU); this PR merges right after it.

Source: `PLAN-portal-p3-role-menu-28oct.md` (open MY REQUESTS decision), PR #1944 crew-note 6461917897, owner
28 Oct ~14:1x option (b), owner requirement 28 Oct ~14:2x (end-to-end exactly like the portal, card section
"End-to-end flows").

## Goal

A salesperson's MY REQUESTS > Stock Inquiry / Complaint / Purchase Request / Sponsorship Form opens the STAFF page
for that form (list, detail, edit, new), showing only their own rows, enforced on the server. Create, save as draft,
submit, revise, comments and attachments behave exactly like the portal because they run the portal's own code.
Everything after submit is unchanged. Staff and admin: no change.

## Rule (card; Q1 pending)

LIMITED in a form = holds its `view_own`, not its `view` (P2 rule, `app/services/own_scope.py:41-49`). Admin and
superadmin are never limited. "Theirs" = `contact_id` = `me().contact_id` (`own_scope.py:59-69`); no linked contact =
nothing. Space is not matched (dev: one space for all 620 rows); create stamps the contact's workspace space.

## Architecture (fixed before code)

Layer: the owned-row rule lives in ONE place on the server (`own_scope.request_clause` + one router dependency per
form router); the write path lives in ONE place (the portal service, reused). No per-form copy of draft / submit /
revise logic, no FE-only hiding as the security boundary.

Server (shared slice S0, before the per-form slices):

1. Migration `pp4_0001_request_view_own` (insert-only, copies `pp2_0001_view_own_perms.py:23-71` and the grant shape
   of `pp3_0001_salesperson_grants.py:25-38`): slugs `procurement.stock_inquiries.view_own`,
   `complaint_management.complaints.view_own`, `procurement.purchase_requests.view_own`,
   `procurement.sponsorship_forms.view_own`; grant role `salesperson` those 4 plus the 4 `.add` slugs. Registry
   mirror next to `permission_registry.py:1030-1058`. Dev SQL to `crew/state/migrations/PORTAL-P4-REQUESTS.sql`.
2. `own_scope.request_clause(model, me)` = `model.contact_id == me.contact_id`.
3. Staff routers (`procurement/stock_inquiries.py`, `procurement/purchase_requests.py`, `complaints/complaints.py`):
   a router dependency for a LIMITED user: list and detail (+ revisions) pass `contact_id=me.contact_id`
   (services already accept it: `procurement_service.py:5614-5625, 9222-9234`, `complaints_service.py:715-730`);
   a foreign id answers 404; every other staff route answers 403 (P2 `_own_scope.py` pattern). The complaints list
   accepts `view_own` next to `view` (`complaints.py:268`). Form comments accept `view_own` on an own row
   (`form_comment_service.py:46-51`).
4. Write surface for a LIMITED user: `/api/v1/my-requests/{kind}/...` mirroring the portal routes
   (`public/portal.py:787-798, 1098-1259, 1369, 1549, 1652-1756`): draft create/save/delete, submit, revise,
   revision-draft, requestor-options, attachments, comments. Identity = a transient, never-persisted portal identity
   (contact_id = `me().contact_id`, space_id = the contact's workspace space, `contact_impersonation.py:69-88`) passed
   to the SAME functions (`portal_service.create_or_update_draft` 1042, `submit_draft` 1089, `delete` ~1391,
   `portal_revision_service.revise` 1507). The portal code reads only `contact_id` / `space_id` off the token in these
   paths (grep: 27 / 17 uses; `token.id` 2, `expires_at` 3, `verified_at` 1, to be checked by the coder). Session =
   CRM session, so impersonation applies (`dependencies.py:182-238`).
5. Grid rules (owner, every grid; Q3): server sort for every column of the 4 lists, multi-select filters on
   Purchase Request / Sponsorship.

Frontend (per-form slices after S0; one coder each, parallel worktrees, folded by the lead):

- Menu: the 4 MY REQUESTS items point at the staff list routes (`config/menu.config.tsx:66-89`), gated on `view_own`;
  `/my-requests?type=<one of 4>` and `/my-requests/<kind>/<id>` redirect to the staff list / detail (deep links,
  P3 Q5 (b)); landing on a favourite among the 4 opens its staff list.
- List: unchanged component; Create gated on `.add` for a limited user, staff unchanged.
- New / Edit: the staff form; for a limited user staff-only fields hidden (card), Save as draft + Submit via the
  my-requests service, requestor picker from `my-requests/{kind}/requestor-options`, frozen on revise; Duplicate via
  `/new?from=<id>`.
- Detail: for a limited user the portal action set only (Q2); responses, status, comments, attachments and revision
  history visible (owner requirement 5).

## Slices

- S0 shared server (red tests first, kill test, security reviewer): items 1-4 above + API-level E2E per form
  through flows 1-4 of the card.
- S1 Stock Inquiry FE, S2 Complaint FE, S3 Purchase Request + Sponsorship FE (shared components), each with its grid
  sort/filter fixes (item 5) and vitest.
- Browser pass on the crew copy, hand test.

## Known pre-existing gaps (not closed here, P3 Q4 accepted)

Staff PUT / DELETE / bulk delete on these 4 forms need sign-in only; PUT accepts `contact_id` / `space_id` / `status`
(`stock_inquiries.py:457-467, 785-794`, `schemas/procurement.py:1357-1358`, `schemas/complaints.py:214-217`).
Closed for limited users only (item 3).

## Acceptance criteria

`portal-p4-requests-acceptance-criteria.md` (written after the owner answers).
