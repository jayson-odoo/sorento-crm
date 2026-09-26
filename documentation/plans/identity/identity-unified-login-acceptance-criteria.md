# UAC: Unified identity, one login for the portal and the CRM (#1280)

Plan: `PLAN-unified-identity-26sep.md` (same folder).
Status: draft, round 3 (27 Sep 2026). Rewritten for the owner rulings of 26 Sep 2026 23:45 MYT on
Q1, Q2, Q3, Q4, Q6, Q8, Q9, Q10 and 27 Sep 2026 00:20 MYT on Q5 (plan section 12). Q11 to Q15 are
unanswered; ACs that depend on them still follow the recommendation and name it as `(Qn)`, to be
rewritten before their slice starts if the owner answers differently.

Owner ruling 26 Sep 2026 23:45 MYT (Q3, Q4), binding on every AC below: no user is ever created
automatically. The owner creates and sets up every user at the backend (create, link to the
contact, set roles), then the person signs in. A contact the owner has not set up keeps using the
portal exactly as today.

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

1. Aisyah is a retail salesperson contact. She already exists as a WhatsApp contact. The owner
   has created her user from her contact (J-E): linked to her contact, role Salesperson, her
   companies. She did nothing.
2. She opens the sign-in page on her phone. One field: "Email or phone number". She types her
   number (any common form: `012-345 6789`, `+60123456789`, `60123456789`).
3. The system recognises a phone number and moves straight to "Enter the code we sent to your
   WhatsApp", masked number shown, six boxes, the phone's own one-time-code autofill offered.
4. She receives the code on WhatsApp, enters it, and lands on the portal home she already knows
   (a salesperson lands on the portal first, Q9), with the forms her market segment grants. She
   never chose a password and never registered.
5. What she submits is recorded against her user (and her contact, as today).

### J-B A staff member signs in as before

1. Staff open the same sign-in page, type their email, and get the password step exactly as
   today. Nothing about staff sign-in changes unless they choose to type their phone number,
   which works the same way as J-A once their phone is verified.

### J-C An existing portal contact taps an old WhatsApp link

1. A contact taps the `/portal/c/{slug}` link they received months ago.
2. The verify card they know appears (their name, masked number); the code is sent to WhatsApp.
3. They enter the code and land on the same portal home, same forms, same submissions.
4. Behind it: if the owner has set up a user for this contact, a normal signed-in user session
   starts (the same one the CRM uses). If not (most dealer contacts), it is today's portal
   session, unchanged, and no user is created (Q3, Q4).
5. No re-registration, no new link, no password, either way.

### J-D A project salesperson grows into the CRM (later, when the owner decides)

1. Today a salesperson gets nothing beyond portal submission (Q8). When the owner decides one
   should, the owner adds a CRM role (for example Project Sales) to that salesperson's user.
2. The salesperson still lands on the portal first (Q9), now with an "Open CRM" link in the portal
   header; the CRM shows Project Sales in the sidebar and a "Portal" entry back. Same sign-in,
   same session.

### J-E The owner sets a person up, then the person signs in

1. The owner opens User Management > Salesperson accounts: every salesperson contact with its
   state, No user yet, Linked, or Needs attention.
2. On Aisyah's row (No user yet) the owner clicks Create user. The Add user modal opens with her
   contact locked, her name and phone filled in, role Salesperson suggested and her companies
   filled in. The owner reviews, changes anything, and saves.
3. The row flips to Linked. Her contact's page shows her user in its User account section.
4. The owner may send her the portal link with the existing "Send portal link" action, or simply
   tell her to sign in with her number. Nothing is sent by itself.
5. For a dealer contact, the owner does the same from the contact's page (User account > Create
   user), with role Portal suggested. For a staff member who is also a salesperson, the owner uses
   Link existing user instead of creating a second one.

### J-E2 The owner looks after identities

1. Users list: a "Kind" filter (Staff / Salesperson / Portal) and a "Sign-in" column (Email,
   Phone, both).
2. A user's page: a "Sign-in" section with email, phone (verified or not), linked WhatsApp
   contact, last sign-in and how, and "Needs attention" when the contact's phone has changed.

### J-F Recovery

1. Forgot password: the existing email reset, unchanged.
2. Lost access to WhatsApp: an admin changes the phone on the user; every session of that user
   ends; the next phone sign-in verifies the new number by its own code.

## S0 Identity model, migration and audit fields

- **AC-01 [BE][T]** One principal per person: a person who signs in to the CRM or the portal is a
  `users` row. A WhatsApp contact links to at most one user (`users.respond_contact_id` unique
  where set). A second user linking the same contact is rejected with 409 `CONTACT_ALREADY_LINKED`
  naming the other user's name (never its id).
- **AC-02 [BE][T]** A user may have no email when it has a phone (Q5, owner ruling 27 Sep 2026
  00:20 MYT: "identity plan q5 - yeah can"): `users.email` is nullable, and a database check
  requires at least one of `email` or `contact_number`. No placeholder email is ever generated.
- **AC-03 [BE][T]** Email uniqueness is case-insensitive: creating or updating a user whose email
  differs only by case from another's is rejected with 409; sign-in with any casing finds the
  user. The migration's pre-flight lists any existing case-duplicates and stops (does not merge
  them silently).
- **AC-04 [BE][T]** Backfill links existing users to contacts: every existing user with no
  `respond_contact_id` whose normalised `contact_number` equals exactly one contact's
  `phone_number` gets linked (the link `respond_link_service` already caches at runtime today);
  ambiguous or already-claimed matches are left unlinked and listed. The S0 PR lists every link by
  name. It creates no user and changes no role. Re-running the backfill changes nothing.
- **AC-05 [BE][T]** Zero downtime: the S0 migration is expand-only (new nullable columns, new
  indexes created concurrently, relaxed NOT NULL), and the previous image's test suite still
  passes against the migrated schema.
- **AC-06 [BE][T]** Existing sign-in is unchanged: every existing user signs in with the same
  email and password after the migration; existing CRM sessions and existing portal tokens keep
  working without a new sign-in.
- **AC-07 [BE][T]** Every session row records how it was created: `user_sessions.auth_method` is
  one of `password`, `phone_otp`, `portal_link` (a portal verify card), `impersonation`.
- **AC-08 [BE][T]** Audit actor contract: every `audit_logs` row written after S0 carries
  `actor_type` (`user`, `contact`, `integration`, `worker`, `scheduler`, `public_link`, `system`), and, where
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
  "Integration: n8n", "Background job for Aisyah", "Scheduled", "Portal: <contact name> (no
  user)"), "on behalf of" for impersonation, and the sign-in method; no UUID is visible.
- **AC-14 [BE][T]** A portal write by a contact with no user records `actor_type = contact`,
  `auth_method = portal_token`, `contact_id` = the contact and no `user_id` (Q3, Q4: such
  contacts keep using the portal).

## S1 Phone sign-in

- **AC-20 [FE][E2E]** The sign-in page has one field, "Email or phone number" (Q7). Input that
  normalises to a phone number goes to the code step; anything with `@` goes to the password step.
  Usable at 375px with the keyboard open (submit button reachable without scrolling the field
  away) and at 1280px.
- **AC-21 [BE][T]** `POST /api/v1/auth/phone/request-code` with a phone number always answers
  200 with the same body, whether or not the number belongs to anyone (no enumeration). A code is
  sent only when the number resolves to exactly one ACTIVE, non-integration user with a linked
  WhatsApp contact whose phone equals the user's phone. A contact with no user never gets a
  sign-in code from this route, and no user is created (Q4).
- **AC-22 [BE][T]** The code goes to WhatsApp only (Q6, owner ruling 26 Sep 2026 23:45 MYT) through the existing `respond_io` queue and the
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
- **AC-27 [BE][T]** Phone sign-in works for staff and admins too (Q10, owner ruling 26 Sep 2026
  23:45 MYT): a staff user and a `superadmin` with a linked phone each sign in by code and get
  their normal CRM session and permissions.
- **AC-28 [FE][E2E]** After sign-in the user lands where they work (Q9, owner ruling 26 Sep 2026
  23:45 MYT): a `callbackUrl` the user may open wins; otherwise a user holding the `salesperson`
  role lands on its portal home even if it also holds CRM permissions; any other user with a CRM
  permission (or admin) lands on the CRM home; a user with none lands on its portal home.

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
- **AC-34 [FE][E2E]** For a contact the owner has set up (linked to an ACTIVE user), the verify
  card on `/portal/c/{slug}` and `/portal?token=` signs the person in to the unified session:
  after the code, the NextAuth session exists, and opening a CRM page they have permission for
  needs no second sign-in. `slug-info` and `token-info` carry `has_user` so the card picks the
  path; the server refuses the unified path for a contact with no user (same 401 as a wrong code).
- **AC-35 [BE][T]** A portal contact with no user is never given one (Q3, Q4, owner ruling 26 Sep
  2026 23:45 MYT): its verify step mints a portal token exactly as today (7-day link token,
  30-day sliding verified token, same limits), and the `users` row count is unchanged after it
  signs in, re-verifies, or submits.
- **AC-36 [BE][T]** Portal tokens (Q11): a token of a contact with no user keeps sliding as today,
  with no end date. From the S2 deploy, a token of a contact that has a user no longer slides, so
  it ends within 30 days, and that person's new verifications mint a user session, not a token.
  Admin "view as contact" tokens are unchanged (Q12).
- **AC-37 [BE][T]** Submissions made on a user session store the same `contact_id`, `space_id` and
  `respond_inbox_url` as before, and the audit row carries the user (AC-08).
- **AC-38 [FE][E2E]** Signing out from the portal ends the user session everywhere that session
  was used (portal and CRM); the user's own device list (`account/security/current-sessions`)
  shows portal sign-ins with their method.
- **AC-39 [FE][E2E]** A user with both CRM and portal access has a "Portal" entry in the user menu
  and an "Open CRM" link in the portal header; a portal-only user who opens a CRM URL lands on
  their portal home, not an empty CRM shell.

## S3 The owner creates and links users

- **AC-40 [BE][T]** A salesperson contact is (Q1, owner ruling 26 Sep 2026 23:45 MYT): a contact in
  any market segment with `is_requestor_selectable = true` (today `retail` and `project`), or a
  contact linked from `sales_agents.contact_id`. One function; it only decides who appears on the
  worklist (AC-50) and which role the create form suggests. It creates nothing.
- **AC-41 [BE][T]** The owner creates a user from a contact: `POST
  /api/v1/user_management/users` accepts `respond_contact_id`, an optional `email` (Q5) and
  `company_ids`; the saved user is linked to the contact, its phone is the contact's phone, its
  roles and companies are exactly what the owner submitted, status ACTIVE when it has a phone,
  INACTIVE with the existing invite email when it has only an email.
- **AC-42 [BE][T]** One person, one user, decided by the owner (Q14): creating a user whose phone
  equals an existing user's answers 409 `PHONE_BELONGS_TO_USER` naming that user (never its id),
  and creates nothing; linking the contact to that existing user instead succeeds and adds no
  role.
- **AC-43 [BE][T]** A contact already linked answers 409 `CONTACT_ALREADY_LINKED` naming its user;
  linking a user already linked to a different contact is refused the same way. Nothing is
  unlinked or merged by itself.
- **AC-44 [BE][T]** Nothing creates a user or changes its roles except the owner's create, edit and
  link actions: adding a contact to a salesperson segment, linking it to a sales agent, removing
  it from every salesperson source, a Respond.io sync, a portal verify and a phone sign-in each
  leave the `users` and `user_role_assignments` row counts unchanged (one test per source).
- **AC-45 [BE][T]** A salesperson gets nothing beyond portal submission (Q8, owner ruling 26 Sep
  2026 23:45 MYT): the `salesperson` and `portal_user` roles are protected, seeded with no CRM
  permissions, never the `is_default` role, and the grant sweep leaves them empty. A user holding
  only `salesperson` gets 403 on every CRM route and sees the portal forms of its contact.
- **AC-46 [BE][T]** A contact's phone change (Respond.io sync or admin edit of the contact) does not
  change the linked user. While the two phones differ, phone sign-in for that user is refused and
  the user is flagged "Needs attention" (AC-52); the owner's "Use new number" updates the user's
  phone, clears `phone_verified_at` and ends its sessions (AC-54).
- **AC-47 [BE][T]** Every create and link is audited with the acting admin (`real_user_id`) and
  names the contact it came from.
- **AC-48 [FE][E2E]** The create form (the existing Add user modal) opened from a contact or a
  worklist row shows, in order: Name, WhatsApp contact (locked), Phone (read-only, from the
  contact), Email (optional when there is a phone, Q5), Roles (`SearchableMultiSelect`,
  `salesperson` suggested for a salesperson contact, `portal_user` for any other), Companies
  (prefilled from the contact). Each 409 shows inline with its action ("Open user", "Link this
  contact to <name> instead"). Usable at 375px and 1280px.
- **AC-49 [BE]** S3 records the supersession of the 14 Aug 2026 "no user account for salespeople"
  ruling (Q2, owner ruling 26 Sep 2026 23:45 MYT) in the `sales_agent.py` docstring and
  `PLAN-customer-sales-agent-assignment-24sep.md`.
- **AC-50 [FE][E2E]** "Salesperson accounts" (under User Management): a DataGrid of every
  salesperson contact with columns Contact, Phone, Segment / Agent, User, State (No user yet,
  Linked, Needs attention); filter by State, defaulting to all; row actions Create user (opens
  AC-48), Open user, or for Needs attention the one resolving action named in words ("Phone
  belongs to <name>": Link to <name>; "<name> is linked to another contact": Open <name>; "No
  longer a salesperson; still has the Salesperson role": Open user). Standard DataGrid rules
  (fixed layout, resizable, explicit sizes, truncate + title), usable at 375px.
- **AC-53 [FE][E2E]** Contact detail: a "User account" section showing the linked user, or "No
  user yet" with Create user and Link existing user for an admin; Unlink is a 5-second deferred
  action with Cancel (D7), never a dialog.

## S4 Admin identity screens

- **AC-51 [FE][E2E]** Users list: a "Kind" filter (Staff, Salesperson, Portal, derived from roles)
  that defaults to showing everyone (lesson: a list that opens filtered cannot be reconciled), and
  a "Sign-in" column (Email, Phone, Email + Phone).
- **AC-52 [FE][E2E]** User detail: a "Sign-in" section in the same place on view and edit, with
  email, phone and its verified state, linked WhatsApp contact (name and masked phone, clickable)
  with Link WhatsApp contact when there is none, last sign-in time and method, and "Needs
  attention: phone differs from WhatsApp contact" with "Use new number" (AC-46); explicit empty
  states ("No phone yet. Add one to allow phone sign-in.").
- **AC-54 [BE][T]** Unlinking, or changing a user's phone or linked contact, revokes every session of
  that user (the same path as force-logout) and writes an audit row.
- **AC-55 [BE][T]** Every new or extended admin route is permission-gated:
  `user_management.users.create` to create from a contact, `user_management.users.edit` for link,
  unlink and phone edits, `user_management.users.view` for the worklist; each has an auth-denial
  test, and the grant sweep gives the new view permission to every role that already holds
  `user_management.users.view`.

## Cross-cutting

- **AC-60 [T]** No em-dash or en-dash in any file this lane adds or edits.
- **AC-61 [E2E]** Every changed screen is verified by agent-browser at 375px and 1280px, reached by
  sidebar clicks from `/` (the portal from its WhatsApp link), with evidence under
  `documentation/plans/identity/evidence/<slice>/`.
- **AC-62 [BE]** `security-reviewer` runs on every slice of this plan (auth, RBAC and portal ingest
  are all touched).
