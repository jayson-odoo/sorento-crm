"""Form SLA per-stage config table.

Configures, per form type, which symbolic transition starts an SLA tracker,
which marks it responded, and which marks it resolved. Multi-stage chains
(e.g. stock_inquiry: project_sales -> purchasing) link via next_config_id.

Revision ID: 178_form_sla_configs
Revises: 177_impersonation_sessions
Create Date: 2026-05-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "178_form_sla_configs"
down_revision = "177_impersonation_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form_sla_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_entity_type", sa.String(length=50), nullable=False),
        sa.Column("stage_code", sa.String(length=100), nullable=False),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("sla_policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("agent_code", sa.String(length=100), nullable=False),
        sa.Column("team_set_code", sa.String(length=100), nullable=True),
        sa.Column("start_event", sa.String(length=100), nullable=False),
        sa.Column("respond_event", sa.String(length=100), nullable=True),
        sa.Column("resolve_event", sa.String(length=100), nullable=True),
        sa.Column(
            "next_config_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("form_sla_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_form_sla_configs_source_entity_type",
        "form_sla_configs",
        ["source_entity_type"],
    )
    op.create_index(
        "ix_form_sla_configs_policy_id",
        "form_sla_configs",
        ["policy_id"],
    )
    op.create_index(
        "uq_form_sla_configs_type_stage_active",
        "form_sla_configs",
        ["source_entity_type", "stage_code"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_form_sla_configs_type_stage_active",
        table_name="form_sla_configs",
    )
    op.drop_index("ix_form_sla_configs_policy_id", table_name="form_sla_configs")
    op.drop_index(
        "ix_form_sla_configs_source_entity_type",
        table_name="form_sla_configs",
    )
    op.drop_table("form_sla_configs")
