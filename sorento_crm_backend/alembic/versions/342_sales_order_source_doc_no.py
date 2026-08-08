"""The two sales-order columns the Order Inquiry feed maps, with DDL behind them.

`sales_orders.source_doc_no` and `internal_note` were mapped onto the model in
"the Order Inquiry sheet creates sales orders" on the strength of them already existing on the
table. They did - on a development database restored from production, where they arrived by
some route this repository never recorded. No migration in the chain creates them, so every
database built from the migrations alone (CI, a new machine, a fresh deploy) has a model that
selects two columns that are not there, and `SELECT sales_orders.source_doc_no` fails on every
read of the table. That is most of the SCM suite.

Added conditionally: the databases that already have the columns are the ones this was found
on, and re-adding them there would fail instead of converging.

Revision ID: 342_sales_order_source_doc_no
Revises: 341_scm_currency_rate
"""
import sqlalchemy as sa
from alembic import op

revision = "342_sales_order_source_doc_no"
down_revision = "341_scm_currency_rate"
branch_labels = None
depends_on = None


def _existing() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sales_orders")}


def upgrade() -> None:
    have = _existing()

    if "source_doc_no" not in have:
        # The document number the order came in on, in the SOURCE system's own numbering.
        # Kept beside `so_number` rather than replacing it, because the two disagree whenever
        # a feed renumbers, and the source's number is what the user searches by.
        op.add_column("sales_orders", sa.Column("source_doc_no", sa.String(), nullable=True))

    if "internal_note" not in have:
        # Free text the feed could not resolve to a column - most often a project name with no
        # matching customer. Held rather than dropped so the person reading the order can see
        # what the sheet said.
        op.add_column("sales_orders", sa.Column("internal_note", sa.Text(), nullable=True))


def downgrade() -> None:
    have = _existing()
    if "internal_note" in have:
        op.drop_column("sales_orders", "internal_note")
    if "source_doc_no" in have:
        op.drop_column("sales_orders", "source_doc_no")
