"""S13d: the trajectory windows become planning-policy configuration, from day 1.

> "we should make things configurable from day 1, not later"   (user, 2026-08-10)

Two nullable columns on `scm.reorder_policy`. NULL means "use the code default" (retail 3
months, project 12 - `app.services.scm.trajectory`), so existing policies keep behaving and
a tenant that plans on different horizons changes a row, not the code. Same shape as
`level_study_months` / `level_cover_months` beside them.

Revision ID: 348_scm_trajectory_windows
Revises: 347_scm_reorder_level_upload
"""
import sqlalchemy as sa
from alembic import op

revision = "348_scm_trajectory_windows"
down_revision = "347_scm_reorder_level_upload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reorder_policy",
        sa.Column("trajectory_window_retail_months", sa.Integer, nullable=True),
        schema="scm",
    )
    op.add_column(
        "reorder_policy",
        sa.Column("trajectory_window_project_months", sa.Integer, nullable=True),
        schema="scm",
    )


def downgrade() -> None:
    op.drop_column("reorder_policy", "trajectory_window_project_months", schema="scm")
    op.drop_column("reorder_policy", "trajectory_window_retail_months", schema="scm")
