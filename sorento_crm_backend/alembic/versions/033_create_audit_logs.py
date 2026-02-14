"""Create audit_logs table for system-wide change tracking

Revision ID: 033_audit_logs
Revises: 032_sla_source_entity
Create Date: Audit trail for complaints, stock inquiries, purchase requests, etc.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = '033_audit_logs'
down_revision = '032_sla_source_entity'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Idempotent: skip if table already exists (e.g. created manually or partial run)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'audit_logs'"
    ))
    if result.scalar() is None:
        op.create_table(
            'audit_logs',
            sa.Column('id', UUID(as_uuid=False), primary_key=True),
            sa.Column('entity_type', sa.String(100), nullable=False),
            sa.Column('entity_id', sa.String(100), nullable=False),
            sa.Column('action', sa.String(20), nullable=False),
            sa.Column('user_id', sa.String(100), nullable=True),
            sa.Column('changed_at', sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
            sa.Column('old_values', JSONB, nullable=True),
            sa.Column('new_values', JSONB, nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('ip_address', sa.String(100), nullable=True),
        )
    else:
        # Table exists (e.g. partial run or old schema): ensure all columns exist
        for col_sql in [
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS changed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS entity_type VARCHAR(100)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS entity_id VARCHAR(100)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS action VARCHAR(20)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_id VARCHAR(100)",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS old_values JSONB",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS new_values JSONB",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS description TEXT",
            "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ip_address VARCHAR(100)",
        ]:
            conn.execute(sa.text(col_sql))
        # changed_at may have been added without NOT NULL default; ensure default exists
        conn.execute(sa.text(
            "ALTER TABLE audit_logs ALTER COLUMN changed_at SET DEFAULT now()"
        ))
    # Create indexes only if they don't exist
    for index_name, columns in [
        ('ix_audit_logs_entity_type', ['entity_type']),
        ('ix_audit_logs_entity_id', ['entity_id']),
        ('ix_audit_logs_entity_type_entity_id', ['entity_type', 'entity_id']),
        ('ix_audit_logs_changed_at', ['changed_at']),
        ('ix_audit_logs_user_id', ['user_id']),
    ]:
        result = conn.execute(sa.text(
            "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"
        ), {"name": index_name})
        if result.scalar() is None:
            op.create_index(index_name, 'audit_logs', columns)


def downgrade() -> None:
    op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_changed_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_entity_type_entity_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_entity_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_entity_type', table_name='audit_logs')
    op.drop_table('audit_logs')
