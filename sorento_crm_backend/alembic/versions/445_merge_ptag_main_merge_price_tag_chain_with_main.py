"""Merge the price tag request chain with main.

Revision ID: 445_merge_ptag_main
Revises: 444_notify_email_on_mention, ptag_0003
Create Date: 2026-08-30

Empty on purpose. The price tag branch forked at `415_merge_pset_pushidea`, added
`ptag_0001` .. `ptag_0003` behind its own merge point `a67d68a2ed9a`, and main has
grown 41 revisions since. Neither side touches a table the other one does, so the
two chains only need one head again.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '445_merge_ptag_main'
down_revision = ('444_notify_email_on_mention', 'ptag_0003')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
