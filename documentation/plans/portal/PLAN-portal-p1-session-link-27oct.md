# PLAN: portal P1, WhatsApp portal link opens a CRM session (27 Oct 2026)

Status: in review (27 Oct 2026). Track: full (auth change) + security review. Lane PORTAL-P1-SESSION-LINK.

Source brief: `documentation/plans/portal/PLAN-portal-unify-scout-27oct.md`, section "Lane briefs" -> P1
(PR #1894, head 5e54df1a). Alignment (option (i), one CRM shell; reuse, no parallel implementation) is in
the same file. This file only records lane decisions; the brief is the contract.

## Scope (as built; brief plus the security-review change below)

- `/public/portal/verify-otp` (unchanged `PortalService.verify_otp`) also returns a one-time
  `portal_link_secret`, only when the contact has an eligible user. For everyone else the body is
  byte-identical to today (`response_model_exclude_none`, no null key).
- New `POST /api/v1/auth/portal-link` (`{portal_link_secret}` -> `LoginResponse`) mints a
  `user_sessions` row with `auth_method = portal_link` via `mint_session` + `build_login_response`.
- NextAuth `phone-otp` provider gains a `portal_link_secret` credential branch (no new provider).
- `PortalVerifyCard` calls `signIn('phone-otp', {portal_link_secret})` after `verifyOtp` only when the
  secret is present, before navigating. Landing unchanged (P3).
- Portal Log out also revokes the session row and signs NextAuth out, only for the user the card signed in.

## Acceptance criteria

AC-1 to AC-7 as in the source brief, section P1, read with lane decision 1 (the exchange takes the
secret, not the portal token; AC-6's `has_user` is not needed). Tests:
`sorento_crm_backend/tests/test_portal_p1_session_link.py`, vitest
`PortalVerifyCard.portalLink.test.tsx`, `portal-client.crmSession.test.ts`,
`auth-options.portal-link.test.ts`.

## Lane decisions

1. **Security review H1: the exchange takes a one-time secret, never a portal token.** `verify_otp`
   stamps `verified_at` on every unverified token of the contact (admin-sent links included), and staff
   "copy portal link" (`get_or_mint_token`) returns the freshly verified 30-day token, so a token-based
   exchange let someone other than the code-holder race the card for a staff session. The secret is
   `secrets.token_urlsafe(32)`, only its sha256 is stored (Redis, 120 s TTL, value = contact id), and
   the exchange reads and deletes it in one MULTI transaction. No Redis = no secret / refusal (fail
   closed); the portal is unaffected.
2. **No `user_sessions.portal_token_id` migration** (the brief left this to the security review). One
   OTP stamps N tokens, so a per-token unique key would allow N sessions; it does not stop the wrong
   holder winning; Redis down already fails closed; the window is 120 s. Revisit trigger: prod Redis
   configured with eviction or without persistence.
3. **`has_user` dropped from slug-info / token-info.** The secret's presence is the card's signal, so
   the public routes do not mark which WhatsApp contacts are staff (security review L1).
4. **Eligibility = phone sign-in's rule** (`_eligible_user_clauses`, shared with `find_eligible`):
   ACTIVE, not trashed, not integration, linked contact, AND the user's own number normalises to the
   contact's phone ("lost phone" rule, plan 5.3). Re-checked at the exchange.
5. **Own rate limit** `rate_limit_portal_link_*` (10 per 300 s per IP; security review M1).
6. **Logout flag holds the user id** (security review L2): portal Log out revokes only if the
   NextAuth session is still that user.
7. **Follow-up, out of scope (security review M2, pre-existing):** the portal link message, `?token=`
   included, is logged to `integration_logs`, and `GET /integrations/logs` has no permission gate.
