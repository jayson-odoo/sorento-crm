"""Store allocated and received metrics on inbound shipment lines.

Revision ID: 123_inbound_line_metrics
Revises: 122_sla_tracking_agent_id_fk
Create Date: 2026-03-29
"""
from collections import defaultdict

from alembic import op
import sqlalchemy as sa


revision = "123_inbound_line_metrics"
down_revision = "122_sla_tracking_agent_id_fk"
branch_labels = None
depends_on = None


def _normalize_spo_number(spo_number: str | None) -> str:
    if not spo_number or not str(spo_number).strip():
        return ""
    return str(spo_number).strip().replace("/", ".").replace("\\", ".")


def _compute_line_status(quantity_shipped: int, allocated_quantity: int, quantity_received: int) -> str:
    qty = quantity_shipped or 0
    alloc = allocated_quantity or 0
    recv = quantity_received or 0
    if alloc == 0:
        return "in_transit"
    if recv >= alloc:
        return "received"
    if qty > alloc:
        return "partially_allocated"
    if alloc >= qty and recv == 0:
        return "allocated"
    if alloc >= qty and recv > 0:
        return "partially_received"
    return "in_transit"


def upgrade() -> None:
    op.add_column(
        "inbound_shipment_lines",
        sa.Column("spo_allocated_quantity", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inbound_shipment_lines",
        sa.Column("quantity_received", sa.Integer(), nullable=False, server_default="0"),
    )

    conn = op.get_bind()

    lines = conn.execute(
        sa.text(
            """
            SELECT id, shipment_id, product_id, quantity_shipped
            FROM inbound_shipment_lines
            """
        )
    ).mappings().all()

    allocated_rows = conn.execute(
        sa.text(
            """
            SELECT inbound_shipment_id AS shipment_id, product_id, COALESCE(SUM(allocated_quantity), 0) AS total
            FROM spo_allocations
            GROUP BY inbound_shipment_id, product_id
            """
        )
    ).mappings().all()
    allocated_map = {
        (row["shipment_id"], row["product_id"]): int(row["total"] or 0)
        for row in allocated_rows
    }

    linked_received_rows = conn.execute(
        sa.text(
            """
            SELECT
                sa.inbound_shipment_id AS shipment_id,
                sa.product_id AS product_id,
                COALESCE(SUM(pl.quantity_expected), 0) AS total
            FROM spo_allocations sa
            JOIN picking_lines pl ON pl.spo_allocation_id = sa.id
            JOIN picking_headers ph ON ph.id = pl.picking_header_id
            WHERE ph.picking_type = 'goods_received'
              AND ph.picking_status = 'approved'
            GROUP BY sa.inbound_shipment_id, sa.product_id
            """
        )
    ).mappings().all()
    linked_received_map = {
        (row["shipment_id"], row["product_id"]): int(row["total"] or 0)
        for row in linked_received_rows
    }

    spo_number_rows = conn.execute(
        sa.text(
            """
            SELECT inbound_shipment_id AS shipment_id, product_id, spo_number
            FROM spo_allocations
            WHERE spo_number IS NOT NULL
            """
        )
    ).mappings().all()
    spo_numbers_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in spo_number_rows:
        normalized = _normalize_spo_number(row["spo_number"])
        if normalized:
            spo_numbers_by_key[(row["shipment_id"], row["product_id"])].add(normalized)

    orphan_received_rows = conn.execute(
        sa.text(
            """
            SELECT
                pl.product_id,
                ph.spo_number,
                COALESCE(SUM(pl.quantity_expected), 0) AS total
            FROM picking_lines pl
            JOIN picking_headers ph ON ph.id = pl.picking_header_id
            WHERE pl.spo_allocation_id IS NULL
              AND ph.picking_type = 'goods_received'
              AND ph.picking_status = 'approved'
              AND ph.spo_number IS NOT NULL
            GROUP BY pl.product_id, ph.spo_number
            """
        )
    ).mappings().all()
    orphan_received_map: dict[tuple[str, str], int] = {}
    for row in orphan_received_rows:
        normalized = _normalize_spo_number(row["spo_number"])
        if not normalized:
            continue
        orphan_received_map[(row["product_id"], normalized)] = int(row["total"] or 0)

    updates = []
    for line in lines:
        key = (line["shipment_id"], line["product_id"])
        allocated_quantity = allocated_map.get(key, 0)
        quantity_received = linked_received_map.get(key, 0)
        for normalized_spo_number in spo_numbers_by_key.get(key, set()):
            quantity_received += orphan_received_map.get(
                (line["product_id"], normalized_spo_number),
                0,
            )
        updates.append(
            {
                "line_id": line["id"],
                "spo_allocated_quantity": allocated_quantity,
                "quantity_received": quantity_received,
                "line_status": _compute_line_status(
                    int(line["quantity_shipped"] or 0),
                    allocated_quantity,
                    quantity_received,
                ),
            }
        )

    if updates:
        conn.execute(
            sa.text(
                """
                UPDATE inbound_shipment_lines
                SET
                    spo_allocated_quantity = :spo_allocated_quantity,
                    quantity_received = :quantity_received,
                    line_status = :line_status
                WHERE id = :line_id
                """
            ),
            updates,
        )


def downgrade() -> None:
    op.drop_column("inbound_shipment_lines", "quantity_received")
    op.drop_column("inbound_shipment_lines", "spo_allocated_quantity")
