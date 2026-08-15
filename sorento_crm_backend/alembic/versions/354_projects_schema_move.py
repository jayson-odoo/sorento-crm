"""Move the projects module's 47 tables into the `projects` schema, dropping the prefix.

ADR-0011 (superseding the schema clause of ADR-0009): the boundary between core CRM and an
installable module is now visible in the database itself, the same way `scm` is. The schema
name is the module key. The `project_` table-name prefix existed to say "this belongs to
the projects module" in a shared namespace; the schema says that now, and saying it twice
would produce `projects.project_quotation_lines`. So 34 tables drop the prefix and 13 keep
their bare name, changing only schema.

**Indexes and constraints are deliberately NOT renamed.** `ALTER TABLE ... SET SCHEMA`
carries them along unchanged, so `projects.parties` keeps indexes named
`ix_project_parties_*`. This is the one place this revision differs from 353, which HAD to
rename them because a rename inside one schema leaves the index names behind. Renaming
200-odd live objects here would add risk for cosmetics. A future autogenerate diff will not
report it as drift, because alembic does not compare index NAMES it did not author; a human
reading `\\d projects.parties` will see it, and this paragraph is the answer.

Every step is guarded on "the source is there and the destination is not", so the revision
no-ops on a database built by `create_all` from the post-move models and does the work on
one built before the move. `downgrade()` is the exact inverse and leaves the (empty)
`projects` schema in place: other objects may land there later, and dropping it would make
the downgrade destructive rather than symmetric.

Neither schema name is a literal in the ALTER statements. `TARGET_SCHEMA` is a module-level
constant and the source is read from `current_schema()` at run time, so the dual-path test
can rebind both to a scratch schema pair. Hardcoding `public` would make that test move the
REAL tables.

Revision ID: 354_projects_schema_move
Revises: 353_project_order_inquiry_rename
"""
from alembic import op
import sqlalchemy as sa

revision = "354_projects_schema_move"
down_revision = "353_project_order_inquiry_rename"
branch_labels = None
depends_on = None


#: Rebound by the migration test to a scratch schema. Never inline this.
TARGET_SCHEMA = "projects"

# (name before the move, name after). Where the two are equal the table only changes
# schema: those 13 never carried the prefix (the 12 legacy tables named in ADR-0009, plus
# the registration table `projects` itself, which has no prefix to drop).
TABLES = (
    ("project_parties", "parties"),
    ("project_types", "types"),
    ("project_templates", "templates"),
    ("project_template_roles", "template_roles"),
    ("projects", "projects"),
    ("project_sales_profile", "sales_profile"),
    ("project_brands", "brands"),
    ("project_stakeholders", "stakeholders"),
    ("project_collaborators", "collaborators"),
    ("project_takeover_requests", "takeover_requests"),
    ("project_template_tasks", "template_tasks"),
    ("project_tasks", "tasks"),
    ("project_leads", "leads"),
    ("project_series", "series"),
    ("project_series_categories", "series_categories"),
    ("project_series_products", "series_products"),
    ("price_floor_rules", "price_floor_rules"),
    ("project_quotation_documents", "quotation_documents"),
    ("quotation_templates", "quotation_templates"),
    ("project_quotation_issues", "quotation_issues"),
    ("quotation_signatures", "quotation_signatures"),
    ("project_quotation_issue_scopes", "quotation_issue_scopes"),
    ("project_quotations", "quotations"),
    ("project_quotation_versions", "quotation_versions"),
    ("project_quotation_lines", "quotation_lines"),
    ("project_samples", "samples"),
    ("project_purchase_orders", "purchase_orders"),
    ("project_purchase_order_lines", "purchase_order_lines"),
    ("project_po_versions", "po_versions"),
    ("project_po_lines", "po_lines"),
    ("project_po_annotations", "po_annotations"),
    ("delivery_schedules", "delivery_schedules"),
    ("delivery_schedule_versions", "delivery_schedule_versions"),
    ("project_delivery_phases", "delivery_phases"),
    ("delivery_schedule_cells", "delivery_schedule_cells"),
    ("customer_item_code_map", "customer_item_code_map"),
    ("project_sales_orders", "sales_orders"),
    ("project_sales_order_lines", "sales_order_lines"),
    ("so_draft_findings", "so_draft_findings"),
    ("order_change_notices", "order_change_notices"),
    ("so_amendments", "so_amendments"),
    ("project_order_inquiries", "order_inquiries"),
    ("project_order_inquiry_rows", "order_inquiry_rows"),
    ("so_line_allocations", "so_line_allocations"),
    ("allocation_claims", "allocation_claims"),
    ("project_so_divergences", "so_divergences"),
    ("project_so_divergence_lines", "so_divergence_lines"),
)


def _source_schema() -> str:
    """Where the tables are BEFORE the move: `public` in production, the scratch schema
    under test. Read rather than assumed, so the test cannot reach the real database."""
    return op.get_bind().execute(sa.text("SELECT current_schema()")).scalar()


def _has_table(schema: str, name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name, schema=schema)


def upgrade() -> None:
    source = _source_schema()
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{TARGET_SCHEMA}"')

    for old, new in TABLES:
        if _has_table(TARGET_SCHEMA, new):
            continue  # already moved and renamed
        if _has_table(source, old) and not _has_table(TARGET_SCHEMA, old):
            op.execute(f'ALTER TABLE "{source}"."{old}" SET SCHEMA "{TARGET_SCHEMA}"')
        # Separately guarded, so a run interrupted between the two steps resumes here.
        if old != new and _has_table(TARGET_SCHEMA, old):
            op.execute(f'ALTER TABLE "{TARGET_SCHEMA}"."{old}" RENAME TO "{new}"')


def downgrade() -> None:
    source = _source_schema()

    for old, new in TABLES:
        if _has_table(source, old):
            continue  # already back
        if old != new and _has_table(TARGET_SCHEMA, new) and not _has_table(TARGET_SCHEMA, old):
            op.execute(f'ALTER TABLE "{TARGET_SCHEMA}"."{new}" RENAME TO "{old}"')
        if _has_table(TARGET_SCHEMA, old):
            op.execute(f'ALTER TABLE "{TARGET_SCHEMA}"."{old}" SET SCHEMA "{source}"')

    # The schema itself stays. Dropping it would make downgrade destructive of anything
    # else that lands there, and leaving it empty keeps this revision idempotent.
