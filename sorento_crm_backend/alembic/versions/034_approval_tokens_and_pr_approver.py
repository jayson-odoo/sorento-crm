"""Add approver fields to purchase_requests and create approval_tokens table

Revision ID: 034_approval_tokens
Revises: 033_audit_logs
Create Date: E-sign / e-approval for purchase requests and sponsorship forms

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '034_approval_tokens'
down_revision = '033_audit_logs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('purchase_requests', sa.Column('approver_user_id', sa.String(100), nullable=True))
    op.add_column('purchase_requests', sa.Column('approver_email', sa.String(255), nullable=True))
    op.add_column('purchase_requests', sa.Column('approval_status', sa.String(50), nullable=True))
    op.add_column('purchase_requests', sa.Column('approved_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column('purchase_requests', sa.Column('approved_by', sa.Text(), nullable=True))
    op.add_column('purchase_requests', sa.Column('approval_signature_ref', sa.Text(), nullable=True))
    op.add_column('purchase_requests', sa.Column('approval_comments', sa.Text(), nullable=True))

    op.create_table(
        'approval_tokens',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(100), nullable=False),
        sa.Column('token', sa.String(255), nullable=False),
        sa.Column('expires', sa.DateTime(timezone=False), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_approval_tokens_token', 'approval_tokens', ['token'], unique=True)
    op.create_index('ix_approval_tokens_entity', 'approval_tokens', ['entity_type', 'entity_id'])


def downgrade() -> None:
    op.drop_index('ix_approval_tokens_entity', table_name='approval_tokens')
    op.drop_index('ix_approval_tokens_token', table_name='approval_tokens')
    op.drop_table('approval_tokens')

    op.drop_column('purchase_requests', 'approval_comments')
    op.drop_column('purchase_requests', 'approval_signature_ref')
    op.drop_column('purchase_requests', 'approved_by')
    op.drop_column('purchase_requests', 'approved_at')
    op.drop_column('purchase_requests', 'approval_status')
    op.drop_column('purchase_requests', 'approver_email')
    op.drop_column('purchase_requests', 'approver_user_id')
