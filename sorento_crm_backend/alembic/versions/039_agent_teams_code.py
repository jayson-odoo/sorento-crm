"""Add code to agent_teams for context-based assignments

Revision ID: 039_agent_teams_code
Revises: 038_attachments_sort_order
Create Date: Agent-team assignments with code (e.g. marketing -> Marketing Team)

"""
from alembic import op
import sqlalchemy as sa


revision = '039_agent_teams_code'
down_revision = '038_attachments_sort_order'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add code column (nullable initially for backfill)
    op.add_column(
        'agent_teams',
        sa.Column('code', sa.Text(), nullable=True),
    )
    # Backfill: use team_id as code for existing rows (unique per agent+team)
    op.execute("""
        UPDATE agent_teams
        SET code = team_id
        WHERE code IS NULL
    """)
    op.alter_column(
        'agent_teams',
        'code',
        existing_type=sa.Text(),
        nullable=False,
    )
    # Drop old unique, add new unique on (agent_id, code)
    op.drop_constraint('uq_agent_teams_agent_team', 'agent_teams', type_='unique')
    op.create_unique_constraint('uq_agent_teams_agent_code', 'agent_teams', ['agent_id', 'code'])
    op.create_index('ix_agent_teams_code', 'agent_teams', ['code'])


def downgrade() -> None:
    op.drop_index('ix_agent_teams_code', table_name='agent_teams')
    op.drop_constraint('uq_agent_teams_agent_code', 'agent_teams', type_='unique')
    op.create_unique_constraint('uq_agent_teams_agent_team', 'agent_teams', ['agent_id', 'team_id'])
    op.drop_column('agent_teams', 'code')
