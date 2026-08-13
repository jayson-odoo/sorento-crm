"""Apply an AutoCount reorder-level listing to `scm.reorder_level`.

AutoCount owns the level; this feed receives it. The reconciliation is the house rule -
same then skip, diff then update, new then create - with one ownership wrinkle inside our
own table:

**A hand-set level is never silently overwritten.** `source` says who wrote the row.
An upload freely updates rows it created (`autocount`) and rows with no level at all, but a
level a person set (`manual` / `accepted_suggestion`) stands, and the disagreement is
REPORTED as a conflict for that person to settle (AC-S13c.3). Feeds have refresh rhythms;
decisions do not, and "last writer wins" between a person and a cron is how a buyer's
number quietly reverts.

The reorder QUANTITY is not contested the same way: nothing in our UI edits it, it is
AutoCount's own figure, so it lands even when the level stands.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.product import Product
from app.models.scm import ReorderLevel
from app.services.scm.reorder_level_reader import LevelReadResult, LevelRow, read_workbook

SOURCE = "autocount"

#: Sources a person wrote. The upload reports a disagreement with these, never resolves it.
_HAND_SET = ("manual", "accepted_suggestion")

#: Below this, two exports of the same number differ by float noise, not by a decision.
_EPSILON = 0.0005

_SAMPLE = 8


def _products_by_code(db: Session, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = (
        db.query(func.upper(func.btrim(Product.product_code)), Product.id)
        .filter(func.upper(func.btrim(Product.product_code)).in_({c.upper() for c in codes}))
        .all()
    )
    return {code: str(pid) for code, pid in rows}


def _warehouses_by_code(db: Session, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = (
        db.query(func.upper(func.btrim(Warehouse.warehouse_code)), Warehouse.id)
        .filter(func.upper(func.btrim(Warehouse.warehouse_code)).in_({c.upper() for c in codes}))
        .all()
    )
    return {code: str(wid) for code, wid in rows}


def _same(a: Optional[float], b: Optional[float]) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) < _EPSILON


def preview(db: Session, data: bytes) -> dict[str, Any]:
    """What the file says and what it would do, before anything is written.

    Runs the same resolution `apply` runs and reports the counts without the writes, so
    the Test button and Confirm cannot disagree about the same file.
    """
    outcome = _resolve(db, read_workbook(data, db=db))
    outcome.pop("_writes", None)
    return outcome


def apply(db: Session, data: bytes, *, actor: Optional[str] = None) -> dict[str, Any]:
    """Write the file. Does not commit; the route owns the transaction."""
    outcome = _resolve(db, read_workbook(data, db=db))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for kind, row, level_row in outcome.pop("_writes"):
        if kind == "create":
            db.add(ReorderLevel(
                id=str(uuid.uuid4()),
                product_id=row["product_id"],
                warehouse_id=row["warehouse_id"],
                level=row["level"],
                reorder_qty=row["reorder_qty"],
                source=SOURCE,
                notes=f"AutoCount upload{f' by {actor}' if actor else ''}",
            ))
        elif kind == "update":
            level_row.level = row["level"]
            if row["reorder_qty"] is not None:
                level_row.reorder_qty = row["reorder_qty"]
            level_row.source = SOURCE
            level_row.updated_at = now
        elif kind == "qty_only":
            # The level stands (a person owns it); AutoCount's quantity still lands.
            level_row.reorder_qty = row["reorder_qty"]
            level_row.updated_at = now
    db.flush()
    return outcome


def _resolve(db: Session, parsed: LevelReadResult) -> dict[str, Any]:
    """Decide what every row means, once, for preview and apply alike."""
    out: dict[str, Any] = {
        "readable": parsed.ok,
        "missing_columns": parsed.missing_columns,
        "unmapped_headers": parsed.unmapped_headers,
        "problems": [{"row": p.row_number, "reason": p.reason} for p in parsed.problems],
        "total_rows": parsed.total_rows,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "conflicts": 0,
        "conflict_rows": [],
        "sample": [
            {
                "item_code": r.item_code,
                "location": r.location,
                "reorder_level": r.reorder_level,
                "reorder_qty": r.reorder_qty,
            }
            for r in parsed.rows[:_SAMPLE]
        ],
        "_writes": [],
    }
    if not parsed.ok:
        return out

    products = _products_by_code(db, {r.item_code for r in parsed.rows})
    warehouses = _warehouses_by_code(db, {r.location for r in parsed.rows if r.location})

    for row in parsed.rows:
        pid = products.get(row.item_code.upper())
        if pid is None:
            out["problems"].append(
                {"row": row.row_number, "reason": f"{row.item_code}: no such item, skipped"}
            )
            continue
        wid: Optional[str] = None
        if row.location is not None:
            wid = warehouses.get(row.location.upper())
            if wid is None:
                # Half-applying it as a product-wide level would put the number somewhere
                # the file did not say.
                out["problems"].append(
                    {"row": row.row_number,
                     "reason": f"{row.item_code}: no such location {row.location}, skipped"}
                )
                continue

        existing: Optional[ReorderLevel] = (
            db.query(ReorderLevel)
            .filter(
                ReorderLevel.product_id == pid,
                ReorderLevel.warehouse_id.is_(None) if wid is None
                else ReorderLevel.warehouse_id == wid,
            )
            .first()
        )
        payload = {
            "product_id": pid,
            "warehouse_id": wid,
            "level": row.reorder_level,
            "reorder_qty": row.reorder_qty,
        }

        if existing is None:
            out["created"] += 1
            out["_writes"].append(("create", payload, None))
            continue

        level_same = _same(
            float(existing.level) if existing.level is not None else None,
            row.reorder_level,
        )
        qty_same = _same(
            float(existing.reorder_qty) if existing.reorder_qty is not None else None,
            row.reorder_qty,
        ) or row.reorder_qty is None

        if level_same and qty_same:
            out["unchanged"] += 1
            continue

        hand_set = (existing.source or "") in _HAND_SET and existing.level is not None
        if hand_set:
            if not level_same:
                out["conflicts"] += 1
                out["conflict_rows"].append({
                    "item_code": row.item_code,
                    "location": row.location,
                    "held_level": float(existing.level),
                    "file_level": row.reorder_level,
                    "held_source": existing.source,
                })
            # The quantity is AutoCount's own figure and lands either way - but through the
            # qty_only write, which leaves `level` AND `source` alone. The full update would
            # flip a manual row to autocount ownership as a side effect of a quantity, and
            # the NEXT upload would then overwrite the level a person set.
            if not qty_same and row.reorder_qty is not None:
                if level_same:
                    out["updated"] += 1
                out["_writes"].append(("qty_only", payload, existing))
            elif level_same:
                out["unchanged"] += 1
            continue

        out["updated"] += 1
        out["_writes"].append(("update", payload, existing))

    return out
