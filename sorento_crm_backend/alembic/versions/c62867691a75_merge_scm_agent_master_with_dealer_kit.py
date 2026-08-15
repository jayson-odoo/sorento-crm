"""Merge the SCM agent-master chain with the dealer-kit chain.

The Dealer Kit epic (PR #57) merged to main while this branch was in flight; both chains
now coexist and CI's bootstrap refuses to stamp on multiple heads. No DDL by construction.

Revision ID: c62867691a75
Revises: 357_scm_so_agent_aliases, 322_merge_dealer_kit_customers
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c62867691a75'
down_revision = ('357_scm_so_agent_aliases', '322_merge_dealer_kit_customers')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
