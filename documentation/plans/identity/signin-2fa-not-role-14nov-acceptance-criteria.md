# UAC: SIGNIN-2FA-NOT-ROLE

Status: v2, after the owner's 14 Nov 13:30 correction (landing unchanged). Behaviour card v2 on PR #2411; remaining
questions proceed on the recommendations (no new CRM 2FA, 30-day sliding, no data delete).

## Landing unchanged
- AC-1 `home_path_for_user` (`phone_signin_service.py:351`) returns exactly what it returns on main for every role mix
  (existing tests stay green; no edit to that function).

## CRM sign-in counts as verified for the user's OWN linked contact (new endpoint)
`POST /api/v1/public/portal/session-from-crm`, body `{ "slug": "<portal slug>" }`, auth = CRM Bearer session.
- AC-2 A signed-in ACTIVE user whose `users.respond_contact_id` is contact X, posting X's slug, gets 200
  `{ token, expires_at }`; the token's row has `verified_at` set and `expires_at` ~ now + 30 days, and `GET
  /api/v1/public/portal/me` with that token answers 200 for contact X. No `portal_otp_codes` row is written.
- AC-3 Same user posting contact Y's slug (any contact not their own) -> 403, no token row written.
- AC-4 No Bearer / invalid session -> 401. An `X-API-Key` principal -> 403. A user with no linked contact -> 403.
  An unknown slug -> 404 (or 403; never a token).
- AC-5 An impersonated CRM session (admin viewing as the salesperson) -> 403: the bridge never mints for an
  impersonation, the existing view-as flow stays the way an admin sees the portal.
- AC-6 `verify_otp` and the bridge mint through ONE shared helper (same verified_at + 30-day expiry rule).

## Portal slug page uses the bridge
- AC-7 `/portal/c/<slug>` with no device portal token and a NextAuth session: calls the bridge once; on success writes
  the portal token + slug and renders the portal landing; no redirect to verify; no request-otp call.
- AC-8 With no NextAuth session, or a bridge refusal/failure: today's redirect to the verify page.
- AC-9 With a device token for a DIFFERENT slug: today's "slug wins" clears it, then AC-7/AC-8 apply.

## No auto-send
- AC-10 `PortalVerifyCard` (slug and token mode) makes NO request-otp call on mount; it shows the masked number and a
  "Send code" button. Pressing it makes exactly one request-otp call and shows the code field; Resend keeps the 60 s
  cooldown. A reload does not send.
- AC-11 The `autoSend` prop goes (nothing sends on mount any more).

## OTP clock
- AC-12 `portal_otp_codes.created_at` is written from the same naive-UTC clock `_utcnow()` it is compared with. With the
  DB session time zone set to `Asia/Seoul`: a code created 2 minutes ago does not trigger "Please wait"; 10 codes
  created 25 hours ago (UTC) do not trigger "Daily verification limit reached".

## Remembered
- AC-13 A verified portal token slides to 30 days on use (unchanged, `portal_service.py:509`).
