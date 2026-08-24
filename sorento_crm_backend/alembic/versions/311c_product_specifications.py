"""Derived spec storage, plus the exception queue a human actually reads.

`product_specifications` holds what derivation could read out of the catalog, keyed on
product_id but derived per product_code: the same model exists once per company
(11,414 codes across 22,805 rows), and deriving per row lets the two copies drift with
nothing detecting it.

`product_spec_exceptions` holds ONLY the rows a human must look at. If it ever fills
with routine successes the filter is wrong, and the queue becomes the data-entry
programme this design exists to avoid. Two reasons ship with it:

  shape_mismatch - the stored L/W/H describe a round or square product. 231 codes have
                    length = width, and a round basin's diameter has been forced into
                    `length` catalog-wide, so ranking "600mm wide basin" against one
                    compares against its depth.
  column_conflict - the description disagrees with a stored column. The column wins,
                    because curated data outranks parsed text, but a human is told.

No values are seeded here. Derivation runs on the worker
(app/tasks/product_spec_tasks.py), because it touches every code in the catalog.

Revision ID: 311c_product_specifications
Revises: 311b_product_spec_registry
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "311c_product_specifications"
down_revision = "311b_product_spec_registry"
branch_labels = None
depends_on = None


SPECS = "product_specifications"
EXCEPTIONS = "product_spec_exceptions"


def _has_table(bind, table: str) -> bool:
    return bool(bind.execute(sa.text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}).scalar())


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, SPECS):
        op.create_table(
            SPECS,
            sa.Column(
                "product_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "values",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "provenance",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("rendered_text", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="derived"),
            sa.Column("derived_hash", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        )
        # GIN on the value bag: the ranker filters and boosts on spec keys, and a
        # btree cannot serve a jsonb containment probe.
        op.create_index(
            "ix_product_specifications_values", SPECS, ["values"], postgresql_using="gin"
        )
        op.create_index("ix_product_specifications_status", SPECS, ["status"])

    if not _has_table(bind, EXCEPTIONS):
        op.create_table(
            EXCEPTIONS,
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("product_code", sa.String(length=100), nullable=False),
            sa.Column("spec_key", sa.String(length=64), nullable=False),
            sa.Column("reason", sa.String(length=48), nullable=False),
            sa.Column("proposed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("stored", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("resolved_by", postgresql.UUID(as_uuid=False), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        # Partial: the queue is only ever read for what is still open.
        op.create_index(
            "ix_product_spec_exceptions_open",
            EXCEPTIONS,
            ["product_code"],
            postgresql_where=sa.text("resolved_at IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, EXCEPTIONS):
        op.drop_table(EXCEPTIONS)
    if _has_table(bind, SPECS):
        op.drop_table(SPECS)
