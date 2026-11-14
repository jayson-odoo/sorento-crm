"""F2 12/13 Nov: a cancel is saved like any change before Confirm.

An unsaved `cancelled` planning-change row is not applied (it stays pending, like an unsaved
qty / date change), so a test that confirms or applies a cancelled row first SAVES it, the way
the board's Save does: `set_row_decision(..., "confirm")`, no composition.
"""
from __future__ import annotations

from app.models.planning_change import PlanningChangeRow
from app.services import planning_change_service


def decide_cancelled_rows(db, batch_id) -> int:
    """Save every pending `cancelled` row of the batch; returns how many were saved."""
    rows = (
        db.query(PlanningChangeRow)
        .filter(
            PlanningChangeRow.batch_id == str(batch_id),
            PlanningChangeRow.kind == "cancelled",
            PlanningChangeRow.applied_state == "pending",
        )
        .all()
    )
    for row in rows:
        planning_change_service.set_row_decision(db, str(batch_id), str(row.id), "confirm")
    db.flush()
    return len(rows)
