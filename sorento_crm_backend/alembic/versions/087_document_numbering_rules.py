"""Create document_numbering_rules table for running number configuration.

Revision ID: 087_document_numbering_rules
Revises: 086_attachments_type_nullable
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa


revision = "087_document_numbering_rules"
down_revision = "086_attachments_type_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_numbering_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("prefix_template", sa.Text(), nullable=True),
        sa.Column("number_digits", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("start_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reset_policy", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("last_reset_key", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_document_numbering_rules_doc_type", "document_numbering_rules", ["doc_type"], unique=True)

    # Seed default rules for purchase_request and sponsorship_form
    op.execute(
        sa.text("""
            INSERT INTO document_numbering_rules (id, doc_type, enabled, prefix_template, number_digits, next_value, start_value, reset_policy)
            VALUES
            (gen_random_uuid()::text, 'purchase_request', true, 'PR-{year}-', 4, 1, 1, 'yearly'),
            (gen_random_uuid()::text, 'sponsorship_form', true, 'SF-{year}-', 4, 1, 1, 'yearly')
        """)
    )


def downgrade() -> None:
    op.drop_index("ix_document_numbering_rules_doc_type", table_name="document_numbering_rules")
    op.drop_table("document_numbering_rules")
