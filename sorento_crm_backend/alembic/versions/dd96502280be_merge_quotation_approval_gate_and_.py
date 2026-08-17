"""merge quotation approval gate and changes requested

Revision ID: dd96502280be
Revises: 330_quotation_approval_gate, 330_quotation_changes_req
Create Date: 2026-08-06 10:32:46.694655

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dd96502280be'
down_revision = ('330_quotation_approval_gate', '330_quotation_changes_req')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
