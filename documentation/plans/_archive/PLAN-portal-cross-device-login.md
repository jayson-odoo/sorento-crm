# PLAN - Portal cross-device "log in with this number" + OTP template

**Status:** Implemented + verified (2026-06-18). Pending: admin maps the
`portal_otp` template default in Respond.io template-defaults screen (out-of-window
OTP won't send until mapped). Confirm the approved template's category - if it's a
WhatsApp *authentication* template, `send_template_message` needs the copy-code
button component added.

## Problem

Opening a portal deep link (`/portal/c/{slug}/complaint/{id}`) on a second device
or as another salesperson surfaces a raw Postgres 500:

```
invalid input syntax for type uuid: "0dfe4390-...-f9197bce7069%3A"
```

Two distinct issues, plus a requested UX change.

### A. The crash (root cause - not auth)

Customer status messages are built as `...{portal_url}: status changed to ...`.
`_complaint_status_link_part` (complaints_service.py:605) returns ` {url}` and the
caller appends `: status...` immediately after. WhatsApp's link auto-detection
swallows the trailing `:` into the URL, so the delivered link ends in `:`. On the
FE the `[id]` route param becomes `"{uuid}:"`, `encodeURIComponent` → `%3A`,
backend `WHERE complaints.id = '{uuid}%3A'` → invalid UUID → 500. The same greedy
`_URL_RE = re.compile(r"https?://\S+")` in respond_messaging_service.py:33 also
grabs the trailing colon for the template `portal_url` var.

### B. Cross-device flow lands on the wrong card

When the second device 401s on load, `SubmissionForm` redirects to
`portalVerifyPath({reason})` with **no slug**. `portalBase(undefined)` reads empty
localStorage → falls to legacy `/portal/verify` → verify card has no token →
`request-link` state ("message us on WhatsApp"). The user never sees the
"this belongs to {name} - log in with this number?" OTP path even though the slug
is right there in the URL.

### C. Requested UX

- Show "This {complaint} belongs to **{full name}** ({masked phone})" + a
  confirm step "Log in with this number?" → Yes → send code.
- OTP delivery: within 24h window → free-form message; outside → **WhatsApp
  template** (replacing the old "chat with us first to open the window" hatch,
  which stays as a secondary fallback).

## Decisions (from user)

- OTP template **already approved** in Respond.io → wire `request_otp` through the
  window-aware `send_text_or_template`.
- Show **full name** on the verify card (slug is shareable - accepted tradeoff).
- Keep the wa.me "message us" button as a **fallback**, below the OTP flow.

## Changes

### Backend

1. **Colon fix (defense in depth)**
 - `respond_messaging_service.extract_first_url`: strip trailing punctuation
     `).,:;!?` from the matched URL.
 - `complaints_service` status messages: ensure the portal URL is not
     immediately followed by `:` (newline / trailing position) so WhatsApp does
     not absorb punctuation.
 - (FE guard below is the belt to this suspenders.)

2. **Expose name** - `PortalService.identity_hint` adds `name` (full contact
   name). Propagates to `slug_info` + `token_info`; add `name` to
   `PortalSlugInfoResponse` / `PortalTokenInfoResponse`.

3. **OTP via template** - 
 - `models/respond_template.py`: add `"portal_otp"` to
     `TEMPLATE_DEFAULT_USE_CASES` (auto-appears in the admin template-defaults
     screen via `get_defaults`).
 - `respond_template_service.PARAM_VARIABLES`: add `"otp_code"`.
 - `portal_service.request_otp`: replace the raw `RespondClient().send_message`
     with `send_text_or_template(db, identifier=…, text=<otp message>,
     use_case="portal_otp", context_vars={"otp_code": code},
     respond_contact_id=contact.id)`. Keep the daily-cap refund on failure;
     `TemplateSendSkipped` (window closed + no default configured) → refund +
     friendly error. **Risk:** WhatsApp *authentication-category* templates need a
     copy-code button component that `send_template_message` does not emit today;
     if the approved template is authentication-category, extend the send shape.
     Confirm category before relying on out-of-window OTP.

### Frontend

4. Pass `slug` into `SubmissionForm`; on `PortalUnauthorizedError` redirect to
   `portalVerifyPath({ slug, reason: 'expired', type: kind })`.
5. Sanitize the `[id]` route param in the deep-link page (trim trailing
   non-`[0-9a-f-]`) so a mangled link can never reach the backend as `%3A`.
6. `PortalVerifyCard`:
 - `SlugInfo`/`TokenInfo` types gain `name`.
 - When entity context is present (deep link: `type` + slug), render a
     `confirm-identity` state: "This {type} belongs to **{name}** ({masked
     phone}). Log in with this number?" + [Yes, send code] → fire OTP → `otp`
     state. Preserve silent auto-fire for the plain verify entry.
 - Keep the wa.me fallback block.

### Tests (Phase 2)

- pytest: `request_otp` routes through template service when window closed
  (mock window), `slug_info`/`token_info` include `name`,
  `extract_first_url` strips trailing punctuation.
- vitest: `PortalVerifyCard` confirm-identity state renders name + type and
  fires OTP only after confirm.
- playwright: cross-device flow - note creds gap (`USER_GUIDE_E2E_*` not in env),
  fall back to MCP interactive if available.

## Verification

MCP interactive: open a complaint deep link in a fresh context (no token) →
confirm-identity card shows name + masked phone → confirm → code field → wa.me
fallback present. Check `browser_network_requests` for `slug-info` + `request-otp`.
