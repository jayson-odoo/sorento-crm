# S3 contract: the owner creates and links users (#1280)

Phase 1 contract for slice S3 of `PLAN-unified-identity-26sep.md` (section 10 S3, sections 6
and 7, 6.3, 6.4). UAC: AC-40 to AC-49, AC-52 to AC-59. Built on the S0 head 03d3b474.
Paths are relative to `sorento_crm_backend/` (BE) and `sorento_crm_frontend/` (FE).

No migration: every column S3 reads (`users.respond_contact_id` unique, nullable `email`,
`phone_verified_at`, `user_sessions.auth_method`, the `salesperson` and `portal_user` roles)
shipped in S0.

## 1. Backend

### 1.1 One function decides the suggested role (AC-40)

`app/services/user_contact_link.py` (new module, the one home for S3 logic that is not a route):

- `is_salesperson_contact(db, contact_id) -> bool`: true when the contact is in any market
  segment with `is_requestor_selectable = true` (`respond_contact_market_segments` join
  `market_segments`), or is the `contact_id` of any `sales_agents` row. Reads only; creates and
  lists nothing.
- `suggested_role_slug(db, contact_id) -> str`: `"salesperson"` when the function above is true,
  else `"portal_user"`.

### 1.2 `POST /api/v1/user-management/users` (existing route, `users.add`)

Body (`UserCreate`): as today, plus

- `email` optional (null or blank means none, stored NULL, lowercased as S0 does);
- `respond_contact_id` optional;
- `company_ids` as today; the FIRST id becomes `last_active_company_id` (today only a single id
  does).

Rules, in this order:

1. `respond_contact_id` given and unknown: 404 (`handle_not_found("Contact", ...)`).
2. `respond_contact_id` already held by a user: 409 `CONTACT_ALREADY_LINKED`, message
   `WhatsApp contact already linked to <name>` (S0 helper, unchanged).
3. When a contact is given, `contact_number` is the contact's `phone_number` normalised with
   `normalize_msisdn`; a `contact_number` in the body is ignored.
4. Neither email nor phone after step 3: 422, code `EMAIL_OR_PHONE_REQUIRED`, message
   `Enter an email or a phone number`.
5. Email held by another user in any case: 409 `EMAIL_TAKEN` (S0, unchanged).
6. Phone held by another user: 409 `PHONE_BELONGS_TO_USER`, message
   `This phone already belongs to <name>` (`user_label`, never an id, never the phone). This
   replaces the old `Phone number <n> is already used by another user.` conflict everywhere
   `_check_contact_number_unique` is called (create and update).
7. Status is decided by the server: `ACTIVE` when the user has a phone, else `INACTIVE`.
   `password` stays NULL. A `status` in the body is ignored on create.
8. Roles exactly as submitted; the `is_default` role only when `role_ids` is empty (as today).
9. Nothing is sent: no invitation, no notification, no email outbox row, no WhatsApp message.
10. When a contact is given, one extra `log_audit` row: entity `user`, action `UPDATE`,
    `description` `Created from WhatsApp contact <contact name or phone>`. The actor
    (`real_user_id` = the acting admin) comes from the S0 audit context. (Corrected during the
    build: the audit `action` column only takes CREATE / READ / UPDATE / DELETE / IMPORT, so
    the description, not a new verb, names what happened; no migration.)

Response: `UserResponse` (201).

### 1.3 `PUT /api/v1/user-management/users/{id}` (existing route, `users.edit`)

Additions to today's behaviour:

- `respond_contact_id` set to a contact id:
  - unknown contact: 404;
  - held by another user: 409 `CONTACT_ALREADY_LINKED` (S0);
  - this user already linked to a DIFFERENT contact: 409 `USER_ALREADY_LINKED`, message
    `<user name> is already linked to WhatsApp contact <contact name>`; nothing changes (the
    owner unlinks first);
  - first link (was NULL): saved, no role added, nothing sent, sessions NOT revoked, audit row
    action `UPDATE`, description `Linked WhatsApp contact <contact name>`.
- `respond_contact_id` set to null or `""` while one is linked (unlink): saved, every session of
  the user revoked (`user_session_service.revoke_all_for_user`), audit row action
  `UPDATE`, description `Unlinked WhatsApp contact <contact name>`.
- `contact_number` changed (normalised value differs, including cleared to null): 409
  `PHONE_BELONGS_TO_USER` when another user holds the new value; else saved,
  `phone_verified_at` set NULL, every session revoked. This is also
  "Use new number" (the FE sends the linked contact's phone).
- Unchanged values (same contact id, same normalised phone) do nothing extra.
- None of these send anything. The `account_email_changed` notice when an existing email is
  REPLACED stays (Q18 recommendation); adding a first email to a phone-only user sends nothing
  (already true in S0).

### 1.4 Unlink as a deferred action (AC-53, D7)

`app/services/record_actions.py` registers:

```
FormAction(key="user.unlink_contact", entity_types=("user",), execute=_unlink_user_contact,
           window=WINDOW_REVERSIBLE, permission="user_management.users.edit",
           label="Unlink WhatsApp contact")
```

`_unlink_user_contact` calls `UserService(db).unlink_contact(user_id)`, which does exactly the
unlink branch of 1.3 (one implementation; the PUT path calls it too), inside an audit actor
scope of the admin who started it (`payload["requested_by_id"]`), whichever request or sweep
commits it. Unlinking a user with no contact is a no-op.

### 1.5 `POST /users/invite` is removed (AC-58)

The route and the Next proxy `app/api/user-management/users/invite/route.ts` are deleted.
Grep of the FE, the n8n exports (`documentation/n8n/`) and the MCP catalogue found no other
caller of the route, so no 410 stub is kept. A POST to the old path answers 405 (the path
matches `PUT /{user_id}` only) and creates nothing. `UserService.invite_user` stays: the
onboarding provisioning task (`app/tasks/onboarding_tasks.py`) calls it for its own,
separately approved, invitation flow (found by the security review; the first grep missed
`app/tasks`).

### 1.6 Invitations (AC-57)

- `POST /users/{id}/resend-invite` unchanged (S0 made it 400 `USER_HAS_NO_EMAIL` with no email).
- Bulk `resend_invite` skips users with no email before calling the sender. Response adds
  `skipped`; message `Invitation links sent to <n> user(s). <m> skipped (no email).` when
  `m > 0` (failed count reported as today when non-zero).

### 1.7 Reads

`GET /users/{id}` and `GET /users/me` (BOTH manual dicts) and `UserResponse` gain:

| Field | Meaning |
| --- | --- |
| `phone_verified_at` | datetime or null |
| `linked_contact` | `{id, name, phone_number}` of the linked contact, or null |
| `phone_differs_from_contact` | true when a contact is linked and `normalize_msisdn(user.contact_number) != contact.phone_number` (a user with no phone and a linked contact also counts as differing) |
| `last_sign_in_method` | `auth_method` of the user's newest `user_sessions` row (by `created_at`), else null |
| `needs_invitation` | true when the user has an email, no password, and no `verification_tokens` row with `identifier = user.id` ever issued |

`GET /users/select` gains three optional filters (all `users.view`, response unchanged):
`phone` (normalised with `normalize_msisdn`, exact match on `contact_number`; a value that does
not normalise returns nothing),
`respond_contact_id` (exact), `unlinked=true` (users with no contact).

`GET /contacts/` rows gain `linked_user_id` and `linked_user_name` (one batched query per
page, never per row). Both are null when the caller lacks `user_management.users.view`.

`GET /contacts/{id}` gains:

- `is_salesperson` (bool) and `suggested_role_slug` (`salesperson` | `portal_user`);
- `linked_user`: `{id, name, email, status, has_password, roles: [{id, name}]}` or null; null
  when the caller lacks `user_management.users.view`.

`RespondContactResponse` declares all five new fields (response_model drops undeclared ones).

`GET /roles/select` must expose `slug` and `is_default` (already in `UserRoleResponse`); the FE
maps `suggested_role_slug` to a role id through it.

### 1.8 Error body

`AppException` bodies stay `{message, detail, code}` (top level). No id of another user appears
anywhere in a 409 body. The FE resolves the other user by `GET /users/select?phone=` or
`?respond_contact_id=`.

## 2. Frontend (existing pages only, AC-59)

No new route under `app/(protected)`, no sidebar entry.

### 2.1 Add user modal (`users/components/user-add-dialog.tsx`, AC-48, AC-58)

Props: `open`, `closeDialog`, and optional `contact?: {id}` (opened from a contact: the contact is
locked). Fields in order:

1. Name (required).
2. Email: optional when there is a phone, required when not (zod `superRefine`).
3. Contact Number: read-only and filled from the contact while one is set; editable otherwise.
4. **WhatsApp contact**: `SearchableSelect`, server-searched (`fetchOptions` over the contacts list,
   label `name - phone`, never an id), `clearable` from Administrative Users, `disabled` (locked)
   when opened from a contact.
5. Copy roles from another user (as today).
6. **Roles**: `SearchableMultiSelect` (replaces the checkbox list); the suggested role gets a
   "Suggested" hint beside the label.
7. Companies (superadmin only, as today), prefilled from `GET /contacts/{id}/companies`.
8. Superior (as today).

Picking a contact (or opening with one) loads `GET /contacts/{id}` and its companies, then fills
Name, Contact Number and Companies and adds the suggested role, but only into fields the owner
has not typed in (react-hook-form `dirtyFields`). Clearing the contact makes Contact Number
editable again and leaves the rest.

The "Send invitation email" checkbox is gone. Save always posts `POST /users` through
`userService.createUser`. Toast `User added`. On success invalidates `['user-users']`,
`['respond-contacts']`, `['respond-contact', contactId]`.

Inline 409s (an `Alert` above the footer, not a toast):

- `CONTACT_ALREADY_LINKED`: the message plus a link button "Open user" (resolves the holder by
  `GET /users/select?respond_contact_id=`, navigates to `/user-management/users/<id>`).
- `PHONE_BELONGS_TO_USER`: `This phone already belongs to <name>.` plus a button
  "Link this contact to <name> instead" when a contact is set (resolves the holder by
  `?phone=`, then `PUT /users/{holder} {respond_contact_id}`; its own 409 shows in the same
  place), else "Open user".
- `EMAIL_TAKEN`: the message.

### 2.2 Administrative Users > a user > Profile tab (AC-52, AC-57)

`users/[id]/components/user-sign-in-section.tsx`, a new Card under the existing profile Card,
title `Sign-in`, header button `Send invitation email` (only when the user has an email and the
viewer has `users.edit`). Rows, in order:

- Email: the address, or `No email`; `Invitation not sent` badge when `needs_invitation`.
- Phone: masked `+60 12-*** 6789` with `verified` / `not verified yet`; empty state
  `No phone yet. Add one to allow phone sign-in.`
- WhatsApp contact: `<name> - <masked phone>` linking to `/user-management/contacts/<id>`, or
  `Not linked`.
- Last sign-in: date time (Malaysia) plus method in words (`email`, `phone`, `portal link`), or
  `Never`.
- When `phone_differs_from_contact`: a warning `Alert` `Needs attention: phone differs from
  WhatsApp contact.` with button `Use new number` (PUT `contact_number` = the contact's phone).
- When linked and the viewer has `users.edit`: `Unlink WhatsApp contact` button running the
  deferred action `user.unlink_contact` (5s countdown with Cancel, `useDeferredAction`, no dialog).

The record action `user.resend_invite` is relabelled `Send invitation email`, hidden when the user
has no email, and opens `AlertDialog` "Send invitation email?" / "An email with a link to set a
password goes to <email>." / Cancel (focused, `autoFocus`) and `Send email`. Only `Send email`
calls `POST /users/{id}/resend-invite`. The section's header button opens the same dialog (one
dialog, owned by `useUserActions`).

Users list bulk "Bulk send invitation" keeps its confirmation and toasts the server message (now
naming skipped users).

### 2.3 Internal Users list (`contacts/components/ContactsList.tsx`, AC-59)

- New column `User` (id `linked_user`, size 180, `truncate` + `title`, sorting off): the linked
  user's name as a link to `/user-management/users/<id>` (click does not open the row), blank
  when none. Not rendered at all without `users.view`.
- Row action `Create user` (icon `UserPlus`), first in the row's menu, only when the row has no
  linked user and the viewer has `users.add`; opens the Add user modal with that contact locked.

### 2.4 Internal Users > a contact > Profile tab (AC-53)

`contacts/[id]/components/ContactUserAccountSection.tsx`, a Card `User account` directly under
Contact Information (always rendered, explicit empty state):

- No user: `No user yet` with `Create user` (users.add; opens the Add user modal, contact locked)
  and `Link existing user` (users.edit; an inline `SearchableSelect` of `GET /users/select?unlinked=true`
  plus a `Link` button; `PUT /users/{picked} {respond_contact_id}`; 409s inline).
- Linked: `User <name link>`, `Roles <badges>`, `Signs in by` (`Email and password` when
  `has_password`, then `WhatsApp code`, `Portal link`), and `Unlink` (users.edit) running
  `user.unlink_contact` on that user (5s countdown with Cancel).
- Without `users.view` the section shows the contact's state only as `No user yet` actions hidden.

### 2.5 Layering

Every new call goes UI -> hook -> service -> `apiFetch`: `userService.ts` gains `createUser`,
`updateUserContactLink`, `useNewNumber`, `findUserByPhone`, `findUserByContact`,
`listUnlinkedUsers`; contact reads stay in `contacts/[id]/services/contactService.ts`. Errors use
`codedError` / `extractApiError`.

## 3. Test list (tester writes these red first)

Backend: `tests/test_identity_s3_create_link.py` (routes and services) and
`tests/test_identity_s3_no_email.py` (AC-56, AC-57, AC-58). Each test named `test_acNN_...`.

- AC-40: segment-requestor contact is salesperson; sales-agent contact is salesperson; other contact
  is not (suggested `portal_user`); the function leaves `users` and `user_role_assignments` counts
  unchanged.
- AC-41: create from contact links it, takes the contact's phone (body phone ignored), roles and
  companies exactly as sent, first company is `last_active_company_id`, ACTIVE, no password;
  email-only create is INACTIVE with no password; phone-only create has NULL email; neither is 422
  `EMAIL_OR_PHONE_REQUIRED`; unknown contact 404.
- AC-42: create whose phone an existing user holds is 409 `PHONE_BELONGS_TO_USER` naming the user,
  body has no id and no phone, user count unchanged; then PUT linking the contact to that user
  succeeds and its roles are unchanged.
- AC-43: create with a held contact is 409 `CONTACT_ALREADY_LINKED`; PUT linking a user already
  linked elsewhere is 409 `USER_ALREADY_LINKED` and both links are unchanged.
- AC-44: adding a contact to a requestor segment, linking it to a sales agent, removing it from both,
  a contact phone update through `ContactService.update_contact`, and a portal OTP verify each leave
  the `users` and `user_role_assignments` counts unchanged; a static test walks `app/` and fails on
  any `User(` or `UserRoleAssignment(` construction outside the allowlist (`user_service.py` create
  paths, `auth.py` signup, onboarding and integration provisioning that exist today, each named).
  Phone sign-in is S1's and not on this branch; S1's AC-21 covers it.
- AC-45: `salesperson` and `portal_user` are protected, not default, and hold zero permissions on the
  bootstrapped database; a user holding only `salesperson` gets 403 on `GET /users/`.
- AC-46: a contact phone change leaves the linked user's phone unchanged and `GET /users/{id}` then
  answers `phone_differs_from_contact: true`; PUT `contact_number` = the new phone clears
  `phone_verified_at`, revokes sessions, and the flag goes false.
- AC-47: create from contact and link each write an audit row with `real_user_id` = the admin and a
  description naming the contact; unlink too.
- AC-52 (BE part): `GET /users/{id}` and `GET /users/me` both carry the five fields; `needs_invitation`
  true for a never-invited email-only user and false after `resend-invite`; `last_sign_in_method`
  is the newest session's method.
- AC-54: unlink (PUT null, and the deferred `user.unlink_contact` executor) revokes every session and
  writes an audit row; phone change revokes; a first link does not revoke (ruling).
- AC-55: POST `/users` without `users.add` 403; PUT link without `users.edit` 403; resend-invite
  without `users.edit` 403; `user.unlink_contact` registered with `users.edit`; contacts list and
  contact detail without `users.view` carry no linked user.
- AC-56: `email_outbox` and `notifications` row counts unchanged, and the Respond send seam never
  called, for: create with email only, phone only, both; link; unlink; `PUT /roles`; `PUT /companies`;
  first email on a phone-only user.
- AC-57: bulk `resend_invite` over one user with email and one without sends one, reports
  `skipped: 1`.
- AC-58: `POST /users/invite` does not answer 201 and creates no user.
- Select filters: `phone`, `respond_contact_id`, `unlinked=true` each return the right user(s).

Frontend (vitest, next to each component):

- `user-add-dialog.s3.test.tsx`: no invitation checkbox; submit calls `createUser` (never an
  `/invite` URL); opened with a contact: contact locked, name, phone and companies filled, the
  suggested role selected; phone read-only with a contact; email optional when a phone is set and
  required when not; a typed name is not overwritten by picking a contact; 409
  `PHONE_BELONGS_TO_USER` shows "Link this contact to <name> instead"; 409
  `CONTACT_ALREADY_LINKED` shows "Open user".
- `user-sign-in-section.test.tsx`: each row's words and empty states, `Invitation not sent`,
  Needs attention + Use new number, Unlink visible only when linked, no UUID in the text.
- `actions.invite.test.tsx`: the action reads "Send invitation email", is absent for a user with no
  email, opens the dialog, Cancel (focused) and Escape send nothing, "Send email" sends once.
- `ContactUserAccountSection.test.tsx`: no user state with both buttons; linked state with name,
  roles, Unlink.
- `ContactsList.user-column.test.tsx`: the User column and the Create user action appear only on a
  row with no user; both absent without `users.view` / `users.add`.
