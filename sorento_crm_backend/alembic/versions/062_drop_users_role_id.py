"""Drop users.role_id; use user_role_assignments only.

Revision ID: 062_drop_users_role_id
Revises: 061_seed_rbac_permissions
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa


revision = "062_drop_users_role_id"
down_revision = "061_seed_rbac_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("users_role_id_idx", table_name="users")
    op.drop_constraint("users_role_id_fkey", "users", type_="foreignkey")
    op.drop_column("users", "role_id")


def downgrade() -> None:
    op.add_column("users", sa.Column("role_id", sa.String(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE users u
            SET role_id = (
                SELECT ura.role_id
                FROM user_role_assignments ura
                WHERE ura.user_id = u.id
                ORDER BY ura.assigned_at
                LIMIT 1
            )
            """
        )
    )
    op.alter_column("users", "role_id", nullable=False)
    op.create_foreign_key("users_role_id_fkey", "users", "user_roles", ["role_id"], ["id"])
    op.create_index("users_role_id_idx", "users", ["role_id"])
