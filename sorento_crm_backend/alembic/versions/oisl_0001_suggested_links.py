"""Order inquiry: a table for the cascade's own guesses, never a real link.

`PLAN-oi-links-autocount-truth-24sep.md` section 3.3/3.9,
`oi-links-autocount-truth-24sep-acceptance-criteria.md` Group S3.

The owner, issue #1215, point 4: "the idea is the suggested link shouldn't be counted as
real link and actually appearing in the PO or SPO column." `projects.order_inquiry_suggested_
links` is the store: one row per placement the cascade walk offers, never a claim, never a
person's name on it, and gone the moment its target document line does (`CASCADE`, unlike a
real link's `SET NULL` - see the model's own docstring, `app/models/project_so.py`).

No data migration: the table starts empty, and the first Auto link all after deploy fills it
for every row still uncovered (plan 3.9). Hand-written and guarded with `IF NOT EXISTS`, the
same shape `oirs_0001_reserve_requests.py` and `421_order_inquiry_links.py` use - the shared
dev database converges through `create_all` rather than `alembic upgrade`
(`sorento_crm_backend/CLAUDE.md`), so this migration's own `upgrade()` must be a no-op
reaching a database that already has the table.

Revision ID: oisl_0001_suggested_links
Revises: oihr_0003_location_column
Create Date: 2026-09-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "oisl_0001_suggested_links"
down_revision = "oihr_0003_location_column"
branch_labels = None
depends_on = None


def _schema(bind, module: str) -> str:
    """Where a module's tables live, for RAW SQL, under BOTH substrates - copied from
    `421_order_inquiry_links.py`'s own helper (see that file's docstring for why):
    `schema_translate_map` rewrites ORM/`Table` constructs only, so a bare `"projects"`
    in a raw `text()` statement would reach the REAL schema from a test running on a
    scratch schema. `tests/_pg_fixture.py` names scratch schemas `<default>_projects`,
    and the current default schema is enough to tell the two substrates apart."""
    current = bind.exec_driver_sql("SELECT current_schema()").scalar()
    return module if current in (None, "public") else f"{current}_{module}"


def upgrade() -> None:
    bind = op.get_bind()
    projects = _schema(bind, "projects")
    bind.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS "{projects}".order_inquiry_suggested_links (
                id UUID PRIMARY KEY,
                company_id UUID REFERENCES companies(id),
                row_id UUID NOT NULL
                    REFERENCES "{projects}".order_inquiry_rows(id) ON DELETE CASCADE,
                po_line_id UUID REFERENCES purchase_order_lines(id) ON DELETE CASCADE,
                spo_allocation_id UUID
                    CONSTRAINT fk_order_inquiry_suggested_links_spo_allocation
                    REFERENCES spo_allocations(id) ON DELETE CASCADE,
                document VARCHAR(80),
                qty NUMERIC(15, 4) NOT NULL
                    CONSTRAINT ck_order_inquiry_suggested_links_qty_positive CHECK (qty > 0),
                trigger VARCHAR(32),
                suggested_at TIMESTAMP NOT NULL DEFAULT now(),
                CONSTRAINT ck_order_inquiry_suggested_links_one_target
                    CHECK ((po_line_id IS NOT NULL)::int
                           + (spo_allocation_id IS NOT NULL)::int = 1)
            );
            CREATE INDEX IF NOT EXISTS ix_order_inquiry_suggested_links_company_id
                ON "{projects}".order_inquiry_suggested_links (company_id);
            CREATE INDEX IF NOT EXISTS ix_order_inquiry_suggested_links_row
                ON "{projects}".order_inquiry_suggested_links (row_id);
            CREATE INDEX IF NOT EXISTS ix_order_inquiry_suggested_links_po_line
                ON "{projects}".order_inquiry_suggested_links (po_line_id);
            CREATE INDEX IF NOT EXISTS ix_order_inquiry_suggested_links_spo_allocation
                ON "{projects}".order_inquiry_suggested_links (spo_allocation_id);
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    projects = _schema(bind, "projects")
    bind.execute(
        sa.text(f'DROP TABLE IF EXISTS "{projects}".order_inquiry_suggested_links')
    )
