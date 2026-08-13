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


def _live_name(new: str, legacy: str) -> str:
    """Whichever of the two names this database currently carries.

    Revision 353 renamed these tables to the module's `project_` prefix and 319 now
    creates them under the new name, so a fresh database is already prefixed here. A
    development database that stopped short of 353 still holds the old name, and this
    revision has to run against that one too.
    """
    return new if sa.inspect(op.get_bind()).has_table(new) else legacy


def _columns(table: str) -> set:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set:
    return {idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    # Idempotent throughout: this branch shares a development database with other
    # worktrees, so a column may already be present from another run.
    rows = _live_name("project_order_inquiry_rows", "order_inquiry_rows")
    inquiries = _live_name("project_order_inquiries", "order_inquiries")
    existing = _columns(rows)
    if "note" not in existing:
        op.add_column(rows, sa.Column("note", sa.Text(), nullable=True))
    if "actioned_by" not in existing:
        op.add_column(
            rows,
            sa.Column(
                "actioned_by",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "actioned_at" not in existing:
        op.add_column(rows, sa.Column("actioned_at", sa.DateTime(timezone=False), nullable=True))

    # Index names carry the new prefix whichever table name they land on: revision 353
    # renames an index it finds under the old name, and skips one already renamed.
    row_indexes = _indexes(rows)
    if not {"ix_order_inquiry_rows_state", "ix_project_order_inquiry_rows_state"} & row_indexes:
        op.create_index("ix_project_order_inquiry_rows_state", rows, ["state"])

    inquiry_indexes = _indexes(inquiries)
    if not {
        "uq_order_inquiry_per_sales_order",
        "uq_project_order_inquiry_per_sales_order",
    } & inquiry_indexes:
        op.create_index(
            "uq_project_order_inquiry_per_sales_order",
            inquiries,
            ["project_sales_order_id"],
            unique=True,
            postgresql_where=sa.text("amendment_id IS NULL"),
        )
    if not {
        "uq_order_inquiry_per_amendment",
        "uq_project_order_inquiry_per_amendment",
    } & inquiry_indexes:
        op.create_index(
            "uq_project_order_inquiry_per_amendment",
            inquiries,
            ["amendment_id"],
            unique=True,
            postgresql_where=sa.text("amendment_id IS NOT NULL"),
        )


def downgrade() -> None:
    rows = _live_name("project_order_inquiry_rows", "order_inquiry_rows")
    inquiries = _live_name("project_order_inquiries", "order_inquiries")
    inquiry_indexes = _indexes(inquiries)
    for name in (
        "uq_project_order_inquiry_per_amendment",
        "uq_order_inquiry_per_amendment",
        "uq_project_order_inquiry_per_sales_order",
        "uq_order_inquiry_per_sales_order",
    ):
        if name in inquiry_indexes:
            op.drop_index(name, table_name=inquiries)
    row_indexes = _indexes(rows)
    for name in ("ix_project_order_inquiry_rows_state", "ix_order_inquiry_rows_state"):
        if name in row_indexes:
            op.drop_index(name, table_name=rows)
    existing = _columns(rows)
    for name in ("actioned_at", "actioned_by", "note"):
        if name in existing:
            op.drop_column(rows, name)
