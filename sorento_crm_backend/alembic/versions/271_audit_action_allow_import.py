"""audit_logs: allow 'IMPORT' action in the check constraint

The coarse per-job import audit (log_import_audit) writes action='IMPORT', but
audit_logs_action_check only permitted CREATE/READ/UPDATE/DELETE — so EVERY
import-audit insert was rejected and silently swallowed by the best-effort
wrapper (`_write_import_audit`). Result: zero import audit rows ever. Widen the
constraint to include IMPORT.

Revision ID: 271_audit_action_allow_import
Revises: 270_health_notify_user_ids
"""
from alembic import op


revision = "271_audit_action_allow_import"
down_revision = "270_health_notify_user_ids"
branch_labels = None
depends_on = None

_ALLOWED = "('CREATE','READ','UPDATE','DELETE','IMPORT')"


def upgrade() -> None:
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check")
    op.execute(
        f"ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check "
        f"CHECK (action IN {_ALLOWED})"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check")
    op.execute(
        "ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check "
        "CHECK (action IN ('CREATE','READ','UPDATE','DELETE'))"
    )
