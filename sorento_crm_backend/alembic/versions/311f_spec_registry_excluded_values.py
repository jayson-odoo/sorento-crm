"""Spec registry: values that exist in the catalog but are not searchable.

`brand` is an OPEN vocabulary - its options are whatever the catalog holds - and the
catalog holds OTHERS (1,956 products) and NO LOGO (651). Those record the ABSENCE of a
brand. Handed to the understanding model as enum options they read as "none of the
above", so a word it could not place was filed under one instead of being left alone:
"interlignet wc" (a misspelt "intelligent") came back branded OTHERS, and the customer
got a shortlist chosen by a bucket rather than by what they said.

Excluding is a calibration decision, not vocabulary, so it follows `rank_weight`:
seeded once at row creation, then owned by whoever tunes it, and never repaired by a
re-seed.

Ticket: jayson-odoo/sorento-crm#98.

Revision ID: 311f_spec_registry_excluded_values
Revises: 311e_spec_registry_user_editable
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "311f_spec_registry_excluded_values"
down_revision = "311e_spec_registry_user_editable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_spec_registry",
        sa.Column(
            "excluded_values",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # Backfill the placeholder brands on an already-seeded database. New rows get this
    # from the seed; this is only for the ones that exist already.
    op.execute(
        """
        UPDATE product_spec_registry
           SET excluded_values = '["OTHERS", "NO LOGO"]'::jsonb
         WHERE spec_key = 'brand'
           AND excluded_values = '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.drop_column("product_spec_registry", "excluded_values")
