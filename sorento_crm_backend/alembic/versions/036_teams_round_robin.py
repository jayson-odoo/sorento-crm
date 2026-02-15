"""Add teams, team_members, agent_teams, agent_team_round_robin_cursors

Revision ID: 036_teams_round_robin
Revises: 035_attachment_directories
Create Date: Agent-team-person decoupling and round-robin assignee for n8n

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '036_teams_round_robin'
down_revision = '035_attachment_directories'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'teams',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_teams_name', 'teams', ['name'])

    op.create_table(
        'team_members',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('team_id', UUID(as_uuid=False), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(100), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sort_order', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_team_members_team_id', 'team_members', ['team_id'])
    op.create_index('ix_team_members_user_id', 'team_members', ['user_id'])
    op.create_unique_constraint('uq_team_members_team_user', 'team_members', ['team_id', 'user_id'])

    op.create_table(
        'agent_teams',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('agent_id', UUID(as_uuid=False), sa.ForeignKey('access_agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('team_id', UUID(as_uuid=False), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_agent_teams_agent_id', 'agent_teams', ['agent_id'])
    op.create_index('ix_agent_teams_team_id', 'agent_teams', ['team_id'])
    op.create_unique_constraint('uq_agent_teams_agent_team', 'agent_teams', ['agent_id', 'team_id'])

    op.create_table(
        'agent_team_round_robin_cursors',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('agent_id', UUID(as_uuid=False), sa.ForeignKey('access_agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('team_id', UUID(as_uuid=False), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('last_assigned_user_id', sa.String(100), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=False), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('agent_id', 'team_id', name='uq_agent_team_cursor'),
    )
    op.create_index('ix_agent_team_round_robin_cursors_agent_team', 'agent_team_round_robin_cursors', ['agent_id', 'team_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_agent_team_round_robin_cursors_agent_team', table_name='agent_team_round_robin_cursors')
    op.drop_table('agent_team_round_robin_cursors')
    op.drop_constraint('uq_agent_teams_agent_team', 'agent_teams', type_='unique')
    op.drop_index('ix_agent_teams_team_id', table_name='agent_teams')
    op.drop_index('ix_agent_teams_agent_id', table_name='agent_teams')
    op.drop_table('agent_teams')
    op.drop_constraint('uq_team_members_team_user', 'team_members', type_='unique')
    op.drop_index('ix_team_members_user_id', table_name='team_members')
    op.drop_index('ix_team_members_team_id', table_name='team_members')
    op.drop_table('team_members')
    op.drop_index('ix_teams_name', table_name='teams')
    op.drop_table('teams')
