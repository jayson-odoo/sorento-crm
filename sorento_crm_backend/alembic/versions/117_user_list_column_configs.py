"""Create user_list_column_configs for per-user listing column preferences.

Revision ID: 117_user_list_column_configs
Revises: 116_work_calendar_working_hours
"""

from alembic import op
import sqlalchemy as sa


revision = "117_user_list_column_configs"
down_revision = "116_work_calendar_working_hours"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_list_column_configs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("listing_key", sa.String(length=255), nullable=False),
        sa.Column("config", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_user_list_column_configs_user_id", "user_list_column_configs", ["user_id"])
    op.create_unique_constraint(
        "uq_user_list_column_configs_user_id_listing_key",
        "user_list_column_configs",
        ["user_id", "listing_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_list_column_configs_user_id_listing_key", "user_list_column_configs", type_="unique")
    op.drop_index("ix_user_list_column_configs_user_id", table_name="user_list_column_configs")
    op.drop_table("user_list_column_configs")

