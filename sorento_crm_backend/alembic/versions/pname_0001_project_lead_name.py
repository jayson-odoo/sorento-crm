"""PROJECT-NAME: a short project name on projects and leads.

Owner ruling 10 Nov: the project header shows a short NAME, the long legal title moves into the
Overview "The development" card. Two nullable VARCHAR(80) columns, additive only: no default, no
backfill (the one-off AI backfill is `scripts/backfill_project_names.py`, dry run first), no
index (the list search is a LIKE over a few thousand rows), not unique and not in the
registration lock (card Q4).

Plan: documentation/plans/projects/PLAN-project-name-10nov.md.

Revision ID: pname_0001_project_lead_name
Revises: ptag_0021_icon_conditions
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "pname_0001_project_lead_name"
down_revision = "ptag_0021_icon_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE projects.projects ADD COLUMN IF NOT EXISTS name VARCHAR(80)")
    op.execute("ALTER TABLE projects.leads ADD COLUMN IF NOT EXISTS name VARCHAR(80)")


def downgrade() -> None:
    op.execute("ALTER TABLE projects.leads DROP COLUMN IF EXISTS name")
    op.execute("ALTER TABLE projects.projects DROP COLUMN IF EXISTS name")
