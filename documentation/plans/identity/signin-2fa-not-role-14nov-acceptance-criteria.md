# UAC: SIGNIN-2FA-NOT-ROLE

Status: draft, assumes the recommended answers on the PR #2411 behaviour card (Q1 a, Q2 a, Q3 a, Q4 a, Q5 a).
Rewritten once the owner answers.

## Landing (backend `home_path_for_user`, all three login routes)
- AC-1 An active user with any CRM role permission or admin/superadmin, with or without the salesperson role and a
  linked contact, gets `home_path == "/"` from `/auth/login`, `/auth/phone/verify` and `/auth/passkey/verify`.
- AC-2 (Q1 a) A pure salesperson (roles within salesperson + portal_user) with a linked contact also gets `"/"`.
- AC-3 A contact-linked user with no CRM role at all (portal-only) keeps the portal home.
- AC-4 Role order never changes the result: same roles, any primary role -> same `home_path`.
- AC-5 A safe deep link `callbackUrl` still wins over `home_path` (unchanged).

## No auto-send (frontend `PortalVerifyCard`)
- AC-6 Opening `/portal/c/<slug>/verify` or `/portal/verify?token=..` makes NO request-otp call on load; it shows the
  masked number and a "Send code" button.
- AC-7 Pressing "Send code" makes exactly one request-otp call and then shows the code field; Resend keeps the 60 s
  cooldown.
- AC-8 Reload after a sent code does not send another.

## Own-contact bridge (Q3 a)
- AC-9 A CRM-signed-in user whose account is linked to contact X, opening `/portal/c/<X slug>` with no portal token,
  gets a portal session for X without any code (no request-otp call, no OTP row).
- AC-10 The same user opening contact Y's slug (not their linked contact) gets the verify card (AC-6); the bridge
  refuses Y server-side (403), whatever the client sends.
- AC-11 The bridge refuses a trashed/inactive user, a user with no linked contact, and an X-API-Key principal.

## Remember verified (Q4 a)
- AC-12 A verified portal token keeps sliding to 30 days (unchanged); a verified device is not asked again.

## OTP clock (Q5 a)
- AC-13 `portal_otp_codes.created_at` is written from the same UTC clock it is compared with: with the DB session time
  zone set to +09:00, a code sent 2 minutes ago does not block a new one (cooldown 60 s), and 10 codes older than 24h
  UTC do not count toward the daily cap.
