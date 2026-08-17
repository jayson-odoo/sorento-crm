"""merge shipment line supplier with proj media flyer

Revision ID: 375_merge_shipment_supplier
Revises: 374_merge_proj_media_flyer, 374_shipment_line_supplier
Create Date: 2026-08-17 22:02:51.822472

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '375_merge_shipment_supplier'
down_revision = ('374_merge_proj_media_flyer', '374_shipment_line_supplier')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
