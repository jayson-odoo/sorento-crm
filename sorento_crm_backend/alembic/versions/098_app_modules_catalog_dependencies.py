"""Store module dependency edges on app_modules_catalog (source of truth for resolver + API).

Revision ID: 098_catalog_deps
Revises: 097_app_store_perm
Create Date: 2026-03-20
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.runtime.module_manifest import MODULE_MANIFEST


revision = "098_catalog_deps"
down_revision = "097_app_store_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_modules_catalog",
        sa.Column(
            "dependencies",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    bind = op.get_bind()
    for mk, m in MODULE_MANIFEST.items():
        deps = sorted(m.dependencies)
        bind.execute(
            sa.text(
                "UPDATE app_modules_catalog SET dependencies = CAST(:deps AS jsonb) "
                "WHERE module_key = :mk"
            ),
            {"deps": json.dumps(deps), "mk": mk},
        )


def downgrade() -> None:
    op.drop_column("app_modules_catalog", "dependencies")
