"""merge project sales and main heads

Revision ID: dcb151730340
Revises: 1095ff13d8f4, 7cc13b71908c
Create Date: 2026-08-13 19:06:07.467860

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dcb151730340'
down_revision = ('1095ff13d8f4', '7cc13b71908c')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
