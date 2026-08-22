"""planning change batches and rows

Revision ID: 29d85dc3ccc3
Revises: 392_schedule_highlight_and_proposals
Create Date: 2026-08-19 08:18:37.237044

`documentation/plans/scm/PLAN-so-book-diff-replanning.md` section 2. Hand-trimmed from the
autogenerate diff: the local DB is a prod copy that drifts ahead of `alembic_version` (see
`sorento_crm_backend/CLAUDE.md`), so the raw diff carried ~3900 lines of unrelated drift
across `scm`/`projects` company-id constraints. Only the two new tables below are this
revision's own change.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '29d85dc3ccc3'
down_revision = '392_schedule_highlight_and_proposals'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'planning_change_batches',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('import_job_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('upload_file_name', sa.String(length=255), nullable=True),
        sa.Column('source_kind', sa.String(length=32), server_default='so_book_upload', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('applied_at', sa.DateTime(), nullable=True),
        sa.Column('applied_by', sa.String(length=100), nullable=True),
        sa.Column('order_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('line_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('result_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('company_id', sa.UUID(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(['applied_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['import_job_id'], ['import_jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='projects',
    )
    op.create_index('ix_planning_change_batches_created_at', 'planning_change_batches', ['created_at'], unique=False, schema='projects')
    op.create_index(op.f('ix_projects_planning_change_batches_company_id'), 'planning_change_batches', ['company_id'], unique=False, schema='projects')

    op.create_table(
        'planning_change_rows',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('batch_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('project_sales_order_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('project_line_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('core_line_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('line_no', sa.Integer(), nullable=True),
        sa.Column('item_code', sa.String(length=120), nullable=True),
        sa.Column('product_name', sa.String(length=255), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('from_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('to_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('days_moved', sa.Integer(), nullable=True),
        sa.Column('held_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('facts_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('inquiry_rows_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('suggested', sa.String(length=16), nullable=False),
        sa.Column('why', sa.Text(), nullable=False),
        sa.Column('proposal_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('decision', sa.String(length=16), nullable=True),
        sa.Column('applied_state', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('applied_reason', sa.Text(), nullable=True),
        sa.Column('board_link', sa.Text(), server_default='', nullable=False),
        sa.Column('result_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('company_id', sa.UUID(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['projects.planning_change_batches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['core_line_id'], ['sales_order_lines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_line_id'], ['projects.sales_order_lines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_sales_order_id'], ['projects.sales_orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='projects',
    )
    op.create_index('ix_planning_change_rows_batch', 'planning_change_rows', ['batch_id'], unique=False, schema='projects')
    op.create_index('ix_planning_change_rows_order', 'planning_change_rows', ['project_sales_order_id'], unique=False, schema='projects')
    op.create_index(op.f('ix_projects_planning_change_rows_company_id'), 'planning_change_rows', ['company_id'], unique=False, schema='projects')


def downgrade() -> None:
    op.drop_index(op.f('ix_projects_planning_change_rows_company_id'), table_name='planning_change_rows', schema='projects')
    op.drop_index('ix_planning_change_rows_order', table_name='planning_change_rows', schema='projects')
    op.drop_index('ix_planning_change_rows_batch', table_name='planning_change_rows', schema='projects')
    op.drop_table('planning_change_rows', schema='projects')
    op.drop_index(op.f('ix_projects_planning_change_batches_company_id'), table_name='planning_change_batches', schema='projects')
    op.drop_index('ix_planning_change_batches_created_at', table_name='planning_change_batches', schema='projects')
    op.drop_table('planning_change_batches', schema='projects')
