"""Public lookup endpoints — used by FE dropdowns and n8n MCP tools."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.schemas.lookup import LookupResolveRequest, LookupResolveResponse
from app.services.lookup_resolver import LookupResolverService
from app.services.lookup_set_service import LookupSetService
from app.models.lookup import LookupBinding, LookupOption, LookupOptionKeyword, LookupSet

router = APIRouter()


@router.get("/by-binding")
async def options_by_binding(
    table: str = Query(..., min_length=1),
    column: str = Query(..., min_length=1),
    include_inactive: bool = Query(False),
    current_user=Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Return active options for the LookupSet bound to (table, column).

    Response: ``{"set_key": str, "set_name": str, "options": [...]}`` when bound,
    ``{"set_key": null, "set_name": null, "options": []}`` when no binding exists.
    Form fields call this on render to decide whether to render a dropdown.
    """
    binding = (
        db.query(LookupBinding)
        .filter(LookupBinding.table_name == table, LookupBinding.column_name == column)
        .first()
    )
    if binding is None:
        return {"set_key": None, "set_name": None, "default_value": None, "options": []}
    s = db.query(LookupSet).filter(LookupSet.id == binding.set_id).first()
    if s is None or (not s.is_active and not include_inactive):
        return {"set_key": None, "set_name": None, "default_value": None, "options": []}
    q = db.query(LookupOption).filter(LookupOption.set_id == s.id)
    if not include_inactive:
        q = q.filter(LookupOption.is_active.is_(True))
    rows = q.order_by(LookupOption.sort_order.asc(), LookupOption.label.asc()).all()
    options = []
    for o in rows:
        kws = db.query(LookupOptionKeyword).filter(LookupOptionKeyword.option_id == o.id).all()
        options.append({
            "value": o.value, "label": o.label,
            "keywords": [k.keyword for k in kws],
            "is_active": o.is_active,
        })
    return {
        "set_key": s.set_key,
        "set_name": s.name,
        "default_value": binding.default_value,  # FE pre-selects on a new form
        "options": options,
    }


@router.get("/{set_key}/options")
async def list_options_public(
    set_key: str,
    include_inactive: bool = Query(False),
    current_user=Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    s = LookupSetService(db).get_by_key(set_key)
    q = db.query(LookupOption).filter(LookupOption.set_id == s.id)
    if not include_inactive:
        q = q.filter(LookupOption.is_active.is_(True))
    rows = q.order_by(LookupOption.sort_order.asc(), LookupOption.label.asc()).all()
    out = []
    for o in rows:
        kws = db.query(LookupOptionKeyword).filter(LookupOptionKeyword.option_id == o.id).all()
        out.append({
            "value": o.value, "label": o.label,
            "keywords": [k.keyword for k in kws],
            "is_active": o.is_active,
        })
    return out


@router.post("/resolve", response_model=LookupResolveResponse)
async def resolve(
    body: LookupResolveRequest,
    current_user=Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    return LookupResolverService(db).resolve(body.set_key, body.raw, body.locale)
