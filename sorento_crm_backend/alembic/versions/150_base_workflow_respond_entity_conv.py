"""Base infrastructure for commercial port: workflow_stages, respond_workspaces,
entity_conversation_messages, respond_contacts.workspace_id.

Revision ID: 150_base_workflow_respond_entity_conv
Revises: 149_forms_form_type

Cherry-picks the base-platform pieces from ijm_icp_crm migrations 161, 166,
170, 171 (commercial-specific tables and seed-data INSERTs are intentionally
excluded - they live in commercial_core's own migration). The
`commercial_lead_respond_contacts` junction and `commercial_leads.respond_workspace_id`
column also belong to commercial_core and are added there.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "150_base_workflow_respond_entity_conv"
down_revision = "149_forms_form_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_stages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("color_hex", sa.String(7), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_terminal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allows_conversion", sa.Boolean(), nullable=True),
        sa.Column("can_go_back", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "domain IN ('lead','quotation','tender','task','order','project')",
            name="ck_workflow_stages_domain",
        ),
        sa.UniqueConstraint("domain", "code", name="uq_workflow_stages_domain_code"),
    )
    op.create_index("ix_workflow_stages_domain_sort", "workflow_stages", ["domain", "sort_order"])
    op.create_index("ix_workflow_stages_domain_active", "workflow_stages", ["domain", "is_active"])

    op.create_table(
        "respond_workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_respond_workspaces_space_id", "respond_workspaces", ["space_id"])
    op.create_index("ix_respond_workspaces_is_active", "respond_workspaces", ["is_active"])
    op.create_index("uq_respond_workspaces_space_id", "respond_workspaces", ["space_id"], unique=True)

    op.create_table(
        "entity_conversation_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("body_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("author_user_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "entity_type IN ("
            "'commercial_project',"
            "'commercial_master_quotation',"
            "'commercial_project_task',"
            "'commercial_master_quotation_task',"
            "'commercial_lead'"
            ")",
            name="ck_entity_conversation_messages_entity_type",
        ),
        sa.CheckConstraint(
            "scope IN ('activity','internal_note')",
            name="ck_entity_conversation_messages_scope",
        ),
    )
    op.create_index(
        "ix_entity_conversation_messages_lookup",
        "entity_conversation_messages",
        ["entity_type", "entity_id", "scope", "created_at"],
    )
    op.create_index(
        "ix_entity_conversation_messages_author",
        "entity_conversation_messages",
        ["author_user_id"],
    )

    op.add_column(
        "respond_contacts",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("respond_workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_respond_contacts_workspace_id", "respond_contacts", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_respond_contacts_workspace_id", table_name="respond_contacts")
    op.drop_column("respond_contacts", "workspace_id")

    op.drop_index("ix_entity_conversation_messages_author", table_name="entity_conversation_messages")
    op.drop_index("ix_entity_conversation_messages_lookup", table_name="entity_conversation_messages")
    op.drop_table("entity_conversation_messages")

    op.drop_index("uq_respond_workspaces_space_id", table_name="respond_workspaces")
    op.drop_index("ix_respond_workspaces_is_active", table_name="respond_workspaces")
    op.drop_index("ix_respond_workspaces_space_id", table_name="respond_workspaces")
    op.drop_table("respond_workspaces")

    op.drop_index("ix_workflow_stages_domain_active", table_name="workflow_stages")
    op.drop_index("ix_workflow_stages_domain_sort", table_name="workflow_stages")
    op.drop_table("workflow_stages")
