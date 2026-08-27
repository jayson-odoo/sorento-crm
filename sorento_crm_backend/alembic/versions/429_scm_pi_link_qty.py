"""F10: a proforma invoice line can be split across two packing lists.

Revision ID: 429_scm_pi_link_qty
Revises: 428_scm_pi_cbm_adjust_revision
Create Date: 2026-08-26

Q9, ruled by the captain on 26 Aug: "one PI may sit in two packing lists; the link carries a
qty, Convert pre-fills each line's remainder, the PI reads Split until fully placed."

Two changes, and the second is the one that matters:

* `scm.proforma_invoice_shipment_link.qty` - HOW MUCH of the line went to that shipment.
  Backfilled from the line's own quantity for every existing link, because until now a
  convert took the whole line and nothing else was possible. NULL is left on a SKIP row
  (`inbound_shipment_line_id IS NULL`), which records why a line went nowhere - a quantity
  there would claim goods were placed.
* `uq_scm_pi_shipment_link_line` stops being UNIQUE. It was what made a second convert of
  the same invoice detectable, and it is exactly what Q9 forbids: one line, two shipments,
  two rows. The refusal moves to the service, which now compares what is placed against
  what the line holds and refuses only an invoice with nothing left to place. Dropping a
  unique index is not reversible without the data being clean, so `downgrade()` rebuilds it
  and will fail loudly on a database that has already split a line - which is correct: the
  split cannot be un-split by a migration.

The index is ALSO declared on the model, so a create_all database matches a migrated one.
"""
import sqlalchemy as sa
from alembic import op

revision = "429_scm_pi_link_qty"
down_revision = "428_scm_pi_cbm_adjust_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proforma_invoice_shipment_link",
        sa.Column("qty", sa.Numeric(), nullable=True),
        schema="scm",
    )
    # Every link written before today took the WHOLE line, so that is what it placed.
    # Skips stay NULL: nothing was placed, and a number there would say otherwise.
    op.execute(
        """
        UPDATE scm.proforma_invoice_shipment_link AS lk
        SET qty = pil.qty
        FROM scm.proforma_invoice_line AS pil
        WHERE pil.id = lk.proforma_invoice_line_id
          AND lk.inbound_shipment_line_id IS NOT NULL
          AND lk.qty IS NULL
        """
    )

    op.drop_index(
        "uq_scm_pi_shipment_link_line",
        table_name="proforma_invoice_shipment_link",
        schema="scm",
    )
    op.create_index(
        "ix_scm_pi_shipment_link_line",
        "proforma_invoice_shipment_link",
        ["proforma_invoice_line_id"],
        schema="scm",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scm_pi_shipment_link_line",
        table_name="proforma_invoice_shipment_link",
        schema="scm",
    )
    # Fails on a database where a line HAS been split, and that is the honest outcome: the
    # unique index and the split cannot both be true.
    op.create_index(
        "uq_scm_pi_shipment_link_line",
        "proforma_invoice_shipment_link",
        ["proforma_invoice_line_id"],
        unique=True,
        schema="scm",
    )
    op.drop_column("proforma_invoice_shipment_link", "qty", schema="scm")
