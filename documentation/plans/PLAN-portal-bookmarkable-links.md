# PLAN — Portal Bookmarkable Links + CSW-Closed OTP Fallback

**Date:** 2026-06-04
**Owner:** TBD
**Status:** Phase 1 ✅ prototype signed off · Phase 2 ✅ BE wired (migration 224, slug-info/logout endpoints, sliding 30d TTL, OTP daily cap, impersonation carve-outs) + FE off mocks + tests green (15 new pytest / 21 portal vitest / 3 e2e) · Phase 3 ✅ /code-review done — 10 verified findings fixed (slug_info space_id fallback, fetchMe grace retry restored, OTP cap excludes failed sends, phantom-sent guard, impersonation-exit token preservation, lookup-failed recovery card, identity_hint extraction, SUBMISSION_KINDS dedup, build_portal_url token_row param); banner double-fetchMe acknowledged as pre-existing. Open config: set `respond_workspaces.whatsapp_number` (or `PORTAL_WHATSAPP_NUMBER` env) to enable the wa.me escape hatch — hidden until configured. Workspace-number auto-fetch from Respond API dropped in favour of the column (decision 6b amended).

## 1. Problem

Two breaking points in the customer portal access flow:

1. **Not bookmarkable.** Portal links arrive as `/portal?token=...`; the FE strips the token into `sessionStorage` and the address bar becomes generic (`/portal`, `/portal/{type}/new`). `sessionStorage` dies on tab close. A bookmarked URL carries no identity — next session the user is locked out and must ask for a fresh link.
2. **OTP undeliverable when CSW is closed.** Token expiry/re-verification sends a 6-digit OTP via Respond.io free-form message. WhatsApp only delivers free-form messages inside the 24h customer-service window (CSW). Outside it, delivery requires a paid WhatsApp template — and the client has no WABA balance. Respond.io's send API is **async**: the API call succeeds even when delivery will fail; failure is only visible by fetching message status by `message_id` later. So today the user sees "code sent", nothing arrives, dead end.

Root cause of both: no durable identity artifact on the user's side.

## 2. Solution overview

Two mechanisms, one design:

- **Stable per-contact URL** — `/portal/c/{slug}` where `slug` is a short random ID on `respond_contacts`. The URL is an *identity hint, not a credential*: it identifies which contact wants in, but entry still requires a live device token or OTP. Safe to bookmark, share, sit in chat history forever.
- **Device trust** — verified portal token moves `sessionStorage` → `localStorage` with a **sliding 30-day TTL**. Active users never re-OTP. The OTP becomes a rare event (new device / 30d dormancy), which also shrinks the CSW problem.
- **CSW escape hatch** — verify page always shows a secondary CTA: "No code? **Message us on WhatsApp**, then tap Resend" → `wa.me/{business_number}?text=...`. The user's inbound message opens the CSW; the resend then delivers free. No polling, no templates, RM0.

## 3. Locked decisions

| # | Decision |
|---|----------|
| 1 | **Both mechanisms** — stable slug URL (any device) + localStorage device trust (silent re-entry). OTP only when no live local token. |
| 2 | **Slug** — new `portal_slug` column on `respond_contacts`: 10–12 char random Crockford base32, lazy-minted on first portal-link mint, immutable. Identity hint, never a credential — knowing it only lets you trigger an OTP *to the contact's own WhatsApp*. `respond_contacts` is unique per phone, so no identity collision. |
| 3 | **Sliding window** — 30d TTL on verified tokens; each authenticated request extends `expires_at` to now+30d, throttled to one DB bump per 24h. Reuse `PortalToken` (no new table). Unverified link-tokens keep fixed 7d. No hard cap for now. |
| 4 | **CSW closed → wa.me click-to-chat reopen.** WhatsApp templates parked until client funds WABA (future: setting flips OTP send to auth template; CTA becomes dead branch). |
| 4b | **Manual resend** — after user sends the WhatsApp message, they return and tap "Resend code". No n8n auto-fire for OTP (slug-matching auto-fire has a spoof surface: attacker texting someone else's slug). |
| 6 | **No message-status polling.** `request-otp` stays fire-and-forget. Verify page always renders the wa.me escape hatch under the code input — robust against every failure mode (window closed, Respond outage, wrong number). Status polling (Respond `GET message/{id}`) deferred unless support tickets show confusion. |
| 6b | **Business WhatsApp number** — fetched from Respond.io workspace/channel info by the token/slug's `space_id` (1 workspace = 1 WhatsApp number), cached 24h. Env override `PORTAL_WHATSAPP_NUMBER_OVERRIDE` as fallback if Respond's API lacks a clean channel-number endpoint (verify during build). |
| 7 | **Bookmark distribution** — (a) once session live, `router.replace` to `/portal/c/{slug}`; all portal pages live under the slug path so the address bar *is* the durable link; (b) one-time dismissible hint "Bookmark this page for easy access" on first verified visit; (c) sent WhatsApp links become `/portal/c/{slug}?token=...` — token half expires, slug half stays a working re-entry point. Old plain `?token=` links keep working. |
| 8 | **Shared device: slug wins.** `/portal/c/{slugY}` with stored token for contact X → ignore token, verify as Y, overwrite localStorage on success. Single token per device. Plain `/portal` with live token → redirect to that contact's slug URL; dead token → generic "use your portal link" page. |
| 9 | **Impersonation carve-outs** — new `is_impersonation` boolean on `portal_tokens`: excluded from sliding extension (keeps fixed short TTL); FE impersonation flow uses sessionStorage only (never persistent); impersonation-end revokes the token (verify wiring during build). Real users' UX unaffected. |
| 10 | **New public surface** — `GET /api/v1/public/portal/slug-info/{slug}` → `{ masked_phone, space_id, whatsapp_number }` (404 unknown slug, no detailed error states); `POST request-otp` accepts `{ slug }` OR `{ token }`; `verify-otp` unchanged — mints fresh verified token, FE writes to localStorage. |
| 10b | **Abuse limits** — existing 60s per-contact cooldown kept; new daily cap 10 OTP sends/contact/day. Slug entropy (~50–60 bits) makes enumeration moot. No per-IP limiting in v1. Masked phone shows last 4: `+60••••1234`. |
| 11 | **Logout + "Not your number?"** — portal header "Log out" clears localStorage **and** revokes server-side. Verify page "Not your number?" clears local state → wa.me link with prefilled "Hi, I'd like my portal link" (opens CSW too, so reply can be free-form). v1: agent replies manually. v1.1 optional: n8n keyword workflow auto-replies with fresh slug link — safe here because identity = sender's own phone (unlike OTP auto-fire). |

## 4. Backend implementation

### 4.1 Migrations

1. `respond_contacts.portal_slug` — `VARCHAR`, nullable, unique index. Lazy backfill (minted on next portal-link request), no data migration.
2. `portal_tokens.is_impersonation` — `BOOLEAN NOT NULL DEFAULT false`. Backfill `true` for tokens referenced by `contact_impersonation_sessions`.
3. `portal_otp_codes` — supports daily-cap query (count by contact + day); add index if needed.

### 4.2 `portal_service.py`

- `get_or_create_slug(contact_id)` — mint Crockford slug, retry on unique collision.
- `mint_token(...)` — set `is_impersonation` when called from impersonation flow; link URL becomes `/portal/c/{slug}?token=...&type=...`.
- `_resolve_portal_token()` — sliding bump: if `verified_at IS NOT NULL AND NOT is_impersonation AND expires_at < now + 29d` → `expires_at = now + 30d` (the 29d check = daily throttle without extra column).
- `request_otp(slug=None, token=None)` — resolve contact from either; enforce cooldown + daily cap (10/day).
- `slug_info(slug)` — masked phone (last 4), `space_id`, business WhatsApp number.
- `revoke_token(token)` — for logout endpoint.
- Workspace number lookup: `RespondClient` method for channel/workspace info, in-process cache 24h, env override.

### 4.3 Routes (`app/api/v1/public/portal.py`)

- `GET /slug-info/{slug}`
- `POST /request-otp` — body now `{ slug? , token? }` (exactly one)
- `POST /logout` — header token → revoke
- Existing endpoints unchanged.

### 4.4 External API

- `POST /external/portal-tokens/` response gains `portal_url` using slug format, so n8n messages carry the durable link.

## 5. Frontend implementation

- **`portal-client.ts`** — `sessionStorage` → `localStorage` (key unchanged); impersonation entry (`?impersonation=1` or equivalent) keeps sessionStorage; store active slug alongside token.
- **Route restructure** — portal pages mounted under `/portal/c/[slug]/...`; legacy `/portal` + `/portal/{type}/new` become thin redirectors (resolve slug from live token, else expired-link page).
- **`/portal/c/[slug]` entry logic** — live local token matching slug's contact → in; mismatch or none → verify page for this slug.
- **Verify page** — works from slug alone (`slug-info`); masked phone; "Send code" / "Resend code"; always-visible wa.me escape hatch ("No code after a minute? Message us on WhatsApp, then tap Resend"); "Not your number?" → clears state + wa.me portal-link request.
- **Bookmark hint** — one-time dismissible (localStorage flag) on first verified visit.
- **Logout** — header button → `POST /logout` + clear localStorage → expired-link page.

## 6. Tests (Phase 2, per three-phase loop)

- **pytest:** slug mint/collision; slug-info (known/unknown/masking); request-otp by slug + by token; cooldown + daily cap; sliding bump (verified vs unverified vs impersonation); logout revoke; external portal-tokens URL shape.
- **vitest:** verify page states (idle / sent / cooldown / wa.me hatch / not-your-number); slug-wins token-mismatch logic; bookmark hint show-once.
- **Playwright e2e:** slug URL → verify → OTP → land in portal → reload (localStorage persists) → logout → locked out. Sidebar-nav rule N/A (portal is public surface), still navigate from portal landing, not deep URLs.

## 7. Open items (verify during build)

- Respond.io API: does workspace/channel info endpoint expose the WhatsApp number cleanly? If not → env var only.
- Impersonation-end: confirm it revokes the token today; wire if not.
- OTP message copy: mention the wa.me fallback in the message itself? (Probably not — message only arrives when delivery worked.)

## 8. Phases

1. **Phase 1 — FE prototype:** slug routes + verify page + wa.me hatch + bookmark hint against mocked `slug-info`/`request-otp`. Playwright MCP walkthrough + screenshots.
2. **Phase 2 — BE wiring + tests:** migrations, service, routes, external API; FE off mocks; all three suites green.
3. **Phase 3 — `/code-review`** then PR.
