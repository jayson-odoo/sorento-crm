"""Seed warehouse master: one warehouses row per Loc (parent site in location).

Revision ID: 133_seed_warehouse_storage_zones_master
Revises: 132_conversation_sla_tracking_message_id
Create Date: 2026-04-07

See ``alembic/warehouse_master_seed.py`` for the row list and helpers.
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import op

revision = "133_seed_warehouse_storage_zones_master"
down_revision = "132_conversation_sla_tracking_message_id"
branch_labels = None
depends_on = None

_ALEMBIC_ROOT = Path(__file__).resolve().parent.parent
if str(_ALEMBIC_ROOT) not in sys.path:
    sys.path.insert(0, str(_ALEMBIC_ROOT))

from warehouse_master_seed import (  # noqa: E402
    downgrade_warehouse_master_seed,
    run_warehouse_master_seed,
)


def upgrade() -> None:
    conn = op.get_bind()
    run_warehouse_master_seed(conn)


def downgrade() -> None:
    conn = op.get_bind()
    downgrade_warehouse_master_seed(conn)
