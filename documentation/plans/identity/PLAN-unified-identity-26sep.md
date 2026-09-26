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
