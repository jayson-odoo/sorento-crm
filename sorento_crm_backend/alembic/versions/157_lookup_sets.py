"""Lookup sets, options, option keywords, bindings.

Revision ID: 157_lookup_sets
Revises: 156_respond_contacts_session_vars
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from app.rbac.permission_registry import sync_permissions


revision = "157_lookup_sets"
down_revision = "156_respond_contacts_session_vars"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lookup_sets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("set_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint("tenant_id", "set_key", name="uq_lookup_sets_tenant_setkey"),
    )
    op.create_index("ix_lookup_sets_is_active", "lookup_sets", ["is_active"])

    op.create_table(
        "lookup_options",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("set_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("lookup_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.String(150), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(
        "uq_lookup_options_set_value_lower",
        "lookup_options",
        ["set_id", sa.text("lower(value)")],
        unique=True,
    )
    op.create_index("ix_lookup_options_set_sort", "lookup_options", ["set_id", "sort_order"])

    op.create_table(
        "lookup_option_keywords",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("option_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("lookup_options.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(150), nullable=False),
        sa.Column("locale", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("option_id", "keyword", "locale", name="uq_lookup_keywords_unique"),
    )
    op.create_index("ix_lookup_keywords_lower", "lookup_option_keywords", [sa.text("lower(keyword)")])

    op.create_table(
        "lookup_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("set_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("lookup_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("column_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint("tenant_id", "table_name", "column_name", name="uq_lookup_bindings_tenant_col"),
    )
    op.create_index("ix_lookup_bindings_set", "lookup_bindings", ["set_id"])

    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        sync_permissions(session, created_by_user_id=None)
    finally:
        session.close()


def downgrade() -> None:
    op.drop_index("ix_lookup_bindings_set", table_name="lookup_bindings")
    op.drop_table("lookup_bindings")
    op.drop_index("ix_lookup_keywords_lower", table_name="lookup_option_keywords")
    op.drop_table("lookup_option_keywords")
    op.drop_index("ix_lookup_options_set_sort", table_name="lookup_options")
    op.drop_index("uq_lookup_options_set_value_lower", table_name="lookup_options")
    op.drop_table("lookup_options")
    op.drop_index("ix_lookup_sets_is_active", table_name="lookup_sets")
    op.drop_table("lookup_sets")
