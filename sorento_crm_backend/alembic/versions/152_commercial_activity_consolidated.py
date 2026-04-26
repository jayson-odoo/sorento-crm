"""Commercial activity consolidated tables (templates, plans, project tasks).

Revision ID: 152_commercial_activity_consolidated
Revises: 151_commercial_core_consolidated

Folds ijm_icp_crm activity-related migrations into a single CREATE pass driven
off the SQLAlchemy model metadata. Depends on commercial_core tables (PR2)
because activity tables FK into commercial_master_quotations / commercial_projects.
"""
from __future__ import annotations

from alembic import op


revision = "152_commercial_activity_consolidated"
down_revision = "151_commercial_core_consolidated"
branch_labels = None
depends_on = None


COMMERCIAL_ACTIVITY_TABLES = (
    "commercial_activity_plan_applications",
    "commercial_activity_task_statuses",
    "commercial_activity_template_nodes",
    "commercial_activity_templates",
    "commercial_project_task_categories",
    "commercial_project_tasks",
    "commercial_quotation_activity_tasks",
)


def upgrade() -> None:
    import app.modules.commercial_core  # noqa: F401  - parent FKs
    import app.modules.commercial_activity  # noqa: F401
    from app.database import Base

    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in COMMERCIAL_ACTIVITY_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    import app.modules.commercial_core  # noqa: F401
    import app.modules.commercial_activity  # noqa: F401
    from app.database import Base

    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in COMMERCIAL_ACTIVITY_TABLES]
    Base.metadata.drop_all(bind=bind, tables=tables, checkfirst=True)
