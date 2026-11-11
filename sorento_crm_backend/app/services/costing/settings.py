"""Company costing settings and the per-category transport rules (AC-ST-01, AC-ST-02).

Every write goes through the ORM so the audit listener records the old and new values. Saving
an identical value changes nothing and writes nothing.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.costing import CostingCategoryRule, CostingSettings
from app.models.product import ProductCategory
from app.services.costing import basis
from app.services.error_handler import AppException
from app.services.costing.formula import to_decimal


def get_settings(db: Session) -> dict:
    """The saved settings, or the defaults (1.1 / primary) when nothing was saved. A read
    writes nothing."""
    sst, method = basis.load_settings(db)
    return {"sst_factor": float(sst), "default_method": method}


def put_settings(db: Session, *, sst_factor: float, default_method: str, actor: Optional[str]) -> dict:
    if sst_factor is None or to_decimal(sst_factor) <= 0:
        raise AppException(status_code=422, message="The SST factor must be greater than zero.")
    if default_method not in ("primary", "average", "last_po"):
        raise AppException(
            status_code=422,
            message="The default cost method is Primary supplier, Average or Last PO price.",
        )
    row = db.query(CostingSettings).first()
    value = to_decimal(sst_factor)
    if row is None:
        db.add(CostingSettings(
            id=str(uuid.uuid4()), sst_factor=value, default_method=default_method, updated_by=actor,
        ))
    else:
        if Decimal(row.sst_factor) != value:
            row.sst_factor = value
        if row.default_method != default_method:
            row.default_method = default_method
        if db.is_modified(row):
            row.updated_by = actor
    db.commit()
    return get_settings(db)


def list_category_rules(db: Session) -> list[dict]:
    """Every category, with its rule or nulls."""
    rules = {r.category_id: r for r in db.query(CostingCategoryRule).all()}
    out = []
    for cat in db.query(ProductCategory).order_by(ProductCategory.category_name):
        rule = rules.get(cat.id)
        out.append({
            "category_id": str(cat.id),
            "category_name": cat.category_name,
            "mode": rule.mode if rule else None,
            "value": float(rule.value) if rule else None,
        })
    return out


def put_category_rule(
    db: Session, category_id: str, *, mode: Optional[str], value: Optional[float], actor: Optional[str]
) -> dict:
    try:
        uuid.UUID(str(category_id))
    except ValueError:
        raise AppException(status_code=404, message="Category not found.", code="NOT_FOUND")
    cat = db.query(ProductCategory).filter(ProductCategory.id == str(category_id)).first()
    if cat is None:
        raise AppException(status_code=404, message="Category not found.", code="NOT_FOUND")
    if (mode is None) != (value is None):
        raise AppException(status_code=422, message="A rule needs both a mode and a value, or neither.")
    if mode is not None and (mode not in ("add", "multiply") or to_decimal(value) <= 0):
        raise AppException(status_code=422, message="A rule is Add or Multiply, with a value above zero.")

    row = db.query(CostingCategoryRule).filter(CostingCategoryRule.category_id == cat.id).first()
    if mode is None:
        if row is not None:
            db.delete(row)
    else:
        new_value = to_decimal(value)
        if row is None:
            db.add(CostingCategoryRule(category_id=cat.id, mode=mode, value=new_value, updated_by=actor))
        else:
            if row.mode != mode:
                row.mode = mode
            if Decimal(row.value) != new_value:
                row.value = new_value
            if db.is_modified(row):
                row.updated_by = actor
    db.commit()
    return {
        "category_id": str(cat.id), "mode": mode, "value": float(value) if value is not None else None,
    }
