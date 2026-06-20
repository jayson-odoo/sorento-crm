"""merge sla-epic (236) + attachment-storage (234b) heads

Revision ID: 932195fa2398
Revises: 234_attachment_storage_status, 236_seed_sla_kpi_view_perm
Create Date: 2026-06-20 15:35:34.887552

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '932195fa2398'
down_revision = ('234_attachment_storage_status', '236_seed_sla_kpi_view_perm')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
