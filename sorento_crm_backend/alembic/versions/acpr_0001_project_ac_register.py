"""AC-PROJECT-REGISTER: register a CRM project in AutoCount.

Plan: documentation/plans/autocount/PLAN-ac-project-register-13nov.md.

Additive only, nullable, no backfill:

- ``projects.projects``: ``autocount_doc_no``, ``autocount_doc_key``, ``autocount_book``,
  ``autocount_pending_create`` (the write-ahead key + body of a create not yet confirmed) and
  ``autocount_registered_at``. Names match ``projects.quotation_documents`` so the shared create
  path works on a project as is.
- ``system_settings.project_autocount_register_enabled`` (NOT NULL, false): "AutoCount project
  registration", OFF on deploy.

Revision ID: acpr_0001_project_ac_register
Revises: agent_0001_proposal_insights
"""
from __future__ import annotations

from alembic import op

revision = "acpr_0001_project_ac_register"
down_revision = "agent_0001_proposal_insights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects.projects "
        "ADD COLUMN IF NOT EXISTS autocount_doc_no VARCHAR(80), "
        "ADD COLUMN IF NOT EXISTS autocount_doc_key VARCHAR(80), "
        "ADD COLUMN IF NOT EXISTS autocount_book VARCHAR(40), "
        "ADD COLUMN IF NOT EXISTS autocount_pending_create JSONB, "
        "ADD COLUMN IF NOT EXISTS autocount_registered_at TIMESTAMP WITHOUT TIME ZONE"
    )
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "project_autocount_register_enabled BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings DROP COLUMN IF EXISTS project_autocount_register_enabled"
    )
    op.execute(
        "ALTER TABLE projects.projects "
        "DROP COLUMN IF EXISTS autocount_registered_at, "
        "DROP COLUMN IF EXISTS autocount_pending_create, "
        "DROP COLUMN IF EXISTS autocount_book, "
        "DROP COLUMN IF EXISTS autocount_doc_key, "
        "DROP COLUMN IF EXISTS autocount_doc_no"
    )
