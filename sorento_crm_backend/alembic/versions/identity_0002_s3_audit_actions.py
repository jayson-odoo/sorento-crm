"""Identity S3 (#1280): audit_logs allow 'link_contact' / 'unlink_contact'.

Contract: documentation/plans/identity/s3-contract.md sections 1.2, 1.3, 1.4.
The owner's create-from-contact, PUT link/unlink, and the `user.unlink_contact`
deferred action each write one named record-action row (never a generic
UPDATE, so the audit trail names the WhatsApp contact directly) - widen the
same constraint migration 271 already widened once for IMPORT.

Revision ID: identity_0002_s3_audit_actions
Revises: identity_0001_s0_model
"""
from alembic import op

revision = "identity_0002_s3_audit_actions"
down_revision = "identity_0001_s0_model"
branch_labels = None
depends_on = None

_ALLOWED = "('CREATE','READ','UPDATE','DELETE','IMPORT','link_contact','unlink_contact')"
_PREVIOUS = "('CREATE','READ','UPDATE','DELETE','IMPORT')"


def upgrade() -> None:
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check")
    op.execute(
        f"ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check "
        f"CHECK (action IN {_ALLOWED})"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check")
    op.execute(
        f"ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_action_check "
        f"CHECK (action IN {_PREVIOUS})"
    )
