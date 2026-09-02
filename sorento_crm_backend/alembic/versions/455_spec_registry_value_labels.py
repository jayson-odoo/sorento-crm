"""Spec registry: a display label per value (#423 folded into the workbench redesign).

`allowed_values` and `synonyms` are the parser's vocabulary and the customer's own
words; neither is what a staff screen should show a reviewer. `pp` reads as `Pp` off
the automatic title-case fallback, and a value like `s/steel` reads worse than that.
`value_labels` is a THIRD, purely cosmetic map - `{"pp": "PP"}` - editable on seed AND
user rows alike (it is staff-owned, like `user_synonyms`, never seed-repaired) and
read by every value display alongside `readableValue`/`readableEntry` (D, E).

One column rather than a table: it is one small dict per key, read every time the
row itself is read, with no lifecycle of its own.

Rechained on merge (2 Sep 2026): this slice and `454_order_inquiry_born_ack` both
branched off `453_shared_brand_attach` in parallel PRs. Renumbered 454 -> 455 and
`down_revision` moved onto `454_order_inquiry_born_ack` to keep a single head; no
merge migration needed since neither touches the other's objects.

Revision ID: 455_spec_registry_value_labels
Revises: 454_order_inquiry_born_ack
"""
from alembic import op
import sqlalchemy as sa

revision = "455_spec_registry_value_labels"
down_revision = "454_order_inquiry_born_ack"
branch_labels = None
depends_on = None

TABLE = "product_spec_registry"


def _columns() -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = current_schema()"
            ),
            {"t": TABLE},
        )
    }


def upgrade() -> None:
    if "value_labels" not in _columns():
        op.add_column(
            TABLE,
            sa.Column(
                "value_labels",
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )


def downgrade() -> None:
    if "value_labels" in _columns():
        op.drop_column(TABLE, "value_labels")
