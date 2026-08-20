"""Allow `supplier_stock_list` as an attachment entity_type.

The loading-plan supplier stock list is now retained as an attachment on apply (best-effort,
after the inventory rows already committed - see `supplier_inventory_service.
store_stock_list_attachment`), keyed `entity_type='supplier_stock_list', entity_id=<supplier_id>`
so it is previewable through the same routes and modal Resource Management uses. Without this
value in the CHECK the insert 400s with `attachments_entity_type_check`, and the best-effort
catch swallows it - the apply still succeeds, it just never keeps a copy.

Rebuilt rather than extended in place, same as 326: Postgres has no "add a value to a CHECK".

Revision ID: 402_attachments_entity_type_allow_supplier_stock_list
Revises: 401_so_class_segment_rank
"""
from alembic import op
from sqlalchemy import text


revision = "402_attachments_entity_type_allow_supplier_stock_list"
down_revision = "401_so_class_segment_rank"
branch_labels = None
depends_on = None

_BEFORE = (
    "product",
    "promotion",
    "complaint",
    "general",
    "complaint_document",
    "order",
    "stock_list",
    "form",
    "inbound_shipment",
    "dealer_kit_asset",
    "project",
    "project_lead",
)
_ADDED = ("supplier_stock_list",)


def _apply(values: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    op.execute(
        text("ALTER TABLE attachments DROP CONSTRAINT IF EXISTS attachments_entity_type_check")
    )
    op.execute(
        text(
            "ALTER TABLE attachments ADD CONSTRAINT attachments_entity_type_check CHECK ("
            f"entity_type IS NULL OR entity_type IN ({listed}))"
        )
    )


def upgrade() -> None:
    _apply(_BEFORE + _ADDED)


def downgrade() -> None:
    # Rows written meanwhile would violate the narrower constraint, so clear them first rather
    # than leaving the downgrade to fail halfway.
    op.execute(
        text("update attachments set entity_type = 'general' where entity_type = 'supplier_stock_list'")
    )
    _apply(_BEFORE)
