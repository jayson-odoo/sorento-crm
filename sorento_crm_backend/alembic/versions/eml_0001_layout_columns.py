"""Email layout columns (#1349, PLAN-email-layout-28sep.md S2).

- ``email_templates.preheader``: the hidden inbox preview line.
- ``email_templates.layout_json``: the ordered block document the shared layout renders.
  NULL keeps a template on the implicit document (brand header, its body_html, footer).
- ``system_settings.email_theme``: the email theme as one object (brand colour, logo,
  button, font, footer), validated by ``app.services.email_layout.EmailTheme``.

All three nullable, no backfill: NULL means "the default", and the defaults live in code.
Additive; downgrade drops them.

Revision ID: eml_0001_layout_columns
Revises: merge_29sep_batch6
Create Date: 2026-09-28
"""
from __future__ import annotations

from alembic import op

revision = "eml_0001_layout_columns"
down_revision = "merge_29sep_batch6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS preheader VARCHAR(255)")
    op.execute("ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS layout_json JSONB")
    op.execute("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS email_theme JSONB")


def downgrade() -> None:
    op.drop_column("system_settings", "email_theme")
    op.drop_column("email_templates", "layout_json")
    op.drop_column("email_templates", "preheader")

