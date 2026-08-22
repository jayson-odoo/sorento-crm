"""Move the projects module's 47 tables into the `projects` schema, dropping the prefix.

ADR-0011 (superseding the schema clause of ADR-0009): the boundary between core CRM and an
installable module is now visible in the database itself, the same way `scm` is. The schema
name is the module key. The `project_` table-name prefix existed to say "this belongs to
the projects module" in a shared namespace; the schema says that now, and saying it twice
would produce `projects.project_quotation_lines`. So 34 tables drop the prefix and 13 keep
their bare name, changing only schema.

**Derived index and constraint names ARE renamed, in both directions.** A table carries its
indexes and constraints through `SET SCHEMA` and `RENAME TO` unchanged, and two families of
name were DERIVED from where the table used to be, so leaving them would make a migrated
database disagree with a bootstrapped one about identifiers that alembic compares by name:

* **SQLAlchemy convention names.** An index with no name of its own is called
  `ix_%(column_0_label)s`, and a schema-qualified table folds its SCHEMA into that label.
  Declaring `schema="projects"` therefore renamed `ix_project_leads_company_id` to
  `ix_projects_leads_company_id` in `Base.metadata`, and `ix_projects_company_id` (on the
  table `projects`) to `ix_projects_projects_company_id`, while the database kept the old
  names. 46 of them, listed in `DERIVED_INDEXES`. Alembic compares indexes BY NAME, so
  every one is permanent autogenerate churn on a migrated database.
* **Postgres default names.** Postgres derives `<table>_pkey`, `<table>_<column>_fkey`,
  `<table>_<column>_key`, `<table>_<column>_check` and `<table>_<columns>_idx` from the
  table name at CREATE time and never revisits them. So a bootstrapped database calls the
  key of `projects.brands` `brands_pkey`, and a migrated one still calls it
  `project_brands_pkey`. Renamed by prefix, from the catalog, in `_reprefix_derived_names`.

Names the models spell out by hand (`ix_project_parties_name`,
`uq_projects_company_developer_title`) are NOT touched: the metadata and the catalog have
always agreed about those. They cannot be told apart from a convention name by looking at
the catalog - both are a single-column index called `ix_<pre-move table>_<column>` - which
is why `DERIVED_INDEXES` is an explicit list rather than a pattern, and why
`tests/test_migration_354_projects_schema_move.py` regenerates it from `Base.metadata` and
fails when the two drift.

The down direction has to do this whether or not it is cosmetic: index names are unique per
SCHEMA, so moving `projects.brands` back beside CORE `public.brands` while it still calls
its key `brands_pkey` is refused outright. Five of the seven colliding tables hit it.

Every step is guarded on "the source is there and the destination is not", so the revision
no-ops on a database built by `create_all` from the post-move models and does the work on
one built before the move. The name steps are guarded separately from the table steps, so a
database already moved by an earlier copy of this revision has its names unified on the next
`upgrade()` rather than being skipped. `downgrade()` leaves the (empty) `projects` schema in
place: other objects may land there later, and dropping it would make the downgrade
destructive rather than symmetric.

`upgrade()` also rewrites `lookup_bindings.table_name` for any row naming one of the 47
tables, because a binding is keyed by the SCHEMA-QUALIFIED table name
(`app/services/lookup_eligibility.py`) - otherwise a binding on core `purchase_orders.status`
would also police `projects.purchase_orders.status`. Only an exact match against one of the
47 pre-move names is rewritten, so a core table's binding is never touched.

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

# (name in the database before the move, name `Base.metadata` derives after it).
#
# These are the indexes SQLAlchemy names for you: `ix_%(column_0_label)s`, where a
# schema-qualified table folds its SCHEMA into the label. So `projects.leads` derives
# `ix_projects_leads_company_id` where `public.project_leads` derived
# `ix_project_leads_company_id`, and the table `projects` derives
# `ix_projects_projects_company_id` where it derived `ix_projects_company_id`.
#
# Spelled out rather than computed because a hand-named index has the SAME shape in the
# catalog (`ix_project_parties_name` is a single-column index called
# `ix_<pre-move table>_<column>` and must NOT be renamed). Only the models can tell the two
# apart, and `tests/test_migration_354_projects_schema_move.py` regenerates this list from
# them, so an `index=True` added or removed on a projects model fails there.
DERIVED_INDEXES = (
    ('ix_allocation_claims_company_id', 'ix_projects_allocation_claims_company_id'),
    ('ix_customer_item_code_map_company_id', 'ix_projects_customer_item_code_map_company_id'),
    ('ix_project_delivery_phases_company_id', 'ix_projects_delivery_phases_company_id'),
    ('ix_delivery_schedule_cells_company_id', 'ix_projects_delivery_schedule_cells_company_id'),
    ('ix_delivery_schedule_versions_company_id', 'ix_projects_delivery_schedule_versions_company_id'),
    ('ix_delivery_schedules_company_id', 'ix_projects_delivery_schedules_company_id'),
    ('ix_project_leads_company_id', 'ix_projects_leads_company_id'),
    ('ix_project_leads_owner_user_id', 'ix_projects_leads_owner_user_id'),
    ('ix_order_change_notices_company_id', 'ix_projects_order_change_notices_company_id'),
    ('ix_project_order_inquiries_company_id', 'ix_projects_order_inquiries_company_id'),
    ('ix_project_order_inquiry_rows_company_id', 'ix_projects_order_inquiry_rows_company_id'),
    ('ix_project_parties_company_id', 'ix_projects_parties_company_id'),
    ('ix_project_parties_party_type', 'ix_projects_parties_party_type'),
    ('ix_project_po_annotations_company_id', 'ix_projects_po_annotations_company_id'),
    ('ix_project_po_lines_company_id', 'ix_projects_po_lines_company_id'),
    ('ix_project_po_versions_company_id', 'ix_projects_po_versions_company_id'),
    ('ix_price_floor_rules_company_id', 'ix_projects_price_floor_rules_company_id'),
    ('ix_projects_admin_ref', 'ix_projects_projects_admin_ref'),
    ('ix_projects_company_id', 'ix_projects_projects_company_id'),
    ('ix_projects_owner_user_id', 'ix_projects_projects_owner_user_id'),
    ('ix_project_purchase_order_lines_company_id', 'ix_projects_purchase_order_lines_company_id'),
    ('ix_project_purchase_orders_company_id', 'ix_projects_purchase_orders_company_id'),
    ('ix_project_quotation_documents_company_id', 'ix_projects_quotation_documents_company_id'),
    ('ix_project_quotation_issue_scopes_company_id', 'ix_projects_quotation_issue_scopes_company_id'),
    ('ix_project_quotation_issues_company_id', 'ix_projects_quotation_issues_company_id'),
    ('ix_project_quotation_lines_company_id', 'ix_projects_quotation_lines_company_id'),
    ('ix_quotation_signatures_company_id', 'ix_projects_quotation_signatures_company_id'),
    ('ix_quotation_templates_company_id', 'ix_projects_quotation_templates_company_id'),
    ('ix_project_quotation_versions_company_id', 'ix_projects_quotation_versions_company_id'),
    ('ix_project_quotations_company_id', 'ix_projects_quotations_company_id'),
    ('ix_project_sales_order_lines_company_id', 'ix_projects_sales_order_lines_company_id'),
    ('ix_project_sales_orders_company_id', 'ix_projects_sales_orders_company_id'),
    ('ix_project_samples_company_id', 'ix_projects_samples_company_id'),
    ('ix_project_series_company_id', 'ix_projects_series_company_id'),
    ('ix_so_amendments_company_id', 'ix_projects_so_amendments_company_id'),
    ('ix_project_so_divergence_lines_company_id', 'ix_projects_so_divergence_lines_company_id'),
    ('ix_project_so_divergences_company_id', 'ix_projects_so_divergences_company_id'),
    ('ix_so_draft_findings_company_id', 'ix_projects_so_draft_findings_company_id'),
    ('ix_so_line_allocations_company_id', 'ix_projects_so_line_allocations_company_id'),
    ('ix_project_stakeholders_company_id', 'ix_projects_stakeholders_company_id'),
    ('ix_project_tasks_assignee_user_id', 'ix_projects_tasks_assignee_user_id'),
    ('ix_project_tasks_company_id', 'ix_projects_tasks_company_id'),
    ('ix_project_template_roles_company_id', 'ix_projects_template_roles_company_id'),
    ('ix_project_template_tasks_company_id', 'ix_projects_template_tasks_company_id'),
    ('ix_project_templates_company_id', 'ix_projects_templates_company_id'),
    ('ix_project_types_company_id', 'ix_projects_types_company_id'),
)

#: Postgres truncates an identifier past this many bytes without saying so, which would
#: leave a name that matches neither end of the rename.
_MAX_IDENTIFIER_BYTES = 63


def _assert_identifiers_fit() -> None:
    too_long = sorted(
        {
            name
            for pair in DERIVED_INDEXES
            for name in pair
            if len(name.encode("utf-8")) > _MAX_IDENTIFIER_BYTES
        }
    )
    if too_long:
        raise RuntimeError(
            "these index names exceed the Postgres identifier limit and would be "
            f"silently truncated: {too_long}"
        )


def _source_schema() -> str:
    """Where the tables are BEFORE the move: `public` in production, the scratch schema
    under test. Read rather than assumed, so the test cannot reach the real database."""
    schema = op.get_bind().execute(sa.text("SELECT current_schema()")).scalar()
    if not schema:
        # A NULL current_schema() means the search_path names nothing that exists. Every
        # ALTER below would then be built against the string "None" and fail somewhere
        # unrecognisable; say so here instead.
        raise RuntimeError(
            "current_schema() is NULL - the connection's search_path resolves to no "
            "existing schema, so this revision cannot tell where the tables are"
        )
    return schema


def _has_table(schema: str, name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name, schema=schema)


def _has_index(schema: str, name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relname = :name AND c.relkind IN ('i','I')"
            ),
            {"schema": schema, "name": name},
        )
        .scalar()
    )


def _rename_index(schema: str, frm: str, to: str) -> None:
    """Rename one index, if it is there and the destination name is free.

    Both halves of the guard matter. On a database built by ``create_all`` the source is
    absent (the name is already the metadata one), and on a database this revision has
    already run the destination is present - either way this is a no-op, which is what
    makes the revision repeatable in both directions.
    """
    if frm == to:
        return
    if not _has_index(schema, frm):
        return
    if _has_index(schema, to):
        # Both names present means two distinct indexes, not a completed rename. Skipping
        # would leave the pre-move name in place and report success, which is the silent
        # catalog drift this revision exists to remove.
        raise RuntimeError(
            f'cannot rename index "{schema}"."{frm}" to "{to}": both already exist'
        )
    op.execute(f'ALTER INDEX "{schema}"."{frm}" RENAME TO "{to}"')


def _derived_names(schema: str, table: str, stem: str):
    """Constraints and indexes on ``schema.table`` whose name derives from ``stem``.

    Postgres auto-names a primary key `<table>_pkey` and a foreign key
    `<table>_<column>_fkey`, so on a database built by ``create_all`` from the post-move
    models the primary key of `projects.brands` is called `brands_pkey` while a migrated
    one still calls it `project_brands_pkey`. See ``_reprefix_derived_names``.
    """
    bind = op.get_bind()
    constraints = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT con.conname FROM pg_constraint con "
                "JOIN pg_class c ON c.oid = con.conrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relname = :table "
                "AND con.conname LIKE :prefix"
            ),
            {"schema": schema, "table": table, "prefix": f"{stem}\\_%"},
        )
    ]
    indexes = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT ic.relname FROM pg_index i "
                "JOIN pg_class ic ON ic.oid = i.indexrelid "
                "JOIN pg_class tc ON tc.oid = i.indrelid "
                "JOIN pg_namespace n ON n.oid = tc.relnamespace "
                "WHERE n.nspname = :schema AND tc.relname = :table "
                "AND ic.relname LIKE :prefix"
            ),
            {"schema": schema, "table": table, "prefix": f"{stem}\\_%"},
        )
    ]
    # A constraint rename carries its backing index with it, so do not do both.
    return constraints, [name for name in indexes if name not in constraints]


def _reprefix_derived_names(schema: str, table: str, frm: str, to: str) -> None:
    """Move Postgres-derived constraint and index names from one table-name stem to another.

    Postgres derives `<table>_pkey`, `<table>_<column>_fkey`, `<table>_<column>_key`,
    `<table>_<column>_check` and `<table>_<columns>_idx` at CREATE time and never revisits
    them. So a database built by ``create_all`` from the post-move models calls the key of
    `projects.brands` `brands_pkey`, and one migrated from before the move still calls it
    `project_brands_pkey`. Both directions rewrite the stem so the two agree.

    On the way down this is not cosmetic: index names are unique per SCHEMA, so moving
    `projects.brands` back beside CORE `brands`, which already owns `brands_pkey`, is
    refused outright. Five of the seven colliding tables hit it.

    Reading the names from the catalog rather than from a list is safe here because a name
    Postgres derived necessarily STARTS with the table name, and nothing the models name by
    hand does (they are all `ix_`, `uq_` or `ck_` prefixed - asserted in
    `tests/test_migration_354_projects_schema_move.py`).
    """
    if frm == to:
        return
    constraints, indexes = _derived_names(schema, table, frm)
    for name in constraints:
        renamed = f"{to}{name[len(frm):]}"
        op.execute(
            f'ALTER TABLE "{schema}"."{table}" RENAME CONSTRAINT "{name}" TO "{renamed}"'
        )
    for name in indexes:
        _rename_index(schema, name, f"{to}{name[len(frm):]}")


def _rewrite_lookup_bindings(schema: str, mapping: dict) -> None:
    """Repoint `lookup_bindings.table_name` at the qualified names, or back.

    A lookup binding is keyed by the SCHEMA-QUALIFIED table name (`Table.key`), because the
    bare name stopped identifying a table the moment seven of them existed twice: keyed on
    `purchase_orders`, one binding would validate writes to BOTH core's table and the
    module's, and reject perfectly good values on whichever one it was not made for.

    Only an exact match against one of the 47 pre-move names is rewritten, so a binding on
    a core table is never touched even when it shares a bare name with a moved one (there
    is no ambiguity: before the move the module's tables carried the prefix, and the 13
    that did not exist only once).
    """
    if not _has_table(schema, "lookup_bindings"):
        return  # a database built before the lookup module, or a partial test schema
    for frm, to in mapping.items():
        op.execute(
            sa.text(
                f'UPDATE "{schema}"."lookup_bindings" SET table_name = :to '
                "WHERE table_name = :frm"
            ).bindparams(to=to, frm=frm)
        )


def upgrade() -> None:
    _assert_identifiers_fit()
    source = _source_schema()
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{TARGET_SCHEMA}"')

    for old, new in TABLES:
        if not _has_table(TARGET_SCHEMA, new):
            if _has_table(source, old) and not _has_table(TARGET_SCHEMA, old):
                op.execute(f'ALTER TABLE "{source}"."{old}" SET SCHEMA "{TARGET_SCHEMA}"')
            # Separately guarded, so a run interrupted between the two steps resumes here.
            if old != new and _has_table(TARGET_SCHEMA, old):
                op.execute(f'ALTER TABLE "{TARGET_SCHEMA}"."{old}" RENAME TO "{new}"')
        # Outside the "not yet moved" guard on purpose: a database moved by an earlier
        # copy of this revision, which did not unify names, gets them unified here.
        if _has_table(TARGET_SCHEMA, new):
            _reprefix_derived_names(TARGET_SCHEMA, new, old, new)

    for pre_move, derived in DERIVED_INDEXES:
        _rename_index(TARGET_SCHEMA, pre_move, derived)

    _rewrite_lookup_bindings(
        source, {old: f"{TARGET_SCHEMA}.{new}" for old, new in TABLES}
    )


def downgrade() -> None:
    _assert_identifiers_fit()
    source = _source_schema()

    # Index names first, while the tables are still in the target schema: after the move
    # back there is nothing left there to find.
    for pre_move, derived in DERIVED_INDEXES:
        _rename_index(TARGET_SCHEMA, derived, pre_move)

    for old, new in TABLES:
        if _has_table(source, old):
            continue  # already back
        if old != new and _has_table(TARGET_SCHEMA, new) and not _has_table(TARGET_SCHEMA, old):
            _reprefix_derived_names(TARGET_SCHEMA, new, new, old)
            op.execute(f'ALTER TABLE "{TARGET_SCHEMA}"."{new}" RENAME TO "{old}"')
        if _has_table(TARGET_SCHEMA, old):
            op.execute(f'ALTER TABLE "{TARGET_SCHEMA}"."{old}" SET SCHEMA "{source}"')

    _rewrite_lookup_bindings(
        source, {f"{TARGET_SCHEMA}.{new}": old for old, new in TABLES}
    )

    # The schema itself stays. Dropping it would make downgrade destructive of anything
    # else that lands there, and leaving it empty keeps this revision idempotent.
