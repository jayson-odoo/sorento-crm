"""Brand dealer group: `brands.dealer_company_id` (BULK-CONTACT-ACCESS, owner ruling 26 Oct).

The company whose dealers get the brand from the access-sheet upload. Nullable (project brands
have none), ON DELETE SET NULL. Seeded by `companies.code` and brand code; only rows still NULL
are touched, so a re-run never overwrites an admin's choice.

Revision ID: bca_0001_brand_dealer_company
Revises: diet_0001_parser_prompt_diet
Create Date: 2026-10-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "bca_0001_brand_dealer_company"
down_revision = "diet_0001_parser_prompt_diet"
branch_labels = None
depends_on = None

SEEDS = {
    "SRT": ("SORENTO", "CABANA", "ELLECI", "WDI", "NO LOGO"),
    "MCH": ("MOCHA", "IBORN"),
}


def upgrade() -> None:
    op.add_column(
        "brands",
        sa.Column(
            "dealer_company_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    bind = op.get_bind()
    for company_code, brand_codes in SEEDS.items():
        bind.execute(
            sa.text(
                "UPDATE brands SET dealer_company_id = c.id FROM companies c "
                "WHERE c.code = :company_code AND brands.dealer_company_id IS NULL "
                "AND upper(btrim(brands.brand_code)) = ANY(:codes)"
            ),
            {"company_code": company_code, "codes": list(brand_codes)},
        )


def downgrade() -> None:
    op.drop_column("brands", "dealer_company_id")
