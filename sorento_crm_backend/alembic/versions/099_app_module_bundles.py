"""App module bundles table (DB-defined install presets).

Revision ID: 099_module_bundles
Revises: 098_catalog_deps
Create Date: 2026-03-20
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "099_module_bundles"
down_revision = "098_catalog_deps"
branch_labels = None
depends_on = None

# Mirrors former MODULE_BUNDLES defaults (module_manifest); full_suite = all catalog keys in manifest order
_BUNDLES: list[tuple[str, str, list[str], str]] = [
    (
        "core_ops",
        "Core Ops",
        ["base", "product", "inventory", "order", "resources"],
        "001",
    ),
    (
        "commercial_plus",
        "Commercial Plus",
        [
            "base",
            "product",
            "inventory",
            "order",
            "resources",
            "marketing",
            "procurement",
        ],
        "002",
    ),
    (
        "service_desk",
        "Service Desk",
        [
            "base",
            "resources",
            "complaints",
            "sla",
            "public_view_links",
            "notifications",
            "audit",
        ],
        "003",
    ),
    (
        "full_suite",
        "Full Suite",
        [
            "base",
            "product",
            "resources",
            "inventory",
            "order",
            "procurement",
            "marketing",
            "complaints",
            "sla",
            "forms",
            "notifications",
            "audit",
            "public_view_links",
        ],
        "004",
    ),
]


def upgrade() -> None:
    op.create_table(
        "app_module_bundles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("bundle_key", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("module_keys", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("sort_order", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_app_module_bundles_bundle_key", "app_module_bundles", ["bundle_key"], unique=True)

    conn = op.get_bind()
    for bk, dname, keys, sort_o in _BUNDLES:
        conn.execute(
            sa.text(
                """
                INSERT INTO app_module_bundles (id, bundle_key, display_name, module_keys, sort_order)
                VALUES (gen_random_uuid(), :bk, :dname, CAST(:keys AS jsonb), :sort_o)
                """
            ),
            {"bk": bk, "dname": dname, "keys": json.dumps(keys), "sort_o": sort_o},
        )


def downgrade() -> None:
    op.drop_index("ix_app_module_bundles_bundle_key", table_name="app_module_bundles")
    op.drop_table("app_module_bundles")
