"""SCM configuration endpoints — small, discoverable quick settings.

At M1 this exposes the single ``dead_stock_days`` knob on the GLOBAL
``scm.reorder_policy`` (scope_type='global', scope_ref NULL). That value drives the
dashboard's "dead" status: on-hand SKUs whose last outbound movement is older than
this window are flagged Dead. Read is gated on the dashboard view slug (so the
setting is visible alongside the numbers it explains); write requires
``scm.config.manage``.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_dashboard import DeadStockDays, DeadStockDaysUpdate
from app.services.error_handler import AppException
from app.services.scm.reorder_policy import (
    DEFAULT_DEAD_STOCK_DAYS,
    global_policy_row,
)

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_MANAGE = require_permission_with_api_key("scm.config.manage")

# Engine default fallback (shared with ScmDashboardService._dead_days_for).
_DEFAULT_DEAD_DAYS = DEFAULT_DEAD_STOCK_DAYS


def _global_policy_row(db: Session):
    # Delegates to the one canonical resolver so the dashboard and this endpoint
    # always agree on which global row wins when duplicates exist.
    return global_policy_row(db)


@router.get("/config/dead-stock-days", response_model=DeadStockDays)
def get_dead_stock_days(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    row = _global_policy_row(db)
    value = int(row[1]) if row and row[1] is not None else _DEFAULT_DEAD_DAYS
    return {"dead_stock_days": value}


@router.put("/config/dead-stock-days", response_model=DeadStockDays)
def set_dead_stock_days(
    payload: DeadStockDaysUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    days = payload.dead_stock_days
    if days < 1 or days > 3650:
        raise AppException(
            status_code=422,
            message="Dead-stock threshold must be between 1 and 3650 days.",
        )
    row = _global_policy_row(db)
    if row:
        db.execute(
            text(
                "UPDATE scm.reorder_policy SET dead_stock_days = :d, is_active = true, "
                "updated_at = now() WHERE id = :id"
            ),
            {"d": days, "id": row[0]},
        )
    else:
        # No seeded global policy — create one (idempotent for legacy installs).
        db.execute(
            text(
                "INSERT INTO scm.reorder_policy "
                "(id, scope_type, scope_ref, policy_type, dead_stock_days, is_active, "
                " source_system, source_ref, created_at, updated_at) "
                "VALUES (:id, 'global', NULL, 'reorder_point', :d, true, "
                " 'manual', 'ui', now(), now())"
            ),
            {"id": str(uuid.uuid4()), "d": days},
        )
    db.commit()
    return {"dead_stock_days": days}
