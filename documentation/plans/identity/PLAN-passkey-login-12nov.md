# PLAN: Passkey sign-in for CRM staff (PASSKEY-LOGIN)

Status: Plan. Behaviour card + mock v1 filed as crew-ask, waiting on owner answers. Track: L
(migration + auth change; security-reviewer required).

## Goal
Staff can sign in to the CRM with a passkey (Face ID / Touch ID / fingerprint / phone), per user,
opt-in. Password and phone OTP stay as fallback. Dealer portal, mandatory passkeys, removing
passwords and auto-login are out of scope.

## Discovery (origin/main 7ede7cfa, 12 Nov 2026)

### What exists, and what this lane does with it

| Piece | Where | Decision |
| --- | --- | --- |
| Password login: throttle, no-enumeration 401, ACTIVE check, `last_sign_in_at`, `mint_session`, `build_login_response` | `sorento_crm_backend/app/api/v1/auth.py:49-146` | Reuse the tail (status check, `last_sign_in_at`, `mint_session`, `build_login_response`) by pulling it into ONE shared `finish_sign_in(db, user, request, auth_method)` that password, phone and passkey all call. No third copy. |
| Session mint | `app/services/user_session_service.py:55-90`, `AUTH_METHODS` at :36 | Reuse as is; add `"passkey"` to `AUTH_METHODS` + model CHECK (`app/models/user_session.py`) + migration. |
| Shared login response shape | `app/services/phone_signin_service.py:353` `build_login_response` | Reuse as is. |
| Per-IP rate limit for unauthenticated routes | `app/services/rate_limit.py` `hit(...)` (used at `auth.py:165`) | Reuse for `/auth/passkey/options` and `/auth/passkey/verify`. |
| Client IP behind proxy; NextAuth forwards it | `app/services/client_ip.py:45`; FE `forwardedForHeader` in `auth-options.ts:153` | Reuse as is. |
| Redis connection | `app/services/queue_service.redis_conn` (via `login_throttle._redis_conn`, `login_throttle.py:33`) | Reuse: one-time challenges live in Redis with a 5 minute TTL, consumed with GETDEL. |
| Device label from User-Agent | `user_session_service.device_label_from_ua` :178 | Reuse as the default passkey name ("Safari on iPhone"). |
| Real user while impersonating | `app/dependencies.get_actor_user_id` (used by `/auth/sessions`, `auth.py:481`) | Reuse: the Passkeys card manages the REAL user; adding a passkey while impersonating is refused. |
| Audit | `audit_service` default-on ORM audit (`audit_service.py:100`), `log_audit(...)` :246 | New `user_passkeys` table is audited by default (add, rename, remove). Sign-in writes one explicit `log_audit` EVENT row `passkey_sign_in` (no actor context exists before sign-in, so `record()` cannot be used). `public_key` is not secret; `credential_id` is not secret. |
| Deferred remove (no confirm dialog) | Backend `app/services/record_actions.py:500-520` (`user.unlink_contact` registration), FE `hooks/useDeferredAction` + `components/common/DeferredActionButton.tsx:160` (used in `users/[id]/components/user-sign-in-section.tsx:59`) | Reuse: register `user_passkey.delete` (10s destructive window) for both self and admin removal, ONE service function `remove_passkey` behind it. |
| Admin "sign out of all devices" | `app/api/v1/user_management/users.py:355` (`users.edit`), FE `hooks/useSessions.ts:45` | Unchanged. Admin passkey list/remove uses the same `user_management.users.edit` slug (view list: `users.view`). No new role or permission. |
| Last sign-in method word | `users/[id]/components/user-sign-in-section.tsx:44` `SIGN_IN_METHOD_WORDS`; backend `app/services/user_contact_link.py:83` | Extend with `passkey: 'passkey'`. |
| NextAuth providers | `app/api/auth/[...nextauth]/auth-options.ts` credentials :137, `phone-otp` :193 | Add a 4th `passkey` Credentials provider modelled on `phone-otp`, posting to `/api/v1/auth/passkey/verify`, same `User` shape + `apiToken`. |
| Login page | `app/(auth)/signin/page.tsx:281-298` (round "Phone number" icon button + Tooltip) | Add a round "Passkey" icon button beside it (mock section 1). |
| Own security page | `app/(protected)/user-management/account/security/page.tsx` (Email, Password, Delete Account cards) | Add a "Passkeys" Card between Password and Delete Account. |
| Rename dialog pattern | `app/(protected)/dealer-kit/accessory-templates/components/RenameAccessoryTemplateDialog.tsx` | Copy its shape for "Rename passkey". |
| Session service/hooks pattern | `services/sessionService.ts`, `hooks/useSessions.ts` | New `services/passkeyService.ts` + `hooks/usePasskeys.ts` in the same layering (UI -> hook -> service -> `lib/api-client`). |
| WebAuthn libraries | none today | Backend `webauthn` (py_webauthn, PyPI 3.0.1); frontend `@simplewebauthn/browser`. |

### Migration precedent
`alembic/versions/dev_login_0001_auth_method.py` widened `ck_user_sessions_auth_method` the same
way (drop + add CHECK). This lane does the same plus one new table. `user_sessions` is read on
every request: the CHECK is added `NOT VALID` then `VALIDATE`d so the table lock is momentary;
timed on a dev copy before merge.

## Behaviour card (filed as crew-ask)

### Flows
1. **Add a passkey** (signed in, My account > Security > Passkeys > "Add passkey"): the browser's
   own Face ID / Touch ID / fingerprint / phone prompt appears; on success the row appears named
   after the device ("Safari on iPhone"), toast "Passkey added". Cancelling the prompt changes
   nothing and shows no error.
2. **Sign in with a passkey** (sign-in page, round "Passkey" button, or the passkey offered by the
   Email field's autofill): pick the passkey, unlock the device, land on the same home page a
   password sign-in lands on. The session is the same 30-day sliding session; the user list
   shows "Last sign-in ..., passkey".
3. **Rename / remove** your own passkey from the row's menu. Remove = 10s countdown with Cancel
   (no confirm dialog), then it is gone.
4. **Admin**: user detail > Sign-in card shows "Passkeys: 2 passkeys" (or "None"); the link opens
   a lightbox listing name, added, last used; Remove with the same countdown. Admins cannot add
   or rename a user's passkey.

### Rules
- Opt-in: nobody gets a passkey unless they add one. Password and phone stay.
- A passkey works only on the address it was made on (a test copy passkey does not work on the
  live CRM). Addresses that may use passkeys are configuration (`WEBAUTHN_ORIGINS`); where it is
  unset, passkeys are off and the button does not show.
- Server checks every sign-in: one-time challenge (5 min, used once), the address, the device's
  signature, user verification (Face ID / fingerprint / PIN, not just "touch"), sign counter.
- A blocked, inactive or trashed user cannot sign in with a passkey (same rule as password).
- Every add, rename, remove and passkey sign-in is in the audit log.
- Throttle: the same per-IP limit pattern as other sign-in routes; one generic failure message
  ("That passkey didn't work. Sign in another way.") that never says whether an account exists.

### Edge cases
- **Lost device**: sign in with password or phone, remove that passkey; or an admin removes it.
  "Sign this user out of all devices" still ends any open session on it.
- **Shared device**: a passkey needs the device's own unlock (Face ID / fingerprint / PIN), so
  another person on the same computer cannot use it without that.
- **New phone**: iCloud Keychain / Google Password Manager passkeys follow the person to the new
  phone; otherwise sign in once with password or phone and add a new passkey.
- **Browser without passkeys / old browser**: the "Passkey" button is hidden; on the Security page
  "Add passkey" is disabled with "This browser can't use passkeys."
- **Test copies on plain http** over the tailnet: browsers refuse passkeys there, so the button is
  hidden until crew switches the copy to https (owner's Tailscale certs). `localhost` works.
- **Passkey removed on the server but still on the phone**: sign-in answers the generic failure
  message; the user signs in another way.
- **Impersonating**: the Passkeys card belongs to the admin (real user), like the devices list;
  adding a passkey while impersonating is refused, so an admin can never plant a passkey on
  someone else's account.

### Questions (at most 5)
1. Adding a passkey: (a) allowed from any signed-in session, (b) ask for the password or a phone
   code again first. **Recommend (a)**: a signed-in session already acts fully as the user for 30
   days; phone-only staff have no password; the list + admin Remove + audit catch a stray one.
2. Login button: (a) round "Passkey" icon beside "Phone number" plus passkey autofill on the Email
   field, (b) a full-width "Sign in with passkey" outline button under Continue. **Recommend (a)**:
   copies the existing phone pattern and keeps "Continue" the one main button.
3. Nudge: (a) no prompt; people add passkeys from My account > Security, (b) after a password
   sign-in on a passkey-capable device with none, a one-time "Add a passkey?" prompt.
   **Recommend (a)** for this lane (simplest; the trigger for (b) is low uptake after release).
4. Admin visibility: (a) the "Passkeys" row in the user's Sign-in card only, (b) also a sortable
   "Passkeys" count column on the Users list. **Recommend (a)** now; (b) when someone needs to
   filter by it.
5. Live address: which hostname(s) do staff open the CRM on in production (one, or also a second
   address)? Needed only as the `WEBAUTHN_ORIGINS` value on the server's env, never in the repo.
   **Recommend** one hostname; passkeys are then on there and on https test copies.

### Mock
`documentation/mockups/passkey-login/index.html` (v1): sign-in page, Passkeys card (filled +
empty), admin Sign-in card + lightbox.

## Status log
- 12 Nov 2026: lane opened; discovery done; behaviour card + mock v1 filed.
