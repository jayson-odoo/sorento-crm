"""Canonical resolution of the GLOBAL ``scm.reorder_policy`` row.

The global policy is meant to be a singleton, but legacy installs / concurrent
seeds can leave duplicate ``scope_type='global'`` rows behind. Both the dashboard
read-model (``ScmDashboardService._dead_days_for``) and the config endpoint
(``app.api.v1.scm.config``) must pick the SAME row when duplicates exist, or the
dashboard's dead-window and the Settings popover disagree. This module is the one
place that ORDER BY lives so the two paths can never drift.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# Engine default fallback when no global policy row carries a value.
DEFAULT_DEAD_STOCK_DAYS = 180
# Days-of-cover ceiling above which a SKU reads as overstock (M2). Engine default
# when no global policy row carries an ``overstock_days`` value.
DEFAULT_OVERSTOCK_DAYS = 120


def global_policy_row(db: Session):
    """The single canonical global reorder_policy row.

    Active rows win over inactive ones; among ties the oldest (``created_at ASC``)
    wins — deterministic, and stable as new duplicates get appended.
    """
    return db.execute(text(
        "SELECT id, dead_stock_days, overstock_days FROM scm.reorder_policy "
        "WHERE scope_type = 'global' ORDER BY is_active DESC, created_at ASC LIMIT 1"
    )).fetchone()


def resolve_global_dead_stock_days(db: Session) -> Optional[int]:
    """Dead-stock window from the canonical global row, or None if unset."""
    row = global_policy_row(db)
    if row and row[1] is not None:
        return int(row[1])
    return None


def resolve_global_overstock_days(db: Session) -> int:
    """Days-of-cover overstock ceiling from the canonical global row.

    Falls back to ``DEFAULT_OVERSTOCK_DAYS`` when no global row carries a value so
    the overstock valuation / filter always has a concrete threshold to compare
    against (never silently disabled by a missing policy).
    """
    row = global_policy_row(db)
    if row and row[2] is not None:
        return int(row[2])
    return DEFAULT_OVERSTOCK_DAYS
