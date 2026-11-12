# UAC: Passkey sign-in for CRM staff (PASSKEY-LOGIN)

Plan: `PLAN-passkey-login-12nov.md`. Questions 1-4 assume the recommended answers until crew
relays the owner's; any change is edited here first. Q5 answered (config hostname list).

## Configuration
- AC-01 `Settings.webauthn_rp_ids` (env `WEBAUTHN_RP_IDS`, comma-separated hostnames, default
  empty) and `Settings.webauthn_rp_name` (env `WEBAUTHN_RP_NAME`, default "Sorento CRM").
- AC-02 An origin is allowed when its hostname is in `webauthn_rp_ids` AND (scheme `https`, any
  port) OR (scheme `http` AND hostname `localhost`). The RP ID used is that hostname. Anything else
  (unlisted hostname, `http` on a non-localhost host, missing/garbled Origin) is not allowed.
- AC-03 With `webauthn_rp_ids` empty every passkey route except the list answers
  `400 {"code": "PASSKEYS_UNAVAILABLE"}`; `GET /api/v1/auth/passkey/status` answers
  `{"enabled": false}` (true when the list is non-empty). No real hostname is committed anywhere.

## Data
- AC-04 New table `user_passkeys`: `id` uuid pk, `user_id` FK `users.id` ON DELETE CASCADE (indexed),
  `credential_id` text UNIQUE (base64url), `public_key` bytea, `sign_count` bigint default 0,
  `transports` json nullable, `aaguid` varchar nullable, `backed_up` bool default false,
  `name` varchar(100) not null, `created_at`, `last_used_at` nullable. Additive migration.
- AC-05 `user_sessions.auth_method` accepts `'passkey'` (`AUTH_METHODS` + `ck_user_sessions_auth_method`,
  added NOT VALID then VALIDATE). Single alembic head.

## Sign in (unauthenticated; prefix `/api/v1/auth`)
- AC-10 `POST /passkey/options` (no body; origin from the `Origin` header) returns
  `{"challenge_id": str, "options": PublicKeyCredentialRequestOptionsJSON}` with `rpId` = the
  origin's hostname, `userVerification: "required"`, empty `allowCredentials` (discoverable
  passkeys; no email asked, so nothing to enumerate). The challenge, origin and RP ID are stored
  in Redis for 300 s under the challenge id. Per-IP rate limit via `rate_limit.hit`; over limit = 429.
- AC-11 `POST /passkey/verify` `{"challenge_id", "credential": AuthenticationResponseJSON}` with a
  valid assertion from a registered passkey of an ACTIVE, non-trashed user returns the same
  `LoginResponse` as `/auth/login` (via `build_login_response`), mints a `user_sessions` row with
  `auth_method = 'passkey'` (30-day rolling, same as password), sets `users.last_sign_in_at`,
  the passkey's `last_used_at` and new `sign_count`, and writes one `audit_logs` row
  `entity_type = 'user_passkeys'`, `event = 'passkey_sign_in'`, `user_id` = that user.
- AC-12 Refused with `401 {"code": "PASSKEY_FAILED", "message": "That passkey didn't work. Sign in another way."}`
  and no session minted, for each of: unknown/expired challenge id; a challenge already used once
  (replay: the second verify of the same challenge fails even with a valid assertion); a
  challenge issued for registration; clientData origin different from the stored origin; RP ID
  hash for a different hostname; unknown credential id; signature by a different key; wrong
  challenge bytes in clientData; user verification flag not set; a sign count that is non-zero and
  not greater than the stored non-zero count (cloned authenticator). The body is byte-identical
  across these cases.
- AC-13 A valid assertion for a user that is INACTIVE / BLOCKED (status not ACTIVE) answers
  `403` with the same detail `/auth/login` uses; a trashed user answers the AC-12 401. No session.
- AC-14 `/passkey/verify` is rate-limited per IP (`rate_limit.hit`, own bucket); over limit = 429
  with Retry-After. Redis down: challenge store unavailable = `400 PASSKEYS_UNAVAILABLE`
  (fail closed for the challenge; never accept an assertion without a stored challenge).

## Own passkeys (authenticated; real user, prefix `/api/v1/auth`)
- AC-20 `GET /passkeys` lists the REAL user's (`get_actor_user_id`) passkeys newest first:
  `[{id, name, created_at, last_used_at}]` (no credential id or key material).
- AC-21 `POST /passkeys/register/options` returns `{"challenge_id", "options": PublicKeyCredentialCreationOptionsJSON}`
  with `rp.id` = origin hostname, `residentKey: "required"`, `userVerification: "required"`,
  `excludeCredentials` = the user's existing credential ids. While impersonating: `403` and no
  challenge.
- AC-22 `POST /passkeys` `{"challenge_id", "credential": RegistrationResponseJSON, "name"?: str}`
  verifies against the stored challenge (must be a registration challenge for THIS user, same
  origin/RP ID, used once) and stores the passkey; `201` with the AC-20 item. Name defaults to
  `device_label_from_ua(User-Agent)`. Reused/duplicate credential id = 409. Bad attestation,
  wrong origin, another user's challenge, replayed challenge = `400 {"code": "PASSKEY_FAILED"}`.
  While impersonating = 403.
- AC-23 `PATCH /passkeys/{id}` `{"name"}` (trimmed, 1-100 chars) renames the caller's own passkey;
  someone else's or unknown id = 404; empty/too long = 422.
- AC-24 Removal is the deferred record action `user_passkey.delete` (entity type `user_passkey`,
  10 s destructive window, `record_actions.register`). Parking it for your OWN passkey needs no
  extra permission; for someone else's passkey it needs `user_management.users.edit`; otherwise
  403 at park time. On commit the row is hard-deleted by the ONE service function both paths use.
- AC-25 Add, rename and remove each leave an audit row (default-on ORM audit for `user_passkeys`).

## Admin (prefix `/api/v1/user-management/users`)
- AC-30 `GET /{user_id}/passkeys` (`user_management.users.view`) returns that user's AC-20 list.
- AC-31 Removal of a user's passkey uses AC-24 with `user_management.users.edit`. No admin add or rename.
- AC-32 `GET /users/{id}` `last_sign_in_method` reports `'passkey'` after a passkey sign-in.

## Frontend
- AC-40 Sign-in page (`app/(auth)/signin/page.tsx`): a round outline icon button,
  `aria-label="Passkey"`, tooltip "Passkey", beside "Phone number", shown only when
  `window.PublicKeyCredential` exists AND `window.isSecureContext` AND `/auth/passkey/status`
  says enabled. Clicking: fetch options, `startAuthentication` (`@simplewebauthn/browser`), then
  `signIn('passkey', {redirect: false, challengeId, credential: JSON})`, then the same landing as
  password sign-in. User cancels the browser prompt = no error shown. Backend refusal = the
  backend's message in the existing error Alert. "Continue" stays the only filled button.
- AC-41 The Email input has `autocomplete="username webauthn"`; where
  `PublicKeyCredential.isConditionalMediationAvailable()` is true the page starts a conditional
  (autofill) passkey request on mount, aborted when the user signs in another way.
- AC-42 NextAuth provider `id: 'passkey'` posts `{challenge_id, credential}` to
  `/api/v1/auth/passkey/verify` with `forwardedForHeader`, returns the same `User` shape as the
  credentials provider (`apiToken` = `token`).
- AC-43 My account > Security: "Passkeys" Card between Password and Delete Account. Header button
  "Add passkey" (outline). Rows: device icon, name (truncate + title), "Added dd/mm/yyyy" and
  "Last used dd/mm/yyyy, h:mm am/pm" (or "Never used") as separate lines, row menu (DropdownMenu)
  with Rename and Remove. Empty: heading "No passkeys yet" + hint "Sign in with Face ID, Touch ID or your fingerprint."
  Unsupported browser / insecure address / disabled: "Add passkey" disabled, hint "This browser can't use passkeys."
- AC-44 Add: options -> `startRegistration` -> POST; success toast "Passkey added", list refreshes.
  Cancel of the browser prompt = nothing. Rename: dialog shaped like `RenameAccessoryTemplateDialog`,
  Save disabled for blank. Remove: `useDeferredAction` + `DeferredActionButton` countdown
  "Removing", Cancel; no confirm dialog.
- AC-45 Admin user detail, Sign-in card (`user-sign-in-section.tsx`): row "Passkeys" with
  "N passkey(s)" link or "None"; the link opens a centred Dialog listing the user's passkeys with a
  row menu holding Remove (only with `users.edit`). `SIGN_IN_METHOD_WORDS.passkey = 'passkey'`.
- AC-46 Layering: `services/passkeyService.ts` -> `hooks/usePasskeys.ts` -> UI; errors through
  `extractApiError`; dates through the shared dd/mm/yyyy helpers. No UUIDs shown. Usable at 375 and 1280.

## Guides
- AC-50 `documentation/user-guides/` page for signing in with a passkey and managing passkeys,
  per `SYNC.md`.
