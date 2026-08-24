"""Let staff take a shipped word away from a value.

`user_synonyms` is additive by design: staff extend the vocabulary and can never remove
a word the n8n parser depends on. That was the right default and it left one thing
impossible.

"Matte black" ships as a synonym of `black`. It is a colour in its own right, and while
the word is bound to `black` there is no way to make it mean anything else - adding a
`matte_black` value does not help, because the word still resolves to `black` first.
The only fix was to edit a seed row, which the next deploy repairs.

`suppressed_synonyms` is the mirror of `user_synonyms`: staff-owned, never
seed-repaired, subtracted at read time. The seed keeps shipping the word; this row says
this business does not use it that way. Nothing is deleted, so removing the suppression
puts it straight back.

Ticket: jayson-odoo/sorento-crm#109.

Revision ID: 311k_spec_registry_suppressed_synonyms
Revises: 311j_spec_registry_user_values
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "311k_spec_registry_suppressed_synonyms"
down_revision = "311j_spec_registry_user_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_spec_registry",
        sa.Column(
            "suppressed_synonyms",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("product_spec_registry", "suppressed_synonyms")
