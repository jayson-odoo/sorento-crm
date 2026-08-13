"""SCM L4: the SO<->PO linkage, claimed by whichever feed sees it first.

A purchase order can be uploaded before its sales order exists, and a sales order before its
purchase order. Neither order may lose the pairing, and neither may invent one.

A nullable FK on the PO line cannot express this. A claim made before the other side exists
has nowhere to live, so it is dropped on the floor and the linkage silently depends on upload
order - which is exactly the failure the user named.

So the pairing is a CLAIM, written by whichever feed knows it, resolved when both sides are
present:

  * `scm.po_history_import` writes claims from the `**SO:174830**` notes inside the PO file.
  * the Order Inquiry feed writes claims per (S/O NO, ITEM CODE, PO NO).
  * the SO and PO uploads resolve claims as their documents arrive.

`so_number` / `po_number` / `item_code` are the numbers as the SOURCE spelled them, kept as
text. That is the whole point: at claim time neither document need exist, so there is nothing
to hold a foreign key to. `so_line_id` and `po_line_id` are filled in on resolution and are
what everything downstream reads.

`item_code` is nullable because the two sources know different things. The Order Inquiry sheet
states the item, so its claims are per line. The PO notes do not - a note sits between lines
and nothing says which side it describes - so those claims are order-level, and guessing a
line would assign one customer's stock to another customer's order.

Revision ID: 334_scm_order_link_claim
Revises: 333_scm_plan_exception
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "334_scm_order_link_claim"
down_revision = "333_scm_plan_exception"
branch_labels = None
depends_on = None

_SORENTO = "00000000-0000-0000-0000-000000000001"
_SOURCES = ("po_history", "order_inquiry", "so_upload", "po_upload", "manual")


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table, schema="scm")


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "order_link_claim"):
        return

    op.create_table(
        "order_link_claim",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        # The numbers as the SOURCE spelled them. Text, not FKs: at claim time neither
        # document need exist, which is the reason this table is here at all.
        sa.Column("so_number", sa.String(100), nullable=False),
        sa.Column("po_number", sa.String(100), nullable=False),
        # Null on an order-level claim (the PO notes cannot say which line).
        sa.Column("item_code", sa.String(100), nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        # Filled in when both sides are present. Null means "still waiting", which is a
        # number the upload result reports rather than a silence.
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "so_line_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("sales_order_lines.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "po_line_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("purchase_order_lines.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "source IN ('" + "', '".join(_SOURCES) + "')",
            name="ck_scm_order_link_claim_source",
        ),
        schema="scm",
    )
    # The same pairing stated twice by two feeds is ONE claim, not two. `coalesce` on the
    # nullable item code because Postgres treats NULLs as distinct in a unique index, so
    # without it every order-level claim would insert again on every re-upload.
    op.create_index(
        "uq_scm_order_link_claim_identity",
        "order_link_claim",
        ["so_number", "po_number", sa.text("coalesce(item_code, '')")],
        unique=True,
        schema="scm",
    )
    # The resolver's query: what is still waiting for the other side.
    op.create_index(
        "ix_scm_order_link_claim_unresolved",
        "order_link_claim",
        ["resolved_at"],
        schema="scm",
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_index(
        "ix_scm_order_link_claim_so", "order_link_claim", ["so_number"], schema="scm"
    )
    op.create_index(
        "ix_scm_order_link_claim_po", "order_link_claim", ["po_number"], schema="scm"
    )
    op.create_index(
        "ix_scm_order_link_claim_company", "order_link_claim", ["company_id"], schema="scm"
    )
    op.execute(
        sa.text(
            "UPDATE scm.order_link_claim SET company_id = :co "
            "WHERE company_id IS NULL AND EXISTS (SELECT 1 FROM companies WHERE id = :co)"
        ).bindparams(co=_SORENTO)
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "order_link_claim"):
        op.drop_table("order_link_claim", schema="scm")
