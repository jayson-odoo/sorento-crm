"""inbound_shipments.container_size_id replaces proforma_invoice.container_size_id (S5).

Capacity is a property of the CONTAINER, not the invoice loaded into it: a packing list
routinely consolidates several PIs (FSCU8103365 = 7 factories), so the fill gauge and the
size belong on the shipment the convert dialog creates, not on any one invoice beneath it
(`PLAN-scm-pi-packing-list-feedback-3sep.md` ruling 1, AC-E3).

Data step: for every draft shipment whose `scm.proforma_invoice_shipment_link` rows name
exactly ONE proforma invoice, that invoice's `container_size_id` is copied onto the
shipment - the same size the operator had chosen before this migration ran. A shipment
consolidating several PIs has no single invoice's choice to inherit and is left NULL,
which reads as the tenant default (AC-D4's own rule, carried over unchanged).

Revision ID: 465_shipment_container_size
Revises: 464_merge_plan_stmt_fulfil
Create Date: 2026-09-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "465_shipment_container_size"
down_revision = "464_merge_plan_stmt_fulfil"
branch_labels = None
depends_on = None

_SHIPMENTS = "inbound_shipments"
_INVOICE = "proforma_invoice"
_INVOICE_SCHEMA = "scm"
_FK_SHIPMENT = "fk_inbound_shipments_container_size"
_IX_SHIPMENT = "ix_inbound_shipments_container_size"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str, schema: str | None = None) -> bool:
    return _inspector().has_table(name, schema=schema)


def _has_column(table: str, column: str, schema: str | None = None) -> bool:
    if not _has_table(table, schema=schema):
        return False
    return column in {col["name"] for col in _inspector().get_columns(table, schema=schema)}


def _has_index(table: str, name: str, schema: str | None = None) -> bool:
    if not _has_table(table, schema=schema):
        return False
    return name in {idx["name"] for idx in _inspector().get_indexes(table, schema=schema)}


def _has_fk(table: str, name: str, schema: str | None = None) -> bool:
    if not _has_table(table, schema=schema):
        return False
    return name in {fk["name"] for fk in _inspector().get_foreign_keys(table, schema=schema)}


def upgrade() -> None:
    if not _has_column(_SHIPMENTS, "container_size_id"):
        op.add_column(
            _SHIPMENTS,
            sa.Column("container_size_id", UUID(as_uuid=False), nullable=True),
        )
    if not _has_fk(_SHIPMENTS, _FK_SHIPMENT):
        op.create_foreign_key(
            _FK_SHIPMENT,
            source_table=_SHIPMENTS,
            referent_table="container_size",
            local_cols=["container_size_id"],
            remote_cols=["id"],
            referent_schema=_INVOICE_SCHEMA,
            ondelete="SET NULL",
        )
    if not _has_index(_SHIPMENTS, _IX_SHIPMENT):
        op.create_index(_IX_SHIPMENT, _SHIPMENTS, ["container_size_id"])

    # One PI per shipment: carry its choice over. A shipment consolidating several PIs is
    # left NULL - there is no single invoice's size to inherit (AC-E3).
    if _has_column(_INVOICE, "container_size_id", schema=_INVOICE_SCHEMA) and _has_table(
        "proforma_invoice_shipment_link", schema=_INVOICE_SCHEMA
    ):
        op.execute(
            sa.text(
                f"""
                UPDATE {_SHIPMENTS} s
                SET container_size_id = sub.container_size_id
                FROM (
                    SELECT l.inbound_shipment_id AS shipment_id,
                           MIN(pi.container_size_id::text)::uuid AS container_size_id
                    FROM {_INVOICE_SCHEMA}.proforma_invoice_shipment_link l
                    JOIN {_INVOICE_SCHEMA}.{_INVOICE} pi ON pi.id = l.proforma_invoice_id
                    GROUP BY l.inbound_shipment_id
                    HAVING COUNT(DISTINCT l.proforma_invoice_id) = 1
                ) sub
                WHERE s.id = sub.shipment_id
                """
            )
        )

    if _has_column(_INVOICE, "container_size_id", schema=_INVOICE_SCHEMA):
        op.drop_column(_INVOICE, "container_size_id", schema=_INVOICE_SCHEMA)


def downgrade() -> None:
    if not _has_column(_INVOICE, "container_size_id", schema=_INVOICE_SCHEMA):
        op.add_column(
            _INVOICE,
            sa.Column("container_size_id", UUID(as_uuid=False), nullable=True),
            schema=_INVOICE_SCHEMA,
        )
        op.create_foreign_key(
            "proforma_invoice_container_size_id_fkey",
            source_table=_INVOICE,
            referent_table="container_size",
            local_cols=["container_size_id"],
            remote_cols=["id"],
            source_schema=_INVOICE_SCHEMA,
            referent_schema=_INVOICE_SCHEMA,
            ondelete="SET NULL",
        )

        # Reverse the data step: a shipment with exactly one source invoice hands its size
        # back to that invoice.
        if _has_column(_SHIPMENTS, "container_size_id") and _has_table(
            "proforma_invoice_shipment_link", schema=_INVOICE_SCHEMA
        ):
            op.execute(
                sa.text(
                    f"""
                    UPDATE {_INVOICE_SCHEMA}.{_INVOICE} pi
                    SET container_size_id = sub.container_size_id
                    FROM (
                        SELECT l.proforma_invoice_id AS invoice_id,
                               MIN(s.container_size_id::text)::uuid AS container_size_id
                        FROM {_INVOICE_SCHEMA}.proforma_invoice_shipment_link l
                        JOIN {_SHIPMENTS} s ON s.id = l.inbound_shipment_id
                        GROUP BY l.proforma_invoice_id
                        HAVING COUNT(DISTINCT l.inbound_shipment_id) = 1
                    ) sub
                    WHERE pi.id = sub.invoice_id
                    """
                )
            )

    if _has_index(_SHIPMENTS, _IX_SHIPMENT):
        op.drop_index(_IX_SHIPMENT, table_name=_SHIPMENTS)
    if _has_fk(_SHIPMENTS, _FK_SHIPMENT):
        op.drop_constraint(_FK_SHIPMENT, _SHIPMENTS, type_="foreignkey")
    if _has_column(_SHIPMENTS, "container_size_id"):
        op.drop_column(_SHIPMENTS, "container_size_id")
