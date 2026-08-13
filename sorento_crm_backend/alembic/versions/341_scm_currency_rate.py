"""A rate per currency, so the plan can compare two prices.

The purchase-order book prices in USD, MYR, CNY and EUR, and most SKUs with more than one
priced supplier have those suppliers in different currencies. Ranking them without a rate
compares 45 against 190 and calls 45 cheaper. This is where the rate lives.

One row per currency, holding the rate we use NOW. History is not kept here on purpose: a
planning run freezes the rate it used onto its own recommendations (`rate_to_base`,
`rate_as_of`), so an old run explains itself without this table having to remember. The base
currency (`MYR`) is not stored - it is 1 by definition, and a stored 1 is a number somebody
can edit to something else.

Revision ID: 341_scm_currency_rate
Revises: 340_scm_committed_reads_the_decision
"""
import sqlalchemy as sa
from alembic import op

revision = "341_scm_currency_rate"
down_revision = "340_scm_committed_reads_the_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "currency_rate",
        sa.Column("currency", sa.String(3), primary_key=True),
        # What one unit of `currency` is worth in the base currency. NUMERIC, not float:
        # a rate is money-adjacent and 4.4 must stay 4.4.
        sa.Column("rate_to_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_by", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        # A non-positive rate would zero out or invert a real cost. The service refuses one
        # too; this is the line that holds when something writes around the service.
        sa.CheckConstraint("rate_to_base > 0", name="ck_currency_rate_positive"),
        schema="scm",
    )

    # The run records the rate it used, so a plan printed today still explains its own
    # numbers after somebody updates the rate tomorrow.
    op.add_column("reorder_recommendation",
                  sa.Column("rate_to_base", sa.Numeric(18, 6), nullable=True),
                  schema="scm")
    op.add_column("reorder_recommendation",
                  sa.Column("rate_as_of", sa.Date(), nullable=True),
                  schema="scm")


def downgrade() -> None:
    op.drop_column("reorder_recommendation", "rate_as_of", schema="scm")
    op.drop_column("reorder_recommendation", "rate_to_base", schema="scm")
    op.drop_table("currency_rate", schema="scm")
