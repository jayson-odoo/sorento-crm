"""What an order inquiry row explains, who acted on it, and one inquiry per publish.

Slice P10 (AC-I1, AC-I2, AC-I7). The tables themselves landed with 319; this adds the
three things deriving rows on publish needs and the constraint that makes publishing
twice safe.

`note` because a verb on its own is not actionable: DELAY without the date it moved
from, or CHANGE SO without the destination, sends purchasing back to a person.
`actioned_by` / `actioned_at` because a state with nobody's name on it cannot answer
"did purchasing act on this, and when".

The two partial unique indexes are the idempotency guard: one inquiry per published
sales order, one per published amendment. Postgres treats NULLs as distinct in a plain
unique index, so the sales-order case needs its own predicate.

Revision ID: 322_order_inquiry_derivation
Revises: 321_allocation_tables
"""
from alembic import op
import sqlalchemy as sa

revision = "322_order_inquiry_derivation"
down_revision = "321_allocation_tables"
branch_labels = None
depends_on = None

TABLE = "order_inquiry_rows"


def _columns(table: str) -> set:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set:
    return {idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    # Idempotent throughout: this branch shares a development database with other
    # worktrees, so a column may already be present from another run.
    existing = _columns(TABLE)
    if "note" not in existing:
        op.add_column(TABLE, sa.Column("note", sa.Text(), nullable=True))
    if "actioned_by" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "actioned_by",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "actioned_at" not in existing:
        op.add_column(TABLE, sa.Column("actioned_at", sa.DateTime(timezone=False), nullable=True))

    if "ix_order_inquiry_rows_state" not in _indexes(TABLE):
        op.create_index("ix_order_inquiry_rows_state", TABLE, ["state"])

    inquiry_indexes = _indexes("order_inquiries")
    if "uq_order_inquiry_per_sales_order" not in inquiry_indexes:
        op.create_index(
            "uq_order_inquiry_per_sales_order",
            "order_inquiries",
            ["project_sales_order_id"],
            unique=True,
            postgresql_where=sa.text("amendment_id IS NULL"),
        )
    if "uq_order_inquiry_per_amendment" not in inquiry_indexes:
        op.create_index(
            "uq_order_inquiry_per_amendment",
            "order_inquiries",
            ["amendment_id"],
            unique=True,
            postgresql_where=sa.text("amendment_id IS NOT NULL"),
        )


def downgrade() -> None:
    for name in ("uq_order_inquiry_per_amendment", "uq_order_inquiry_per_sales_order"):
        if name in _indexes("order_inquiries"):
            op.drop_index(name, table_name="order_inquiries")
    if "ix_order_inquiry_rows_state" in _indexes(TABLE):
        op.drop_index("ix_order_inquiry_rows_state", table_name=TABLE)
    existing = _columns(TABLE)
    for name in ("actioned_at", "actioned_by", "note"):
        if name in existing:
            op.drop_column(TABLE, name)
