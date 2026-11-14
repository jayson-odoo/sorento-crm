# PLAN: sign-in verification is 2FA only, never role (SIGNIN-2FA-NOT-ROLE)

Status: Build (behaviour card v2 after owner correction 14 Nov 13:30: landing unchanged; fix = no second code for the user's own linked contact, no auto-send, OTP clock). Track: M, LEAD pattern, auth change (security-reviewer required).

Owner ruling 14 Nov: a verification code is a deliberate 2FA step decided the same way for every user, never because
of a role; once verified, do not re-prompt.

## Discovery (origin/main d8bc3b60)

- `sorento_crm_backend/app/services/phone_signin_service.py:351-389` `home_path_for_user`: (1) pure salesperson
  (`is_salesperson` :341, roles within salesperson+portal_user, linked contact) -> `/my-requests` (inside the CRM, no
  code); (2) salesperson + ANY other role + linked contact -> `/portal/c/<slug>` (checked BEFORE admin at :383); (3)
  admin or any CRM permission -> `/`; (4) contact only -> portal home; else `/`.
- `sorento_crm_frontend/app/(auth)/signin/page.tsx:59-76` `pickLandingUrl`: bare `/` callback falls back to `homePath`.
- `app/(auth)/portal/c/[slug]/page.tsx:30-37`: no device portal token -> verify page. So case (2) always meets a code.
- `app/(auth)/portal/components/PortalVerifyCard.tsx:146-170` `autoFire`: requests a WhatsApp code on mount (guard only
  sessionStorage); `autoSend` prop defaults true; only a deep link (`?type=`) shows a confirm step first.
- `app/(protected)/my-requests/verify/page.tsx`: inside the CRM there is no code step any more (redirects to `/`).
- Device trust exists: `portal_service.py:62` verified portal token lives 30 days, sliding. CRM session: 30 days sliding
  (`user_session_service.py`). CRM sign-in has NO second factor today (password, passkey, phone code are each a full
  sign-in; the phone code IS the sign-in).
- Clock bug: `app/models/portal.py:58` `created_at` is naive with `server_default=func.now()` (DB session time zone),
  but `portal_service.py:158` `_utcnow()` = `datetime.utcnow()`. On a DB whose zone is ahead of UTC (dev: +9h) every row
  looks 9h newer: the daily cap (:660-673) counts ~33h of rows, and the 60 s cooldown (:651-658) sees a negative age, so
  "Please wait" holds for ~9h after any code.

## Reuse map

- `home_path_for_user` (phone_signin_service.py:351): extend in place (drop the role branch); used by password, phone and
  passkey login through `build_login_response` :392, so one change covers all three.
- `pickLandingUrl` (signin/page.tsx:65): reuse as is.
- `PortalVerifyCard` `sendCode` (:122) and `handleConfirmIdentity` (:216): reuse; the mount path stops calling `sendCode`.
- `_utcnow` (portal_service.py:158): reuse as the single clock for both writing and reading `created_at`.

## Design (v2)
- Landing: unchanged (owner 13:30: salespeople use the portal).
- Bridge: `POST /api/v1/public/portal/session-from-crm` (CRM Bearer) mints a verified 30-day portal token for the
  caller's OWN `respond_contact_id` only; shared helper with `verify_otp`. Refuses other contacts, API keys,
  impersonation, inactive users.
- Portal slug page: no device token + CRM session -> bridge -> landing; else verify card.
- Verify card: no send on mount; Send code button.
- OTP clock: `created_at` written by `_utcnow()`.
UAC: `signin-2fa-not-role-14nov-acceptance-criteria.md`.
