# UAC: PORTAL-P3-ROLE-MENU (28 Oct 2026, v2 on owner answers)

Plan: `PLAN-portal-p3-role-menu-28oct.md` (design v2, slices 1-3).

"Salesperson" = ACTIVE, not trashed, holds role `salesperson`, every role in {salesperson, portal_user},
linked WhatsApp contact (`users.respond_contact_id`). "Staff" = everyone else, including a user who
holds `salesperson` plus any other role ("mixed").

## Slice 1: grant, landing, sidebar, forms in the CRM

### Grant
- P3-01 After the migration, role `salesperson` holds its previous slugs plus exactly
  `projects.projects.view_own` and `sla_management.conversations.view_own`.
- P3-02 No other role changes; running the upgrade twice adds no row; downgrade removes exactly
  those two pairs.

### Who / me
- P3-03 `GET /user-management/users/me` for a salesperson carries
  `salesperson: {portal_kinds: [...], portal_slug: "<slug>"}`; `portal_kinds` equals the contact's
  `visible_form_types` from `/public/portal/me` (same service), in portal order.
- P3-04 Same field is `null` for staff, admin, superadmin, mixed users, users without a linked
  contact, and users whose roles are only `portal_user`.

### Landing
- P3-05 Salesperson sign-in (password or phone, no callbackUrl): `home_path` = `/my-requests`.
- P3-06 Staff, admin, superadmin, mixed, `portal_user`-only: `home_path` unchanged from today.
- P3-07 Portal verify card, plain link, contact linked to a salesperson: after the code the browser
  opens `/my-requests` in the CRM shell.
- P3-08 Portal verify card for a contact without a CRM user, or whose user is not a salesperson, or
  whose CRM session fails (inactive, trashed, 401): same requests and same destination as today.
- P3-09 `/my-requests` with no `?type=` opens the starred default tab for that contact
  (localStorage `sorento.portalDefaultTab.<contact_id>`) when it is visible, else Stock Inquiry.

### Sidebar
- P3-10 Salesperson sidebar: MY WORK (Projects, Conversations, Customer Asks) then MY REQUESTS with one
  item per kind in `portal_kinds` except `customer_asks` and `conversation`, in portal order, labels
  from `lib/portal-form-kinds.ts`. No other heading or item.
- P3-11 A kind missing from `portal_kinds` has no item; a heading with no item does not render.
- P3-12 Staff, admin, superadmin and mixed users: sidebar identical to today (no MY WORK / MY
  REQUESTS, every existing item kept under the same gate).
- P3-13 Usable, not clipped, at 375 px (mobile header menu) and 1280 px.

### Pages
- P3-14 Salesperson opens Projects and Conversations from the sidebar: page renders (no
  AccessDenied), lists only their own rows (P2), no create/edit/delete/reply buttons appear that the
  portal does not offer.
- P3-15 Each MY REQUESTS item renders the existing portal list for that kind inside the CRM shell;
  New, open detail, edit, submit, revise, duplicate, attachments and comments behave as in the portal
  and every link they produce stays under `/my-requests`.
- P3-16 The embedded landing shows no portal header or portal log-out; the CRM user menu is the only
  log-out.
- P3-17 Staff holding `.view` see the Projects and Conversations pages exactly as today.
- P3-18 The portal at `/portal/...` is unchanged for every visitor (links, landing, verify, log-out).

## Slice 2: deep links (Q5 b)
- P3-19 Salesperson opening a WhatsApp deep link `/portal/c/{slug}/{kind}/{id}` (after the code, or
  with a token already on the device) lands on `/my-requests/{kind}/{id}`; `?type=X` lands on
  `/my-requests?type=X`.
- P3-20 Anyone else opening the same link: today's portal page.

## Slice 3: CRM sign-in without a portal token on the device
- P3-21 Salesperson signed in at `/signin` with no portal token: a MY REQUESTS page asks for the
  WhatsApp code once (existing verify card, inside the CRM), then shows the requested kind.
- P3-22 No new route mints a portal token from a CRM session.

## Known, accepted (owner 28 Oct)
- Sign-in-only GETs readable by any CRM session (plan "Owner answers" Q4). Not tested here.
