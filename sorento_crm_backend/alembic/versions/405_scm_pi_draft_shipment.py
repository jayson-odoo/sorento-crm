"""scm: PI -> draft inbound shipment convert (packing-list amendment, 20 Aug evening).

`PLAN-scm-proforma-to-spo.md`'s Amendment section: "pick one or more PIs -> the system
creates a DRAFT inbound shipment pre-filled with their lines". What this adds:

* `scm.proforma_invoice_shipment_link` - one row per PI line the convert touched, pointing at
  the shipment line it became (or, for an unmatched line, recording why it did not). See the
  model docstring for why this is a link table rather than a column.
* `draft` joins the `inbound_shipments.shipment_status` vocabulary. The constraint already
  existed on the shared local/prod database (added outside any migration in this repo - see
  `coverage_service.py`'s note) with six values; this drops and recreates it with the
  seventh. NOT additionally declared on the model - see the comment at
  `InboundShipment.__table_args__` for why a `create_all` (test) schema deliberately does
  not enforce this column's vocabulary.

Revision ID: 405_scm_pi_draft_shipment
Revises: 404_reorder_rec_moq_override
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "405_scm_pi_draft_shipment"
down_revision = "404_reorder_rec_moq_override"
branch_labels = None
depends_on = None

_STATUS_CHECK = "inbound_shipments_shipment_status_check"
_OLD_STATUSES = (
    "in_transit", "arrived_at_port", "at_warehouse",
    "partially_received", "fully_received", "closed",
)
_NEW_STATUSES = ("draft",) + _OLD_STATUSES


def _check_sql(statuses: tuple[str, ...]) -> str:
    values = ", ".join(f"'{s}'" for s in statuses)
    return f"shipment_status IN ({values})"


def upgrade() -> None:
    op.create_table(
        "proforma_invoice_shipment_link",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id", name="fk_scm_pi_shipment_link_company_id"),
            nullable=True,
        ),
        sa.Column(
            "proforma_invoice_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.proforma_invoice.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "proforma_invoice_line_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.proforma_invoice_line.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "inbound_shipment_id",
            UUID(as_uuid=False),
            sa.ForeignKey("inbound_shipments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "inbound_shipment_line_id",
            UUID(as_uuid=False),
            sa.ForeignKey("inbound_shipment_lines.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("unmatched_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="scm",
    )
    op.create_index(
        "ix_scm_pi_shipment_link_invoice", "proforma_invoice_shipment_link",
        ["proforma_invoice_id"], schema="scm",
    )
    op.create_index(
        "ix_scm_pi_shipment_link_shipment", "proforma_invoice_shipment_link",
        ["inbound_shipment_id"], schema="scm",
    )
    op.create_index(
        "ix_scm_pi_shipment_link_company_id", "proforma_invoice_shipment_link",
        ["company_id"], schema="scm",
    )
    op.create_index(
        "uq_scm_pi_shipment_link_line", "proforma_invoice_shipment_link",
        ["proforma_invoice_line_id"], unique=True, schema="scm",
    )

    # Drop-then-recreate rather than assume it exists: a `create_all` CI database never had
    # it, a hand-migrated local/prod one does.
    op.execute(f"ALTER TABLE inbound_shipments DROP CONSTRAINT IF EXISTS {_STATUS_CHECK}")
    op.execute(
        f"ALTER TABLE inbound_shipments ADD CONSTRAINT {_STATUS_CHECK} "
        f"CHECK ({_check_sql(_NEW_STATUSES)})"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE inbound_shipments DROP CONSTRAINT IF EXISTS {_STATUS_CHECK}")
    op.execute(
        f"ALTER TABLE inbound_shipments ADD CONSTRAINT {_STATUS_CHECK} "
        f"CHECK ({_check_sql(_OLD_STATUSES)})"
    )
    op.drop_table("proforma_invoice_shipment_link", schema="scm")
