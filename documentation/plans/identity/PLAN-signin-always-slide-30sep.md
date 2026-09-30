# PLAN: CRM sign-in always uses the 30-day sliding session (SIGNIN-ALWAYS-SLIDE)

Status: in review (Track: full). PR #1404. Plan created: 2026-09-30.

Track note: first filed as small fix (under 300 lines, no migration); re-tracked to FULL on the
30 Sep process audit because the diff changes staff auth/session lifetime and NextAuth, which is on
the small-fix exclusion list (`PRINCIPLES.md` "Small fix track": no auth change). Full-track
steps run for this lane: UAC file (`signin-always-slide-30sep-acceptance-criteria.md`), red-first
regression tests with kill test, `reviewer` + `security-reviewer` in parallel, agent-browser pass at
1280 and 375, DoD gate. Journey/grill: the owner's instruction below is the journey; no open
questions to grill (owner ruling is explicit and matches the archived staff-sessions plan).

## Journey

Owner, 30 Sep 2026: "sign in, be it phone or email, needs the same mechanism as portal; I don't want
the user to tick remember me; when there is activity on continuous days the session just continues".

## Grill (feature skill step 2, run late on the 30 Sep process audit)

The code was written before this grill, so every question below is asked against a change that
already implements the recommendation. Sent to the owner as one `crew-ask` on PR #1404
(30 Sep 2026). An answer that differs from the recommendation reopens the lane.

| # | Decision | Options | Recommendation (implemented) | Owner answer |
| --- | --- | --- | --- | --- |
| G1 | Absolute cap | (a) pure sliding, no cap; (b) hard cap e.g. 90d | (a): owner asked for "exactly like portal", which has no cap | pending |
| G2 | Idle window | (a) 30d without a request; (b) shorter e.g. 7d | (a): matches portal and phone today | pending |
| G3 | Existing 8h (`rolling=false`) rows | (a) lapse within 8h; (b) migration flips them | (a): at most one extra sign-in, no migration | pending |
| G4 | Legacy `remember_me` in the login body | (a) accept and ignore; (b) 422 | (a): a cached old bundle keeps signing in | pending |
| G5 | Shared/kiosk devices (30d session left behind) | (a) accept, rely on logout / sign out other devices / admin force logout; (b) idle timeout or "public computer" option | (a); trigger for (b): a real shared-device incident | pending |
| G6 | Impersonation has no TTL of its own (was implicitly 8h for unticked admins) | (a) backlog a follow-up for an 8h impersonation TTL; (b) in this PR; (c) leave | (a): predates the lane, keeps this PR to sign-in | pending |
| G7 | Tell users they stay signed in | (a) no UI text, one line in the Outline guide batch; (b) hint under Continue | (a): CLAUDE.md "no feature explanations inside the UI" | pending |
| G8 | Phone sign-in and portal | no change, both already slide 30d | confirm no change | pending |

## TDD note

Order was code first, tests second, on the small-fix track. Rules allow that track to write tests
and fix in one pass, but still require reds shown red. Once re-tracked to FULL, each behaviour was
proven with a kill test instead: break the implementing line, show the named test go red, restore.
Results are in the PR's DoD gate comment and in the table below.

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

See `signin-always-slide-30sep-acceptance-criteria.md` (AC-1 to AC-6, with the test for each).

## Evidence run (agent-browser, 30 Sep 2026)

Stack: this branch in the cloud sandbox. Backend `uvicorn` on :8000 against a throwaway
`sorento_ci` DB (bootstrap_env), frontend `npm run dev` on :3000. Tool: `agent-browser@0.27.0`
with named sessions `slide` (signed in) and `slideout` (signed out). No shared DB touched.

1. `open http://localhost:3000/` at 1280x800 while signed out. The sign-in form renders with
   Email, Password, Forgot Password?, Continue and the phone button. DOM check:
   `{checkboxes: 0, rememberText: false, overflowX: false}`.
2. Fill `zzt.slide@example.com` / password, then click Continue. `POST /api/v1/auth/login` returns 200 and
   the app shell (Dashboards) loads. DB: `auth_method=password, rolling=t,
   remaining=29 days 23:59:43`.
3. Simulate a day: `expires_at -= 1 day 1 hour` gives `remaining=28 days 22:59:38`. Click the
   sidebar "Dashboards" link. DB: `remaining=29 days 23:59:53`, so the session slid forward on
   activity.
4. Signed-out session at 1280x800 and at 375x812: open `/` (redirects to
   `/signin?callbackUrl=%2F`). Email mode, then click "Phone number". Phone mode shows the country
   select, the Phone number input, Continue and Back to email. The DOM check in all four
   states (email/phone x 1280/375) is `{checkboxes: 0, rememberText: false, overflowX: false}`.
   The 375 screenshot shows the card unclipped.
5. Screenshots committed (repo cap: two per lane, each under 200 KB):
   `evidence/signin-always-slide-email-1280.png` (email mode, 1280) and
   `evidence/signin-always-slide-phone-375.png` (phone mode, 375). The other two states are
   covered by the DOM check in step 4.

Stack note: this ran on the branch's own stack in the cloud sandbox, not on the crew test copy.
The worker cannot reach the owner's machine; the owner's hand test on the crew copy passed.

Phone OTP end-to-end is not walked in the browser. It needs a Respond.io send, which the sandbox
must not call. It is covered by `test_regression_phone_otp_session_is_30d_and_slides_after_a_day`
and was part of the owner's hand test (PASS).
