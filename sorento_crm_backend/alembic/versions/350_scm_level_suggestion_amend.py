"""S14: the buyer can amend the suggested AutoCount level before carrying it over.

The engine's `suggested_level` stays untouched beside the amendment, so the screen can
say "you set 30; the engine said 24" instead of quietly rewriting the engine's number.
A new engine refresh clears the amendment: it was a judgement about THAT suggestion.

Revision ID: 350_scm_level_suggestion_amend
Revises: 349_scm_price_advice_config
"""
import sqlalchemy as sa
from alembic import op

revision = "350_scm_level_suggestion_amend"
down_revision = "349_scm_price_advice_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reorder_level",
        sa.Column("amended_level", sa.Numeric(14, 4), nullable=True),
        schema="scm",
    )
    op.add_column(
        "reorder_level",
        sa.Column("amended_at", sa.DateTime(timezone=False), nullable=True),
        schema="scm",
    )
    op.add_column(
        "reorder_level",
        sa.Column("amended_by", sa.String(), nullable=True),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_column("reorder_level", "amended_by", schema="scm")
    op.drop_column("reorder_level", "amended_at", schema="scm")
    op.drop_column("reorder_level", "amended_level", schema="scm")
