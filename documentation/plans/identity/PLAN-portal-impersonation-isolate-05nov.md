# PLAN: Portal impersonation isolated from the admin's staff session

Status: Build (lane PORTAL-IMPERSONATION-ISOLATE, small fix track: FE-only diff, no migration, no
RBAC change; security reviewer still runs because it touches the impersonation boundary)

UAC: `portal-impersonation-isolate-acceptance-criteria.md` (alongside).

## Owner (5 Nov)

"before we unify the login page, the portal login impersonation is isolated from the login session,
but now when i impersonate, i can't use as usual on system view so I can't access things like
product cause my portal view don't have access"

## Root cause (measured)

Two mechanisms, and only one of them is per tab:

1. **Portal (contact) impersonation** mints a verified `portal_tokens` row
   (`sorento_crm_backend/app/api/v1/user_management/contact_impersonation.py:155-207`) and the FE
   keeps it in `sessionStorage` (`app/(auth)/portal/lib/portal-client.ts:304-336`). That is per tab
   and never touches the staff session. This was the whole story before the unify.
2. **CRM view-as** (`impersonation_sessions`): the backend applies it only to a request that carries
   `X-Impersonate-User-Id` and matches the admin's open row
   (`sorento_crm_backend/app/dependencies.py:231-286`). So the backend is already per request. The
   account-wide reach comes from the frontend:
   - `lib/impersonation-store.ts:22-46` persists the view-as in **localStorage** (every tab of the
     browser), and `lib/api.ts:24-47` stamps the header from that store on every `/api/v1/*` call;
   - `app/(protected)/layout.tsx:26-31` calls `hydrate()` on every protected page load, and
     `hooks/useImpersonation.ts:20-24` copies the server's `/impersonation/current` row into the
     store. So every tab **and every other browser** of that admin adopts the view-as on its next
     load (the crew helpers sharing one admin login hijacked each other this way).

PORTAL-P3/P4 (`137f655fa`, #1953, 30 Oct) routed a salesperson contact's portal impersonation into
mechanism 2 (`ContactImpersonateDialog.tsx:66-76`, `app/(auth)/portal/page.tsx:84-97`,
`hooks/useEnterCrmView.ts`). From then on "Impersonate in portal" on a salesperson turned the
admin's whole account into that salesperson, which has no Products access.

## Design (smallest that restores isolation)

The view-as lives in the tab that started it, nowhere else:

- `lib/impersonation-store.ts`: persist in `sessionStore` (per tab, survives a reload of that tab)
  instead of `localStore`. A leftover localStorage entry from before this change is deleted on
  load and never read.
- `hooks/useImpersonation.ts` `hydrate()`: only **validates** the tab's own view-as against
  `/impersonation/current` (cleared when the server has ended it or it now names someone else). A
  tab with no view-as never adopts the server's row.
- Nothing else changes: the header is still sent only by a tab holding a view-as, the backend still
  honours it only for an admin with a matching open row, audit is unchanged (target is the actor,
  admin is `real_user_id`), start/stop endpoints still use `get_real_user`.

Consequences, stated so nobody is surprised:

- Same tab as today: Impersonate on a salesperson contact still switches **that** tab to
  `/my-requests` (P3 F1 ruling kept). Other tabs and other browsers stay the admin.
- Exit in the impersonating tab ends the server row; a tab that still sends the header (a
  duplicated tab, the browser's "Duplicate tab" copies sessionStorage) gets
  `X-Impersonation-Ended` and drops to the admin with the existing toast. No re-login anywhere.
- One open view-as per admin stays (unique index `uq_impersonation_sessions_active_admin`):
  starting view-as of Y in tab C ends X in tab A, which then falls back to the admin, same toast.

No backend code change. Backend tests pin the per-request contract so a later change cannot
reintroduce account-wide view-as server side.

## Out of scope / asked

- `phone_signin_service.home_path_for_user` (`:337-341`) sends a user holding `salesperson` plus
  another role (admin included) and a linked contact to their portal home before the admin check.
  That is sign-in routing, not impersonation; raised as a crew-ask on the PR.

## Tests

Backend `tests/test_impersonation_isolation.py` (real session tokens, real `get_current_user`):
- tab A (token + header) is the salesperson; tab B (same token, no header) is the admin;
- a staff-only permission route answers 403 to tab A and 200 to tab B;
- stopping in A: A's header is ignored with `X-Impersonation-Ended: 1`, B unchanged, same token
  still valid (no re-login);
- a non-admin's start is 403 and a non-admin's header is ignored.

Frontend vitest:
- `lib/impersonation-store.isolation.test.ts`: persisted in sessionStorage only, a legacy
  localStorage entry is dropped and not adopted.
- `hooks/useImpersonation.hydrate.test.tsx`: a tab with no view-as does not adopt the server's
  session; a tab whose view-as the server ended clears it; a matching one is kept.
- `lib/api.sessionEnd.test.ts` seeds the view-as in sessionStorage.
