# PLAN: Unified identity, one login for the portal and the CRM (#1280)

Status: draft plan + UAC, 26 Sep 2026, awaiting the owner's answers to section 12. Track: full
(migration, auth, RBAC, portal ingest). Nothing built. The plan rides in the first feature PR
(S0); this lane is docs only.
UAC: `identity-unified-login-acceptance-criteria.md` (same folder; the Journey is there, and every
AC traces to a step in it).
Classification: CORE (auth and users are base-platform), tables stay in `public`.
Companion: #1281 (audit trail analysis) relies on the actor contract in section 8.

All line refs are `origin/main` at 51d30ccc5. Paths are relative to `sorento_crm_backend/` (BE)
and `sorento_crm_frontend/` (FE) unless given in full. No database was reachable from the
planning session, so every row count this plan needs is named as an S0 pre-flight query rather
than stated as a fact.

## Contents

0. Owner words
1. Why
2. The decision in one paragraph
3. What exists today (measured)
4. Design: one principal, several ways in
5. Sign-in and recovery flows
6. Counterpart users for salesperson and dealer contacts
7. Permissions each kind of user gets
8. The audit actor contract (for #1281)
9. Migration path: zero downtime, no re-registration
10. Slices, each with its definition of done and UAC ids
11. Risks, out of scope, named triggers
12. Grill questions for the owner

## 0. Owner words

26 Sep 2026 ~13:50Z, issue #1280, verbatim and binding:

> "I think eventually all our portal and user sign in needs to be unified. Because the one who use
> the portal for basic portal submission function will grow to use our project sales modules, use
> our sales opportunities module. So I think we need to find a way to unify. I'm thinking that we
> should support like user login, user email and password login, or also a phone number login. We
> should unify this. So for all the contacts that are like for product salesperson, retail
> salesperson, we also need to create like a counterpart user for them so in the future all of
> them can use our system and be audit trailed by our system."

Read as four requirements: (R1) one sign-in for portal and CRM; (R2) email + password OR phone
number; (R3) a counterpart user for every product and retail salesperson contact; (R4) everything
those people do is audit-trailed as them.

This reverses a recorded ruling: `app/models/sales_agent.py:7-10` and `:206-209` carry the
captain's 14 Aug 2026 ruling that salespeople "shouldn't have user account in our system, or
optional at least", repeated in `documentation/plans/sales/PLAN-customer-sales-agent-assignment-24sep.md:10`.
#1280 is the owner's newer word; Q2 asks the owner to confirm it explicitly so the docstring and
that plan can be corrected in S3.

## 1. Why

Today there are two identity worlds that never meet (section 3):

- **CRM staff** are `users` rows, signed in by email + password, holding an opaque
  `user_sessions` token behind NextAuth.
- **Portal visitors** are WhatsApp contacts (`respond_contacts`), holding an opaque
  `portal_tokens` token after a WhatsApp code, with no user row at all.

The owner's point is that these are the same people on a timeline: a salesperson who submits a
price tag request on the portal today will work project sales opportunities in the CRM tomorrow.
With two worlds that person needs a second account, a second sign-in, and their history is split
across a contact id and a user id. The audit trail (#1281) cannot say "Aisyah did this" across
both, because the audit log has no actor kind and three different id namespaces for actors.

## 2. The decision in one paragraph

**The person is the existing `users` row; nothing new is introduced as a "principal".** A user
may carry an email (with a password) and/or a phone (verified by a WhatsApp code), and links to
at most one WhatsApp contact through the column that already exists for it
(`users.respond_contact_id`), made unique. Both ways in produce the one session kind that already
exists (`user_sessions`, behind NextAuth). The portal stops holding its own token and derives its
(contact, space) from the signed-in user's linked contact, so every ownership rule, form grant
and company scope the portal has today keeps working unchanged. Every salesperson contact gets
its user up front; every other portal contact gets one silently the next time it signs in. The
audit log gains an actor kind plus the few fields that say how and on whose behalf. No new
identity table, no new OTP table, no new session table.

Why not a separate `principals` or `identities` table with users and contacts hanging off it:
`users` already has email, password, phone (unique), status, roles, company grants, sessions and
a contact link. A new table would duplicate each of those and migrate every `*_by` FK for no
behaviour the owner asked for. The trigger that would justify it is named in section 11.

## 3. What exists today (measured)

### 3.1 CRM users, roles, permissions, company scope

- **One `users` table, owned by the backend** (`app/models/user.py:18-123`). `email` String,
  unique, NOT NULL (:23); `password` nullable bcrypt (:24); `contact_number` (:29) with
  `uq_users_contact_number` (:121-122, "One phone == one user"), stored as E.164 digits without
  `+` by `normalize_msisdn` (`app/services/phone_utils.py:22`, Malaysia default); `status`
  String INACTIVE / ACTIVE / BLOCKED (:36); `email_verified_at`, `last_sign_in_at`, `is_trashed`,
  `is_protected`, `is_integration` (machine principal, never a password); `respond_user_id`
  (the Respond.io agent id); `last_active_company_id`; `respond_contact_id` FK to
  `respond_contacts` ON DELETE SET NULL (:61-63), **not unique**.
- **Prisma is gone.** There is no `sorento_crm_frontend/prisma/`; CLAUDE.md's Prisma lines are
  stale (a docs fix riding in S0).
- **Roles:** `user_roles` (slug, `is_default`, `is_protected`), `user_role_assignments` (many
  roles per user), `user_permissions`, `user_role_permissions` (`app/models/user.py:172-237`).
  `superadmin` and `admin` pass every check (`app/services/user_service.py:1138,1173,1206`),
  cached 30s. `require_permission` and variants at `app/dependencies.py:313-488`. Signup, create
  and invite assign the `is_default` role when none is given.
- **Module guard:** `require_module_enabled_with_api_key` (`app/modules/runtime/guards.py:62`)
  needs a staff session or an API key; `/public` (portal) and `/auth` are mounted without it
  (`app/api/v1/__init__.py:50,221`).
- **Company scope:** `user_companies` grants per user, roles global; the resolver's decision table
  is `app/services/company_scope_resolver.py:12-32` (staff: one active company; admin: all;
  portal token: the contact's `respond_contact_companies`; no principal: fail closed). For
  `/public/` paths **a Bearer token is checked before the portal token** (:323-328), which matters
  for S2 (AC-32). Two leftovers there: a `jwt.decode(bearer, jwt_secret)` attempt (:81) and an
  env `EXTERNAL_API_KEY` compare (:66-68); real API-key auth moved to `integration_api_keys`
  (`app/dependencies.py:491-560`).
- **Teams** `teams` / `team_members(user_id)` (`app/models/access.py:518-588`).

### 3.2 CRM sign-in and sessions

- **NextAuth, one provider:** `CredentialsProvider` (email, password, rememberMe)
  (`app/api/auth/[...nextauth]/auth-options.ts:64-125`). `authorize()` posts to FastAPI
  `/api/v1/auth/login` and stores the returned opaque `apiToken` (:121) in the NextAuth JWT with
  id, email, name, roles and company grants (:126-185). `/api/auth/token` hands the `apiToken` to
  the browser; a 401 with `session_revoked` / `session_expired` / `session_invalid` signs out
  (`lib/api.ts:195`).
- **FastAPI validates the opaque token, not a JWT:** `get_current_user`
  (`app/dependencies.py:184`) resolves `user_sessions` (`app/models/user_session.py:28-47`:
  token, user_id, expires_at, revoked_at, rolling, user_agent, ip_address, last_seen_at), loads
  the user and first role, rejects non-ACTIVE. Rolling 30 days (slide at 29) or 8 hours when not
  remembered (`app/services/user_session_service.py:25-34`). Impersonation: admin with an open
  `ImpersonationSession` + `X-Impersonate-User-Id` (`app/dependencies.py:114-153`). The archived
  `PLAN-staff-rolling-sessions-fastapi-auth.md` fully shipped (migration `237_user_sessions`,
  revocation, device list at `account/security/current-sessions`).
- **Login throttle:** 8 failures per email+IP lock 15 minutes, Redis, fails open
  (`app/services/login_throttle.py:15-17`).
- **Gaps measured:** an unknown email returns `404 "User not found. Please register first."`
  (`app/api/v1/auth.py:59-65`), which enumerates emails (fixed in S1, AC-26); login and create
  match email case-sensitively (`auth.py:55`, `user_service.py:492,521`) while update lowercases
  (`user_service.py:570-574`), so case-duplicates are possible (AC-03); login does not check
  `is_trashed`; self-signup creates an INACTIVE user and never sends its email (`auth.py:226`,
  and the sign-in page links no signup); session tokens are stored in plain text (section 11).
- **No Next.js middleware:** CRM pages are gated client-side in `app/(protected)/layout.tsx:24-58`.
- **Account lifecycle:** admin create (with password) or invite (no password, INACTIVE)
  (`app/api/v1/user_management/users.py:554-588`, resend `:652`); accept-invite and reset both go
  through `/auth/change-password?token=`, which sets ACTIVE and revokes sessions
  (`auth.py:358-411`); forgot password is non-enumerating and rate-limited (`auth.py:243-328`);
  force-logout (`users.py:274`); delete is soft `is_trashed`, hard only once trashed
  (`user_service.py:641-666`).

### 3.3 Portal sign-in

- **The portal principal is a contact plus a Respond.io space, carried by an opaque token.**
  `portal_tokens` (`app/models/portal.py:26-44`: token, `contact_id` Text no FK, `space_id`,
  `expires_at`, `revoked_at`, `verified_at`, `is_impersonation`). `portal_otp_codes`
  (`portal.py:47-62`, sha256 of a 6-digit code, keyed by contact).
- **Lifetimes** (`app/services/portal_service.py:57-68`): a minted link token lasts 7 days; an
  OTP-verified token 30 days sliding (`resolve_token` :378-409); a code 10 minutes, 60s cooldown,
  5 attempts, 10 sends per contact per day; per-IP limit on `request-otp` 30 per 60s
  (`app/config.py:199-200`). No reCAPTCHA anywhere in the backend.
- **Every token starts unverified** (`mint_token` :247 never sets `verified_at`); `verify_otp`
  (:598-645) verifies all the contact's tokens and mints a fresh 30-day one. The docstring at
  `app/api/v1/external/portal_tokens.py:4` claiming OTP is bypassed is wrong.
- **Cross-device login shipped:** `/portal/c/{slug}` is an identity hint, `GET /slug-info/{slug}`
  and `GET /token-info` return contact id, space id, name and masked phone, and the verify card
  fires `request-otp {contact_id, space_id}` itself (`portal.py:111`,
  FE `PortalVerifyCard.tsx:110,161-200`). The person never types a phone number.
- **Code delivery** is an RQ job on the `respond_io` queue (`app/tasks/respond_io_tasks.py:180`,
  template `portal_otp`, variable `otp_code`), so it needs the worker. **There is no SMS provider
  anywhere in the codebase** (no Twilio, no SMS code).
- **Route dependency:** `get_portal_token` (`app/api/v1/public/portal.py:88-105`) reads
  `X-Portal-Token` or `?token=` and stamps the contact into `db.info["actor_contact_id"]` and a
  context var. About 46 route dependencies use it (27 in `portal.py`, 19 in
  `portal_price_tag.py`, plus `ai_extract.py`).
- **Other token mints:** staff (`app/api/v1/user_management/contacts.py:650-681`, permission
  `user_management.contacts.portal_link`); n8n / MCP `POST /external/portal-tokens/`; admin
  "view as contact" (`contact_impersonation.py:109-196`) mints a pre-verified token, and
  `contact_impersonation_sessions.portal_token_id` is a NOT NULL FK to `portal_tokens`.
- **FE:** the portal lives under `app/(auth)/portal/` (legacy tree plus `c/[slug]`), outside
  NextAuth. `portal-client.ts` keeps `sorento.portalToken` in localStorage (impersonation in
  sessionStorage, which wins) and sends `X-Portal-Token` (:268-322, :359).
- **Form grants by market segment** (`app/services/portal_form_visibility_service.py:44-109`):
  base four kinds, plus the union of `market_segments.portal_form_types` over the contact's
  segments, then `contact_portal_form_overrides` rows win (`app/models/price_tag.py:56-79`). All
  keyed on `respond_contacts.id` (plan `documentation/plans/portal/PLAN-portal-forms-market-segment.md`).
- **What a submission records:** `contact_id` + `space_id` + `respond_inbox_url` from the token
  (`portal_service.py:1234-1265`); ownership everywhere is
  `entity.contact_id == token.contact_id AND entity.space_id == token.space_id`, else 404 or 403
  `OWNER_MISMATCH` (:811-835); price tag checks contact only
  (`portal_price_tag.py:831-853`). Portal status messages deep-link through
  `submission_link(contact_id)` to `/portal/c/{slug}/{type}/{id}` (about 10 callers).

### 3.4 Contacts, sales agents, dealer contacts, Respond.io contacts

- **`respond_contacts`** (`app/models/access.py:230-307`) is the WhatsApp identity and the portal
  identity: `id` Text PK, `phone_number` Text NOT NULL UNIQUE (:234, normalised digits),
  `respond_io_id` (:238), `portal_slug` unique (:241), `workspace_id` FK to `respond_workspaces`
  (:242). No email, no user id, no customer id, no type column. Classified only by links:
  access types (`respond_contact_access_types`, seeded codes `end_user`, `dealer`,
  `alembic/versions/094_contact_access_types.py:61-62`), market segments
  (`respond_contact_market_segments`, seeded `retail`, `project`,
  `263_market_segments.py:107-109`, with `is_requestor_selectable` at `access.py:143` feeding the
  "Requested by / Salesperson" picker), companies (`respond_contact_companies`,
  `app/models/company.py:65`).
- **Nothing in the code defines "product salesperson" or "retail salesperson".** The closest
  facts: the `retail` and `project` segments, both requestor-selectable, and `sales_agents`.
  "Product salesperson" is read in this plan as "project salesperson" (the `project` segment),
  which a voice transcription would produce; Q1 asks.
- **`sales_agents`** (`app/models/sales_agent.py:42-134`) is the AutoCount salesperson master,
  one row per agent code, with `person_label`, nullable `company_id`, and `contact_id` Text FK to
  `respond_contacts` (:86-93). `customers.sales_agent_id` (`app/models/order.py:142-146`) gives a
  customer one agent; the portal price tag debtor dropdown reads the agent by its contact
  (`price_tag_request_service.py:2390,2408-2411`).
- **Requested-by routing** stores people as contacts: `purchase_requests.requested_by_contact_id`,
  `stock_inquiries.salesperson_contact_id` (`documentation/plans/PLAN-requested-by-contact-routing.md`),
  CS pins `respond_contact_cs_routing` (`access.py:310-361`).
- **Dealer contacts:** a dealer is a `customers` row (ADR `documentation/adr/0007-a-dealer-is-a-customer-not-a-company.md`);
  its WhatsApp people link through `respond_contact_customers` (`access.py:11-64`, one primary per
  contact per company) and usually carry access type `dealer`. `customer_contacts`
  (`order.py:220-252`) are staff-typed address-book people with no link to contacts or users.
- **Respond.io contacts** are synced in by `respond_sync_handler.py:111` and matched by
  `respond_io_id` or phone (`app/services/respond_identifier.py:18,45`). Every automated send goes
  through `send_text_or_template` (`app/services/respond_messaging_service.py:545`), free text in
  the 24h window, the approved template outside it.
- **The contact-to-user link already exists:** `users.respond_contact_id`, set by an admin
  (`user_service.py:598`) or cached from a unique phone match between `users.contact_number` and
  `respond_contacts.phone_number` (`app/services/respond_link_service.py:25-48`). Used today for
  staff WhatsApp notifications only. Onboarding intake provisions a user and a contact side by
  side but never sets this link (`app/services/onboarding_service.py:784`), and types
  `onboarding_people.respond_contact_id` as UUID against a Text PK (`app/models/onboarding.py:246`).

### 3.5 Every place a "who did this" is recorded

- **About 150 actor columns in three id namespaces plus free text** (full table in the lane's
  research notes, summarised): `created_by` / `updated_by` / `*_by` / `*_by_id` pointing at
  `users.id` (roughly 40 with an FK, 60+ without); six contact-typed actors
  (`requested_by_contact_id` `procurement.py:1018`, `submitted_by_contact_id` `portal.py:114`,
  `uploaded_by_contact_id` `resources.py:170`, `collected_by_contact_id` `price_tag.py:153`,
  `author_contact_id` `price_tag.py:450`, ticket comment `respond_contact_id`), four of them paired
  with a user column; about five holding a Respond.io agent id (`complaints.assigned_to:68`,
  `last_responded_by`, `sla.responded_by:99`); about six free-text names or emails
  (`procurement.requested_by:1014`, `approver_email:1040`, `onboarding.requester_email:138`);
  three that hold "an id or a name" (`complaints.rejected_by/resolved_by`, `sla.resolved_by:103`).
- **`audit_logs`** (`app/models/audit.py:9-45`): entity_type, entity_id, action, `user_id` (UUID,
  no FK), `contact_id` (no FK), old/new values, description, ip_address, trace_id, company_id. No
  actor kind, no user agent, no session, no integration, no impersonator. 44 models opt in with
  `__audit_track__`; the before-flush listener is `app/services/audit_service.py:323`.
- **How the actor is found:** context vars (`app/audit_context.py`); `LoggingMiddleware` resets
  them per request (`app/middleware/logging_middleware.py:20`); JWT dependencies set the user
  (`app/dependencies.py:222,273,306`); the portal sets the contact.
- **Measured gaps** that the section 8 contract closes: (a) no actor kind, so worker, scheduler,
  unauthenticated and lost-context writes all render "System"
  (`app/api/v1/audit/audit_logs.py:110-116`); (b) an API-key write looks exactly like its act-as
  user, and `api_call_log.actor` is always NULL
  (`app/middleware/api_call_log_middleware.py:197`); (c) RQ and scheduler jobs never set the audit
  context although tasks receive a `user_id` argument (`app/tasks/export_tasks.py`,
  `autocount_pull_tasks.py:236`); (d) impersonation rewrites only four column names
  (`audit_service.py:251-274`) and stores no impersonator; (e) **suspected, to confirm by test in
  S0:** admin "view as contact" writes are credited to the contact although the docstring
  (`contact_impersonation.py:7-9`) says the admin stays the actor; (f) **suspected, to confirm by
  test in S0:** `get_current_user_or_api_key` (`app/dependencies.py:531`) is a sync dependency
  running in a copied context, so its `set_audit_context` may be invisible at flush, leaving
  `user_id` NULL on writes through the ~41 route files that use it; (g) no user agent or session
  on audit rows.
- **Actor kinds that exist today:** staff user; impersonating admin; integration acting as a user
  (n8n, MCP, AutoCount ESB); portal contact; admin viewing as a contact; Respond.io agent; Respond.io
  contact (chatbot, webhooks); worker or scheduler; anonymous public-link approver.
- **MCP** sends the shared API key plus `X-Source: mcp`, `X-Tool-Name`, `X-Correlation-Id`
  (`sorento_crm_mcp/sorento_crm_mcp/http_client.py:25,91-95`) and has four write tools
  (`record_actions.py`), all acting as the integration's act-as user.

## 4. Design: one principal, several ways in

### 4.1 The person

- **A person who signs in is a `users` row.** Staff, salespeople and portal contacts alike. A
  user has at most one linked WhatsApp contact (`users.respond_contact_id`, made unique where set,
  AC-01), and a contact has at most one user. The contact stays the WhatsApp and portal identity
  it is today: everything keyed on `respond_contacts.id` (form grants, ownership of submissions,
  requested-by, sales agents, CS pins, `respond_inbox_url`) is untouched. The user is what signs
  in, holds roles, holds a session, and is written into the audit log.
- **Email becomes optional** (AC-02, Q5). `users.email` NOT NULL is relaxed; a check constraint
  requires `email IS NOT NULL OR contact_number IS NOT NULL`. A salesperson with only WhatsApp is a
  user with a phone and no email. Placeholder emails (`6012...@phone.local`) are rejected as a
  design: the email outbox, invite, reset and SLA emails all read `users.email`, and a fake
  address turns each of them into a silent bounce. S0 lists every `users.email` reader
  (`grep -rn "\.email" app/`), and each one that would break on NULL gets a guard (skip the email
  channel, never raise) with a test.
- **Email is unique case-insensitively** (AC-03): a unique index on `lower(email)` replaces the
  plain one, and every write lowercases. The S0 pre-flight query lists case-duplicates first; if
  any exist the migration stops and they go to the owner (never a silent merge).
- **Phone stays unique** (the existing `uq_users_contact_number`), normalised by the one
  normaliser `normalize_msisdn`. `phone_verified_at` (new, nullable) is set by a successful code
  and cleared when the number changes. The second normaliser, `utils/phone_normalize.normalize_phone`
  (digits only), is not used by anything in this plan.

### 4.2 The ways in

| Method | Who | Proves | Result |
| --- | --- | --- | --- |
| Email + password | any user with a password (as today) | knows the password | `user_sessions` row, `auth_method = password` |
| Phone + WhatsApp code | any ACTIVE non-integration user whose phone resolves to a linked contact (AC-21, AC-27) | holds the WhatsApp number | `user_sessions` row, `auth_method = phone_otp` |
| Portal link (`/portal/c/{slug}`, `/portal?token=`) | a portal contact | holds the WhatsApp number (the same code) | `user_sessions` row, `auth_method = portal_link`; the user is created at this step if missing (AC-35) |
| API key | integrations (n8n, MCP, AutoCount) | holds the key | unchanged; acts as the integration's user, now named in audit (AC-09) |
| Admin "view as contact" | admins | an admin session | unchanged token, now audited as the admin (AC-11, Q12) |

- **Phone login reuses the portal's code machinery, not a new table.** The typed number is
  normalised, resolved to one contact (`respond_contacts.phone_number`, unique) and that contact's
  linked user; the code is stored in the existing `portal_otp_codes` keyed by that contact, sent
  by the existing `send_portal_otp_respond_message` task, and checked by the same limits. The
  difference from the portal flow is only the entry (a typed phone instead of a slug) and the
  result (a user session instead of a portal token). A user whose phone has no contact cannot use
  phone sign-in until an admin links one (AC-52 shows it); creating Respond.io contacts from a
  typed number at sign-in is not done (it would let anyone create contacts).
- **No enumeration** (AC-21, AC-26): request-code answers the same body for every number; email
  login answers the same 401 for an unknown email and a wrong password.
- **SMS is not built** (Q6). The codebase has no SMS provider; WhatsApp is how every one of these
  people already talks to Sorento. Named trigger in section 11.

### 4.3 One session model

- **`user_sessions` is the only session.** It gains `auth_method` (AC-07). NextAuth gains a
  second Credentials provider, `phone-otp`, whose `authorize()` posts `{phone, code}` (or
  `{contact_id, space_id, code}` from the portal verify card) to FastAPI and stores the returned
  `apiToken` exactly as email login does. Everything downstream of the token (company context,
  roles, 401 sign-out, device list, force-logout, revocation on password change) works unchanged.
- **Lifetime:** phone and portal sessions are 30-day rolling, the same as "remember me" today
  (Q15: the portal's 30-day sliding token is what these people are used to). Email sessions keep
  their remember-me choice.
- **The portal reads the same session.** Portal pages obtain the `apiToken` from
  `/api/auth/token` and send `Authorization: Bearer`. `get_portal_token` becomes
  `get_portal_principal`, returning the same three things every portal route reads today
  (`contact_id`, `space_id`, and an id for logout), from either (a) a user session whose user has a
  linked contact, space from the contact's workspace, or (b) a legacy `X-Portal-Token` until those
  expire (AC-36). The 46 route signatures change type, not logic; AC-31 proves each form kind
  answers identically under both principals.
- **Company scope for portal routes stays the contact's** (AC-32): the resolver's `/public/`
  branch checks for a portal principal before a Bearer user, so a salesperson with CRM grants still
  sees portal data scoped exactly as the portal did.
- **Where a person lands** (AC-28, AC-39, Q9): any CRM permission (or admin) means the CRM home or
  the `callbackUrl`; none means the portal home `/portal/c/{slug}` of the linked contact. The
  `(protected)` layout sends a portal-only user to their portal home instead of rendering an empty
  shell; the user menu carries "Portal" for anyone with a linked contact, and the portal header
  carries "Open CRM" for anyone with a CRM permission.

## 5. Sign-in and recovery flows

Screens are designed at 375px first, then 1280px. No explanatory prose in the UI (PRINCIPLES
design mandates); copy below is the full visible text.

### 5.1 Sign-in (`/signin`, AC-20, AC-25)

- **Step 1**, one field. Label "Email or phone number", `inputmode="email"` until the first
  character is a digit or `+`, then `inputmode="tel"`; `autocomplete="username"`. Primary button
  "Continue", full width at 375px. Link "Forgot password?" under it.
- The client decides: contains `@` means password step; otherwise the FE normalises the phone
  with the same rules as the backend (a shared test vector list keeps them equal) and calls
  `request-code`. An input that is neither shows "Enter an email or a phone number" inline.
- **Step 2a, password** (as today): the email shown read-only with "Change", password field,
  "Keep me signed in", "Sign in".
- **Step 2b, code:** heading "Enter the code sent to your WhatsApp", the masked number
  (`+60 12-*** 6789`) with "Change number", six single-digit boxes (`inputmode="numeric"`,
  `autocomplete="one-time-code"` on the first, paste fills all), "Resend code" disabled with a
  60-second countdown, and "Use password instead" only when the user has one. At 375px with the
  on-screen keyboard open the boxes and the submit sit above the fold; the code auto-submits on
  the sixth digit.
- **Errors in words:** wrong code "That code is not right. 4 tries left."; expired "That code has
  expired. Send a new one."; limit "Too many tries. Try again in 12 minutes." (from the 429's
  seconds); no WhatsApp contact or unknown number: nothing distinguishes it on screen (the code
  simply never arrives), by design.

### 5.2 Portal link (AC-34, AC-35)

The verify card the contact already knows stays as it is visually. What changes is behind the
button: `verify` calls NextAuth `signIn('phone-otp', {contact_id, space_id, code})`, FastAPI finds
or creates the user (section 6.3), mints a `user_sessions` row with `auth_method = portal_link`,
and the page continues to the portal home with the session in place. `sorento.portalToken` is no
longer written; an existing stored token keeps working until it expires (AC-36).

### 5.3 Recovery

- **Forgot password:** unchanged (email reset link, 1 hour, non-enumerating). A phone-only user
  has no password to forget: the code IS the sign-in.
- **A phone-only user can add a password** from Account > Security ("Set a password"), and an
  email from Account > Profile (verified by the existing email-verification link before it is
  used for sign-in). Both optional.
- **Lost access to the WhatsApp number:** an admin edits the phone on the user (AC-54): every
  session ends, `phone_verified_at` clears, and the next phone sign-in to the new number verifies
  it. A user with an email can also recover through the password reset.
- **A contact's number changes in Respond.io** (AC-46): the linked user's `contact_number` follows
  and is marked unverified; a collision with another user is refused on the user side and listed
  in S4's "Needs attention".
- **Blocked or trashed users** cannot sign in by any method, including a code (fixes the measured
  `is_trashed` gap at the same time).

## 6. Counterpart users for salesperson and dealer contacts

### 6.1 Who is a salesperson contact (Q1)

One function, `is_salesperson_contact(contact)`, used by the backfill, the sync hooks and the S4
view (AC-40): the contact is in any market segment with `is_requestor_selectable = true` (today
`retail` and `project`), **or** is the `contact_id` of any `sales_agents` row. Both sources exist
and are admin-maintained today; no new flag is added. If the owner defines the two salesperson
kinds differently (for example by access type), only this function changes.

### 6.2 Salesperson contacts: provisioned up front (AC-41 to AC-47)

- **Backfill (S3 migration + a re-runnable service):** for every salesperson contact with no
  linked user: if exactly one user has the same phone, link it and add the `salesperson` role
  (one person, one user, AC-42, Q14); if that user is already linked to another contact, report
  it and skip (AC-43); otherwise create a user: name from the contact, `contact_number` from the
  contact, no email, no password, status ACTIVE, role `salesperson`, company grants copied from
  `respond_contact_companies`, `last_active_company_id` the first of those.
- **Stays true** (AC-44): the market segment assignment service and the sales agent service call
  the same provisioning function after they add a contact, inside their own transaction. Losing
  every salesperson source removes the `salesperson` role; the user and its history stay.
- **Why up front and not at first sign-in:** the owner asked for the counterpart user to exist
  "so in the future all of them can use our system and be audit trailed", and salespeople are
  referenced by other people's records (requested-by, sales agent, CS pins) before they ever sign
  in; S3 can then show the user beside those references.
- **Onboarding intake** starts setting `users.respond_contact_id` when it provisions both (it
  creates them side by side today and leaves them unlinked); its UUID-typed
  `onboarding_people.respond_contact_id` is left alone (not read by this plan).

### 6.3 Every other portal contact, dealer contacts included (Q3, Q4)

- **Created at the next portal sign-in, not in bulk** (AC-35): when the portal verify step
  succeeds for a contact with no user, the same provisioning function runs with role
  `portal_user`. A dealer contact is a portal contact like any other (ADR 0007: a dealer is a
  `customers` row, and its people are contacts); it gets a user the day it signs in, and never
  earlier.
- **Why not bulk for dealers:** most dealer contacts never open the portal; bulk creation would
  fill the Users list with accounts that never sign in, and every one of them would need its
  company grants and clashes reviewed now for no gain. Anything a dealer contact does happens
  either on the portal (signed in, so a user exists by then) or on WhatsApp (recorded as the
  contact, as today, and the contact resolves to a user once one exists).

### 6.4 The sales agent ruling

The 14 Aug 2026 ruling is superseded by #1280 once the owner confirms Q2: S3 edits the
`sales_agent.py` docstring and adds a one-line supersession note to
`PLAN-customer-sales-agent-assignment-24sep.md`. `sales_agents` gains no `user_id`: the path
agent -> contact -> user already exists and is one join.

## 7. Permissions each kind of user gets

| Kind (derived, never stored) | How it gets a user | Roles at creation | CRM access | Portal access |
| --- | --- | --- | --- | --- |
| Staff | admin create or invite (as today) | as chosen, else `is_default` | per roles | only if a contact is linked |
| Salesperson | S3 backfill / sync | `salesperson` (protected, no permissions) | none until an admin adds a role | the linked contact's forms (market segment base + overrides) |
| Portal | first portal sign-in | `portal_user` (protected, no permissions) | none until an admin adds a role | the linked contact's forms |
| Integration | as today | as today | as today | none |

- **Portal access is not a permission.** It follows from having a linked contact, exactly as it
  follows from holding a token today, and the forms shown are the contact's (AC-33). No
  `portal.*` permission is added; the market segment grants and per-contact overrides stay the one
  source of truth.
- **The two roles are empty on purpose** (AC-45, Q8). The owner's growth path ("will grow to use
  our project sales modules") is served by adding permissions to `salesperson` once, which grants
  every salesperson at the same moment, or by adding a Project Sales role to one person. Which
  project sales permissions a salesperson should get by default is Q8's second half; until the
  owner names them, the role stays empty so nobody gains CRM access by a migration.
- **Kind is derived** for the S4 filter: Integration if `is_integration`; else Salesperson if the
  user holds `salesperson`; else Portal if it holds `portal_user` and no other role; else Staff.
  No `user_type` column.
- **Company grants** for provisioned users copy the contact's companies; a contact in no company
  gives a user with no grants, which scopes to zero rows (fail closed, as the portal does today)
  and appears in S4 as "Needs attention: no company".

## 8. The audit actor contract (for #1281)

This section is the contract #1281's analysis builds on. It says what every audited action
carries once S0 ships; which modules and functions must be audited at all is #1281's scope, not
this plan's.

### 8.1 Fields on every `audit_logs` row (AC-08)

| Field | Type | Meaning |
| --- | --- | --- |
| `actor_type` | text, NOT NULL for new rows (nullable column, backfilled `legacy`) | `user`, `integration`, `worker`, `scheduler`, `public_link`, `system` |
| `user_id` | existing | the effective actor (the user the action is attributed to); for a worker job, the user who enqueued it |
| `real_user_id` | new, nullable | the person actually at the keyboard: the impersonating admin, else equal to `user_id` |
| `auth_method` | new, nullable | `password`, `phone_otp`, `portal_link`, `portal_token` (legacy, until AC-36 ends it), `api_key`, `impersonation` |
| `session_id` | new, nullable | `user_sessions.id` (never the token) |
| `integration_id` | new, nullable | the `integrations` row behind an API key |
| `contact_id` | existing | the actor's linked contact (derived from the user when a user acts; set directly for a contact-only action such as a chatbot turn) |
| `job_id` | new, nullable | the RQ job id or scheduler task name |
| `ip_address`, `trace_id`, `company_id` | existing | unchanged |
| `user_agent` | new, nullable | truncated to 512 characters |

How each actor kind fills it:

| Actor | `actor_type` | `user_id` | `real_user_id` | `auth_method` | other |
| --- | --- | --- | --- | --- | --- |
| Staff / salesperson / portal user, signed in | `user` | self | self | session's method | `session_id`, `contact_id` if linked |
| Admin impersonating a user | `user` | target | admin | `impersonation` | `session_id` of the admin |
| Admin "view as contact" | `user` | the contact's user if any, else NULL | admin | `impersonation` | `contact_id` = contact (AC-11) |
| Legacy portal token (until expiry) | `user` if the contact has a user, else `public_link` | contact's user or NULL | same | `portal_token` | `contact_id` |
| Integration (n8n, MCP, AutoCount) | `integration` | act-as user | act-as user | `api_key` | `integration_id`; MCP's `X-Tool-Name` goes into `description` |
| RQ job | `worker` | enqueuing user or NULL | enqueuing real user | NULL | `job_id` |
| Scheduler tick | `scheduler` | NULL | NULL | NULL | `job_id` = task name |
| Anonymous public link (quotation sign, approval, onboarding intake) | `public_link` | NULL | NULL | NULL | the free-text name/email stays in `description` |
| Migration / backfill | `system` | NULL | NULL | NULL | `description` names the migration |

### 8.2 How it is stamped (S0)

- `app/audit_context.py` gains the new fields; the session dependencies set them where they set
  the user today (`app/dependencies.py:222,273,306`), the API-key path sets `integration`, the
  portal principal sets its own.
- **Jobs carry their actor:** `enqueue` helpers pass `actor = {user_id, real_user_id, trace_id}`
  in the job meta, and one RQ job wrapper (the worker's `perform_job` hook) sets the audit context
  from it with `actor_type = worker`; scheduler handlers set `scheduler`. One place each, not per
  task.
- **The two suspected gaps are tested first** (AC-11, AC-12): a red test for each, then the fix
  (for the sync dependency: set the context in an async wrapper, or store the actor in
  `db.info` the way the portal contact already is, whichever the test proves works).
- **Impersonation** stops rewriting four column names by hand: `real_user_id` on the audit row
  says who was at the keyboard, and the `*_by` columns keep the effective user, which is what the
  screen shows today.
- **`api_call_log.actor`** (always NULL today) is filled with `user_id` and `integration_id` from
  the same context, so the API log and the audit log agree.

### 8.3 Rules for new code (added to PR-CHECKLIST in S0)

- A new "who did this" column is `<verb>_by_user_id`, String FK to `users.id` ON DELETE SET NULL.
  Never contact-typed, never a Respond.io agent id, never a name or an email.
- An action a contact takes without a user (chatbot turn, WhatsApp ingest) is recorded against the
  contact and, when the contact has a user, that user too; display resolves contact -> user.
- The ~150 existing actor columns are **not** migrated by this plan. #1281 decides, per module,
  which get a `*_by_user_id` counterpart; the contact -> user link this plan creates is what makes
  that backfill a join.
- **Display:** the audit screens render `actor_type` and `auth_method` as words (AC-13): "Aisyah
  (phone)", "Nurain on behalf of Aisyah", "Integration: n8n as Ops Bot", "Background job for
  Aisyah", "Scheduled: daily reorder run", "Public link". `legacy` rows render as today.

## 9. Migration path: zero downtime, no re-registration

Deploys are blue/green: the new container runs `alembic upgrade head` while the old image still
serves (`documentation/plans/portal/PLAN-portal-forms-market-segment.md` D4 is the precedent), so
every migration here is **expand only**, and every contract step is its own later release.

### 9.1 Pre-flight queries (S0, run on the prod copy, results pasted into the S0 PR)

1. Case-duplicate emails: `SELECT lower(email), count(*) FROM users GROUP BY 1 HAVING count(*) > 1`.
2. Contacts claimed by more than one user:
   `SELECT respond_contact_id, count(*) FROM users WHERE respond_contact_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1`.
3. Users whose `contact_number` matches exactly one contact but are unlinked (the backfill set).
4. Salesperson contacts by rule (6.1), split into: already linked, phone matches one user, phone
   matches a user linked elsewhere, no match (the S3 creation set).
5. Portal contacts with a live token and no user (the population AC-35 will create lazily), and
   contacts whose tokens span more than one `space_id` (the S2 space-derivation risk, section 11).
6. Every reader of `users.email` that would fail on NULL (code grep, listed in the PR).

A non-empty result for 1 or 2 stops S0 and goes to the owner as a list of names; nothing is
merged or unlinked automatically.

### 9.2 Releases

| Release | Expand (migration) | Code | Old image safe because |
| --- | --- | --- | --- |
| S0 | `users.email` DROP NOT NULL + check (email or phone); unique `lower(email)` index created concurrently beside the old one; unique partial index on `users.respond_contact_id`; `users.phone_verified_at`; `user_sessions.auth_method` (nullable, backfilled `password`); audit columns (nullable); roles `salesperson`, `portal_user` seeded, protected, empty; link backfill (9.1 query 3) | audit stamping; email lowercased on write | no row has a NULL email yet; new columns are nullable and ignored by the old image |
| S1 | none | phone request / verify routes; NextAuth `phone-otp` provider; sign-in page | additive routes |
| S2 | none | portal principal from the user session; verify card signs in; legacy tokens stop sliding | the old image still resolves `X-Portal-Token`, and no token is revoked |
| S3 | salesperson backfill (data only, re-runnable) | provisioning hooks; `salesperson` role sync | new users have NULL email, which the old image's readers were guarded for in S0 |
| S4 | none | admin screens | additive screens |
| Contract (S2 + 30 days, its own small PR) | drop the old case-sensitive email index | remove `X-Portal-Token` support except impersonation tokens | every legacy token has expired (AC-36) |

- **No re-registration** (AC-06): staff keep email + password; portal contacts keep their link and
  their code (the user is created behind the verify step); salespeople find a user already made.
- **No forced sign-out** at any release: existing `user_sessions` rows stay valid; existing portal
  tokens stay valid until natural expiry.
- **Rollback:** every release is additive; rolling back the image leaves unused columns and
  extra `user_sessions` rows (the old image reads them as ordinary sessions, which they are).

## 10. Slices, each with its definition of done and UAC ids

Order is S0 -> S1 -> S2 -> S3 -> S4; S1 and S3 can run in parallel after S0 (S3 does not need
phone sign-in to create users; the users just cannot sign in until S1). One lane per slice, one
PR per lane; this plan rides in the S0 PR. Every slice runs the full track and
`security-reviewer` (AC-62).

### S0 Identity model, migration, audit fields

- Scope: section 4.1, 9.1, the S0 row of 9.2, section 8 in full, CLAUDE.md corrections (Prisma
  gone, staff tokens are opaque sessions, the `system` principal is replaced by integrations).
- UAC: AC-01 to AC-13, AC-60, AC-62.
- Done when: pre-flight results in the PR and clean (or owner-ruled); migration applies on a clone
  of the prod copy and the previous image's suite passes against it (AC-05); red-then-green tests
  for AC-11 and AC-12 committed; audit screens show actor words at 375px and 1280px; every
  `users.email` reader guarded with a test; single alembic head.

### S1 Phone sign-in

- Scope: sections 4.2, 4.3 (session part), 5.1, 5.3 (password and lost-phone parts).
- UAC: AC-20 to AC-28.
- First task: read the approved `portal_otp` WhatsApp template's text; if it names the portal, ask
  the owner whether it may be reused for CRM sign-in or a `login_otp` template must be approved
  first (Meta approval lead time is the slice's longest pole).
- Done when: a staff user and a phone-only user each sign in by code through the real worker and a
  real WhatsApp send on the lane stack; enumeration tests green; browser evidence at 375px (keyboard
  open) and 1280px.

### S2 Portal on the unified session

- Scope: sections 4.3 (portal part), 5.2, the S2 row of 9.2.
- UAC: AC-30 to AC-39.
- First task: confirm whether NextAuth's `SessionProvider` wraps the `(auth)` group today; if not,
  mount it for `/portal` only.
- Done when: every portal form kind proven identical under both principals (AC-31); a contact with
  no user signs in from an old WhatsApp link and lands on the same home with a new user behind it;
  a salesperson with a CRM role moves portal -> CRM -> portal with one sign-in; legacy token
  sliding off; evidence at both widths.

### S3 Counterpart users for salesperson contacts

- Scope: sections 6 and 7.
- UAC: AC-40 to AC-47.
- Done when: the backfill runs on a clone with its created / linked / reported counts in the PR
  matching pre-flight query 4; re-run creates nothing; sync hooks tested from both sources
  (segment, sales agent); roles verified empty after the grant sweep; the sales agent docstring and
  the 24 Sep plan carry the supersession note.

### S4 Admin screens

- Scope: section 4.2 admin parts, AC-50 to AC-55; Users list filter and column, user Sign-in
  section, contact User account section, Salesperson accounts view.
- UAC: AC-50 to AC-55, AC-61.
- Done when: each screen reached by sidebar clicks from `/`, every state (loading, empty, error,
  needs attention) seen at 375px and 1280px; Unlink is a deferred action; the view permission is
  swept onto existing roles.

## 11. Risks, out of scope, named triggers

### Risks

- **Space derivation.** Portal rows are owned by `(contact_id, space_id)`; a user session derives
  the space from the contact's workspace. A contact whose tokens were minted in a different space
  would lose sight of rows under the old space. Pre-flight query 5 measures it; if any exist, S2
  resolves the space from the contact's most recent verified token instead, and the plan is
  corrected before S2 starts.
- **WhatsApp template outside the 24h window.** A code to someone who has not messaged Sorento in
  24 hours needs the approved template; a paused or rejected template stops every phone sign-in.
  Mitigation: email + password stays available to anyone with one; S1 logs every send to
  `integration_log` (AC-22) so a template failure is visible in the outbox the same day.
- **Worker down means no codes** (as it already does for the portal). The system health page
  already watches the worker; no new mechanism.
- **A salesperson in the wrong segment gets a user.** The rule reads admin-maintained segments and
  agents; the user has no CRM permission (AC-45), so the cost of a wrong user is a row in the list,
  not access.
- **Phone sign-in for admins.** A WhatsApp code is weaker than a password for `superadmin`
  accounts (SIM swap). Q10 recommends allowing it for everyone; if the owner prefers, admin roles
  are excluded by one check in request-code.
- **Enumeration by timing.** request-code must do the same work for unknown numbers (enqueue
  nothing, but answer after the same lookup); the S1 security review checks it.

### Out of scope (with the trigger that would bring each in)

- **SMS delivery.** Trigger: the first salesperson who must sign in and cannot receive WhatsApp,
  or `integration_log` showing a sustained template failure rate. Then: one SMS provider behind
  the same request-code route, chosen by the user's channel.
- **A separate `identities` / `principals` table.** Trigger: a person who legitimately needs two
  WhatsApp contacts (two numbers) under one user, or a login method that is not a user attribute
  (for example a third-party identity provider with several accounts per person).
- **Hashing session tokens at rest** (`user_sessions.token`, `portal_tokens.token` are plain
  text today). A real gap measured in section 3.2, orthogonal to unification; logged to the backlog
  as its own security lane.
- **Migrating the ~150 existing actor columns** to `*_by_user_id`. #1281's per-module decision.
- **Email sign-in by code (passwordless email).** Trigger: a user with email and no phone who
  cannot keep a password.
- **Self-signup.** The signup route exists but sends no email and is not linked from sign-in;
  nothing in #1280 asks for public self-registration. Left as is.
- **Dealers as tenants** (their own CRM): ADR 0007's flip condition; not this plan.
- **Default project sales permissions for salespeople:** Q8's second half; a data change to the
  `salesperson` role once the owner names them.

## 12. Grill questions for the owner

Each has a recommendation; the UAC is written to the recommendation. Answers get recorded here
verbatim and on #1280, and any AC they change is rewritten before its slice starts.

1. **Who is a "product salesperson" and a "retail salesperson"?** Nothing in the code defines
   them. **Recommend:** a contact in any market segment flagged "Requested by / Salesperson"
   selectable (today `retail` and `project`, reading "product" as "project"), plus any contact
   linked to a sales agent. (AC-40)
2. **Confirm #1280 overrides the 14 Aug 2026 ruling that salespeople get no user account.**
   **Recommend:** yes; S3 records the supersession in `sales_agent.py` and the 24 Sep plan.
3. **Dealer contacts: users up front, or at their first portal sign-in?** **Recommend:** at first
   sign-in (role Portal), never in bulk; most dealer contacts never open the portal. (AC-35)
4. **Does every portal contact become a user when it next signs in (the one session model)?**
   **Recommend:** yes, silently behind the same WhatsApp code; nobody registers. (AC-34, AC-35)
5. **May a user have no email (phone only)?** **Recommend:** yes, with at least one of email or
   phone required; no made-up placeholder emails. (AC-02)
6. **Code channel: WhatsApp only, or SMS too?** **Recommend:** WhatsApp only now (every one of
   these people already talks to Sorento on WhatsApp, and there is no SMS provider); add SMS when
   the trigger in section 11 arrives. (AC-22)
7. **Sign-in screen: one "Email or phone number" field, or two tabs?** **Recommend:** one field;
   the system tells email from phone, one fewer decision. (AC-20)
8. **What can a salesperson user do in the CRM on day one?** **Recommend:** nothing (portal only),
   through a protected Salesperson role that starts empty; when you name the project sales
   permissions every salesperson should have, they go on that role once and reach everyone. Which
   permissions, if any, should it carry from day one? (AC-45)
9. **Where does someone land after signing in?** **Recommend:** CRM home if they hold any CRM
   permission, otherwise their portal home; people with both get a Portal entry in the user menu
   and an Open CRM link on the portal. (AC-28, AC-39)
10. **Phone sign-in for staff and admins too?** **Recommend:** yes for every active user with a
    verified phone, admins included; if you want admins password-only, it is one check. (AC-27)
11. **Old portal sessions: keep forever or phase out?** **Recommend:** keep working until they
    expire, stop extending them from the S2 deploy so they all end within 30 days; old WhatsApp
    links keep working forever as sign-in links. (AC-36)
12. **Admin "view as contact": keep it as is?** **Recommend:** keep it, and fix the audit so its
    actions are recorded as the admin on behalf of the contact. (AC-11)
13. **Lost phone: who fixes it?** **Recommend:** an admin changes the number on the user, which
    signs that user out everywhere; the next sign-in verifies the new number. No self-service
    number change without a code to the new number. (AC-54, section 5.3)
14. **A salesperson contact whose phone already belongs to a staff user: same person?**
    **Recommend:** yes, link to that user and add the Salesperson role, never a second user; a
    phone owned by a user already linked to a different contact is shown to an admin, not
    guessed. (AC-42, AC-43)
15. **How long does a phone or portal sign-in last?** **Recommend:** 30 days, extended while in
    use (what portal users have today). (AC-24)
