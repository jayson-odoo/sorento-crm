"""DEMO helper - simulate actionable Stock-allocation rows on a reorder run.

On the current dataset every disposition the engine produces is a "hold" (overstock
just above the cover ceiling, no action), so the Stock-allocation view is always empty
of call-to-actions. This script flips a handful of existing hold disposition rows on the
latest completed run to the two ACTIONABLE dispositions the UI renders - Discontinue
(dead stock) and Promote/reallocate - purely so the view can be demonstrated populated.

It is idempotent and reversible: it only rewrites the frozen ``inputs.disposition_action``
(+ a human ``triggered_reason`` label) on a few rows; re-running the real plan regenerates
honest dispositions. Nothing else is touched - no stock, no orders.

Usage (from sorento_crm_backend/, with the venv active):
    python scripts/simulate_stock_allocation.py                 # latest completed run
    python scripts/simulate_stock_allocation.py --run <run_id>  # a specific run
    python scripts/simulate_stock_allocation.py --count 8       # how many rows to flip
    python scripts/simulate_stock_allocation.py --reset         # flip them all back to hold
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import SessionLocal


def _latest_completed_run(db) -> str | None:
    return db.execute(
        text(
            "SELECT id::text FROM scm.reorder_run WHERE status = 'completed' "
            "ORDER BY COALESCE(finished_at, created_at) DESC LIMIT 1"
        )
    ).scalar()


# (disposition_action, human reason label) applied round-robin to the flipped rows.
_ACTIONS = [
    ("discontinue", "Dead stock: no movement in 90+ days"),
    ("promo", "Overstocked: reallocate or promote to clear cover"),
]


def simulate(run_id: str, count: int) -> int:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT id::text AS id FROM scm.reorder_recommendation "
                "WHERE run_id = :rid AND rec_type = 'disposition' "
                "AND COALESCE(inputs->>'disposition_action', 'hold') = 'hold' "
                "ORDER BY net_position DESC NULLS LAST LIMIT :lim"
            ),
            {"rid": run_id, "lim": count},
        ).mappings().all()
        if not rows:
            print(f"No hold disposition rows found on run {run_id}.")
            return 0
        for i, r in enumerate(rows):
            action, reason = _ACTIONS[i % len(_ACTIONS)]
            db.execute(
                text(
                    "UPDATE scm.reorder_recommendation "
                    "SET inputs = jsonb_set(COALESCE(inputs, '{}'::jsonb), "
                    "'{disposition_action}', to_jsonb(CAST(:action AS text)), true), "
                    "triggered_reason = :reason "
                    "WHERE id = :id"
                ),
                {"action": action, "reason": reason, "id": r["id"]},
            )
        db.commit()
        print(f"Flipped {len(rows)} disposition row(s) to actionable on run {run_id}.")
        return len(rows)
    finally:
        db.close()


def reset(run_id: str) -> int:
    db = SessionLocal()
    try:
        res = db.execute(
            text(
                "UPDATE scm.reorder_recommendation "
                "SET inputs = jsonb_set(COALESCE(inputs, '{}'::jsonb), "
                "'{disposition_action}', to_jsonb(CAST('hold' AS text)), true) "
                "WHERE run_id = :rid AND rec_type = 'disposition' "
                "AND inputs->>'disposition_action' IN ('discontinue', 'promo')"
            ),
            {"rid": run_id},
        )
        db.commit()
        print(f"Reset {res.rowcount} disposition row(s) back to hold on run {run_id}.")
        return res.rowcount
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Simulate actionable Stock-allocation rows.")
    ap.add_argument("--run", help="Run id (defaults to the latest completed run).")
    ap.add_argument("--count", type=int, default=6, help="How many rows to flip (default 6).")
    ap.add_argument("--reset", action="store_true", help="Flip simulated rows back to hold.")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        run_id = args.run or _latest_completed_run(db)
    finally:
        db.close()
    if not run_id:
        print("No completed run found.")
        return

    if args.reset:
        reset(run_id)
    else:
        simulate(run_id, args.count)


if __name__ == "__main__":
    main()
