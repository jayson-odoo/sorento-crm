"""Complaint root cause + resolution master data + FKs on complaints.

Adds ``complaint_root_causes`` and ``complaint_resolutions`` master tables.
Adds ``root_cause_id``, ``resolution_id``, ``root_cause_notified_at``,
``resolution_notified_at`` columns to ``complaints``. Syncs RBAC permissions
for the two new master-data resources.

Revision ID: 175_complaint_root_cause_resolution
Revises: 174_email_templates_and_automation
Create Date: 2026-05-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "175_complaint_root_cause_resolution"
down_revision = "174_email_templates_and_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "complaint_root_causes",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint("name", name="uq_complaint_root_causes_name"),
    )
    op.create_index(
        "ix_complaint_root_causes_is_active",
        "complaint_root_causes",
        ["is_active"],
    )

    op.create_table(
        "complaint_resolutions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint("name", name="uq_complaint_resolutions_name"),
    )
    op.create_index(
        "ix_complaint_resolutions_is_active",
        "complaint_resolutions",
        ["is_active"],
    )

    op.add_column(
        "complaints",
        sa.Column("root_cause_id", UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("resolution_id", UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("root_cause_notified_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("resolution_notified_at", sa.DateTime(timezone=False), nullable=True),
    )

    op.create_foreign_key(
        "fk_complaints_root_cause_id",
        "complaints",
        "complaint_root_causes",
        ["root_cause_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_complaints_resolution_id",
        "complaints",
        "complaint_resolutions",
        ["resolution_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_complaints_root_cause_id", "complaints", ["root_cause_id"])
    op.create_index("ix_complaints_resolution_id", "complaints", ["resolution_id"])

    from sqlalchemy.orm import Session

    from app.rbac.permission_registry import sync_permissions

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        sync_permissions(session)
    finally:
        session.close()


def downgrade() -> None:
    op.drop_index("ix_complaints_resolution_id", table_name="complaints")
    op.drop_index("ix_complaints_root_cause_id", table_name="complaints")
    op.drop_constraint("fk_complaints_resolution_id", "complaints", type_="foreignkey")
    op.drop_constraint("fk_complaints_root_cause_id", "complaints", type_="foreignkey")
    op.drop_column("complaints", "resolution_notified_at")
    op.drop_column("complaints", "root_cause_notified_at")
    op.drop_column("complaints", "resolution_id")
    op.drop_column("complaints", "root_cause_id")

    op.drop_index("ix_complaint_resolutions_is_active", table_name="complaint_resolutions")
    op.drop_table("complaint_resolutions")
    op.drop_index("ix_complaint_root_causes_is_active", table_name="complaint_root_causes")
    op.drop_table("complaint_root_causes")
