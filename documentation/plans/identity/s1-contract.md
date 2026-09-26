# S1 contract: phone sign-in on the existing /signin (#1280)

Phase 1 contract for slice S1 of `PLAN-unified-identity-26sep.md` (section 10 S1; sections 4.2,
4.3 session part, 5.1, 5.3 password and lost-phone parts). UAC: AC-20 to AC-29 in
`identity-unified-login-acceptance-criteria.md`. Paths are relative to `sorento_crm_backend/`
(BE) and `sorento_crm_frontend/` (FE).

## First task: the WhatsApp template (plan S1 "First task")

- The approved template text itself lives in Respond.io and the `respond_message_templates` table,
  not in the repo. What the repo shows: the use case is `portal_otp`, labelled "Portal OTP" and
  described as "Login verification code sent when a contact opens the portal on a new device"
  (`services/whatsappTemplateService.ts`), and the in-window free text is "Your Sorento portal
  verification code is {code}..." (`app/services/portal_service.py`). Both name the portal.
- So S1 builds against a new use case `login_otp` behind the setting
  `phone_signin_otp_use_case` (default `"login_otp"`). At send time, when no default template is
  configured for that use case, the send falls back to `portal_otp`. Phone sign-in therefore works
  on day one with the portal template, and switches to a sign-in template the moment the owner
  maps an approved one in the template defaults screen. The in-window free text for sign-in names
  no portal: "Your Sorento sign-in code is {code}. It expires in 10 minutes. Please do not share it
  with anyone."
- `login_otp` joins `TEMPLATE_DEFAULT_USE_CASES` and `REQUIRED_PARAM_VARIABLE` (`otp_code`), and
  the FE template list gains "Sign-in OTP".

## Backend

### `POST /api/v1/auth/phone/request-code` (public, AC-21, AC-22, AC-23)

Request `{ "phone": "012-345 6789" }` (any format; normalised by `normalize_msisdn`).

- 422 when the number does not normalise to 8 to 15 digits: `detail` "Enter a valid phone
  number." (depends only on the typed text, never on the database).
- 429 per IP (bucket `phone_signin_otp`, the portal OTP IP limits `rate_limit_portal_otp_*`),
  per number cooldown (60 s) and per number daily cap (10 per 24 h). All three are keyed on the IP
  or the typed number, never on whether it belongs to anyone. Body
  `detail = { code: "RATE_LIMITED", message: "Too many tries. Try again in N minutes.",
  retry_after_seconds }` plus `Retry-After`.
- 200 otherwise, the same body for every number:
  `{ "sent_to": "+60••••6789", "expires_in_seconds": 600, "resend_in_seconds": 60 }`
  where `sent_to` is the mask of the TYPED number (never a stored one).
- A code is created and sent only when the number resolves to exactly one user that is ACTIVE,
  not trashed, not an integration, has `respond_contact_id` set, and whose contact's phone
  normalises to the same number as the user's phone. The code is a `portal_otp_codes` row keyed
  by that contact, space = the contact's workspace `space_id`, sent by the RQ task
  `send_login_otp_respond_message` on the `respond_io` queue, which writes an `integration_logs`
  row on success and on failure. When the contact's own DB cooldown or daily cap (shared with the
  portal) blocks a send, nothing is sent and the answer is still the same 200.
- Unknown numbers do the same lookups; only the insert and the enqueue are skipped. Nothing is
  ever created for a contact with no user, and no user is ever created.
- Every 200 records "a code was requested for this number now" in Redis (10 minute TTL) for the
  verify step's messages.

### `POST /api/v1/auth/phone/verify` (public, AC-23, AC-24, AC-27)

Request `{ "phone": "...", "code": "123456" }`.

- 200: `LoginResponse` (the email login shape, plus `home_path`). Creates a `user_sessions` row
  with `auth_method = "phone_otp"`, rolling 30 days (`remember=True`); consumes the code; stamps
  `users.phone_verified_at` and `last_sign_in_at`.
- 401 `detail = { code: "CODE_EXPIRED", message: "That code has expired. Send a new one." }` when
  no code was requested for this number in the last 10 minutes.
- 401 `detail = { code: "CODE_WRONG", message: "That code is not right. N tries left.",
  attempts_left: N }` for a wrong code, an unknown number, a user who is no longer eligible, or a
  contact whose code is missing. The tries count is kept per typed number (Redis), so an unknown
  number counts down exactly like a known one.
- 429 `detail = { code: "RATE_LIMITED", message: "Too many tries. Try again in N minutes.",
  retry_after_seconds }` on the fifth wrong try and after, for 15 minutes per number; a new
  request-code does not lift it. Also the per-IP limit.
- 422 for an invalid number or a code that is not 6 digits.

### `POST /api/v1/auth/login` (AC-26)

- An unknown email, a trashed user and a wrong password answer the same 401
  `detail: "Invalid credentials."`, with a throwaway bcrypt on the unknown path so the timing
  matches. INACTIVE and BLOCKED keep today's 403 after a correct password.
- `LoginResponse` gains `home_path` (AC-28): `/portal/c/{slug}` of the linked contact for a user
  holding `salesperson`; `/` for a user with any CRM permission or an admin role; the portal home
  for a user with neither and a linked contact; else `/`.

### `POST /api/v1/auth/password` (session, plan 5.3)

Request `{ "current_password": "..."?, "new_password": "..." }`. When the user already has a
password, `current_password` is required and checked (400 "Current password is not right.").
A phone-only user sets one without it. New password: 8 characters or more. On success every
OTHER session of the user is revoked (the current one stays). `GET /api/v1/user-management/account/`
gains `has_password` (bool) and `phone_verified_at`.

### Lost phone (plan 5.3)

`PUT /api/v1/user-management/users/{id}` that changes `contact_number` clears
`phone_verified_at` and revokes every session of that user. Blocked and trashed users cannot sign
in by any method.

## Frontend

- `/signin`: under "Sign in to Sorento", a full-width two-option `Tabs` (`variant="default"`)
  "Email | Phone", Email selected. Email content is today's form unchanged. Phone step 1:
  "Phone number" `Input` (`inputMode="tel"`, `autoComplete="tel"`, placeholder
  "e.g. 012-345 6789"), full-width "Continue". Step 2: "We'll send a code to your WhatsApp
  <sent_to>" with "Change number", then the shared code field. The error `Alert` sits under the
  toggle in both modes.
- Shared `components/auth/OtpCodeField.tsx`: "Verification code" label, `Input variant="lg"`,
  numeric, `one-time-code`, placeholder "6-digit code", centred and letter-spaced, and the outline
  "Resend in Ns" / "Resend code" button; fires `onComplete` on the sixth digit. The portal
  `PortalVerifyCard` and `/signin` both import it (`data-testid="otp-code-field"`).
- NextAuth gains a second Credentials provider `phone-otp` posting `{phone, code}` to
  `/api/v1/auth/phone/verify`; the token carries `homePath`. After any sign-in the page goes to
  a safe `callbackUrl`, else `session.user.homePath`, else `/`.
- `services/phoneSigninService.ts` (`requestSigninCode`) through `lib/api-client`, used by the hook
  `usePhoneSignin`.
- Account > Security: the Password card's button reads "Set a password" when `has_password` is
  false, "Change password" otherwise, and opens a modal (Current password only when one exists,
  New password, Confirm new password, Save).
