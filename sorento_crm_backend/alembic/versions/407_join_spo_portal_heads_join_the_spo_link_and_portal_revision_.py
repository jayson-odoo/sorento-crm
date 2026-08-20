"""join the spo link and portal revision heads

Revision ID: 407_join_spo_portal_heads
Revises: 406_scm_shipment_spo_link, b6d2f4a8c7e1
Create Date: 2026-08-21 00:42:33.427822

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '407_join_spo_portal_heads'
down_revision = ('406_scm_shipment_spo_link', 'b6d2f4a8c7e1')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
