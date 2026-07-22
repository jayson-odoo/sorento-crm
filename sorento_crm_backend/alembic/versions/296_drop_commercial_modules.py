"""Drop the commercial_core / commercial_activity modules.

The modules were never used: every one of the 23 tables holds 0 rows, no
frontend pages were ever built (the sidebar entries pointed at routes that do
not exist), `tenant_modules` has no commercial row, and `api_call_log` records
no traffic to any commercial endpoint.

They were also actively harmful to keep: the ORM models declared 50 columns that
no migration ever created (commercial_projects 19, commercial_master_quotations
17, commercial_leads 6, commercial_tenders 6, commercial_quotation_revisions 2),
so the models did not describe the real schema. That drift blocked using the
models as a source of truth for building a test/CI database.

Drops the tables and the 45 `commercial_*` permission rows. Downgrade is
intentionally not supported — recreating empty tables whose model definitions
have been deleted would serve no purpose.

Revision ID: 296_drop_commercial_modules
Revises: 295_drop_mcp_tool_ownership
"""
from alembic import op

revision = "296_drop_commercial_modules"
down_revision = "295_drop_mcp_tool_ownership"
branch_labels = None
depends_on = None


# Dropped with CASCADE so inter-table FKs do not dictate ordering.
COMMERCIAL_TABLES = [
    "commercial_activity_plan_applications",
    "commercial_activity_task_statuses",
    "commercial_activity_template_nodes",
    "commercial_activity_templates",
    "commercial_lead_notes",
    "commercial_lead_respond_contacts",
    "commercial_leads",
    "commercial_master_quotation_activities",
    "commercial_master_quotations",
    "commercial_process_settings",
    "commercial_project_customers",
    "commercial_project_leads",
    "commercial_project_task_categories",
    "commercial_project_tasks",
    "commercial_projects",
    "commercial_quotation_activity_tasks",
    "commercial_quotation_revisions",
    "commercial_reminder_defaults",
    "commercial_sales_orders",
    "commercial_tasks",
    "commercial_tender_checkpoint_templates",
    "commercial_tender_milestones",
    "commercial_tenders",
]


def upgrade():
    for table in COMMERCIAL_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # Role grants first (FK to user_permissions), then the permissions.
    op.execute(
        "DELETE FROM user_role_permissions WHERE permission_id IN "
        "(SELECT id FROM user_permissions WHERE slug LIKE 'commercial\\_%')"
    )
    op.execute("DELETE FROM user_permissions WHERE slug LIKE 'commercial\\_%'")

    # App-Store rows, if this tenant ever had them.
    op.execute("DELETE FROM tenant_modules WHERE module_key IN ('commercial_core', 'commercial_activity')")
    op.execute("DELETE FROM app_modules_catalog WHERE module_key IN ('commercial_core', 'commercial_activity')")


def downgrade():
    """Not supported — the module code and models were deleted alongside this."""
    raise NotImplementedError(
        "commercial_core / commercial_activity were removed permanently; "
        "restore the module packages from git history before re-adding the schema."
    )
