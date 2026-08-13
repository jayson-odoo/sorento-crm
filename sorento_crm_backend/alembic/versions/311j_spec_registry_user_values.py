"""Let staff add a value to a shipped specification.

`allowed_values` on a seeded key is refused by the API on purpose: the seed repairs it on
every deploy so the CRM ranker and the n8n parser can never disagree about what a value
is called, and an edit there would be silently reverted.

That left a dead end. Pointing a rule at a value the key does not have is rejected with
"add the value to this specification first" — and there was no way to add one. The
instruction was impossible to follow for every shipped key, which is all but the ones
staff created themselves.

`user_values` is the same escape hatch `user_synonyms` already is: ADDITIVE, never
seed-repaired, merged with the shipped list at read time. Staff extend the vocabulary;
they cannot remove or rename what the parser depends on.

Ticket: jayson-odoo/sorento-crm#104.

Revision ID: 311j_spec_registry_user_values
Revises: 311i_configurable_derivation_rules
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "311j_spec_registry_user_values"
down_revision = "311i_configurable_derivation_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_spec_registry",
        sa.Column("user_values", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("product_spec_registry", "user_values")
