#!/usr/bin/env python3
"""Make every project on the Lost / Dormant stage carry the matching outcome.

PROJECT-CLASH-LOST (owner, 5 Nov 2026): PPF2611001 sat on the Lost stage while the Projects
list read Outcome "Won", because moving a project onto Lost never touched its stored outcome
(it followed the quotations only). The code now syncs outcome on every stage move
(`project_service.change_status`), but rows moved before that fix stay wrong until repaired.

Rule: project on a status whose key is `lost` or `dormant`, with `outcome` different from
that key -> `outcome = <key>`. Nothing else is touched.

Read-only count for DBeaver (same rule):

    SELECT p.project_code, p.title, s.label AS stage, p.outcome
    FROM projects.projects p
    JOIN public.statuses s ON s.id = p.status_id
    WHERE s.key IN ('lost', 'dormant') AND p.outcome <> s.key
    ORDER BY p.project_code;

Run from sorento_crm_backend/ AFTER `alembic upgrade head`:
    python scripts/backfill_project_outcome_from_stage.py            # dry-run, writes nothing
    python scripts/backfill_project_outcome_from_stage.py --apply    # writes

Idempotent: a second `--apply` run reports zero candidates.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.base import set_company_scope
from app.models.projects import Project
from app.models.status import Status

TERMINAL_KEYS = ("lost", "dormant")


def candidates(db):
    """`(project, status_key)` for every project whose outcome disagrees with its stage."""
    return (
        db.query(Project, Status.key)
        .join(Status, Status.id == Project.status_id)
        .filter(Status.key.in_(TERMINAL_KEYS), Project.outcome != Status.key)
        .order_by(Project.project_code)
        .all()
    )


def backfill(db, apply: bool) -> dict:
    rows = candidates(db)
    changes = [(p.project_code, p.title, p.outcome, key) for p, key in rows]
    if apply:
        for project, key in rows:
            project.outcome = key
        db.commit()
    return {"candidates": len(rows), "updated": len(rows) if apply else 0, "changes": changes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the change. Default is dry-run.")
    args = parser.parse_args()

    db = SessionLocal()
    # No request, no principal: `None` is the sanctioned all-companies scope.
    set_company_scope(db, None)
    try:
        result = backfill(db, apply=args.apply)
        for code, title, old, new in result["changes"]:
            print(f"{code}\t{title}\t{old} -> {new}")
        if args.apply:
            print(f"Done. {result['updated']} project(s) updated.")
            print(f"Re-check: {backfill(db, apply=False)['candidates']} candidate(s) remain.")
        else:
            print(f"[dry-run] {result['candidates']} project(s) would be updated. No writes.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
