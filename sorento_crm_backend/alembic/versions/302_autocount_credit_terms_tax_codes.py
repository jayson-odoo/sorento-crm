"""AutoCount ingest Slice 1: credit_terms + tax_codes mirror tables.

Both are read-only mirrors of AutoCount masters pushed in by the ESB. Explicit
op.create_table (not autogenerate-implicit) because a schema built from
create_all on a legacy DB never runs migration bodies, so the DDL must be
unconditional and idempotent here. Guarded with an existence check so a re-run
(or a create_all DB that already has the ORM tables) is a no-op.

Revision ID: 302_autocount_credit_terms_tax_codes
Revises: 307_admin_listing_company
"""
from alembic import op
import sqlalchemy as sa


revision = "302_autocount_credit_terms_tax_codes"
# Chained onto main's head (the multi_company chain's merge node) rather than the
# shared ancestor cbf3a0044924, so the autocount chain (302..309) STACKS on top
# of main instead of forking a second head off cbf3a0044924. Keeps a single
# alembic head after this branch merges. See PLAN-autocount-ingest-ui.md.
down_revision = "307_admin_listing_company"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "credit_terms" not in tables:
        op.create_table(
            "credit_terms",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("display_term", sa.String(length=100), nullable=False),
            sa.Column("terms", sa.String(length=255), nullable=True),
            sa.Column("term_days", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        )
        op.create_unique_constraint("uq_credit_terms_display_term", "credit_terms", ["display_term"])

    if "tax_codes" not in tables:
        op.create_table(
            "tax_codes",
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("tax_code", sa.String(length=100), nullable=False),
            sa.Column("supply_purchase", sa.String(length=1), nullable=True),
            sa.Column("tax_rate", sa.Numeric(9, 4), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        )
        op.create_unique_constraint("uq_tax_codes_tax_code", "tax_codes", ["tax_code"])


def downgrade() -> None:
    op.drop_table("tax_codes")
    op.drop_table("credit_terms")
