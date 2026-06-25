"""SLA tier response/resolution hours: Integer -> Numeric(6,2) for sub-hour SLAs.

Revision ID: 246_sla_tier_hours_decimal
Revises: 245_coverage_redirect_assignments
Create Date: 2026-06-24

Requirement: SLAs shorter than one hour (e.g. 30 minutes = 0.5). The columns were
whole-hour integers; widen to Numeric(6,2). Reversible (rounds to int on downgrade).
"""
from alembic import op
import sqlalchemy as sa


revision = "246_sla_tier_hours_decimal"
down_revision = "245_coverage_redirect_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sla_policy_tiers",
        "response_hours",
        existing_type=sa.Integer(),
        type_=sa.Numeric(6, 2),
        existing_nullable=False,
        postgresql_using="response_hours::numeric(6,2)",
    )
    op.alter_column(
        "sla_policy_tiers",
        "resolution_hours",
        existing_type=sa.Integer(),
        type_=sa.Numeric(6, 2),
        existing_nullable=False,
        existing_server_default="24",
        postgresql_using="resolution_hours::numeric(6,2)",
    )


def downgrade() -> None:
    op.alter_column(
        "sla_policy_tiers",
        "response_hours",
        existing_type=sa.Numeric(6, 2),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="round(response_hours)::integer",
    )
    op.alter_column(
        "sla_policy_tiers",
        "resolution_hours",
        existing_type=sa.Numeric(6, 2),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default="24",
        postgresql_using="round(resolution_hours)::integer",
    )
