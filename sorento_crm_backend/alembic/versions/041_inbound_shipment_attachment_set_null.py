"""Inbound shipment attachment_id: SET NULL on delete, nullable

When an attachment is permanently deleted, set inbound_shipments.attachment_id to NULL
instead of blocking the delete (RESTRICT).

Revision ID: 041_inbound_shipment_attachment_set_null
Revises: 040_attachment_full_directory_path
Create Date: Allow attachment delete; inbound shipment keeps record, attachment_id becomes null

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '041_inbound_attach_setnull'
down_revision = '040_attachment_full_dir_path'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Make attachment_id nullable
    op.alter_column(
        'inbound_shipments',
        'attachment_id',
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=True,
    )
    # 2. Drop existing FK (RESTRICT) and create new one with SET NULL
    op.drop_constraint(
        'inbound_shipments_attachment_id_fkey',
        'inbound_shipments',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'inbound_shipments_attachment_id_fkey',
        'inbound_shipments',
        'attachments',
        ['attachment_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'inbound_shipments_attachment_id_fkey',
        'inbound_shipments',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'inbound_shipments_attachment_id_fkey',
        'inbound_shipments',
        'attachments',
        ['attachment_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    # Revert nullable - will fail if any rows have NULL attachment_id
    op.alter_column(
        'inbound_shipments',
        'attachment_id',
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=False,
    )
