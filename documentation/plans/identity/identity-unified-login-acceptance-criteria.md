# UAC: Unified identity, one login for the portal and the CRM (#1280)

Plan: `PLAN-unified-identity-26sep.md` (same folder).
Status: draft, written to the recommendations in the plan's section 12 ("Grill questions for the
owner"). Every AC below that depends on an unanswered question names it as `(Qn)`; when the owner
answers differently, the AC is rewritten before its slice starts.

Owner words, 26 Sep 2026 ~13:50Z, issue #1280 (verbatim, binding):

> "I think eventually all our portal and user sign in needs to be unified. Because the one who use
> the portal for basic portal submission function will grow to use our project sales modules, use
> our sales opportunities module. So I think we need to find a way to unify. I'm thinking that we
> should support like user login, user email and password login, or also a phone number login. We
> should unify this. So for all the contacts that are like for product salesperson, retail
> salesperson, we also need to create like a counterpart user for them so in the future all of
> them can use our system and be audit trailed by our system."

Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` browser pass (agent-browser, sidebar navigation
from `/`, 375px AND 1280px), `[T]` a named automated test (pytest on Postgres or vitest).

## Journey

Screens are designed at 375px first (a salesperson's phone), then checked at 1280px.

### J-A A retail salesperson signs in on her phone (WhatsApp only, no email)

1. Aisyah is a retail salesperson contact. She already exists as a WhatsApp contact; since S3 she
   also has a counterpart user, created for her without her doing anything.
2. She opens the sign-in page on her phone. One field: "Email or phone number". She types her
   number (any common form: `012-345 6789`, `+60123456789`, `60123456789`).
3. The system recognises a phone number and moves straight to "Enter the code we sent to your
   WhatsApp", masked number shown, six boxes, the phone's own one-time-code autofill offered.
4. She receives the code on WhatsApp, enters it, and lands on the portal home she already knows,
   with the forms her market segment grants. She never chose a password and never registered.
5. What she submits is recorded against her user (and her contact, as today).

### J-B A staff member signs in as before

1. Staff open the same sign-in page, type their email, and get the password step exactly as
   today. Nothing about staff sign-in changes unless they choose to type their phone number,
   which works the same way as J-A once their phone is verified.

### J-C An existing portal contact taps an old WhatsApp link

1. A dealer contact taps the `/portal/c/{slug}` link they received months ago.
2. The verify card they know appears (their name, masked number); the code is sent to WhatsApp.
3. They enter the code. Behind it, their user is created at that moment (Q3, Q4) and a normal
   signed-in session starts. They land on the same portal home, same forms, same submissions.
4. No re-registration, no new link, no password.

### J-D A project salesperson grows into the CRM

1. An admin adds a CRM role (for example Project Sales) to a salesperson's user.
2. The salesperson's next page load shows the CRM shell with Project Sales in the sidebar and a
   "Portal" entry to get back to their submissions. Same sign-in, same session.

### J-E An admin looks after identities

1. Users list: a "Kind" filter (Staff / Salesperson / Portal) and a "Sign-in" column (Email,
   Phone, both).
2. A user's page: a "Sign-in" section with email, phone (verified or not), linked WhatsApp
   contact, last sign-in and how.
3. A contact's page: a "User account" section (linked user, or "No user yet" with Create).
4. A "Salesperson accounts" view listing every salesperson contact with its user state:
   linked, created, or needs attention (a phone clash) with the one action that resolves it.

### J-F Recovery

1. Forgot password: the existing email reset, unchanged.
2. Lost access to WhatsApp: an admin changes the phone on the user; every session of that user
   ends; the next phone sign-in verifies the new number by its own code.

## S0 Identity model, migration and audit fields

- **AC-01 [BE][T]** One principal per person: a person who signs in to the CRM or the portal is a
  `users` row. A WhatsApp contact links to at most one user (`users.respond_contact_id` unique
  where set). A second user linking the same contact is rejected with 409 `CONTACT_ALREADY_LINKED`
  naming the other user's name (never its id).
- **AC-02 [BE][T]** A user may have no email when it has a phone (Q5): `users.email` is nullable,
  and a database check requires at least one of `email` or `contact_number`. No placeholder email
  is ever generated.
- **AC-03 [BE][T]** Email uniqueness is case-insensitive: creating or updating a user whose email
  differs only by case from another's is rejected with 409; sign-in with any casing finds the
  user. The migration's pre-flight lists any existing case-duplicates and stops (does not merge
  them silently).
- **AC-04 [BE][T]** Backfill links existing users to contacts: every user with no
  `respond_contact_id` whose normalised `contact_number` equals exactly one contact's
  `phone_number` gets linked; ambiguous or already-claimed matches are left unlinked and listed
  (see AC-50). Re-running the backfill changes nothing.
- **AC-05 [BE][T]** Zero downtime: the S0 migration is expand-only (new nullable columns, new
  indexes created concurrently, relaxed NOT NULL), and the previous image's test suite still
  passes against the migrated schema.
- **AC-06 [BE][T]** Existing sign-in is unchanged: every existing user signs in with the same
  email and password after the migration; existing CRM sessions and existing portal tokens keep
  working without a new sign-in.
- **AC-07 [BE][T]** Every session row records how it was created: `user_sessions.auth_method` is
  one of `password`, `phone_otp`, `portal_link` (a portal verify card), `impersonation`.
- **AC-08 [BE][T]** Audit actor contract: every `audit_logs` row written after S0 carries
  `actor_type` (`user`, `integration`, `worker`, `scheduler`, `public_link`, `system`), and, where
  they exist, `user_id` (the effective actor), `real_user_id` (the impersonating admin, else equal
  to `user_id`), `auth_method`, `session_id`, `integration_id`, `contact_id` (the actor's linked
  contact), `ip_address`, `user_agent`, `trace_id`, `company_id`.
- **AC-09 [BE][T]** An integration write names the integration: a write through an API key has
  `actor_type = integration`, `integration_id` set, and `user_id` = the integration's act-as user.
- **AC-10 [BE][T]** A background job keeps its user: an RQ job enqueued by a signed-in user writes
  audit rows with `actor_type = worker` and `user_id` = the enqueuing user; a scheduler tick
  writes `actor_type = scheduler` and no user.
- **AC-11 [BE][T]** Admin "view as contact" is credited to the admin: a portal write made through
  an impersonation token has `real_user_id` = the admin and `contact_id` = the contact (confirms,
  then fixes, the gap measured in plan section 3.5).
- **AC-12 [BE][T]** The actor survives a synchronous dependency: a write through a route using
  `get_current_user_or_api_key` records the caller's `user_id` (confirms, then fixes, the
  suspected context loss in plan section 3.5).
- **AC-13 [FE][T]** The audit screens render the new fields as words: actor kind ("Staff",
  "Integration: n8n", "Background job for Aisyah", "Scheduled"), "on behalf of" for impersonation,
  and the sign-in method; no UUID is visible.

## S1 Phone sign-in

- **AC-20 [FE][E2E]** The sign-in page has one field, "Email or phone number" (Q7). Input that
  normalises to a phone number goes to the code step; anything with `@` goes to the password step.
  Usable at 375px with the keyboard open (submit button reachable without scrolling the field
  away) and at 1280px.
- **AC-21 [BE][T]** `POST /api/v1/auth/phone/request-code` with a phone number always answers
  200 with the same body, whether or not the number belongs to anyone (no enumeration). A code is
  sent only when the number resolves to exactly one ACTIVE, non-integration user with a linked
  WhatsApp contact.
- **AC-22 [BE][T]** The code goes to WhatsApp (Q6) through the existing `respond_io` queue and the
  portal OTP template, and every send writes an `integration_log` row on success and failure.
- **AC-23 [BE][T]** Limits: 10-minute expiry, 60-second resend cooldown, 5 wrong attempts per
  code, 10 sends per number per day, and the existing per-IP limit, all enforced server-side;
  hitting one answers 429 with the seconds to wait.
- **AC-24 [BE][T]** `POST /api/v1/auth/phone/verify` with the right code creates a `user_sessions`
  row (`auth_method = phone_otp`, 30-day rolling, Q15) and returns the same shape as email login,
  so NextAuth stores it the same way. It stamps `users.phone_verified_at`.
- **AC-25 [FE][E2E]** The code step: six boxes with `autocomplete="one-time-code"`, paste of a
  six-digit code fills all boxes, a resend button counting down from 60, "Use password instead"
  shown only when the user has a password, and a "Change number" back link.
- **AC-26 [BE][T]** Email login no longer reveals whether an email exists: an unknown email and a
  wrong password return the same 401 body.
- **AC-27 [BE][T]** Phone sign-in works for staff too (Q10): a staff user with a verified, linked
  phone signs in by code and gets their normal CRM session and permissions.
- **AC-28 [FE][E2E]** After sign-in the user lands where they work (Q9): a user holding any CRM
  permission (or admin) lands on the CRM home or their `callbackUrl`; a user holding none lands
  on their portal home.

## S2 Portal on the unified session

- **AC-30 [BE][T]** Every portal route accepts a signed-in user session: the portal principal
  (contact, space) is derived from the user's linked contact and that contact's workspace. A user
  with no linked contact gets 403 `NO_PORTAL_CONTACT`.
- **AC-31 [BE][T]** Ownership is unchanged: a user session sees exactly the submissions its
  linked contact saw under a portal token (same list, same 404 / 403 `OWNER_MISMATCH` answers),
  proven by one test per portal form kind comparing the two principals.
- **AC-32 [BE][T]** Company scope is unchanged for portal routes: a user session on a `/public/`
  portal route is scoped to the linked contact's companies, not the user's CRM company grants.
- **AC-33 [BE][T]** Form visibility is unchanged: the forms a user sees on the portal are the
  forms its linked contact sees today (market segment base plus per-contact overrides).
- **AC-34 [FE][E2E]** The verify card on `/portal/c/{slug}` and `/portal?token=` signs the person
  in to the unified session: after the code, the NextAuth session exists, and opening a CRM page
  they have permission for needs no second sign-in.
- **AC-35 [BE][T]** A portal contact with no user gets one at that verify step (Q3, Q4): role
  `portal_user`, status ACTIVE, no password, phone from the contact, email empty, company grants
  copied from the contact's companies, and linked to the contact. Re-verifying never creates a
  second user.
- **AC-36 [BE][T]** Legacy portal tokens keep working until they expire, and from the S2 deploy
  they no longer slide (Q11), so every legacy token ends within 30 days of S2. A new portal
  verification mints no new `portal_tokens` row except for admin "view as contact" (Q12).
- **AC-37 [BE][T]** Submissions made on a user session store the same `contact_id`, `space_id` and
  `respond_inbox_url` as before, and the audit row carries the user (AC-08).
- **AC-38 [FE][E2E]** Signing out from the portal ends the user session everywhere that session
  was used (portal and CRM); the user's own device list (`account/security/current-sessions`)
  shows portal sign-ins with their method.
- **AC-39 [FE][E2E]** A user with both CRM and portal access has a "Portal" entry in the user menu
  and a way back to the CRM from the portal header; a portal-only user who opens a CRM URL lands
  on their portal home, not an empty CRM shell.

## S3 Counterpart users for salesperson contacts

- **AC-40 [BE][T]** A salesperson contact is (Q1): a contact in any market segment with
  `is_requestor_selectable = true` (today `retail` and `project`), or a contact linked from
  `sales_agents.contact_id`. The rule is one function, used by the backfill, the sync and the
  admin view.
- **AC-41 [BE][T]** Backfill: every salesperson contact with no linked user gets one: role
  `salesperson` (Q8), ACTIVE, no password, phone and name from the contact, no email, company
  grants copied from the contact. Re-running creates nothing new.
- **AC-42 [BE][T]** One person, one user (Q14): when a salesperson contact's phone equals an
  existing user's `contact_number`, that user is linked and given the `salesperson` role instead
  of creating a second user.
- **AC-43 [BE][T]** A clash is never auto-resolved: a contact whose phone matches a user already
  linked to a different contact is left unlinked and reported (AC-50), and the backfill carries on
  with the rest.
- **AC-44 [BE][T]** Stays true after the backfill: adding a contact to a salesperson segment, or
  linking it to a sales agent, provisions its user in the same transaction; removing it from every
  salesperson source removes the `salesperson` role but never deletes the user or its history.
- **AC-45 [BE][T]** A provisioned user can do nothing in the CRM until given more: the
  `salesperson` and `portal_user` roles are protected, seeded with no CRM permissions, and are
  never the `is_default` role; the grant sweep leaves them empty.
- **AC-46 [BE][T]** A contact's phone change (Respond.io sync or admin edit) updates the linked
  user's `contact_number` and clears `phone_verified_at`; a change that would collide with another
  user is refused on the user side and reported.
- **AC-47 [BE][T]** Provisioning is audited: each created or linked user writes an audit row with
  `actor_type = system` (backfill) or the acting admin, naming the contact it came from.

## S4 Admin screens

- **AC-50 [FE][E2E]** "Salesperson accounts" (under User Management): a DataGrid of every
  salesperson contact with columns Contact, Phone, Segment / Agent, User, State (Linked, Created,
  Needs attention); filter by State; a "Needs attention" row names the clash in words and offers
  the one resolving action (Link to this user, or Open the clashing user). Standard DataGrid rules
  (fixed layout, resizable, explicit sizes, truncate + title), usable at 375px.
- **AC-51 [FE][E2E]** Users list: a "Kind" filter (Staff, Salesperson, Portal, derived from roles)
  that defaults to showing everyone (lesson: a list that opens filtered cannot be reconciled), and
  a "Sign-in" column (Email, Phone, Email + Phone).
- **AC-52 [FE][E2E]** User detail: a "Sign-in" section in the same place on view and edit, with
  email, phone and its verified state, linked WhatsApp contact (name and masked phone, clickable),
  last sign-in time and method; explicit empty states ("No phone yet. Add one to allow phone
  sign-in.").
- **AC-53 [FE][E2E]** Contact detail: a "User account" section showing the linked user, or "No
  user yet" with a Create user action for an admin; Unlink is a 5-second deferred action with
  Cancel (D7), never a dialog.
- **AC-54 [BE][T]** Unlinking or changing a user's phone or linked contact revokes every session of
  that user (the same path as force-logout) and writes an audit row.
- **AC-55 [BE][T]** Every new admin route is permission-gated: `user_management.users.edit` for
  link, unlink and phone edits; `user_management.users.view` for the salesperson view; each has
  an auth-denial test, and the grant sweep gives the new view permission to every role that
  already holds `user_management.users.view`.

## Cross-cutting

- **AC-60 [T]** No em-dash or en-dash in any file this lane adds or edits.
- **AC-61 [E2E]** Every changed screen is verified by agent-browser at 375px and 1280px, reached by
  sidebar clicks from `/` (the portal from its WhatsApp link), with evidence under
  `documentation/plans/identity/evidence/<slice>/`.
- **AC-62 [BE]** `security-reviewer` runs on every slice of this plan (auth, RBAC and portal ingest
  are all touched).
