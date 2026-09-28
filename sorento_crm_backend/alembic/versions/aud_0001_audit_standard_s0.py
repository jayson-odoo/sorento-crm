"""Audit standard S0 (#1281): evolve audit_logs into the one append-only backbone.

Owner ruling 26 Sep 2026 23:45 MYT (decision 2): "the recommended standard should be applied
now, we must do the right thing now" - evolve `audit_logs` in place, no second table
(documentation/plans/audit/PLAN-audit-standard-26sep.md).

1. Six nullable columns, so every existing row and reader keeps working: `root_entity_type`,
   `root_entity_id`, `event`, `source`, `reason`, `correlation_id`; indexes on `event`,
   `correlation_id` and the root pair. WHO acted is identity S0's actor columns
   (`identity_0001_s0_model`, plan section 8, the audit actor contract): S0 adds none.
   No backfill: history before S0 has none of this to recover (decision 10), and the report
   records the date each gap closed instead.
2. `audit_logs_action_check` gains `EVENT` (a side effect that changed no row: a download, a
   send, a login). The constraint exists only in migrations (271); create_all never built it.
3. `changed_at` defaults to `clock_timestamp()` instead of `now()`: now() is the transaction's
   start, so every row one request wrote shared a timestamp and history order was random.
4. Append-only: UPDATE, DELETE and TRUNCATE raise unless the transaction ran
   `SET LOCAL sorento.audit_maintenance = 'on'` AS a member of the NOLOGIN role
   `sorento_audit_maintainer` (created here only when the migration runs as a superuser; with
   no such role, only a superuser). A login with CREATEROLE is refused whatever its membership:
   it could grant itself the role, and a CREATEROLE login that created the role is a member
   through PG16's implicit grant (review S1-r2). So an app login cannot use the flag unless a
   superuser grants it the role and it holds no CREATEROLE (review S1).
   The role is left in place on downgrade: roles are cluster-wide and may hold grants. The
   DDL is frozen here (a migration keeps meaning what it meant when it ran);
   `app.models.audit` carries the same text for create_all.

Locks (review S2): the three indexes are built CONCURRENTLY and the widened CHECK is added
NOT VALID, both so every audited business write (an INSERT here) keeps flowing while the
table is scanned; VALIDATE CONSTRAINT and the index builds run in an autocommit block after
the rest commits. So the upgrade is rerun-safe (IF NOT EXISTS, DROP ... IF EXISTS), and an
INVALID index left by an interrupted build is dropped and rebuilt.

Any later migration that rewrites audit rows must run
`SET LOCAL sorento.audit_maintenance = 'on'` first.

Downgrade drops the triggers and the function first, then deletes the EVENT rows (the old
CHECK would reject them), restores the old CHECK and drops the columns.

Revision ID: aud_0001_audit_standard_s0
Revises: fin_0001_billing_documents
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op

ENSURE_MAINTAINER_ROLE_SQL = """
DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sorento_audit_maintainer') THEN
        -- A superuser only: a CREATEROLE login that creates the role is made a member of it
        -- (PG16's implicit ADMIN grant to the creator), which is the app login in a
        -- single-role deployment (review S1-r2, probe P1).
        IF coalesce((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false) THEN
            BEGIN
                CREATE ROLE sorento_audit_maintainer NOLOGIN;
            EXCEPTION
                WHEN duplicate_object OR unique_violation THEN
                    NULL;
            END;
        ELSE
            RAISE NOTICE 'sorento_audit_maintainer not created (a superuser must create it): until then only a superuser can maintain audit_logs';
        END IF;
    END IF;
END
$do$
"""
APPEND_ONLY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION audit_logs_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    maintainer boolean := false;
BEGIN
    IF coalesce(current_setting('sorento.audit_maintenance', true), '') = 'on' THEN
        -- A CREATEROLE login can make itself a member (PG15: it may grant any non-superuser
        -- role; PG16: it holds ADMIN on a role it created), so its membership proves nothing
        -- (review S1-r2). session_user too: SET ROLE to the maintainer role would hide it.
        IF EXISTS (
            SELECT 1 FROM pg_roles
            WHERE rolname IN (current_user, session_user) AND rolcreaterole AND NOT rolsuper
        ) THEN
            maintainer := false;
        ELSIF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sorento_audit_maintainer') THEN
            maintainer := pg_has_role(current_user, 'sorento_audit_maintainer', 'MEMBER');
        ELSE
            maintainer := coalesce((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false);
        END IF;
    END IF;
    IF maintainer THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        IF TG_OP = 'UPDATE' THEN RETURN NEW; END IF;
        RETURN NULL;
    END IF;
    RAISE EXCEPTION 'audit_logs is append-only (% refused)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END
$$
"""
APPEND_ONLY_TRIGGERS_SQL = (
    "CREATE TRIGGER audit_logs_append_only_row BEFORE UPDATE OR DELETE ON audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only()",
    "CREATE TRIGGER audit_logs_append_only_truncate BEFORE TRUNCATE ON audit_logs "
    "FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_append_only()",
)

revision = "aud_0001_audit_standard_s0"
down_revision = "fin_0001_billing_documents"
branch_labels = None
depends_on = None

_OLD_ALLOWED = "('CREATE','READ','UPDATE','DELETE','IMPORT')"
_NEW_ALLOWED = "('CREATE','READ','UPDATE','DELETE','IMPORT','EVENT')"

_COLUMNS = (
    ("root_entity_type", "VARCHAR(100)"),
    ("root_entity_id", "VARCHAR(100)"),
    ("event", "VARCHAR(100)"),
    ("source", "VARCHAR(20)"),
    ("reason", "TEXT"),
    ("correlation_id", "VARCHAR(64)"),
)

# CREATE INDEX CONCURRENTLY: a plain build takes a SHARE lock, which blocks the INSERT every
# audited business write makes for as long as the build scans audit_logs (review S2).
_INDEXES = (
    ("ix_audit_logs_event", "CREATE INDEX {c} IF NOT EXISTS ix_audit_logs_event ON audit_logs (event)"),
    (
        "ix_audit_logs_correlation_id",
        "CREATE INDEX {c} IF NOT EXISTS ix_audit_logs_correlation_id ON audit_logs (correlation_id)",
    ),
    (
        "ix_audit_logs_root_entity",
        "CREATE INDEX {c} IF NOT EXISTS ix_audit_logs_root_entity ON audit_logs (root_entity_type, root_entity_id)",
    ),
)


def _index_valid(bind, name: str):
    """pg_index.indisvalid for ``name`` (True / False), or None when there is no such index."""
    return bind.execute(
        sa.text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)"),
        {"name": name},
    ).scalar()


def _ensure_index(bind, name: str, statement: str, *, concurrently: bool) -> None:
    """Build ``name``, never leaving an INVALID one behind (identity_0001_s0_model's pattern).

    An interrupted or failed CREATE INDEX CONCURRENTLY leaves an INVALID index, which
    `IF NOT EXISTS` would then keep forever. So: drop an INVALID one before building, check
    again after, rebuild once, and stop naming the index if it is still INVALID.
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
            raise RuntimeError(f"aud_0001_audit_standard_s0: index {name} is still INVALID after a rebuild; drop it and rerun.")


def _upgrade(concurrently: bool) -> None:
    """Rerun-safe: the autocommit block below commits the first half on its own, so a rerun
    after a failed index build must find every earlier step already done and move on."""
    bind = op.get_bind()
    for name, ddl in _COLUMNS:
        bind.execute(sa.text(f"ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS {name} {ddl}"))

    # NOT VALID: the ADD takes ACCESS EXCLUSIVE only for the catalogue change, not for a scan
    # of every row; VALIDATE (SHARE UPDATE EXCLUSIVE, writes carry on) runs after this
    # transaction commits, or the ADD's lock would still be held through the scan.
    bind.execute(sa.text("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check"))
    bind.execute(
        sa.text(f"ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check CHECK (action IN {_NEW_ALLOWED}) NOT VALID")
    )
    bind.execute(sa.text("ALTER TABLE audit_logs ALTER COLUMN changed_at SET DEFAULT clock_timestamp()"))

    bind.execute(sa.text(ENSURE_MAINTAINER_ROLE_SQL))
    bind.execute(sa.text(APPEND_ONLY_FUNCTION_SQL))
    bind.execute(sa.text("DROP TRIGGER IF EXISTS audit_logs_append_only_row ON audit_logs"))
    bind.execute(sa.text("DROP TRIGGER IF EXISTS audit_logs_append_only_truncate ON audit_logs"))
    for statement in APPEND_ONLY_TRIGGERS_SQL:
        bind.execute(sa.text(statement))

    def _finish(b, concurrent: bool) -> None:
        b.execute(sa.text("ALTER TABLE audit_logs VALIDATE CONSTRAINT audit_logs_action_check"))
        for name, statement in _INDEXES:
            _ensure_index(b, name, statement, concurrently=concurrent)

    if concurrently:
        with op.get_context().autocommit_block():
            _finish(op.get_bind(), True)
    else:
        _finish(bind, False)


def upgrade() -> None:
    _upgrade(concurrently=True)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only_row ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only_truncate ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_append_only()")

    op.execute("DELETE FROM audit_logs WHERE action = 'EVENT'")
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check")
    op.execute(f"ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check CHECK (action IN {_OLD_ALLOWED})")
    op.execute("ALTER TABLE audit_logs ALTER COLUMN changed_at SET DEFAULT now()")

    for name, _statement in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for name, _ddl in reversed(_COLUMNS):
        op.drop_column("audit_logs", name)
