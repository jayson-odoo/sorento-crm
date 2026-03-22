"""Workflow forms module: definitions, versions, submissions, purge support.

Revision ID: 105_workflow_forms
Revises: 104_orders_estimated_delivery_label
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.rbac.permission_registry import sync_permissions

revision = "105_workflow_forms"
down_revision = "104_orders_estimated_delivery_label"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_form_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("draft_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_user_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_workflow_form_definitions_code", "workflow_form_definitions", ["code"], unique=True)
    op.create_index("ix_workflow_form_definitions_is_active", "workflow_form_definitions", ["is_active"])

    op.create_table(
        "workflow_form_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("definition_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_user_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["definition_id"], ["workflow_form_definitions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_workflow_form_versions_definition_id", "workflow_form_versions", ["definition_id"])
    op.create_index(
        "uq_workflow_form_versions_def_ver",
        "workflow_form_versions",
        ["definition_id", "version_number"],
        unique=True,
    )

    op.add_column(
        "workflow_form_definitions",
        sa.Column(
            "published_version_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workflow_form_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_table(
        "workflow_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("definition_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("current_state_code", sa.String(64), nullable=False),
        sa.Column("header_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_user_id", sa.String(64), nullable=True),
        sa.Column("updated_by_user_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["definition_id"], ["workflow_form_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["workflow_form_versions.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_workflow_submissions_definition_id", "workflow_submissions", ["definition_id"])
    op.create_index("ix_workflow_submissions_version_id", "workflow_submissions", ["version_id"])
    op.create_index("ix_workflow_submissions_current_state_code", "workflow_submissions", ["current_state_code"])
    op.create_index(
        "ix_workflow_submissions_definition_created",
        "workflow_submissions",
        ["definition_id", "created_at"],
    )

    op.create_table(
        "workflow_submission_lines",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("line_group_id", sa.String(64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["submission_id"], ["workflow_submissions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_workflow_submission_lines_submission_id", "workflow_submission_lines", ["submission_id"])
    op.create_index(
        "ix_workflow_submission_lines_submission_group",
        "workflow_submission_lines",
        ["submission_id", "line_group_id"],
    )

    op.create_table(
        "workflow_submission_transition_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("from_state_code", sa.String(64), nullable=True),
        sa.Column("to_state_code", sa.String(64), nullable=False),
        sa.Column("transition_id", sa.String(64), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["workflow_submissions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_workflow_submission_transition_logs_submission_id",
        "workflow_submission_transition_logs",
        ["submission_id"],
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO app_modules_catalog (id, module_key, display_name, description, sort_order, is_core, dependencies)
            SELECT gen_random_uuid(), :mk, :dname, :desc, :sort_o, false, CAST(:deps AS jsonb)
            WHERE NOT EXISTS (SELECT 1 FROM app_modules_catalog WHERE module_key = :mk)
            """
        ),
        {
            "mk": "workflow_forms",
            "dname": "Workflow forms",
            "desc": "Build approval-style forms with customizable fields, states, and notifications.",
            "sort_o": "045",
            "deps": '["base", "notifications"]',
        },
    )

    session = Session(bind=conn)
    try:
        sync_permissions(session, created_by_user_id=None)
    finally:
        session.close()


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM app_modules_catalog WHERE module_key = 'workflow_forms'"),
    )

    op.drop_index("ix_workflow_submission_transition_logs_submission_id", table_name="workflow_submission_transition_logs")
    op.drop_table("workflow_submission_transition_logs")
    op.drop_index("ix_workflow_submission_lines_submission_group", table_name="workflow_submission_lines")
    op.drop_index("ix_workflow_submission_lines_submission_id", table_name="workflow_submission_lines")
    op.drop_table("workflow_submission_lines")
    op.drop_index("ix_workflow_submissions_definition_created", table_name="workflow_submissions")
    op.drop_index("ix_workflow_submissions_current_state_code", table_name="workflow_submissions")
    op.drop_index("ix_workflow_submissions_version_id", table_name="workflow_submissions")
    op.drop_index("ix_workflow_submissions_definition_id", table_name="workflow_submissions")
    op.drop_table("workflow_submissions")

    op.drop_column("workflow_form_definitions", "published_version_id")
    op.drop_index("uq_workflow_form_versions_def_ver", table_name="workflow_form_versions")
    op.drop_index("ix_workflow_form_versions_definition_id", table_name="workflow_form_versions")
    op.drop_table("workflow_form_versions")

    op.drop_index("ix_workflow_form_definitions_is_active", table_name="workflow_form_definitions")
    op.drop_index("ix_workflow_form_definitions_code", table_name="workflow_form_definitions")
    op.drop_table("workflow_form_definitions")
