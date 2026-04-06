"""Re-apply warehouse-per-Loc seed if revision 133 previously created storage_zones only.

Revision ID: 134_reapply_warehouse_master_per_loc
Revises: 133_seed_warehouse_storage_zones_master
Create Date: 2026-04-08

Idempotent: safe if 133 already ran the warehouse-per-Loc logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import op

revision = "134_reapply_warehouse_master_per_loc"
down_revision = "133_seed_warehouse_storage_zones_master"
branch_labels = None
depends_on = None

_ALEMBIC_ROOT = Path(__file__).resolve().parent.parent
if str(_ALEMBIC_ROOT) not in sys.path:
    sys.path.insert(0, str(_ALEMBIC_ROOT))

from warehouse_master_seed import run_warehouse_master_seed  # noqa: E402


def upgrade() -> None:
    conn = op.get_bind()
    run_warehouse_master_seed(conn)


def downgrade() -> None:
    pass
