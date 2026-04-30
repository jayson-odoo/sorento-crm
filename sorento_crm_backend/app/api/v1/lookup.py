"""Public lookup endpoints — used by FE dropdowns and n8n MCP tools."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.lookup import LookupResolveRequest, LookupResolveResponse
from app.services.lookup_resolver import LookupResolverService
from app.services.lookup_set_service import LookupSetService
from app.models.lookup import LookupOption, LookupOptionKeyword

router = APIRouter()


@router.get("/{set_key}/options")
async def list_options_public(
    set_key: str,
    include_inactive: bool = Query(False),
    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
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
    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
    db: Session = Depends(get_db),
):
    return LookupResolverService(db).resolve(body.set_key, body.raw, body.locale)
