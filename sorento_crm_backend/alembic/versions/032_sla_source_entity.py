"""Add source_entity_type and source_entity_id to conversation_sla_tracking

Revision ID: 032_sla_source_entity
Revises: 031_inquiry_complaint
Create Date: Link SLA tracking to stock_inquiry/complaint for Update & Reply

"""
from alembic import op
import sqlalchemy as sa


revision = '032_sla_source_entity'
down_revision = '031_inquiry_complaint'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'conversation_sla_tracking',
        sa.Column('source_entity_type', sa.String(50), nullable=True),
    )
    op.add_column(
        'conversation_sla_tracking',
        sa.Column('source_entity_id', sa.String(100), nullable=True),
    )
    op.create_index(
        'ix_conversation_sla_tracking_source_entity',
        'conversation_sla_tracking',
        ['source_entity_type', 'source_entity_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_conversation_sla_tracking_source_entity', table_name='conversation_sla_tracking')
    op.drop_column('conversation_sla_tracking', 'source_entity_id')
    op.drop_column('conversation_sla_tracking', 'source_entity_type')
