# PLAN — Security fix cluster (rate-limiting + object-level authz)

**Status:** DRAFT for USER GRILL, 2026-06-30. No code. All items CONFIRMED in the audit. Two independent sub-plans; grill each. Format per item: root cause · fix + recommendation · alternative rejected · risk · UAC · open questions.

---

## SUB-PLAN 1 — Rate-limiting (auth + portal OTP)

**Confirmed gaps:**
- `/auth/signup` (`auth.py:143`) — no throttle → account-creation spam + **email enumeration** (409 on existing email).
- `/auth/reset-password` (`auth.py:212`) — no throttle → reset-link flooding / token brute-force.
- Portal OTP `request_otp` (`portal_service.py:461`) — per-contact 60s cooldown + 10/day cap, but **no per-IP global limit** → contact enumeration + DOS of the Respond.io send queue. Unauthenticated endpoint.
- (Login already has `login_throttle` — `auth.py:44-97` — reuse it.)

**Fix (recommended):**
- **Reuse the existing `login_throttle`** (per email+ip, fails open if Redis down) on `reset_password` and `signup`. For signup, key by IP (no pre-existing account) + cap accounts/hour/IP; return the SAME response timing/shape for new vs existing email to kill enumeration (or at least throttle the 409 path).
- **Add a per-IP global limiter** on `/public/portal/*` (e.g. 30 req/min/IP) in front of `request_otp`; genericize invalid-contact responses (always 404, no timing/error-detail difference).
- *Alternative rejected:* a full API-gateway/WAF rate-limit layer — out of scope for an app-level fix now; the in-app `login_throttle` pattern is already present and proven.

**Risk/blast radius:** low — additive throttles. Watch: throttle must **fail open** if Redis is down (login_throttle already does) so a Redis outage doesn't lock out auth. Don't over-tighten signup (legit bursts from shared office IP) — make the cap configurable.

**UAC:**
- Rapid repeated `reset-password`/`signup`/`portal request-otp` from one IP → 429 after the threshold; `Retry-After` set.
- Existing-vs-new email on signup → indistinguishable response (no enumeration); throttled either way.
- Redis down → auth still works (fail-open), logged.
- Unit tests per endpoint (throttle hit + fail-open); no regression to login.

**Open questions to grill:**
1. Signup: block enumeration by returning a generic "check your email" for BOTH new + existing (recommended), or keep 409 but throttle it?
2. Thresholds (reset/signup/IP-global) — your preferred numbers? Make them env-configurable?
3. Portal OTP: per-IP global limit value, and is a CAPTCHA acceptable on the portal OTP request as defense-in-depth?

---

## SUB-PLAN 2 — Object-level authz (presigned URLs + portal attachments)

**Confirmed gaps:**
- Presigned-URL endpoint (`external/presigned_url.py:88`) — gates on `get_external_api_user` (X-API-Key) but signs **any `file_path`** with no attachment-ownership/permission check (**IDOR**). CloudFront signer uses a **single global key_pair_id** (not per-tenant), so signed URLs are global.
- Portal attachment download (`public/portal.py:715,734`) — `_list_attachments_for` + `_safe_presigned_url` don't re-verify contact ownership; relies on upstream `list_submissions` scoping.

**Fix (recommended):**
- **Presigned endpoint:** after resolving the Attachment row for `file_path`, verify the caller (X-API-Key → `EXTERNAL_API_KEY_ACT_AS_USER_ID` user) has permission to view the **parent entity** the attachment belongs to; 403 otherwise. Reject `file_path`s that don't resolve to a known Attachment row (no signing arbitrary keys).
- **Portal:** ensure `list_submissions` consistently filters `token.contact_id == submission.contact_id`, and re-assert ownership before generating any presigned URL in `_list_attachments_for`.
- **Key scoping (bigger, grill):** evaluate per-tenant CloudFront key groups OR a short presign TTL + audit log of every presign. (Multi-tenant is currently stubbed to DEFAULT_TENANT, so cross-tenant isn't active yet, but cross-entity within the tenant is.)
- *Alternative rejected:* rely on "S3 keys are unguessable" — not a security control; keys appear in URLs/logs.

**Risk/blast radius:** MEDIUM-HIGH change to a hot integration path (n8n uses presigned URLs). Must not break legitimate n8n flows — verify the act-as user has the needed view perms, or n8n's presign calls will start 403'ing. **Coordinate with whoever owns the n8n EXTERNAL_API_KEY_ACT_AS_USER_ID role.**

**UAC:**
- Presign for an attachment the act-as user CAN view → signed URL (works as today).
- Presign for an attachment the act-as user CANNOT view, or a `file_path` with no Attachment row → 403/404, no URL.
- Portal: contact A cannot obtain a presigned URL for contact B's attachment (test).
- n8n's existing presign flows still work (regression — verify the act-as role has the perms those flows need).

**Open questions to grill:**
1. What role is `EXTERNAL_API_KEY_ACT_AS_USER_ID`, and does it have broad view perms (so adding the check won't break n8n)? May need a dedicated service role.
2. Per-tenant CloudFront keys now, or defer until real multi-tenant lands (and just add object-authz + short TTL + audit for now)?
3. Presign TTL — current value acceptable, or shorten?

---

## Sequence
Independent of the broken-Creates/lookup-403 plan. Suggested: **Sub-plan 1 (rate-limiting) first** — self-contained, low-risk, high listed-co value. **Sub-plan 2 (authz)** second — needs the n8n-role coordination to avoid breaking integrations. Each: implement → pytest (throttle/authz unit tests) → verify → deploy.

*(Quick wins not needing a plan, can batch anytime: marketing delete no-op → implement real hard-delete; campaign status casing → normalize; dead filters → remove the never-written options; OTP SHA256 → bcrypt.)*
