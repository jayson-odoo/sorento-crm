"""Sales module, S1 fix round 3: commission tiers on a target (plan 3.3, UAC S4-1).

The owner's retest of 27 Sep (PR #1297, "how do i add commission"): tiers are added, edited and
removed on the target record's Commission tab in Edit mode.

1. `sales.targets.commission_method`, varchar(16) not null default `none`, check `none`,
   `marginal` or `retroactive`. Existing targets get `none` from the default.
2. `sales.target_commission_tiers` (plan 3.3): `from_pct` numeric(7,2), `rate` numeric(9,4),
   `bonus_amount` numeric(15,2) null; cascade from the header; unique `(target_id, from_pct)`.
   New table, so no backfill.

Downgrade drops the table and the column.

Revision ID: sales_0005_commission_tiers
Revises: sales_0004_target_brands
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.sales import translated_schema

revision = "sales_0005_commission_tiers"
down_revision = "sales_0004_target_brands"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    # ALTER TABLE ignores `schema_translate_map`, so the schema is named explicitly (sales_0004).
    schema = translated_schema(op.get_bind())
    op.add_column(
        "targets",
        sa.Column(
            "commission_method", sa.String(16), nullable=False, server_default=sa.text("'none'")
        ),
        schema=schema,
    )
    op.create_check_constraint(
        "ck_sales_targets_commission_method",
        "targets",
        "commission_method IN ('none', 'marginal', 'retroactive')",
        schema=schema,
    )

    op.create_table(
        "target_commission_tiers",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("company_id", _UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column(
            "target_id",
            _UUID,
            sa.ForeignKey("sales.targets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_pct", sa.Numeric(7, 2), nullable=False),
        sa.Column("rate", sa.Numeric(9, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("bonus_amount", sa.Numeric(15, 2), nullable=True),
        sa.CheckConstraint("from_pct >= 0", name="ck_sales_target_commission_tiers_from_pct"),
        sa.CheckConstraint("rate >= 0", name="ck_sales_target_commission_tiers_rate"),
        sa.CheckConstraint(
            "bonus_amount IS NULL OR bonus_amount >= 0",
            name="ck_sales_target_commission_tiers_bonus",
        ),
        schema="sales",
    )
    op.create_index(
        "ix_sales_target_commission_tiers_company_id",
        "target_commission_tiers",
        ["company_id"],
        schema="sales",
    )
    op.create_index(
        "uq_sales_target_commission_tiers_target_from",
        "target_commission_tiers",
        ["target_id", "from_pct"],
        unique=True,
        schema="sales",
    )


def downgrade() -> None:
    schema = translated_schema(op.get_bind())
    op.drop_table("target_commission_tiers", schema="sales")
    op.drop_constraint("ck_sales_targets_commission_method", "targets", schema=schema, type_="check")
    op.drop_column("targets", "commission_method", schema=schema)
