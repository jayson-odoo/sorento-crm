"""Give the two order-inquiry tables the module's `project_` prefix.

35 of the projects module's 47 tables are already named `project_*`, and SCM ships its
own order-inquiry concept, so `order_inquiries` / `order_inquiry_rows` in the shared
schema read as the wrong one. The other 12 unprefixed tables (`so_amendments`,
`delivery_schedules` and friends) predate the convention and are not renamed here:
ownership is defined by the module's model files, and the prefix is the convention for
NEW tables. These two are renamed because their names actively collide.

Both tables are branch-only and unreleased, but the shared development database
already holds them under the old names, so this is a rename rather than a re-create.
The creating revisions (319, 322) now emit the new names directly, which means on a
fresh database there is nothing here to do: every step is guarded on "the old name is
present and the new one is not", so this revision no-ops on CI and does the work on a
development database. Postgres renames neither indexes nor constraints along with the
table, so each one is renamed explicitly or the next autogenerate would try to fix it.

**Superseded as a convention by 354** (ADR-0011): the client reversed the schema clause of
ADR-0009 two days later, so the module's tables now live in a `projects` schema and the
`project_` prefix this revision applied is dropped again there - `project_order_inquiries`
becomes `projects.order_inquiries`. This revision is nonetheless still correct and stays
exactly as it is: it ran when the tables were in the default schema, which is true at the
moment it executes, and it is what made the shared development database and a fresh one
agree on a single name before 354 moved them. Rewriting it would be the expensive kind of
change ADR-0009 warned about, and 354 would then have two different starting names to
guard against instead of one.

Revision ID: 353_project_order_inquiry_rename
Revises: dcb151730340
"""
from alembic import op
import sqlalchemy as sa

revision = "353_project_order_inquiry_rename"
down_revision = "dcb151730340"
branch_labels = None
depends_on = None


TABLES = (
    ("order_inquiries", "project_order_inquiries"),
    ("order_inquiry_rows", "project_order_inquiry_rows"),
)

INDEXES = (
    ("ix_order_inquiries_order", "ix_project_order_inquiries_order"),
    ("ix_order_inquiries_company_id", "ix_project_order_inquiries_company_id"),
    ("uq_order_inquiry_per_sales_order", "uq_project_order_inquiry_per_sales_order"),
    ("uq_order_inquiry_per_amendment", "uq_project_order_inquiry_per_amendment"),
    ("ix_order_inquiry_rows_inquiry", "ix_project_order_inquiry_rows_inquiry"),
    ("ix_order_inquiry_rows_company_id", "ix_project_order_inquiry_rows_company_id"),
    ("ix_order_inquiry_rows_state", "ix_project_order_inquiry_rows_state"),
)

# (table the constraint lives on, old name, new name). The table is named here under
# its NEW name because constraints are renamed after the table itself moved.
CONSTRAINTS = (
    ("project_order_inquiries", "order_inquiries_pkey", "project_order_inquiries_pkey"),
    (
        "project_order_inquiries",
        "order_inquiries_project_sales_order_id_fkey",
        "project_order_inquiries_project_sales_order_id_fkey",
    ),
    (
        "project_order_inquiries",
        "order_inquiries_amendment_id_fkey",
        "project_order_inquiries_amendment_id_fkey",
    ),
    (
        "project_order_inquiries",
        "order_inquiries_raised_by_fkey",
        "project_order_inquiries_raised_by_fkey",
    ),
    (
        "project_order_inquiries",
        "order_inquiries_company_id_fkey",
        "project_order_inquiries_company_id_fkey",
    ),
    (
        "project_order_inquiry_rows",
        "order_inquiry_rows_pkey",
        "project_order_inquiry_rows_pkey",
    ),
    (
        "project_order_inquiry_rows",
        "order_inquiry_rows_order_inquiry_id_fkey",
        "project_order_inquiry_rows_order_inquiry_id_fkey",
    ),
    (
        "project_order_inquiry_rows",
        "order_inquiry_rows_so_line_id_fkey",
        "project_order_inquiry_rows_so_line_id_fkey",
    ),
    (
        "project_order_inquiry_rows",
        "order_inquiry_rows_actioned_by_fkey",
        "project_order_inquiry_rows_actioned_by_fkey",
    ),
    (
        "project_order_inquiry_rows",
        "order_inquiry_rows_company_id_fkey",
        "project_order_inquiry_rows_company_id_fkey",
    ),
)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(name: str) -> bool:
    row = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind IN ('i', 'I') AND c.relname = :name "
            "AND n.nspname = current_schema()"
        ),
        {"name": name},
    ).first()
    return row is not None


def _has_constraint(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    row = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = :table AND con.conname = :name "
            "AND n.nspname = current_schema()"
        ),
        {"table": table, "name": name},
    ).first()
    return row is not None


def _rename_tables(pairs) -> None:
    for old, new in pairs:
        if _has_table(old) and not _has_table(new):
            op.execute(f'ALTER TABLE "{old}" RENAME TO "{new}"')


def _rename_indexes(pairs) -> None:
    for old, new in pairs:
        if _has_index(old) and not _has_index(new):
            op.execute(f'ALTER INDEX "{old}" RENAME TO "{new}"')


def _rename_constraints(triples) -> None:
    for table, old, new in triples:
        if _has_constraint(table, old) and not _has_constraint(table, new):
            op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"')


def upgrade() -> None:
    _rename_tables(TABLES)
    _rename_constraints(CONSTRAINTS)
    _rename_indexes(INDEXES)


def downgrade() -> None:
    _rename_constraints([(table, new, old) for table, old, new in CONSTRAINTS])
    _rename_indexes([(new, old) for old, new in INDEXES])
    _rename_tables([(new, old) for old, new in TABLES])
