# PLAN: CRM sign-in always uses the 30-day sliding session (SIGNIN-ALWAYS-SLIDE)

Status: implemented (small fix track: no migration, no permission change), PR #1404.

## Journey

Owner, 30 Sep 2026: "sign in, be it phone or email, needs the same mechanism as portal; I don't want
the user to tick remember me; when there is activity on continuous days the session just continues".

## Facts (b8cdbebe4)

- Sessions already slide: `user_session_service.resolve_session` re-extends a `rolling` row to now+30d
  once under 29 days remain.
- Phone OTP already minted `remember=True`; only email login honoured the checkbox (`remember_me`,
  default False, so an unticked box gave a fixed 8h session).
- Portal rule is the same pure slide with no absolute cap
  (`_archive/PLAN-staff-rolling-sessions-fastapi-auth.md:31`).

## Change

1. `mint_session` loses its `remember` argument and `SHORT_TTL`: every row is `rolling=True`,
   `expires_at = now + 30d`.
2. `LoginRequest.remember_me` is accepted (an older client still signs in) and ignored.
3. Sign-in page, `signin-schema.ts` and the NextAuth credentials provider drop `rememberMe`.
4. Unchanged: per-request revocation check, device list + revoke endpoints, password reset/change
   revoking all sessions, admin force logout and deactivation. Existing `rolling=False` rows keep
   their fixed 8h and lapse on their own; the column stays (no migration).

## Acceptance

- AC-1: email login with no `remember_me`, `false` or `true` yields `rolling=True`, ~30d expiry.
- AC-2: a request after a simulated day moves `expires_at` back to ~now+30d.
- AC-3: logout revokes the session; the next request is 401.
- AC-4: the sign-in page shows no checkbox and no "Remember me" in email or phone mode.
- AC-5: phone sign-in path unchanged (`test_identity_s1_phone_signin.py` green).

Tests: `tests/test_auth_login.py`, `tests/test_user_session_service.py`,
`app/(auth)/signin/page.test.tsx`.
