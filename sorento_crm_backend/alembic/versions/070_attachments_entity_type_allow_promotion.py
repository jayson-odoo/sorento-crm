"""Allow entity_type='promotion' on attachments (fix check constraint).

Revision ID: 070_entity_type_promotion
Revises: 069_promotion_attachment_type
Create Date: 2026-02-28

"""
from alembic import op
from sqlalchemy import text


revision = "070_entity_type_promotion"
down_revision = "069_promotion_attachment_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing check so we can add one that includes 'promotion'.
    op.execute(text("ALTER TABLE attachments DROP CONSTRAINT IF EXISTS attachments_entity_type_check"))
    # Allow NULL or any of the known entity types used by the app (including promotion).
    op.execute(
        text(
            "ALTER TABLE attachments ADD CONSTRAINT attachments_entity_type_check CHECK ("
            " entity_type IS NULL OR entity_type IN ("
            " 'product', 'promotion', 'complaint', 'general', 'complaint_document',"
            " 'order', 'stock_list', 'form', 'inbound_shipment'"
            " ))"
        )
    )


def downgrade() -> None:
    op.execute(text("ALTER TABLE attachments DROP CONSTRAINT IF EXISTS attachments_entity_type_check"))
    # Restore previous constraint (without 'promotion')
    op.execute(
        text(
            "ALTER TABLE attachments ADD CONSTRAINT attachments_entity_type_check CHECK ("
            " entity_type IS NULL OR entity_type IN ("
            " 'product', 'complaint', 'general', 'complaint_document',"
            " 'order', 'stock_list', 'form', 'inbound_shipment'"
            " ))"
        )
    )
