"""Make the spec registry user-editable without losing the anti-drift guarantee.

`seed_spec_registry` repairs vocabulary drift on every deploy so the CRM ranker and the
n8n parser can never disagree about what a value is called. That directly fights a UI
that lets staff edit the same fields — without a marker, the deploy silently wins.

`source` separates the two populations: `seed` rows keep being repaired, `user` rows are
never touched. `user_synonyms` is the additive middle ground, so adding one word to a
shipped key does not require taking ownership of the row.

Ticket: jayson-odoo/sorento-crm#100.

Revision ID: 311e_spec_registry_user_editable
Revises: 311d_spec_registry_match_tolerance
"""
from alembic import op
import sqlalchemy as sa

revision = "311e_spec_registry_user_editable"
down_revision = "311d_spec_registry_match_tolerance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_spec_registry",
        sa.Column("source", sa.String(16), nullable=False, server_default=sa.text("'seed'")),
    )
    op.add_column(
        "product_spec_registry",
        sa.Column(
            "user_synonyms",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # Every existing row came from the seed, which is already the column default.


def downgrade() -> None:
    op.drop_column("product_spec_registry", "user_synonyms")
    op.drop_column("product_spec_registry", "source")
