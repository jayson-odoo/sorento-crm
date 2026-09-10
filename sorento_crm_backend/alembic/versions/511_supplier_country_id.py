"""Supplier country FK (S2, `PLAN-local-supplier-oi-routing.md`).

Replaces the free-text `suppliers.country` (NULL on all 1,163 rows, verified) with
`country_id`, a FK to the new `countries` table (`510_countries`), `ON DELETE
RESTRICT`. Repoints the supplier list-query metadata field `country` at the joined
`country.name` - `_update_supplier_country_field` is named after
`alembic/versions/445_autocount_grant_sweep.py`'s `apply(bind)`-on-a-rolled-back-
connection pattern, since `list_query_fields` is itself migration-seeded
(`101_list_query_metadata.py`) and a blank scratch schema never sees the seed row.

Revision ID: 511_supplier_country_id
Revises: 510_countries
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "511_supplier_country_id"
down_revision = "510_countries"
branch_labels = None
depends_on = None


def _update_supplier_country_field(bind) -> None:
    """AC-2.8: the `country` field on the `suppliers` list-query resource now reads
    the joined country's name, never the (now-dropped) free-text column."""
    bind.execute(
        sa.text(
            """
            UPDATE list_query_fields f
            SET compile_key = 'country.name'
            FROM list_query_resources r
            WHERE r.id = f.resource_id
              AND r.resource_key = 'suppliers'
              AND f.field_key = 'country'
            """
        )
    )


def upgrade() -> None:
    op.add_column(
        "suppliers",
        sa.Column(
            "country_id", UUID(as_uuid=False), sa.ForeignKey("countries.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_suppliers_country_id", "suppliers", ["country_id"])
    # IF EXISTS: some databases converged this table through `create_all` rather than
    # migration history and never ran the migration that first added this index (see
    # `sorento_crm_backend/CLAUDE.md`'s note on the shared local Postgres), so it is not
    # a given that it is there to drop.
    op.execute("DROP INDEX IF EXISTS ix_suppliers_country")
    op.drop_column("suppliers", "country")
    _update_supplier_country_field(op.get_bind())


def downgrade() -> None:
    op.add_column("suppliers", sa.Column("country", sa.String(100), nullable=True))
    op.create_index("ix_suppliers_country", "suppliers", ["country"])
    op.drop_index("ix_suppliers_country_id", table_name="suppliers")
    op.drop_column("suppliers", "country_id")
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE list_query_fields f
            SET compile_key = 'supplier.country'
            FROM list_query_resources r
            WHERE r.id = f.resource_id
              AND r.resource_key = 'suppliers'
              AND f.field_key = 'country'
            """
        )
    )
