"""Audit standard S0 (#1281): evolve audit_logs into the one append-only backbone.

Owner ruling 26 Sep 2026 23:45 MYT (decision 2): "the recommended standard should be applied
now, we must do the right thing now" - evolve `audit_logs` in place, no second table
(documentation/plans/audit/PLAN-audit-standard-26sep.md).

1. Nine nullable columns, so every existing row and reader keeps working: `root_entity_type`,
   `root_entity_id`, `event`, `principal_type`, `principal_id`, `on_behalf_of_user_id`,
   `source`, `reason`, `correlation_id`; indexes on `event`, `correlation_id` and the root pair.
   No backfill: history before S0 has none of this to recover (decision 10), and the report
   records the date each gap closed instead.
2. `audit_logs_action_check` gains `EVENT` (a side effect that changed no row: a download, a
   send, a login). The constraint exists only in migrations (271); create_all never built it.
3. `changed_at` defaults to `clock_timestamp()` instead of `now()`: now() is the transaction's
   start, so every row one request wrote shared a timestamp and history order was random.
4. Append-only: UPDATE, DELETE and TRUNCATE raise unless the transaction ran
   `SET LOCAL sorento.audit_maintenance = 'on'`. The DDL is `app.models.audit`'s, the same copy
   `create_all` installs through the table's after_create hook.

Any later migration that rewrites audit rows (the S-1 password scrub) must run
`SET LOCAL sorento.audit_maintenance = 'on'` first.

Downgrade drops the triggers and the function first, then deletes the EVENT rows (the old
CHECK would reject them), restores the old CHECK and drops the columns.

Revision ID: aud_0001_audit_standard_s0
Revises: 527_audit_logs_scrub_secrets
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.audit import APPEND_ONLY_FUNCTION_SQL, APPEND_ONLY_TRIGGERS_SQL

revision = "aud_0001_audit_standard_s0"
down_revision = "527_audit_logs_scrub_secrets"
branch_labels = None
depends_on = None

_OLD_ALLOWED = "('CREATE','READ','UPDATE','DELETE','IMPORT')"
_NEW_ALLOWED = "('CREATE','READ','UPDATE','DELETE','IMPORT','EVENT')"

_COLUMNS = (
    ("root_entity_type", sa.String(100)),
    ("root_entity_id", sa.String(100)),
    ("event", sa.String(100)),
    ("principal_type", sa.String(20)),
    ("principal_id", sa.String(100)),
    ("on_behalf_of_user_id", postgresql.UUID(as_uuid=False)),
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

    op.execute(APPEND_ONLY_FUNCTION_SQL.format(schema=""))
    for statement in APPEND_ONLY_TRIGGERS_SQL:
        op.execute(statement.format(schema=""))


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
