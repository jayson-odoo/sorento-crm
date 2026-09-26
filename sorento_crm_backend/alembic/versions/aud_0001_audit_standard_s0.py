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
   `sorento_audit_maintainer` (created here when the migration role may; with no such role,
   only a superuser). The app login is not a member, so it cannot use the flag (review S1).
   The role is left in place on downgrade: roles are cluster-wide and may hold grants. The
   DDL is frozen here (a migration keeps meaning what it meant when it ran);
   `app.models.audit` carries the same text for create_all.

Any later migration that rewrites audit rows (the S-1 password scrub) must run
`SET LOCAL sorento.audit_maintenance = 'on'` first.

Downgrade drops the triggers and the function first, then deletes the EVENT rows (the old
CHECK would reject them), restores the old CHECK and drops the columns.

Revision ID: aud_0001_audit_standard_s0
Revises: identity_0001_s0_model
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op

ENSURE_MAINTAINER_ROLE_SQL = """
DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sorento_audit_maintainer') THEN
        BEGIN
            CREATE ROLE sorento_audit_maintainer NOLOGIN;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'sorento_audit_maintainer not created (needs CREATEROLE): only a superuser can maintain audit_logs';
            WHEN duplicate_object OR unique_violation THEN
                NULL;
        END;
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
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sorento_audit_maintainer') THEN
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
down_revision = "identity_0001_s0_model"
branch_labels = None
depends_on = None

_OLD_ALLOWED = "('CREATE','READ','UPDATE','DELETE','IMPORT')"
_NEW_ALLOWED = "('CREATE','READ','UPDATE','DELETE','IMPORT','EVENT')"

_COLUMNS = (
    ("root_entity_type", sa.String(100)),
    ("root_entity_id", sa.String(100)),
    ("event", sa.String(100)),
    ("source", sa.String(20)),
    ("reason", sa.Text()),
    ("correlation_id", sa.String(64)),
)


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column("audit_logs", sa.Column(name, type_, nullable=True))
    op.create_index("ix_audit_logs_event", "audit_logs", ["event"])
    op.create_index("ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"])
    op.create_index("ix_audit_logs_root_entity", "audit_logs", ["root_entity_type", "root_entity_id"])

    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check")
    op.execute(f"ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check CHECK (action IN {_NEW_ALLOWED})")
    op.execute("ALTER TABLE audit_logs ALTER COLUMN changed_at SET DEFAULT clock_timestamp()")

    op.execute(ENSURE_MAINTAINER_ROLE_SQL)
    op.execute(APPEND_ONLY_FUNCTION_SQL)
    for statement in APPEND_ONLY_TRIGGERS_SQL:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only_row ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only_truncate ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_append_only()")

    op.execute("DELETE FROM audit_logs WHERE action = 'EVENT'")
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check")
    op.execute(f"ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check CHECK (action IN {_OLD_ALLOWED})")
    op.execute("ALTER TABLE audit_logs ALTER COLUMN changed_at SET DEFAULT now()")

    op.drop_index("ix_audit_logs_root_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_correlation_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event", table_name="audit_logs")
    for name, _type in reversed(_COLUMNS):
        op.drop_column("audit_logs", name)
