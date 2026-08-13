"""Hold one supplier's current stock list, so a container can be planned against it.

A SNAPSHOT per supplier, replaced whole on every upload. The alternative - merging the new
file into the old rows - keeps an item the supplier no longer lists as loadable stock forever,
and the first symptom is a container planned around something that is not in their warehouse.
Replacement is stated in the result (`rows_replaced`) rather than done quietly, because it is
the one destructive thing this upload does.

Which supplier the file describes cannot be derived: the sheet carries model numbers and
quantities, never the name of who wrote it. So it is asked for, once, in the dialog - the only
question this upload puts to the user.

Products are RESOLVED, never created (the rule the Order Inquiry feed established): an
unmatched model number is real stock at the supplier, so the row is kept and reported, but it
cannot join a loading plan, whose lines hang off our own purchase-order lines.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.scm import SupplierInventory
from app.services.scm.supplier_inventory_reader import InventoryReadResult, read_workbook
from app.services.scm.upload_validation import envelope, named

SOURCE_SYSTEM = "scm_supplier_inventory"

#: How many sample rows the preview shows. Enough to recognise the file, short enough to read.
_SAMPLE = 25


def _uuid() -> str:
    return str(uuid.uuid4())


def _parse(db: Session, data: bytes) -> InventoryReadResult:
    return read_workbook(data, db=db)


def _products_by_code(db: Session, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = (
        db.query(Product.product_code, Product.id)
        .filter(Product.product_code.in_(list(codes)))
        .all()
    )
    return {str(code): str(pid) for code, pid in rows}


def _supplier_label(db: Session, supplier_id: str) -> Optional[str]:
    row = db.execute(
        text("SELECT supplier_name FROM suppliers WHERE id = :i"), {"i": supplier_id}
    ).first()
    return row[0] if row else None


def _summarise(db: Session, parsed: InventoryReadResult) -> dict[str, Any]:
    codes = {r.item_code for r in parsed.rows}
    known = _products_by_code(db, codes)
    unmatched = sorted(c for c in codes if c not in known)
    unmeasured = [r.item_code for r in parsed.rows if r.cbm_per_unit is None]
    packed = sum(r.qty_packed for r in parsed.rows)
    unfinished = sum(r.qty_unfinished for r in parsed.rows)
    return {
        "rows": len(parsed.rows),
        "items_matched": len(codes) - len(unmatched),
        "items_unmatched": len(unmatched),
        "unmatched_item_codes": unmatched[:50],
        "qty_packed": packed,
        "qty_unfinished": unfinished,
        # Loadable volume is what the plan spends, so it is stated here rather than left to be
        # discovered when a plan comes back half empty.
        "loadable_cbm": round(
            sum(
                (r.cbm_per_unit or 0) * r.qty_packed
                for r in parsed.rows
                if r.cbm_per_unit is not None
            ),
            3,
        ),
        "items_unmeasured": len(unmeasured),
        "unmeasured_item_codes": sorted(set(unmeasured))[:50],
        "unmapped_headers": parsed.unmapped_headers,
        "unreadable_rows": len(parsed.problems),
    }


def preview(db: Session, data: bytes, *, supplier_id: str) -> dict:
    """What the file says, and what it would replace, before anything is written."""
    parsed = _parse(db, data)
    summary = _summarise(db, parsed) if parsed.ok else {}
    held = (
        db.query(SupplierInventory)
        .filter(SupplierInventory.supplier_id == supplier_id)
        .count()
    )
    return {
        "readable": parsed.ok,
        "missing_columns": parsed.missing_columns,
        "problems": [{"row": p.row_number, "reason": p.reason} for p in parsed.problems[:50]],
        "supplier_id": supplier_id,
        "supplier_name": _supplier_label(db, supplier_id),
        "rows_held_now": held,
        "sample": [
            {
                "item_code": r.item_code,
                "product_name": r.product_name,
                "qty_packed": r.qty_packed,
                "qty_unfinished": r.qty_unfinished,
                "cbm_per_unit": r.cbm_per_unit,
            }
            for r in parsed.rows[:_SAMPLE]
        ],
        "summary": summary,
    }


def validate(db: Session, data: bytes, *, supplier_id: str) -> dict:
    """The Test verdict: the same read `apply` performs, with nothing written."""
    parsed = _parse(db, data)
    if not parsed.ok:
        missing = ", ".join(parsed.missing_columns)
        reason = (
            f"the file has no {missing} column"
            if parsed.missing_columns
            else "the file could not be read"
        )
        problems = [reason] + [f"row {p.row_number}: {p.reason}" for p in parsed.problems[:5]]
        return envelope(ok=False, problems=problems, warnings=[], summary={})

    summary = _summarise(db, parsed)
    warnings = [
        named(
            summary["items_unmatched"],
            summary["unmatched_item_codes"],
            one="model number is not in the catalogue, so it cannot be loaded",
            many="model numbers are not in the catalogue, so they cannot be loaded",
        ),
        named(
            summary["items_unmeasured"],
            summary["unmeasured_item_codes"],
            one="row has no volume, so it cannot be fitted to a container",
            many="rows have no volume, so they cannot be fitted to a container",
        ),
        named(
            len(parsed.problems),
            [f"row {p.row_number}" for p in parsed.problems],
            one="row could not be read",
            many="rows could not be read",
        ),
        named(
            len(parsed.unmapped_headers),
            parsed.unmapped_headers,
            one="column is not recognised and will be ignored",
            many="columns are not recognised and will be ignored",
        ),
    ]
    if not summary["rows"]:
        return envelope(
            ok=False,
            problems=["the file has a header but no stock rows"],
            warnings=[],
            summary=summary,
        )
    return envelope(ok=True, problems=[], warnings=warnings, summary=summary)


def apply(
    db: Session,
    data: bytes,
    *,
    supplier_id: str,
    as_of: Optional[date] = None,
    actor: Optional[str] = None,
) -> dict:
    """Replace this supplier's snapshot with the file. Does not commit."""
    parsed = _parse(db, data)
    if not parsed.ok:
        return {
            "readable": False,
            "missing_columns": parsed.missing_columns,
            "rows_written": 0,
            "rows_replaced": 0,
            "summary": {},
        }

    summary = _summarise(db, parsed)
    stamp = as_of or datetime.now().date()
    known = _products_by_code(db, {r.item_code for r in parsed.rows})

    replaced = (
        db.query(SupplierInventory)
        .filter(SupplierInventory.supplier_id == supplier_id)
        .delete(synchronize_session=False)
    )
    # The delete has to reach the database before the inserts, or the unique identity index
    # rejects a model number that appears in both the old snapshot and the new one.
    db.flush()

    # A supplier who lists the same model twice (two spec lines of one body) is one row here:
    # the loading plan asks "how many can I load", and two rows would answer it twice.
    merged: dict[str, dict] = {}
    for r in parsed.rows:
        cur = merged.setdefault(
            r.item_code,
            {
                "qty_packed": 0.0,
                "qty_unfinished": 0.0,
                "cbm_per_unit": None,
                "product_name": None,
                "brand": None,
                "spec": None,
                "remark": None,
            },
        )
        cur["qty_packed"] += r.qty_packed
        cur["qty_unfinished"] += r.qty_unfinished
        if cur["cbm_per_unit"] is None and r.cbm_per_unit is not None:
            cur["cbm_per_unit"] = r.cbm_per_unit
        for f in ("product_name", "brand", "spec", "remark"):
            if cur[f] is None:
                cur[f] = getattr(r, f)

    written = 0
    for code, v in merged.items():
        db.add(
            SupplierInventory(
                id=_uuid(),
                supplier_id=supplier_id,
                item_code=code,
                product_id=known.get(code),
                qty_packed=v["qty_packed"],
                qty_unfinished=v["qty_unfinished"],
                cbm_per_unit=v["cbm_per_unit"],
                product_name=v["product_name"],
                brand=v["brand"],
                spec=v["spec"],
                remark=v["remark"],
                as_of=stamp,
                uploaded_by=actor,
                source_system=SOURCE_SYSTEM,
                source_ref="supplier_inventory",
            )
        )
        written += 1
    db.flush()

    return {
        "readable": True,
        "missing_columns": [],
        "supplier_id": supplier_id,
        "supplier_name": _supplier_label(db, supplier_id),
        "as_of": stamp.isoformat(),
        "rows_written": written,
        "rows_replaced": replaced,
        "duplicate_models_merged": len(parsed.rows) - written,
        "problems": [{"row": p.row_number, "reason": p.reason} for p in parsed.problems[:50]],
        "summary": summary,
    }
