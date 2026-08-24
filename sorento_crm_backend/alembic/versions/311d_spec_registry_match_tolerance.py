"""Per-key numeric match tolerance on the spec registry.

One module-level "+/- 5mm reads as exact" was applied to every numeric key, so a
one-bowl sink scored a PERFECT `bowl_count` match for "double bowl" - 1 and 2 are
within 5. Tolerance is a property of the quantity, so it belongs on the row.

`match_decay = 0` means exact-or-nothing, which is what a count needs. Millimetre keys
keep the previous behaviour exactly (5 / 150), so this migration is behaviour-preserving
for dimensions and only changes counts.

Ticket: jayson-odoo/sorento-crm#96.

Revision ID: 311d_spec_registry_match_tolerance
Revises: 311c_product_specifications
"""
from alembic import op
import sqlalchemy as sa

revision = "311d_spec_registry_match_tolerance"
down_revision = "311c_product_specifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_spec_registry",
        sa.Column(
            "match_tolerance",
            sa.Numeric(10, 3),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "product_spec_registry",
        sa.Column(
            "match_decay",
            sa.Numeric(10, 3),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # Backfill from the unit so existing rows keep behaving as they did. Anything
    # measured in millimetres carries the old constants; everything else (counts,
    # enums, booleans) becomes exact-or-nothing, which is the fix.
    op.execute(
        """
        UPDATE product_spec_registry
           SET match_tolerance = 5, match_decay = 150
         WHERE unit = 'mm'
        """
    )


def downgrade() -> None:
    op.drop_column("product_spec_registry", "match_decay")
    op.drop_column("product_spec_registry", "match_tolerance")
