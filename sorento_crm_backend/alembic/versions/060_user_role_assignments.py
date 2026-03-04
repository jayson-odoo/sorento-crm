"""Create user_role_assignments table for multi-role per user.

Revision ID: 060_user_role_assignments
Revises: 059_user_quick_access
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa


revision = "060_user_role_assignments"
down_revision = "059_user_quick_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_role_assignments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.String(), sa.ForeignKey("user_roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_role_assignments_user_id", "user_role_assignments", ["user_id"])
    op.create_index("ix_user_role_assignments_role_id", "user_role_assignments", ["role_id"])
    op.create_unique_constraint(
        "uq_user_role_assignments_user_id_role_id",
        "user_role_assignments",
        ["user_id", "role_id"],
    )

    # Backfill: one row per user from current users.role_id
    op.execute(
        sa.text(
            """
            INSERT INTO user_role_assignments (id, user_id, role_id, assigned_at)
            SELECT
                gen_random_uuid()::text,
                u.id,
                u.role_id,
                COALESCE(u.created_at, now())
            FROM users u
            WHERE u.role_id IS NOT NULL
            ON CONFLICT (user_id, role_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_role_assignments_user_id_role_id", "user_role_assignments", type_="unique")
    op.drop_index("ix_user_role_assignments_role_id", table_name="user_role_assignments")
    op.drop_index("ix_user_role_assignments_user_id", table_name="user_role_assignments")
    op.drop_table("user_role_assignments")
