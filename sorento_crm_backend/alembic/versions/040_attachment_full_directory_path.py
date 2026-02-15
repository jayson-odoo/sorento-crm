"""Add full_directory_path to attachments for AI agent discovery

Revision ID: 040_attachment_full_directory_path
Revises: 039_agent_teams_code
Create Date: Store full path (e.g. SORENTO CABANA --> SORENTO --> Product Photo --> Angle Valve)

"""
from alembic import op
import sqlalchemy as sa


revision = '040_attachment_full_dir_path'
down_revision = '039_agent_teams_code'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'attachments',
        sa.Column('full_directory_path', sa.Text(), nullable=True),
    )

    # Backfill: compute full path for all attachments with directory_id
    # Using a recursive CTE to walk from each attachment's directory up to root
    # Cast name to TEXT so non-recursive and recursive terms have matching types (varchar(255) vs varchar)
    op.execute("""
        WITH RECURSIVE dir_path AS (
            SELECT id, name, parent_id, name::TEXT AS path
            FROM attachment_directories
            WHERE parent_id IS NULL

            UNION ALL

            SELECT d.id, d.name, d.parent_id,
                   CONCAT(p.path, ' --> ', d.name)
            FROM attachment_directories d
            JOIN dir_path p ON d.parent_id = p.id
        )
        UPDATE attachments a
        SET full_directory_path = dp.path
        FROM dir_path dp
        WHERE a.directory_id = dp.id
    """)


def downgrade() -> None:
    op.drop_column('attachments', 'full_directory_path')
