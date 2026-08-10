"""S10 - the reorder levels the buyer owns, and the movement that suggests them.

Reading a level is a dashboard view; setting one changes what the next plan buys, so it is a
planning action and carries the same permission as launching a run.

No UUID reaches a display field: every row resolves to a product code and a warehouse code.
The ids are still in the payload because that is what a write has to key on.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.base import get_company_scope
from app.services.company_scope import resolve_write_company_id
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm import reorder_level_service as svc

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_EDIT = require_permission_with_api_key("scm.reorder.run")


@router.get("/reorder-levels")
def list_levels(product_query: Optional[str] = Query(None),
                warehouse_id: Optional[str] = Query(None),
                only_unset: bool = Query(False),
                limit: int = Query(200, ge=1, le=1000),
                db: Session = Depends(get_db), _=Depends(_VIEW)) -> dict[str, Any]:
    """Levels with their suggestion, newest-touched first."""
    co, co_params = company_sql_predicate(db, "rl.company_id", param_prefix="rll")
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit, **co_params}
    if product_query:
        where.append("(p.product_code ILIKE :q OR p.product_name ILIKE :q)")
        params["q"] = f"%{product_query}%"
    if warehouse_id:
        where.append("(rl.warehouse_id::text = :wid OR rl.warehouse_id IS NULL)")
        params["wid"] = warehouse_id
    if only_unset:
        where.append("rl.level IS NULL")
    if co:
        where.append(co)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.execute(text(f"""
        SELECT rl.id::text AS id, p.product_code, p.product_name,
               w.warehouse_code, w.segment,
               rl.product_id::text AS product_id,
               rl.warehouse_id::text AS warehouse_id,
               rl.level, rl.source, rl.suggested_level, rl.suggested_at,
               rl.suggestion_basis, rl.notes, rl.updated_at
          FROM scm.reorder_level rl
          JOIN products p ON p.id = rl.product_id
          LEFT JOIN warehouses w ON w.id = rl.warehouse_id
          {clause}
         ORDER BY COALESCE(rl.updated_at, rl.created_at) DESC
         LIMIT :limit
    """), params).mappings().all()
    return {"rows": [_row(r) for r in rows], "count": len(rows)}


@router.put("/reorder-levels")
def set_level(payload: dict = Body(...), db: Session = Depends(get_db),
              _=Depends(_EDIT)) -> dict[str, Any]:
    """Set the level for one (product, location). `warehouse_id` omitted = product-wide."""
    product_id = payload.get("product_id")
    if not product_id:
        raise AppException(status_code=422, message="product_id is required.")
    level = payload.get("level")
    row = svc.upsert_level(
        db, product_id=str(product_id),
        warehouse_id=(str(payload["warehouse_id"]) if payload.get("warehouse_id") else None),
        level=(float(level) if level is not None else None),
        source=str(payload.get("source") or svc.SOURCE_MANUAL),
        notes=payload.get("notes"),
        company_id=_company_id(db))
    return _row(row)


@router.post("/reorder-levels/accept-suggestion")
def accept(payload: dict = Body(...), db: Session = Depends(get_db),
           _=Depends(_EDIT)) -> dict[str, Any]:
    """Take our number as the buyer's own. The stored suggestion is copied at its current
    value, so a later refresh cannot silently move a level somebody has agreed to."""
    product_id = payload.get("product_id")
    if not product_id:
        raise AppException(status_code=422, message="product_id is required.")
    row = svc.accept_suggestion(
        db, product_id=str(product_id),
        warehouse_id=(str(payload["warehouse_id"]) if payload.get("warehouse_id") else None),
        company_id=_company_id(db))
    return _row(row)


@router.post("/reorder-levels/refresh-suggestions")
def refresh(payload: dict = Body(default_factory=dict), db: Session = Depends(get_db),
            _=Depends(_EDIT)) -> dict[str, Any]:
    """Recompute suggestions from the last N months of movement. Stored levels are untouched."""
    product_ids = [str(p) for p in (payload.get("product_ids") or [])]
    if not product_ids:
        raise AppException(status_code=422,
                           message="Name the products whose suggestions should be recomputed.")
    warehouse_ids = [str(w) for w in (payload.get("warehouse_ids") or [])] or None
    written = svc.refresh_suggestions(
        db, product_ids, warehouse_ids,
        study_months=int(payload.get("study_months") or svc.DEFAULT_STUDY_MONTHS),
        cover_months=float(payload.get("cover_months") or svc.DEFAULT_COVER_MONTHS),
        company_id=_company_id(db))
    return {"updated": written}


@router.get("/reorder-levels/movement")
def movement(product_id: str = Query(...), warehouse_id: Optional[str] = Query(None),
             months: int = Query(svc.DEFAULT_STUDY_MONTHS, ge=1, le=24),
             db: Session = Depends(get_db), _=Depends(_VIEW)) -> dict[str, Any]:
    """What actually left the building, by month. The evidence behind a suggestion."""
    data = svc.monthly_movement(db, [product_id],
                                [warehouse_id] if warehouse_id else None, months=months)
    return {"product_id": product_id, "months": data.get(product_id, [])}


def _row(r: Any) -> dict[str, Any]:
    d = dict(r)
    return {
        "id": d.get("id"),
        "product_id": d.get("product_id"),
        "product_code": d.get("product_code"),
        "product_name": d.get("product_name"),
        "warehouse_id": d.get("warehouse_id"),
        # None here is a fact, not a gap: the level applies to the product everywhere.
        "warehouse_code": d.get("warehouse_code"),
        "segment": d.get("segment"),
        "level": _f(d.get("level")),
        "source": d.get("source"),
        "suggested_level": _f(d.get("suggested_level")),
        "suggested_at": d.get("suggested_at").isoformat() if d.get("suggested_at") else None,
        "suggestion_basis": d.get("suggestion_basis"),
        "notes": d.get("notes"),
    }


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def _company_id(db: Session) -> Optional[str]:
    """The active company, stamped by hand because these writes are raw SQL.

    Raw SQL bypasses the ORM's `before_insert` stamp entirely, so an unstamped level lands
    with a NULL company_id and is then invisible to every scoped read - which looks like the
    save silently failed. No `ambiguous` default: a request that cannot name one company must
    not create a level, because the next planning run would read it for everybody.
    """
    return resolve_write_company_id(get_company_scope(db))
