"""Public lookup endpoints — used by FE dropdowns and n8n MCP tools."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.models.base import set_company_scope
from app.schemas.lookup import LookupResolveRequest, LookupResolveResponse
from app.services.contact_access_type_service import ContactAccessTypeService
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
    # AC-I3: the MCP forwards contact_id + space_id in the BODY (POST param-order
    # constraint), so the query-param scope resolver never scoped this call.
    # Re-derive the contact's company scope from the body here so a scoped
    # contact's raw value resolves to THEIR company's row, not another company's
    # same-coded row. No contact identity in the body -> leave the resolver scope
    # as-is. An unresolved/orphan contact -> empty scope (0 rows, fail-closed).
    #
    # L3: apply the body-derived override ONLY for the X-API-Key/MCP principal.
    # A logged-in JWT user keeps their own resolver-set active-company scope — a
    # forged contact_id/space_id in the body must never let them re-scope their
    # session into another company's data.
    is_api_key = (current_user or {}).get("auth_method") == "api_key"
    contact_id = (body.contact_id or "").strip()
    space_id = (body.space_id or "").strip()
    if is_api_key and contact_id and space_id:
        company_ids = ContactAccessTypeService(db).resolve_contact_company_ids(
            contact_id, space_id
        )
        set_company_scope(db, frozenset(company_ids))
    return LookupResolverService(db).resolve(body.set_key, body.raw, body.locale)
