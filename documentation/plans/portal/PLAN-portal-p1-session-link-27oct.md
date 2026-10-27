# PLAN: portal P1, WhatsApp portal link opens a CRM session (27 Oct 2026)

Status: in progress (27 Oct 2026). Track: full (auth change) + security review. Lane PORTAL-P1-SESSION-LINK.

Source brief: `documentation/plans/portal/PLAN-portal-unify-scout-27oct.md`, section "Lane briefs" -> P1
(PR #1894, head 5e54df1a). Alignment (option (i), one CRM shell; reuse, no parallel implementation) is in
the same file. This file only records lane decisions; the brief is the contract.

## Scope (from the brief)

- New `POST /api/v1/auth/portal-link` (`{portal_token}` -> `LoginResponse`), minting a `user_sessions` row
  with `auth_method = portal_link` via `mint_session` + `build_login_response`.
- `has_user` boolean on `/public/portal/slug-info/{slug}` and `/public/portal/token-info`.
- `PortalVerifyCard` calls `signIn('phone-otp', {portal_token})` after `verifyOtp` only when `has_user`.
- NextAuth `phone-otp` provider gains a `portal_token` credential branch (no new provider).
- Portal Log out also calls NextAuth `signOut` (revokes the session row).

## Acceptance criteria

AC-1 to AC-7 exactly as in the source brief, section P1. Tests: pytest per AC on the route; vitest on the
PortalVerifyCard branch.

## Lane decisions

(filled in as they are made: one-time exchange decision from the security review, rate limit, etc.)
