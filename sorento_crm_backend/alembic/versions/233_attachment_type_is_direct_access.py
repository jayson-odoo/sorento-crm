"""AttachmentType.is_direct_access - flag types whose files are dealer-downloadable.

crm_resource_attachments_list is pinned to these (direct_access_only). Backfills
the existing "Direct Access" type (created in prod) to true.
"""
from alembic import op
import sqlalchemy as sa


revision = "233_attachment_type_is_direct_access"
down_revision = "232_form_sla_notify_assignee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachment_types",
        sa.Column(
            "is_direct_access",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Flag the pre-existing "Direct Access" type (idempotent, case-insensitive).
    op.execute(
        "UPDATE attachment_types SET is_direct_access = true "
        "WHERE lower(type_name) = 'direct access'"
    )


def downgrade() -> None:
    op.drop_column("attachment_types", "is_direct_access")
