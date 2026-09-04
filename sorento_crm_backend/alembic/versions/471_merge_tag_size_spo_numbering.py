"""merge tag_size_preset + seed_crm_spo_numbering heads

462_tag_size_preset (#625) forked from 464_overdue_grace, which
468_merge_overdue_grace_desc, 469_shipment_spo_link_not_unique and
470_seed_crm_spo_numbering (#632, #636) had already merged past, leaving two
alembic heads on main. This no-op merge restores a single head.

Revision ID: 471_merge_tag_size_spo_numbering
Revises: 462_tag_size_preset, 470_seed_crm_spo_numbering
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "471_merge_tag_size_spo_numbering"
down_revision = ("462_tag_size_preset", "470_seed_crm_spo_numbering")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
