"""Identity S0 (#1280): one principal per person, audit actor columns. Expand only.

Contract: documentation/plans/identity/s0-contract.md section 1.

Pre-check, before any DDL: a case-duplicate email or a WhatsApp contact claimed by more
than one user raises RuntimeError naming the users (names, never ids). Nothing runs.

`users`
- `email` DROP NOT NULL; `ck_users_email_or_phone` (email or phone, at least one).
- `uq_users_email_lower` unique on lower(email), beside the existing unique index (the
  contract release drops the old one).
- `uq_users_respond_contact_id` unique on respond_contact_id WHERE NOT NULL. The old plain
  `ix_users_respond_contact_id` stays until the contract release.
- `phone_verified_at` naive UTC timestamp.

`user_sessions.auth_method` VARCHAR(20), server default 'password', checked against
password | phone_otp | portal_link | impersonation.

`audit_logs`: actor_type (server default 'legacy'), real_user_id, auth_method, session_id,
integration_id, job_id, user_agent; index `ix_audit_logs_real_user_id`.

Roles `salesperson` and `portal_user`: protected, not default, no permissions.

Link backfill (AC-04): an unlinked, untrashed, non-integration user whose contact_number
equals exactly one contact's phone_number, where no user holds that contact yet, gets
linked, with one `system` audit row per link. Re-running changes nothing.

The three indexes build CONCURRENTLY in `upgrade()`, which cannot run inside the
migration's transaction, so they sit in an autocommit block. `_upgrade(concurrently=False)`
is the same logic inside one transaction, which is what the migration test runs.

Revision ID: identity_0001_s0_model
Revises: sales_0002_team_leader
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op

revision = "identity_0001_s0_model"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None

_BACKFILL_DESCRIPTION = "migration identity_0001_s0_model: link backfill"

_NEW_ROLES = (
    ("salesperson", "Salesperson", "Sales agent signing in by phone."),
    ("portal_user", "Portal", "Portal access only."),
)

_AUDIT_COLUMNS = (
    ("actor_type", "VARCHAR(20) DEFAULT 'legacy'"),
    ("real_user_id", "UUID"),
    ("auth_method", "VARCHAR(20)"),
    ("session_id", "UUID"),
    ("integration_id", "UUID"),
    ("job_id", "VARCHAR(128)"),
    ("user_agent", "VARCHAR(512)"),
)

_INDEXES = (
    ("uq_users_email_lower", "CREATE UNIQUE INDEX {c} IF NOT EXISTS uq_users_email_lower ON users (lower(email))"),
    (
        "uq_users_respond_contact_id",
        "CREATE UNIQUE INDEX {c} IF NOT EXISTS uq_users_respond_contact_id ON users (respond_contact_id) "
        "WHERE respond_contact_id IS NOT NULL",
    ),
    ("ix_audit_logs_real_user_id", "CREATE INDEX {c} IF NOT EXISTS ix_audit_logs_real_user_id ON audit_logs (real_user_id)"),
)


def _constraint_exists(bind, table: str, name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_constraint WHERE conname = :name "
                "AND conrelid = to_regclass(:table)"
            ),
            {"name": name, "table": table},
        ).scalar()
    )


def _index_valid(bind, name: str):
    """pg_index.indisvalid for ``name`` (True / False), or None when there is no such index."""
    return bind.execute(
        sa.text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)"),
        {"name": name},
    ).scalar()


def _ensure_index(bind, name: str, statement: str, *, concurrently: bool) -> None:
    """Build ``name``, never leaving an INVALID one behind.

    An interrupted or failed CREATE INDEX CONCURRENTLY leaves an INVALID index, which
    enforces nothing and which `IF NOT EXISTS` would then keep forever. So: drop an
    INVALID one before building, check again after, rebuild once, and stop naming the
    index if it is still INVALID.
    """
    c = "CONCURRENTLY" if concurrently else ""
    drop = f"DROP INDEX {c} IF EXISTS {name}"
    create = statement.format(c=c)
    if _index_valid(bind, name) is False:
        bind.execute(sa.text(drop))
    bind.execute(sa.text(create))
    if _index_valid(bind, name) is False:
        bind.execute(sa.text(drop))
        bind.execute(sa.text(create))
        if _index_valid(bind, name) is False:
            raise RuntimeError(
                f"identity_0001_s0_model: index {name} is still INVALID after a rebuild. "
                "Check for duplicate values it would reject, drop it, and rerun."
            )


def _preflight(bind) -> None:
    """Plan 9.1 Q1 and Q2: stop before any DDL, naming the people, never an id."""
    problems = []
    dup_emails = bind.execute(
        sa.text(
            "SELECT string_agg(coalesce(nullif(trim(u.name), ''), u.email), ', ' ORDER BY u.created_at) "
            "FROM users u WHERE u.email IS NOT NULL "
            "GROUP BY lower(u.email) HAVING count(*) > 1 ORDER BY 1"
        )
    ).scalars().all()
    for names in dup_emails:
        problems.append(f"same email in a different case: {names}")
    shared_contacts = bind.execute(
        sa.text(
            "SELECT coalesce(nullif(trim(rc.name), ''), rc.phone_number, 'unnamed contact'), "
            "string_agg(coalesce(nullif(trim(u.name), ''), u.email), ', ' ORDER BY u.created_at) "
            "FROM users u LEFT JOIN respond_contacts rc ON rc.id = u.respond_contact_id "
            "WHERE u.respond_contact_id IS NOT NULL "
            "GROUP BY u.respond_contact_id, rc.name, rc.phone_number HAVING count(*) > 1 ORDER BY 1"
        )
    ).all()
    for contact, names in shared_contacts:
        problems.append(f"WhatsApp contact {contact} linked to more than one user: {names}")
    if problems:
        raise RuntimeError(
            "identity_0001_s0_model stopped before any change. Resolve these with the owner first: "
            + "; ".join(problems)
        )


def _seed_roles(bind) -> None:
    for slug, name, description in _NEW_ROLES:
        bind.execute(
            sa.text(
                "INSERT INTO user_roles (id, slug, name, description, is_trashed, is_protected, is_default, created_at) "
                "VALUES (gen_random_uuid()::text, :slug, :name, :description, false, true, false, now()) "
                "ON CONFLICT (slug) DO NOTHING"
            ),
            {"slug": slug, "name": name, "description": description},
        )


def _backfill_links(bind) -> None:
    """AC-04. One statement: pick, link, audit. Only rows still unlinked are touched."""
    bind.execute(
        sa.text(
            """
            WITH candidates AS (
                SELECT u.id AS user_id, u.contact_number
                FROM users u
                WHERE u.respond_contact_id IS NULL
                  AND u.contact_number IS NOT NULL
                  AND u.contact_number <> ''
                  AND u.is_trashed = false
                  AND coalesce(u.is_integration, false) = false
            ),
            matches AS (
                SELECT c.user_id, rc.id AS contact_id,
                       count(*) OVER (PARTITION BY c.user_id) AS contacts_for_phone
                FROM candidates c
                JOIN respond_contacts rc ON rc.phone_number = c.contact_number
            ),
            picks AS (
                SELECT m.user_id, m.contact_id
                FROM matches m
                WHERE m.contacts_for_phone = 1
                  AND NOT EXISTS (SELECT 1 FROM users o WHERE o.respond_contact_id = m.contact_id)
            ),
            linked AS (
                UPDATE users u
                SET respond_contact_id = p.contact_id
                FROM picks p
                WHERE u.id = p.user_id AND u.respond_contact_id IS NULL
                RETURNING u.id, u.respond_contact_id
            )
            INSERT INTO audit_logs (id, entity_type, entity_id, action, old_values, new_values, actor_type, description)
            SELECT gen_random_uuid(), 'users', linked.id, 'UPDATE',
                   jsonb_build_object('respond_contact_id', NULL),
                   jsonb_build_object('respond_contact_id', linked.respond_contact_id),
                   'system', :description
            FROM linked
            """
        ),
        {"description": _BACKFILL_DESCRIPTION},
    )


def _upgrade(concurrently: bool) -> None:
    bind = op.get_bind()
    _preflight(bind)

    bind.execute(sa.text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL"))
    if not _constraint_exists(bind, "users", "ck_users_email_or_phone"):
        bind.execute(
            sa.text(
                "ALTER TABLE users ADD CONSTRAINT ck_users_email_or_phone "
                "CHECK (email IS NOT NULL OR contact_number IS NOT NULL)"
            )
        )
    bind.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP WITHOUT TIME ZONE"))

    # A constant default is metadata-only on PG 11+, so no table rewrite.
    bind.execute(
        sa.text("ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS auth_method VARCHAR(20) DEFAULT 'password'")
    )
    if not _constraint_exists(bind, "user_sessions", "ck_user_sessions_auth_method"):
        bind.execute(
            sa.text(
                "ALTER TABLE user_sessions ADD CONSTRAINT ck_user_sessions_auth_method "
                "CHECK (auth_method IN ('password', 'phone_otp', 'portal_link', 'impersonation'))"
            )
        )

    for column, ddl in _AUDIT_COLUMNS:
        bind.execute(sa.text(f"ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS {column} {ddl}"))

    _seed_roles(bind)
    _backfill_links(bind)

    if concurrently:
        with op.get_context().autocommit_block():
            for name, statement in _INDEXES:
                _ensure_index(op.get_bind(), name, statement, concurrently=True)
    else:
        for name, statement in _INDEXES:
            _ensure_index(bind, name, statement, concurrently=False)


def _downgrade() -> None:
    bind = op.get_bind()
    # Checked first, so a refusal leaves everything in place.
    phone_only = bind.execute(
        sa.text(
            "SELECT string_agg(coalesce(nullif(trim(name), ''), contact_number), ', ') "
            "FROM users WHERE email IS NULL"
        )
    ).scalar()
    if phone_only:
        raise RuntimeError(
            "identity_0001_s0_model downgrade stopped: these users have no email, so "
            f"users.email cannot be NOT NULL again: {phone_only}"
        )
    for name, _statement in _INDEXES:
        bind.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
    bind.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_email_or_phone"))
    bind.execute(sa.text("ALTER TABLE user_sessions DROP CONSTRAINT IF EXISTS ck_user_sessions_auth_method"))
    bind.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS phone_verified_at"))
    bind.execute(sa.text("ALTER TABLE user_sessions DROP COLUMN IF EXISTS auth_method"))
    for column, _ddl in _AUDIT_COLUMNS:
        bind.execute(sa.text(f"ALTER TABLE audit_logs DROP COLUMN IF EXISTS {column}"))
    for slug, _name, _description in _NEW_ROLES:
        bind.execute(
            sa.text(
                "DELETE FROM user_roles r WHERE r.slug = :slug "
                "AND NOT EXISTS (SELECT 1 FROM user_role_assignments a WHERE a.role_id = r.id) "
                "AND NOT EXISTS (SELECT 1 FROM user_role_permissions p WHERE p.role_id = r.id)"
            ),
            {"slug": slug},
        )
    bind.execute(sa.text("ALTER TABLE users ALTER COLUMN email SET NOT NULL"))


def upgrade() -> None:
    _upgrade(concurrently=True)


def downgrade() -> None:
    _downgrade()
