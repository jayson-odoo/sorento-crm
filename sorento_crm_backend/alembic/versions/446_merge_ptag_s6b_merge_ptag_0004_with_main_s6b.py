"""Merge the price tag request chain with main's S6b (deferred actions).

Revision ID: 446_merge_ptag_s6b
Revises: ptag_0004, s6b_record_action_entity_id
Create Date: 2026-08-31

Empty on purpose. `ptag_0004` (assigned_to) forked from `445_merge_ptag_main`,
main grew five more revisions (Apple alignment S4-S6b + scm ladder v7.1 S3)
ending at `s6b_record_action_entity_id`. Neither side touches a table the
other one does, so the two chains only need one head again.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '446_merge_ptag_s6b'
down_revision = ('ptag_0004', 's6b_record_action_entity_id')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
