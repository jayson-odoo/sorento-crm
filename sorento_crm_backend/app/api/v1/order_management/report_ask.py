"""`GET /api/v1/order-management/report-ask`: the chatbot's one flexible sales report (lane
REPORT-ENGINE, slice 1a; `documentation/plans/chatbot/PLAN-report-engine.md` section 0 and 10).

A ranking (one `group_by`) or a number over delivered or ordered sales, for a required period,
with the common filters. Every gate runs here, from `contact_id`, never in the lane or the
prompt: the API key, the `sales_orders.sales_report` reveal grant, the audience (a
customer-scoped contact is a DEALER and may only slice by product, brand, category, month),
the contact's stock visibility policy over locations, and the engine's own company arm.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.order_management._contact_scope import (
    enforce_customer_scope,
    require_contact_identity_pair,
)
from app.api.v1.order_management.orders import _normalize_entities
from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.order import Customer
from app.models.product import Brand, ProductCategory
from app.models.sales_agent import SalesAgent
from app.schemas.report_ask import ReportAskResponse
from app.services.error_handler import AppException, handle_not_found
from app.services.reports import ask
from app.services.sales_report_service import _resolve_products
from app.services.uuid_list_param import parse_uuid_list

router = APIRouter()

GRANT = "sales_orders.sales_report"
_RATE_LIMIT = 10
_RATE_WINDOW_SECONDS = 600
_DEALER_MESSAGE = "That breakdown is not available for your account."
_CHANNELS = {"dealer": "Dealer", "project": "Project team"}


def _unprocessable(message: str, code: str) -> AppException:
    return AppException(422, message, code=code)


def _names(db: Session, model: Any, name_column: Any, ids: list[str]) -> list[str]:
    return sorted(str(r[0]) for r in db.query(name_column).filter(model.id.in_(ids)).all())


def _echo(
    db: Session,
    *,
    product_code: str,
    named_customers: Optional[list[str]],
    brand_ids: Optional[list[str]],
    category_ids: Optional[list[str]],
    agent_ids: Optional[list[str]],
    warehouse_codes: list[str],
    channel: Optional[str],
) -> list[dict[str, Any]]:
    """The filters the caller named, by name, in the catalogue's word order."""
    out: list[tuple[str, list[str]]] = []
    if named_customers:
        out.append(("customer", _names(db, Customer, Customer.customer_name, named_customers)))
    if product_code:
        out.append(("product", [product_code.upper()]))
    if brand_ids:
        out.append(("brand", _names(db, Brand, Brand.brand_name, brand_ids)))
    if category_ids:
        out.append(("category", _names(db, ProductCategory, ProductCategory.category_name, category_ids)))
    if agent_ids:
        out.append(("sales_agent", _names(db, SalesAgent, SalesAgent.sales_agent, agent_ids)))
    if warehouse_codes:
        out.append(("location", list(warehouse_codes)))
    if channel:
        out.append(("channel", [_CHANNELS[channel]]))
    return [
        {"key": key, "label": ask.GROUP_LABELS[key], "values": values}
        for key, values in out
        if values
    ]


@router.get("/report-ask")
def report_ask(
    request: Request,
    date_from: Optional[date] = Query(None, description="First day of the period (ISO). Required."),
    date_to: Optional[date] = Query(None, description="Last day of the period (ISO). Required."),
    basis: str = Query("delivered", description="delivered (DO lines by DO date) | ordered (SO lines by SO date)."),
    measure: str = Query("amount", description="amount | qty - what the ranking sorts by."),
    group_by: Optional[str] = Query(
        None,
        description="customer | product | brand | category | sales_agent | location | channel | month. Absent = one total.",
    ),
    top_n: Optional[int] = Query(None, description="1 to 100. Required with group_by."),
    sort: str = Query("desc", description="desc (top) | asc (bottom)."),
    product_code: Optional[str] = Query(None, description="Product code prefix, at least 3 characters."),
    brand_ids: Optional[list[str]] = Query(None),
    category_ids: Optional[list[str]] = Query(None),
    sales_agent_ids: Optional[list[str]] = Query(None),
    customer_ids: Optional[list[str]] = Query(None),
    warehouse_codes: Optional[list[str]] = Query(None),
    channel: Optional[str] = Query(None, description="dealer | project"),
    contact_id: Optional[str] = Query(None, description="Respond.io contact id. Required with space_id."),
    space_id: Optional[str] = Query(None, description="Respond.io workspace id. Required with contact_id."),
    current_user: dict = Depends(require_permission_with_api_key("order_management.orders.view")),
    db: Session = Depends(get_db),
):
    require_contact_identity_pair(contact_id, space_id)
    if not (contact_id and space_id):
        raise AppException(
            422,
            "contact_id and space_id are required",
            detail="contact_id, space_id",
            code="contact_identity_required",
        )
    if not request.headers.get("X-API-Key"):
        raise AppException(403, "This route is for the chatbot only", code="api_key_required")

    if date_from is None or date_to is None:
        raise _unprocessable("date_from and date_to are required", "period_required")
    if date_from > date_to:
        raise _unprocessable("date_from is after date_to", "date_range_inverted")

    basis_norm = (basis or "").strip().lower()
    if basis_norm not in ask.CATALOGUE:
        raise _unprocessable(f"Unknown basis '{basis}'", "unknown_basis")
    measure_norm = (measure or "").strip().lower()
    if measure_norm not in ask.MEASURES:
        raise _unprocessable(f"Unknown measure '{measure}'", "unknown_measure")
    sort_norm = (sort or "").strip().lower()
    if sort_norm not in ("desc", "asc"):
        raise _unprocessable(f"Unknown sort '{sort}'", "unknown_sort")
    group_norm = (group_by or "").strip().lower() or None
    if group_norm is not None and group_norm not in ask.CATALOGUE[basis_norm]["dimensions"]:
        raise _unprocessable(f"Unknown group_by value '{group_by}'", "unknown_group_by")
    if group_norm is not None:
        if top_n is None:
            raise _unprocessable("A ranking needs top_n", "top_n_required")
        if not 1 <= top_n <= 100:
            raise _unprocessable("top_n must be between 1 and 100", "top_n_out_of_range")
    elif top_n is not None and not 1 <= top_n <= 100:
        raise _unprocessable("top_n must be between 1 and 100", "top_n_out_of_range")
    channel_norm = (channel or "").strip().lower() or None
    if channel_norm is not None and channel_norm not in _CHANNELS:
        raise _unprocessable(f"Unknown channel value '{channel}'", "invalid_channel")
    code = (product_code or "").strip()
    if code and len(code) < 3:
        raise _unprocessable("product_code must be at least 3 characters", "product_code_too_short")

    # The reveal grant, off the resolved contact (the sales report route's own gate).
    from app.services.contact_field_reveal_service import granted_keys
    from app.services.field_access import resolve_contact_with_null_workspace_fallback

    resolved = resolve_contact_with_null_workspace_fallback(db, contact_id=contact_id, space_id=space_id)
    keys = granted_keys(db, resolved) if resolved else []
    if GRANT not in keys:
        raise AppException(403, "Sales report is not enabled for your account.", code="sales_report_not_enabled")

    from app.services import rate_limit

    if not rate_limit.hit(
        "report_ask", str(resolved), limit=_RATE_LIMIT, window_seconds=_RATE_WINDOW_SECONDS
    ).allowed:
        return JSONResponse(
            content={
                "status": "busy",
                "message": "Too many reports in the last 10 minutes.",
                "basis": basis_norm,
                "basis_label": ask.CATALOGUE[basis_norm]["label"],
                "measure": measure_norm,
                "sort": sort_norm,
                "group_by": group_norm,
                "group_label": ask.GROUP_LABELS.get(group_norm) if group_norm else None,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "filters": [],
                "rows": [],
                "more": 0,
                "total_count": 0,
                "total": {"qty": 0, "amount": 0.0},
            }
        )

    named_customers = parse_uuid_list(customer_ids, param_name="customer_ids")
    brands = parse_uuid_list(brand_ids, param_name="brand_ids")
    categories = parse_uuid_list(category_ids, param_name="category_ids")
    agents = parse_uuid_list(sales_agent_ids, param_name="sales_agent_ids")
    codes = _normalize_entities(warehouse_codes) or []

    # Audience: a customer-scoped contact is a DEALER, forced to its own customers (a named
    # customer outside them is the scope helper's own 403).
    scoped = enforce_customer_scope(
        db,
        contact_id=contact_id,
        space_id=space_id,
        customer_ids=named_customers,
        customer_query=None,
    )
    if scoped is not None:
        outside = (
            (group_norm is not None and group_norm not in ask.DEALER_KEYS)
            or bool(agents)
            or bool(codes)
            or channel_norm is not None
        )
        if outside:
            raise AppException(403, _DEALER_MESSAGE, code="report_dimension_not_allowed")

    products = _resolve_products(db, code) if code else []
    if code and not products:
        raise handle_not_found("Product", product_code)

    filters: dict[str, list[str]] = {}
    customers = scoped if scoped is not None else named_customers
    if customers:
        filters["customer"] = customers
    if products:
        filters["product"] = [str(p.id) for p in products]
    if brands:
        filters["brand"] = brands
    if categories:
        filters["category"] = categories
    if agents:
        filters["sales_agent"] = agents
    if channel_norm:
        filters["channel"] = [channel_norm]

    from app.services.stock_visibility import resolve_policy

    policy = resolve_policy(db, resolved, space_id) if resolved else None
    data = ask.run_ask(
        db,
        basis=basis_norm,
        measure=measure_norm,
        group_by=group_norm,
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        warehouse_codes=codes,
        policy=policy,
        sort=sort_norm,
        top_n=top_n,
    )
    data.update(
        basis=basis_norm,
        basis_label=ask.CATALOGUE[basis_norm]["label"],
        measure=measure_norm,
        sort=sort_norm,
        group_by=group_norm,
        group_label=ask.GROUP_LABELS[group_norm] if group_norm else None,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        filters=_echo(
            db,
            product_code=code,
            named_customers=named_customers if scoped is None else None,
            brand_ids=brands,
            category_ids=categories,
            agent_ids=agents,
            warehouse_codes=codes,
            channel=channel_norm,
        ),
    )
    return JSONResponse(content=ReportAskResponse(**data).model_dump(mode="json"))
