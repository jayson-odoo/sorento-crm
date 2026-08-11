"""The buyer's keep-or-discontinue call, recorded beside the engine's advisory.

`products.is_discontinued` is DERIVED from the AutoCount description on every product
sync, so the decision cannot live there - a click would be overwritten by the next
upload. Same doctrine as reorder levels: the system records the decision, applying it
in AutoCount (marking the description) stays the buyer's job. One row per product,
overwritten on a change of mind - the advisory recomputes every run regardless.

Revision ID: 352_scm_product_lifecycle_decision
Revises: 351_scm_product_health_thresholds
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "352_scm_product_lifecycle_decision"
down_revision = "351_scm_product_health_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_lifecycle_decision",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("product_id", UUID(as_uuid=False),
                  sa.ForeignKey("products.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("decided_by", UUID(as_uuid=False), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_table("product_lifecycle_decision", schema="scm")
