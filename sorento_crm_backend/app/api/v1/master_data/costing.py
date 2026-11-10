"""Product costing: the Costing page, its settings, dated exchange rates and party profiles
(lane PRODUCT-COSTING, `documentation/plans/products/CONTRACT-product-costing.md` section 4).

Every route is gated on the staff session with `require_permission` (never the API-key
variant): `products.cost.view` to read, and `products.party_costing.manage` as well to write.
Exchange-rate writes need `scm.config.manage` instead of manage. No route here imports
anything: the data is maintained on the page.

Nothing here writes `products.list_price` or calls AutoCount.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_actor_user_id, require_permission
from app.services.costing import basis, export as export_service, page, party as party_service
from app.services.costing.actor import acting
from app.services.costing import rates as rate_service
from app.services.costing import save as save_service
from app.services.costing import settings as settings_service
from app.services.costing.formula import to_decimal
from app.services.error_handler import AppException

router = APIRouter()

COST_VIEW = "products.cost.view"
MANAGE = "products.party_costing.manage"
RATE_WRITE = "scm.config.manage"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_view = Depends(require_permission(COST_VIEW))


def _today() -> date:
    from app.services.reports.registry import today_malaysia

    return today_malaysia()


def _actor(request: Request, user: dict) -> Optional[str]:
    """Who the row is stamped to: the real user at the keyboard, also under impersonation."""
    return get_actor_user_id(request, user) if (user or {}).get("id") else None


def _split(value: Optional[str]) -> list:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


# ------------------------------------------------------------------ rows


def _ids(value: Optional[str], name: str) -> list:
    """The ids of a comma-separated filter; a malformed one is a 422, not an empty result."""
    out = _split(value)
    bad = [v for v in out if not party_service.valid_uuid(v)]
    if bad:
        raise AppException(status_code=422, message=f"{name} must be ids.")
    return out


def _rows_query(
    party_id, q, category_id, brand_id, cost_method, has_cost, as_of, page_no, limit, sort, direction
) -> page.RowsQuery:
    methods = _split(cost_method)
    bad = [m for m in methods if m not in basis.METHODS]
    if bad:
        raise AppException(status_code=422, message=f"Unknown cost method: {', '.join(bad)}.")
    return page.RowsQuery(
        party_id=_ids(party_id, 'party_id')[0] if party_id else None, q=q,
        category_ids=_ids(category_id, 'category_id'), brand_ids=_ids(brand_id, 'brand_id'),
        methods=methods, has_cost=bool(has_cost), as_of=as_of, page=page_no, limit=limit,
        sort=sort, direction=direction,
    )


@router.get("/rows")
def get_rows(
    party_id: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Alias of query."),
    category_id: Optional[str] = Query(None),
    brand_id: Optional[str] = Query(None),
    cost_method: Optional[str] = Query(None),
    has_cost: Optional[bool] = Query(None),
    as_of: Optional[date] = Query(None),
    page_no: int = Query(1, ge=1, alias="page"),
    limit: int = Query(50, ge=1, le=500),
    sort: Literal["product_code", "category_name", "landing", "final", "markup_pct", "margin_pct"] = Query(
        "product_code"
    ),
    direction: Literal["asc", "desc"] = Query("asc", alias="dir"),
    _user: dict = _view,
    db: Session = Depends(get_db),
):
    rq = _rows_query(party_id, query or q, category_id, brand_id, cost_method, has_cost, as_of, page_no, limit, sort, direction)
    result = page.list_rows(db, rq, _today())
    return {
        "data": [page.serialize_row(r) for r in result["rows"]],
        "total": result["total"], "page": page_no, "limit": limit,
        "as_of": result["as_of"].isoformat(), "view": result["view"], "party": result["party"],
        "settings": result["settings"],
    }


class RowChange(BaseModel):
    """One product's cells. Only keys present are changed; `null` clears."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    markup_pct: Optional[float] = Field(None, ge=0, lt=10000, allow_inf_nan=False)
    transport_mode: Optional[Literal["add", "multiply"]] = None
    transport_value: Optional[float] = Field(None, lt=1e8, allow_inf_nan=False)
    cost_method: Optional[Literal["primary", "selected", "average", "last_po"]] = None
    cost_method_supplier_id: Optional[str] = None

    @model_validator(mode="after")
    def _cells(self):
        given = self.model_fields_set
        if "transport_mode" in given or "transport_value" in given:
            if (self.transport_mode is None) != (self.transport_value is None):
                raise ValueError("Transport needs a mode and a value together, or neither.")
            if self.transport_value is not None and self.transport_value <= 0:
                raise ValueError("The transport value must be above zero.")
        if "cost_method" in given:
            if self.cost_method == "selected" and not self.cost_method_supplier_id:
                raise ValueError("Selected supplier needs a supplier.")
            if self.cost_method != "selected" and self.cost_method_supplier_id is not None:
                raise ValueError("Only Selected supplier takes a supplier.")
        elif "cost_method_supplier_id" in given:
            raise ValueError("A supplier needs a cost method.")
        return self


class RowsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_id: Optional[str] = None
    changes: list[RowChange] = Field(..., max_length=500)


@router.patch("/rows", dependencies=[_view])
def patch_rows(
    request: Request,
    body: RowsPatch,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    changes = [
        save_service.Change(
            product_id=c.product_id,
            given=frozenset(c.model_fields_set),
            markup_pct=to_decimal(c.markup_pct) if c.markup_pct is not None else None,
            transport_mode=c.transport_mode,
            transport_value=to_decimal(c.transport_value) if c.transport_value is not None else None,
            cost_method=c.cost_method,
            cost_method_supplier_id=c.cost_method_supplier_id,
        )
        for c in body.changes
    ]
    with acting(db, _actor(request, current_user)):
        updated = save_service.apply_changes(db, body.party_id or None, changes, actor=_actor(request, current_user))
    return {"updated": updated}


@router.get("/rows/{product_id}/suppliers")
def get_row_suppliers(
    product_id: str,
    party_id: Optional[str] = Query(None),
    as_of: Optional[date] = Query(None),
    _user: dict = _view,
    db: Session = Depends(get_db),
):
    return {"data": page.supplier_rows(db, product_id, party_id or None, as_of or _today())}


@router.get("/rows/{product_id}/history")
def get_row_history(
    product_id: str,
    party_id: Optional[str] = Query(None),
    _user: dict = _view,
    db: Session = Depends(get_db),
):
    return {"data": page.history(db, product_id, party_id or None)}


@router.get("/export")
def export_rows(
    party_id: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Alias of query."),
    category_id: Optional[str] = Query(None),
    brand_id: Optional[str] = Query(None),
    cost_method: Optional[str] = Query(None),
    has_cost: Optional[bool] = Query(None),
    as_of: Optional[date] = Query(None),
    sort: Literal["product_code", "category_name", "landing", "final", "markup_pct", "margin_pct"] = Query(
        "product_code"
    ),
    direction: Literal["asc", "desc"] = Query("asc", alias="dir"),
    _user: dict = _view,
    db: Session = Depends(get_db),
):
    rq = _rows_query(party_id, query or q, category_id, brand_id, cost_method, has_cost, as_of, 1, None, sort, direction)
    content = export_service.build_workbook(page.list_rows(db, rq, _today()))
    stamp = (as_of or _today()).isoformat()
    return Response(
        content=content, media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="costing-{stamp}.xlsx"'},
    )


# ------------------------------------------------------------------ settings and transport rules


class SettingsBody(BaseModel):
    sst_factor: float = Field(..., gt=0, lt=100, allow_inf_nan=False)
    default_method: Literal["primary", "average", "last_po"]


@router.get("/settings")
def get_settings(_user: dict = _view, db: Session = Depends(get_db)):
    return settings_service.get_settings(db)


@router.put("/settings", dependencies=[_view])
def put_settings(
    request: Request,
    body: SettingsBody,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    with acting(db, _actor(request, current_user)):
        return settings_service.put_settings(
            db, sst_factor=body.sst_factor, default_method=body.default_method, actor=_actor(request, current_user)
        )


class RuleBody(BaseModel):
    mode: Optional[Literal["add", "multiply"]] = None
    value: Optional[float] = Field(None, lt=1e8, allow_inf_nan=False)

    @model_validator(mode="after")
    def _both_or_neither(self):
        if (self.mode is None) != (self.value is None):
            raise ValueError("A rule needs a mode and a value, or neither.")
        if self.value is not None and self.value <= 0:
            raise ValueError("The value must be above zero.")
        return self


@router.get("/category-rules")
def get_category_rules(_user: dict = _view, db: Session = Depends(get_db)):
    return {"data": settings_service.list_category_rules(db)}


@router.put("/category-rules/{category_id}", dependencies=[_view])
def put_category_rule(
    request: Request,
    category_id: str,
    body: RuleBody,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    with acting(db, _actor(request, current_user)):
        return settings_service.put_category_rule(
            db, category_id, mode=body.mode, value=body.value, actor=_actor(request, current_user)
        )


# ------------------------------------------------------------------ exchange rates


class RateCreate(BaseModel):
    currency: str = Field(..., min_length=1, max_length=10)
    effective_from: date
    rate_to_base: Optional[float] = Field(None, gt=0, lt=1e12, allow_inf_nan=False)
    units_per_base: Optional[float] = Field(None, gt=0, lt=1e12, allow_inf_nan=False)
    note: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def _one_rate(self):
        if (self.rate_to_base is None) == (self.units_per_base is None):
            raise ValueError("Give the rate as MYR per unit or as units per MYR 1, not both.")
        return self


class RateUpdate(BaseModel):
    rate_to_base: Optional[float] = Field(None, gt=0, lt=1e12, allow_inf_nan=False)
    units_per_base: Optional[float] = Field(None, gt=0, lt=1e12, allow_inf_nan=False)
    note: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def _at_most_one_rate(self):
        if self.rate_to_base is not None and self.units_per_base is not None:
            raise ValueError("Give the rate as MYR per unit or as units per MYR 1, not both.")
        return self


@router.get("/exchange-rates")
def get_exchange_rates(
    currency: Optional[str] = Query(None), _user: dict = _view, db: Session = Depends(get_db)
):
    return {"data": rate_service.list_rates(db, _today(), currency)}


@router.post("/exchange-rates", status_code=201, dependencies=[_view])
def post_exchange_rate(
    request: Request,
    body: RateCreate,
    current_user: dict = Depends(require_permission(RATE_WRITE)),
    db: Session = Depends(get_db),
):
    with acting(db, _actor(request, current_user)):
        return rate_service.create_rate(
            db, currency=body.currency, effective_from=body.effective_from,
            rate_to_base=body.rate_to_base, units_per_base_in=body.units_per_base, note=body.note,
            actor=_actor(request, current_user), today=_today(),
        )


@router.put("/exchange-rates/{rate_id}", dependencies=[_view])
def put_exchange_rate(
    request: Request,
    rate_id: str,
    body: RateUpdate,
    current_user: dict = Depends(require_permission(RATE_WRITE)),
    db: Session = Depends(get_db),
):
    with acting(db, _actor(request, current_user)):
        return rate_service.update_rate(
            db, rate_id, rate_to_base=body.rate_to_base, units_per_base_in=body.units_per_base,
            note_given="note" in body.model_fields_set, note=body.note, today=_today(),
        )


# ------------------------------------------------------------------ parties


class PartyBody(BaseModel):
    markup_pct: float = Field(..., ge=0, lt=10000, allow_inf_nan=False)
    cost_method: Optional[Literal["primary", "average", "last_po"]] = None
    is_active: bool = True


class PartyProductsBody(BaseModel):
    product_ids: list[str] = Field(..., max_length=500)

    @field_validator("product_ids")
    @classmethod
    def _uuids(cls, ids):
        if not all(party_service.valid_uuid(i) for i in ids):
            raise ValueError("Unknown product.")
        return ids


@router.get("/parties/{customer_id}")
def get_party(customer_id: str, _user: dict = _view, db: Session = Depends(get_db)):
    return party_service.get_party(db, customer_id)


@router.get("/parties/{customer_id}/product-ids")
def get_party_product_ids(customer_id: str, _user: dict = _view, db: Session = Depends(get_db)):
    """Every product id on the party's list: a cheap read with no costing, for the Add products picker."""
    return {"data": party_service.product_ids(db, customer_id)}


@router.put("/parties/{customer_id}", dependencies=[_view])
def put_party(
    request: Request,
    customer_id: str,
    body: PartyBody,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    with acting(db, _actor(request, current_user)):
        return party_service.put_party(
            db, customer_id, markup_pct=body.markup_pct, cost_method=body.cost_method,
            is_active=body.is_active, actor=_actor(request, current_user),
        )


@router.post("/parties/{customer_id}/products", dependencies=[_view])
def post_party_products(
    request: Request,
    customer_id: str,
    body: PartyProductsBody,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    with acting(db, _actor(request, current_user)):
        return party_service.add_products(db, customer_id, body.product_ids, actor=_actor(request, current_user))
