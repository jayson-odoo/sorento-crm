"""Seed document_numbering_rules for external API promotion codes.

Revision ID: 137_seed_external_promotion_numbering
Revises: 136_system_settings_procurement_default_approvers
Create Date: 2026-04-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "137_seed_external_promotion_numbering"
down_revision = "136_system_settings_procurement_default_approvers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(
        text(
            "SELECT 1 FROM document_numbering_rules WHERE doc_type = 'external_promotion' LIMIT 1"
        )
    ).first()
    if row:
        return
    op.execute(
        sa.text(
            """
            INSERT INTO document_numbering_rules (
                id, doc_type, enabled, prefix_template, number_digits,
                next_value, start_value, reset_policy, last_reset_key
            )
            VALUES (
                gen_random_uuid()::text,
                'external_promotion',
                true,
                'PROMO{year}_',
                4,
                1,
                1,
                'yearly',
                NULL
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM document_numbering_rules WHERE doc_type = 'external_promotion'"
        )
    )
