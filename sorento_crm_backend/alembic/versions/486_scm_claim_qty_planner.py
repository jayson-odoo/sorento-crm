"""`planner` joins the order-link claim's source vocabulary, and it carries a qty
(R20, AC-I5, plan section 9 of PLAN-scm-purchasing-consolidation-6sep.md).

The SPO planner's SO-covered dialog (R19) lets the operator tick a RETAIL sales-order line
and type exactly how much of this SPO covers it. The project half of a tick already has
somewhere to live (`projects.order_inquiry_links.qty`); the retail half did not - a claim
row records the pairing (`so_number`, `po_number`/`spo_allocation_id`) but never a quantity,
because every existing writer already knows both ends of its pairing without needing to
state one (a book claim is unresolved until `resolve()` fills it in; a placement claim's own
"how much" lives on the link it sits beside). A planner claim is written FULLY RESOLVED, in
the same breath as the allocation it points at, and the ONE thing none of the other columns
states is how much of that allocation this particular sales-order line was promised - so it
needs the column the others never did.

`qty` is nullable: every existing row (book claims, placement claims) has nothing to put
there and nothing reads it for them - `NOT NULL` would need a backfill for a figure that
does not exist for 90k+ rows. `Numeric(15, 4)` matches `sales_order_lines.qty_ordered` and
`purchase_order_lines.qty_ordered`, the two quantity columns a planner claim sits between.

Constraint only for `source`, plus the additive column - no data moves, and no existing row
needs migrating.

Revision ID: 486_scm_claim_qty_planner
Revises: 485_shipment_line_photo_type
"""
import sqlalchemy as sa
from alembic import op

revision = "486_scm_claim_qty_planner"
down_revision = "485_shipment_line_photo_type"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_scm_order_link_claim_source"
_OLD = (
    "source IN ('po_history', 'order_inquiry', 'so_upload', 'po_upload', 'manual', "
    "'crm_supply', 'autocount')"
)
_NEW = (
    "source IN ('po_history', 'order_inquiry', 'so_upload', 'po_upload', 'manual', "
    "'crm_supply', 'autocount', 'planner')"
)


def upgrade() -> None:
    op.add_column(
        "order_link_claim",
        sa.Column("qty", sa.Numeric(15, 4), nullable=True),
        schema="scm",
    )
    op.drop_constraint(_CONSTRAINT, "order_link_claim", schema="scm", type_="check")
    op.create_check_constraint(_CONSTRAINT, "order_link_claim", _NEW, schema="scm")


def downgrade() -> None:
    # A `planner` row would fail the narrower check, so it is relabelled rather than
    # deleted - same reasoning migration 458/473 already give for their own new source
    # values: the attribution is real evidence, and a downgrade that destroys it is worse
    # than one that stores it under the nearest older word.
    op.execute(
        "UPDATE scm.order_link_claim SET source = 'manual' WHERE source = 'planner'"
    )
    op.drop_constraint(_CONSTRAINT, "order_link_claim", schema="scm", type_="check")
    op.create_check_constraint(_CONSTRAINT, "order_link_claim", _OLD, schema="scm")
    op.drop_column("order_link_claim", "qty", schema="scm")
