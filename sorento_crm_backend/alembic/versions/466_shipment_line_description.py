"""inbound_shipment_lines.description carries the supplier's own wording (S9).

The container workbook's DESCRIPTION column used to print the product's catalogue name - on
prod that reads as the internal code, not what the factory called the item on its own PI. This
adds the column and backfills it, for every shipment line linked (via
`scm.proforma_invoice_shipment_link`) to a PI line, from that PI line's `description` - only
where the shipment line's own is still NULL, so a value already typed on the packing list
(edited in the grid after this column existed but before this migration's stamp caught up on a
shared, create_all-converged dev database) is never overwritten.

A shipment line linked to more than one PI line (a split placement) takes the first by link id -
same "first one wins" rule `convert_to_draft_shipment` itself uses for material and the other
merged-line measurements.

Revision ID: 466_shipment_line_description
Revises: 465_shipment_container_size
Create Date: 2026-09-03
"""
import sqlalchemy as sa
from alembic import op

revision = "466_shipment_line_description"
down_revision = "465_shipment_container_size"
branch_labels = None
depends_on = None

_LINES = "inbound_shipment_lines"
_LINK = "proforma_invoice_shipment_link"
_LINK_SCHEMA = "scm"
_PI_LINE = "proforma_invoice_line"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str, schema: str | None = None) -> bool:
    return _inspector().has_table(name, schema=schema)


def _has_column(table: str, column: str, schema: str | None = None) -> bool:
    if not _has_table(table, schema=schema):
        return False
    return column in {col["name"] for col in _inspector().get_columns(table, schema=schema)}


def upgrade() -> None:
    if not _has_column(_LINES, "description"):
        op.add_column(_LINES, sa.Column("description", sa.Text(), nullable=True))

    if _has_table(_LINK, schema=_LINK_SCHEMA) and _has_table(_PI_LINE, schema=_LINK_SCHEMA):
        op.execute(
            sa.text(
                f"""
                UPDATE {_LINES} sl
                SET description = sub.description
                FROM (
                    SELECT DISTINCT ON (l.inbound_shipment_line_id)
                        l.inbound_shipment_line_id AS shipment_line_id,
                        pl.description AS description
                    FROM {_LINK_SCHEMA}.{_LINK} l
                    JOIN {_LINK_SCHEMA}.{_PI_LINE} pl ON pl.id = l.proforma_invoice_line_id
                    WHERE l.inbound_shipment_line_id IS NOT NULL
                      AND pl.description IS NOT NULL
                    ORDER BY l.inbound_shipment_line_id, l.id
                ) sub
                WHERE sl.id = sub.shipment_line_id
                  AND sl.description IS NULL
                """
            )
        )


def downgrade() -> None:
    if _has_column(_LINES, "description"):
        op.drop_column(_LINES, "description")
