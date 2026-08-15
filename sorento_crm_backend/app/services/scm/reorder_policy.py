"""Canonical resolution of the GLOBAL ``scm.reorder_policy`` row.

``scope_type = 'global'`` is NOT a singleton by design: other resolvers
(`level_suggestion_service`, `price_history_service`, `product_economics_service`,
`trajectory_service._windows`) read MULTIPLE active global rows ranked by
``priority``, an override-layering pattern the test suite exercises directly. But
the buyer-facing quick settings (dead-stock-days, planning mode) and the dashboard
read-model both want ONE canonical answer, or the dashboard's dead-window and the
Settings popover disagree. This module is the one place that ORDER BY lives so
every reader of "the" global row picks the SAME one, and the one place writes to
it go through (`upsert_global_policy`) so two concurrent first saves can never
both create it.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.scm.cover_service import (
    COVER_SCOPES,
    DEFAULT_COVER_SCOPE,
)

# Engine default fallback when no global policy row carries a value.
DEFAULT_DEAD_STOCK_DAYS = 180
# Days-of-cover ceiling above which a SKU reads as overstock (M2). Engine default
# when no global policy row carries an ``overstock_days`` value.
DEFAULT_OVERSTOCK_DAYS = 120

PlanningMode = Literal["auto", "manual"]
# policy_type values that resolve to each universal planning mode (S1). Only
# 'reorder_level' reads as manual; everything else (reorder_point, periodic_review,
# min_max, or a legacy/unset value) reads as auto.
_MANUAL_POLICY_TYPE = "reorder_level"
_AUTO_POLICY_TYPE = "reorder_point"


def global_policy_row(db: Session):
    """The single canonical global reorder_policy row.

    Active rows win over inactive ones; among ties the oldest (``created_at ASC``)
    wins — deterministic, and stable as new duplicates get appended.

    Columns are appended, never reordered: callers read this by index.
    """
    return db.execute(text(
        "SELECT id, dead_stock_days, overstock_days, policy_type, cover_scope "
        "FROM scm.reorder_policy "
        "WHERE scope_type = 'global' ORDER BY is_active DESC, created_at ASC LIMIT 1"
    )).fetchone()


def planning_mode_from_policy_type(policy_type: Optional[str]) -> PlanningMode:
    """Map a raw ``policy_type`` to the universal planning-mode label (UAC A1).

    Only ``reorder_level`` is manual; ``reorder_point``/``periodic_review`` and any
    other/unset value read as auto.
    """
    return "manual" if policy_type == _MANUAL_POLICY_TYPE else "auto"


def mode_to_policy_type(mode: PlanningMode) -> str:
    """The reverse of `planning_mode_from_policy_type`: the `policy_type` value a
    universal planning-mode write should set on the global row (UAC A1)."""
    return _MANUAL_POLICY_TYPE if mode == "manual" else _AUTO_POLICY_TYPE


def resolve_global_planning_mode(db: Session) -> PlanningMode:
    """The mode the NEXT reorder run will use, derived from the global row."""
    row = global_policy_row(db)
    return planning_mode_from_policy_type(row[3] if row else None)


def resolve_global_cover_scope(db: Session) -> str:
    """Where "use stock" may draw from, per the canonical global row.

    An unset value resolves to ``own_pool`` (the captain's answer: "either I use stock from
    BRW, or buy"), so a row that predates the column never silently offers the whole network.
    """
    row = global_policy_row(db)
    value = row[4] if row else None
    return value if value in COVER_SCOPES else DEFAULT_COVER_SCOPE


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


#: Arbitrary fixed key for the transaction-scoped advisory lock `upsert_global_policy`
#: takes. Any 64-bit int works here; picked once and never reused for another lock in
#: this codebase.
_GLOBAL_POLICY_LOCK_KEY = 0x5343_4D5F_4750_4F4C  # "SCM_GPOL" packed into 8 bytes


def upsert_global_policy(db: Session, **updates) -> None:
    """Atomically create-or-update the CANONICAL GLOBAL ``scm.reorder_policy`` row -
    the one `global_policy_row` resolves to.

    The config endpoints (`set_planning_mode`, `set_dead_stock_days`) used to hand-roll
    their own SELECT-then-INSERT/UPDATE: read `global_policy_row`, branch on whether it
    came back, write. Two concurrent FIRST saves can both see "no row yet" and both
    INSERT - the `system_settings` duplicate-row failure class migration 253 fixed with a
    unique index. That fix does NOT transfer here: `scope_type = 'global'` is deliberately
    NOT a singleton - `level_suggestion_service` / `price_history_service` /
    `product_economics_service` / `trajectory_service._windows` all read MULTIPLE active
    global rows ranked by `priority`, an override-layering pattern the test suite exercises
    directly (inserting an extra global row is a normal way to scope a config value to one
    test). A unique index on `scope_type` would outlaw that.

    So the race is closed with a Postgres transaction-scoped advisory lock instead of a
    constraint: every caller serializes on the same fixed key before its own
    read-then-branch, so two concurrent first saves can no longer both observe "no
    canonical row yet". The lock releases automatically at the caller's next commit or
    rollback.

    ``updates`` are exactly the columns THIS caller means to touch, applied on both the
    insert and the update path - callers never have to know or restate the row's other
    columns. A brand-new row still needs a valid ``policy_type`` (NOT NULL): callers that
    do not touch it (e.g. a dead-stock-days-only save) get the engine default
    (``reorder_point``, auto), matching what the old hand-rolled INSERT used.
    """
    if not updates:
        return
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _GLOBAL_POLICY_LOCK_KEY})

    row = global_policy_row(db)
    if row:
        set_sql = ", ".join(f"{c} = :{c}" for c in updates)
        db.execute(
            text(
                f"UPDATE scm.reorder_policy SET {set_sql}, is_active = true, updated_at = now() "
                "WHERE id = :id"
            ),
            {"id": row[0], **updates},
        )
        return

    row_values: dict = {"policy_type": _AUTO_POLICY_TYPE, **updates}
    insert_cols = ["id", "scope_type", "scope_ref", "is_active",
                    "source_system", "source_ref", "created_at", "updated_at",
                    *row_values.keys()]
    literal_sql = {
        "id": ":id", "scope_type": "'global'", "scope_ref": "NULL", "is_active": "true",
        "source_system": "'manual'", "source_ref": "'ui'",
        "created_at": "now()", "updated_at": "now()",
    }
    insert_vals_sql = ", ".join(literal_sql.get(c, f":{c}") for c in insert_cols)
    db.execute(
        text(
            f"INSERT INTO scm.reorder_policy ({', '.join(insert_cols)}) "
            f"VALUES ({insert_vals_sql})"
        ),
        {"id": str(uuid.uuid4()), **row_values},
    )
