# S0 contract: identity model, migration, audit actor fields (#1280)

Plan: `PLAN-unified-identity-26sep.md` sections 4.1, 8, 9.1, 9.2 (S0 row), 10 (S0).
UAC: `identity-unified-login-acceptance-criteria.md` AC-01 to AC-14, AC-60, AC-62.
This file is the Phase 1 contract the tester writes against and the coder builds to. Paths are
relative to `sorento_crm_backend/` (BE) and `sorento_crm_frontend/` (FE).

## 1. Schema (one migration, `identity_0001_s0_model`, expand only)

Revision id `identity_0001_s0_model` (<= 32 chars), `down_revision` = current main head
(`sales_0002_team_leader` at the time of writing; re-parent with `scripts/alembic-reparent.sh`).

Pre-check, before any DDL: if a case-duplicate email (plan 9.1 Q1) or a contact claimed by more
than one user (Q2) exists, raise `RuntimeError` naming the users (names, never ids). Nothing runs.

`users`
- `email` DROP NOT NULL.
- `ck_users_email_or_phone` CHECK (`email IS NOT NULL OR contact_number IS NOT NULL`).
- `uq_users_email_lower` UNIQUE INDEX on `lower(email)`, created CONCURRENTLY, beside the existing
  unique constraint (the old one is dropped by the later contract release, not here).
- `uq_users_respond_contact_id` UNIQUE INDEX on `respond_contact_id` WHERE
  `respond_contact_id IS NOT NULL`, created CONCURRENTLY. The old plain `ix_users_respond_contact_id`
  stays (contract release drops it).
- `phone_verified_at` TIMESTAMP (naive UTC), nullable.

`user_sessions`
- `auth_method` VARCHAR(20), nullable, `server_default 'password'` (metadata-only on PG 11+, so
  every existing row reads `password` and a session the OLD image mints during the blue/green swap
  is also correctly `password`). CHECK `ck_user_sessions_auth_method` IN
  (`password`, `phone_otp`, `portal_link`, `impersonation`).

`audit_logs` (all nullable)
- `actor_type` VARCHAR(20), `server_default 'legacy'` (existing rows and rows the old image writes
  during the swap read `legacy`; new code always writes an explicit value).
- `real_user_id` UUID, `auth_method` VARCHAR(20), `session_id` UUID, `integration_id` UUID,
  `job_id` VARCHAR(128), `user_agent` VARCHAR(512).
- index `ix_audit_logs_real_user_id` (CONCURRENTLY).

`user_roles`: seed `salesperson` (name "Salesperson") and `portal_user` (name "Portal"),
`is_protected = true`, `is_default = false`, no `user_role_permissions` rows. Idempotent
(`ON CONFLICT (slug) DO NOTHING`). Also seeded by `app.services.reference_seed.run` so a
`bootstrap_env` database (CI) and app startup have them.

Link backfill (AC-04): for every user with `respond_contact_id IS NULL`, `contact_number` set,
`is_trashed = false`, `is_integration = false`, whose `contact_number` equals exactly ONE
`respond_contacts.phone_number`, and that contact is not already any user's `respond_contact_id`:
set the link. Per link, insert one `audit_logs` row: `entity_type 'users'`, `entity_id` = user id,
`action 'UPDATE'`, `old_values {"respond_contact_id": null}`, `new_values {"respond_contact_id":
<contact id>}`, `actor_type 'system'`, `description 'migration identity_0001_s0_model: link
backfill'`. Creates no user, touches no role. Re-running changes nothing.

Downgrade: drops everything added (indexes, check constraints, columns, the two roles if they have
no assignments), restores `users.email` NOT NULL only if no NULL email exists (else raise).

CONCURRENTLY cannot run inside the migration's transaction: `upgrade()` wraps the index
creation in `op.get_context().autocommit_block()`. The module exposes `_upgrade(concurrently:
bool)` / `_downgrade()` so the migration test (which runs inside a rolled-back transaction) calls
`_upgrade(concurrently=False)`; `upgrade()` is `_upgrade(concurrently=True)`.

Models mirror all of it (CI builds its schema from the models through `bootstrap_env`):
`User.email` nullable, the check constraint and both unique indexes in `__table_args__`
(`Index(..., unique=True, postgresql_where=...)`, `Index("uq_users_email_lower", func.lower(...),
unique=True)`), `phone_verified_at`; `UserSession.auth_method`; the `AuditLog` columns.

## 2. Writes (AC-01, AC-03)

- Every write of `users.email` stores `email.strip().lower()`; empty string stores NULL
  (`UserService.create_user`, `invite_user`, `update_user`, `auth.signup`, any other writer).
- A create or update whose lowercased email equals another user's lowercased email answers
  **409** (AppException) with `code "EMAIL_TAKEN"` and message "Email already belongs to <name>".
- Login (`POST /api/v1/auth/login`) and forgot-password find the user by `lower(email) =
  lower(payload.email)`.
- Setting `respond_contact_id` (create or `PUT /api/v1/user-management/users/{id}`) to a contact
  another user already holds answers **409** with `code "CONTACT_ALREADY_LINKED"` and message
  "WhatsApp contact already linked to <other user's name>" (name, falling back to email, never
  an id). The unique index is the backstop.
- `respond_link_service.resolve_user_respond_contact` never caches a phone match onto a contact
  another user already holds (returns the contact, skips the cache write).

## 3. Sessions (AC-07)

`user_session_service.mint_session(..., auth_method: str = "password")`, validated against the
four values (ValueError otherwise). `/auth/login` passes `password`. `resolve_session` is
unchanged. The session row's `auth_method` is what `get_current_user` stamps on the audit actor.

## 4. Audit actor (AC-08 to AC-12, AC-14)

`app/audit_context.py` gains one dataclass and one carrier, beside the existing API (which keeps
working):

```python
@dataclass
class AuditActor:
    actor_type: str            # user | contact | integration | worker | scheduler | public_link | system
    user_id: str | None = None         # effective actor
    real_user_id: str | None = None    # at the keyboard; equals user_id unless impersonating
    auth_method: str | None = None     # password | phone_otp | portal_link | portal_token | api_key | impersonation
    session_id: str | None = None
    integration_id: str | None = None
    contact_id: str | None = None
    job_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None      # truncated to 512
    tool_name: str | None = None       # MCP X-Tool-Name, written into description when the row has none

def stamp_actor(actor: AuditActor, *, db=None, request=None) -> None
def get_actor(db=None) -> AuditActor | None   # db.info["audit_actor"] wins over the contextvar
```

`stamp_actor` sets the contextvar AND `db.info["audit_actor"]` (the carrier that survives FastAPI
running a sync dependency in another threadpool thread, the AC-12 gap) AND
`request.state.audit_actor` (read by the API call log middleware). The flush listener
(`audit_service._session_before_flush`) and `log_audit` read `get_actor(session)`; when nothing
was stamped the row is `actor_type 'system'`.

Who stamps what (plan 8.1 table):

| Caller | Stamp |
| --- | --- |
| `LoggingMiddleware`, per request, before anything else | default `public_link` for paths under `/api/v1/public/`, else `system`; with ip, user agent |
| `get_current_user`, `get_current_user_optional`, `get_real_user`, the Bearer branch of `get_current_user_or_api_key` | `user`, user_id = real_user_id = the session's user, `auth_method` = the session row's, `session_id`, `contact_id` = the user's `respond_contact_id` |
| `_maybe_apply_impersonation` (admin impersonating a user) | `user`, user_id = target, real_user_id = admin, `auth_method 'impersonation'`, session_id = the admin's session |
| `get_external_api_user`, the API-key branch of `get_current_user_or_api_key` | `integration`, user_id = real_user_id = act-as user, `auth_method 'api_key'`, `integration_id`, `tool_name` from `X-Tool-Name` |
| `get_portal_token`, token of a contact with no user | `contact`, contact_id, `auth_method 'portal_token'`, no user |
| `get_portal_token`, token of a contact that has a user | `user`, user_id = real_user_id = that user, `auth_method 'portal_token'`, contact_id |
| `get_portal_token`, `is_impersonation` token (admin "view as contact") | `user`, user_id = the contact's user or NULL, real_user_id = the admin (from `contact_impersonation_sessions.portal_token_id`), `auth_method 'impersonation'`, contact_id (AC-11) |
| RQ job (worker `perform_job` and the in-process `run_sync_rq_jobs` drain) | `worker`, user_id / real_user_id from the job meta written by `enqueue_job`, `job_id` = RQ job id |
| scheduler tick (`scheduler_session`, and per task in `run_due_tasks`) | `scheduler`, `job_id` = the tick / task name |

`get_current_user_or_api_key` becomes `async def` (matching `get_current_user`), so its stamp is
visible in the contextvar too, not only through `db.info`.

`enqueue_job` writes `job.meta["actor"] = {"user_id", "real_user_id", "trace_id"}` from the
current actor. `_swap_actor_fields_during_impersonation` is removed: `real_user_id` says who was at
the keyboard, `*_by` columns keep the effective user (plan 8.2).

`api_call_log.actor` is filled as `user:<user_id>` or `integration:<integration_id>` from
`request.state.audit_actor`.

## 5. Audit read API (AC-13)

`GET /api/v1/audit/logs/` rows (`AuditLogResponse`) gain: `actor_type`, `auth_method`,
`real_user_id`, `integration_id`, `job_id`, and `actor_label` (words, never an id):

| Row | `actor_label` |
| --- | --- |
| `user`, not impersonating | "<user name> (<method word>)", e.g. "Aisyah (phone)"; no method: "<user name>" |
| `user`, real != effective | "<real user name> on behalf of <effective user or contact name>" |
| `integration` | "Integration: <integration name> as <act-as user name>" |
| `worker` | "Background job for <user name>", or "Background job" with no user |
| `scheduler` | "Scheduled: <job_id>" |
| `contact` | "Portal: <contact name> (no user)" |
| `public_link` | "Public link" |
| `system` | "System" |
| `legacy` / NULL | today's `user_display_name` (contact name, else user name, else "System") |

Method words: password "email", phone_otp "phone", portal_link "portal", portal_token "portal",
api_key "API key", impersonation "impersonation".

FE (`types/audit.types.ts`, `app/(protected)/system-management/audit-logs/types/auditLog.types.ts`)
mirror the fields. `components/audit/AuditTrail.tsx` renders "by <actor_label>" (fallback
`user_display_name`, then "System"; never `user_id`). `AuditLogsList.tsx` Actor column renders
`actor_label` (same fallback), and the detail drawer adds "Actor kind" and "Sign-in method" rows:

- kind: user "Staff", contact "Portal contact", integration "Integration", worker "Background
  job", scheduler "Scheduled", public_link "Public link", system "System"; legacy / NULL: row hidden.
- method: password "Email and password", phone_otp "Phone code", portal_link "Portal link",
  portal_token "Portal token", api_key "API key", impersonation "Impersonation"; NULL: "-".

## 6. Null-email guards (plan 4.1, 9.1 Q6)

Every reader of `users.email` that would raise or mis-send on NULL gets a guard: skip the email
channel (never raise), `or ""` for display, `Optional[str]` for response schemas. Each guarded
path has a test. The reader list is in the PR body.
