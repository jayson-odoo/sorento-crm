"""Let a business take away a value the seed ships.

`user_values` could only ever ADD. A shipped value was permanent: the eleven finishes
that ship with `finish` rendered as locked chips with no remove control, so a business
that does not sell "french gold" had no way to stop the ranker offering it, and no way
to say so in the only place they can see the vocabulary.

Deleting the seed row is not the answer - the next deploy repairs it, silently. This is
the same subtractive escape hatch `suppressed_synonyms` already gives words: the value
stays in the seed, this business stops using it, and putting it back is one click.

Revision ID: 311l_spec_registry_suppressed_values
Revises: 311k_spec_registry_suppressed_synonyms
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "311l_spec_suppressed_values"
down_revision = "311k_spec_registry_suppressed_synonyms"
branch_labels = None
depends_on = None

TABLE = "product_spec_registry"
COLUMN = "suppressed_values"


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, TABLE, COLUMN):
        op.add_column(
            TABLE,
            sa.Column(
                COLUMN,
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
