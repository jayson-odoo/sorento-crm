"""`GET /api/v1/order-management/report-ask`: the chatbot's one flexible sales report (lane
REPORT-ENGINE, slice 1a; `documentation/plans/chatbot/PLAN-report-engine.md` section 0 and 10).

A ranking (one `group_by`) or a number over delivered, ordered or outstanding sales (all from
sales order lines), for a required period, with the common filters. Every gate runs here, from
`contact_id`, never in the lane or the prompt: the API key, the `sales_orders.sales_report`
reveal grant, the audience (a customer-scoped contact is a DEALER and may only slice by product,
brand, category, month), the contact's stock visibility policy over locations, and the engine's
own company arm.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import false, func, or_, text
from sqlalchemy.orm import Session

from app.api.v1.order_management._contact_scope import (
    enforce_customer_scope,
    require_contact_identity_pair,
)
from app.api.v1.order_management.orders import _normalize_entities
from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.models.base import company_scope, set_brand_scope
from app.models.company import Company, RespondContactCompany
from app.models.order import Customer
from app.models.product import Brand, Product, ProductCategory
from app.models.sales_agent import SalesAgent
from app.services import contact_asker
from app.schemas.report_ask import ReportAskChatResponse, ReportAskResponse
from app.services.contact_brand_scope import contact_brand_scope
from app.services.error_handler import AppException, handle_not_found
from app.services.reports import ask, spec_set
from app.services.sales_report_service import TOP_SELLING_N_CEILING, _resolve_products
from app.services.uuid_list_param import parse_uuid_list

router = APIRouter()

GRANT = "sales_orders.sales_report"
#: The reveal the outstanding kinds (`ask.OPEN_BASES`) need instead of `GRANT` (owner Q6, 27 Oct 2026).
OUTSTANDING_GRANT = "sales_orders.outstanding"
#: The cap's defaults, used only when the settings row is missing: the live numbers are
#: `system_settings.report_ask_rate_limit` / `report_ask_rate_window_minutes`.
_DEFAULT_RATE_LIMIT = 10
_DEFAULT_RATE_WINDOW_MINUTES = 10
_DEALER_MESSAGE = "That breakdown is not available for your account."
_CHANNEL_LABELS = {"dealer": "Dealer", "project": "Project team"}
_CHANNELS = {c: _CHANNEL_LABELS[c] for c in ask.SALES_CHANNELS}
#: The route's default basis for a direct API caller that names none: invoiced, the one sales
#: definition (SALES-UNIFIED). The chatbot lane never relies on it: it always sends one.
DEFAULT_BASIS = "invoiced"
_MAX_VALUES = 50
_MIN_YEAR, _MAX_YEAR = 1900, 2200

#: Every query key the route declares; any other is 422 `unknown_param`.
_PARAMS = frozenset(
    {
        "date_from", "date_to", "basis", "measure", "group_by", "top_n", "sort", "product_code",
        "product_ids", "brand_ids", "category_ids", "sales_agent_ids", "customer_ids", "warehouse_codes",
        "channel", "contact_id", "space_id", "customer_agent_ids", "dataset", "compare_to", "mine", "spec", "company",
    }
)
#: The chat dataset's own query keys (CA-3); any other is 422 `unknown_param`.
_CHAT_PARAMS = frozenset(
    {
        "dataset", "date_from", "date_to", "basis", "measure", "group_by", "top_n", "sort", "subjects",
        "product_ids", "customer_ids", "contact_id", "space_id", "askers", "category_ids", "brand_ids",
    }
)
CHAT_GRANT = "chatbot.analytics"
_CHAT_DEFAULT_BASIS = "asks"
_CHAT_DEFAULT_MEASURE = "asks"
#: The filter params: present but resolving to nothing is 422 `empty_filter`, never "no filter".
_FILTER_PARAMS = (
    "product_code", "product_ids", "brand_ids", "category_ids", "sales_agent_ids", "customer_ids",
    "warehouse_codes", "channel", "customer_agent_ids",
)
#: The echo's name for the "(no agent)" key in an agent filter (REPORT-DRILLDOWN).
_NO_AGENT_NAME = "(no agent)"
#: The echo line of a run limited to the asking salesperson's own customers.
_BOOK_LABEL, _BOOK_VALUE = "Limited to", "your customers"


def _agent_values(raw: Optional[list[str]], param_name: str) -> Optional[list[str]]:
    """An agent id list that may also name `ask.NO_AGENT_KEY` ("no agent", the drill down of a
    "(no agent)" row): the parsed ids, plus the key when named. None when nothing is given."""
    if raw is None:
        return None
    pieces = [p.strip() for item in raw for p in str(item or "").split(",") if p.strip()]
    none = any(p.lower() == ask.NO_AGENT_KEY for p in pieces)
    ids = parse_uuid_list([p for p in pieces if p.lower() != ask.NO_AGENT_KEY], param_name=param_name) or []
    out = ids + ([ask.NO_AGENT_KEY] if none else [])
    return out or None


def _rate_limit_setting(db: Session) -> tuple[int, int]:
    """`(limit, window_minutes)` from System Settings, read per request so a change on the
    Chatbot media page applies on the next report with no restart. A limit of 0 means no limit."""
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    limit = getattr(row, "report_ask_rate_limit", None) if row else None
    window = getattr(row, "report_ask_rate_window_minutes", None) if row else None
    return (
        _DEFAULT_RATE_LIMIT if limit is None else int(limit),
        int(window) if window else _DEFAULT_RATE_WINDOW_MINUTES,
    )


def _unprocessable(message: str, code: str, detail: Optional[str] = None) -> AppException:
    return AppException(422, message, detail=detail, code=code)


def _allowed(values: Any) -> str:
    return "allowed: " + ", ".join(values)


def _lookup_pairs(
    db: Session, model: Any, name_column: Any, ids: list[str], grants: set[str], label: str,
    *, shared: bool = False,
) -> list[tuple[str, str]]:
    """`(id, name)` of `ids`, inside the contact's companies. An id naming no row is 404, so a
    named filter never quietly widens to "no filter"."""
    # No company of its own: every id is outside the contact's companies (fail closed).
    cond = model.company_id.in_(sorted(grants)) if grants else false()
    if grants and shared:
        cond = or_(model.company_id.is_(None), cond)
    with company_scope(db, None):
        rows = db.query(model.id, name_column).filter(model.id.in_(ids), cond).all()
    found = {str(i): str(n) for i, n in rows}
    for wanted in ids:
        if wanted not in found:
            raise handle_not_found(label, wanted)
    return list(found.items())


def _lookup(
    db: Session, model: Any, name_column: Any, ids: list[str], grants: set[str], label: str,
    *, shared: bool = False,
) -> list[str]:
    """The names of `ids` (`_lookup_pairs`), sorted."""
    return sorted(n for _i, n in _lookup_pairs(db, model, name_column, ids, grants, label, shared=shared))


def _echo(
    db: Session,
    grants: set[str],
    *,
    product_code: str,
    product_names: list[str],
    customers: Optional[list[str]],
    brands: Optional[list[str]],
    categories: Optional[list[str]],
    agents: Optional[list[str]],
    warehouse_codes: list[str],
    channel: Optional[str],
    card_agents: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """The filters the caller named, by name, in the catalogue's word order. Looks every id
    up, so an id naming no row is 404 here."""
    out: list[tuple[str, list[str]]] = []
    if customers:
        out.append(("customer", _lookup(db, Customer, Customer.customer_name, customers, grants, "Customer")))
    if product_names:
        out.append(("product", product_names))
    elif product_code:
        out.append(("product", [product_code.upper()]))
    if brands:
        # Chat fix PR-B S6 (AC-B8): each name once (a brand per company is one brand).
        out.append(("brand", sorted(set(_lookup(db, Brand, Brand.brand_name, brands, grants, "Brand")))))
    if categories:
        # Chat fix PR-B S6: a category by its readable class label ("Water Closet"), never the
        # code its live name copies ("SRT-WC"); a category with no label keeps its name.
        label = func.coalesce(ProductCategory.class_label, ProductCategory.category_name)
        out.append(("category", sorted(set(_lookup(db, ProductCategory, label, categories, grants, "Category")))))
    for key, values in (("sales_agent", agents), ("customer_agent", card_agents)):
        if values:
            ids = [v for v in values if v != ask.NO_AGENT_KEY]
            names = _lookup(db, SalesAgent, SalesAgent.sales_agent, ids, grants, "Sales agent", shared=True) if ids else []
            out.append((key, sorted(names + ([_NO_AGENT_NAME] if ask.NO_AGENT_KEY in values else []))))
    if warehouse_codes:
        out.append(("location", list(warehouse_codes)))
    if channel:
        out.append(("channel", [_CHANNELS[channel]]))
    return [{"key": key, "label": ask.FILTER_LABELS[key], "values": values} for key, values in out if values]


#: REPORT-SMART-1021: keys a sales body carries only when counted or compared, so a body
#: that is neither stays what every caller already reads.
_OPTIONAL_KEYS = ("count", "prev", "change_pct", "compare_to", "compare_from", "compare_until", "code", "sales_agent_fill_rate", "summary")


def _drop_unset(part: dict, compared: bool) -> dict:
    for key in _OPTIONAL_KEYS:
        # A compared body keeps `change_pct` None: the earlier figure was zero ("new").
        if part.get(key, 0) is None and not (compared and key == "change_pct"):
            part.pop(key)
    return part


def _response(data: dict) -> JSONResponse:
    content = ReportAskResponse(**data).model_dump(mode="json")
    compared = content.get("compare_to") is not None
    _drop_unset(content, compared)
    _drop_unset(content["total"], compared)
    for row in content["rows"]:
        _drop_unset(row, compared)
    for group in (content.get("summary") or {}).get("groups", []):
        for row in group["rows"]:
            if row.get("ordered_qty") is None:
                row.pop("ordered_qty")
    return JSONResponse(content=content)


@router.get("/report-ask")
def report_ask(
    request: Request,
    date_from: Optional[date] = Query(
        None, description="First day of the period (ISO). Required, except on outstanding / pending_delivery / unpaid."
    ),
    date_to: Optional[date] = Query(
        None, description="Last day of the period (ISO). Required, except on outstanding / pending_delivery / unpaid."
    ),
    basis: str = Query(
        DEFAULT_BASIS,
        description="invoiced (default) | delivered | ordered | outstanding | pending_delivery | unpaid. invoiced = SALES: "
        "billing document lines, invoices + cash sales + debit notes - credit notes, excluding tax, by document date (the "
        "Top selling items report's figures; no location). delivered / ordered / outstanding rank SALES ORDER lines (the "
        "SO's own agent), dated by the line's required date, else the SO date; pending_delivery ranks the lines of "
        "delivery orders not yet delivered (by DO date); unpaid sums what posted invoices still owe (by document date; "
        "no product, place or channel axis).",
    ),
    measure: str = Query(
        "amount",
        description="amount | qty | customers | orders | products - what the ranking sorts by (the last three count).",
    ),
    group_by: Optional[str] = Query(
        None,
        description="customer | product | brand | category | sales_agent | location | channel | month | spec:<key>. "
        "Absent = one total.",
    ),
    top_n: Optional[int] = Query(None, description=f"1 to {TOP_SELLING_N_CEILING}. Required with group_by."),
    sort: str = Query("desc", description="desc (top) | asc (bottom)."),
    product_code: Optional[str] = Query(None, description="Product code prefix, at least 3 characters."),
    product_ids: Optional[list[str]] = Query(None, description="Product ids; ANDed with product_code."),
    brand_ids: Optional[list[str]] = Query(None),
    category_ids: Optional[list[str]] = Query(None),
    sales_agent_ids: Optional[list[str]] = Query(None),
    customer_ids: Optional[list[str]] = Query(None),
    customer_agent_ids: Optional[list[str]] = Query(
        None,
        description="Customers whose assigned agent (the customer card) is one of these; 'none' = no agent.",
    ),
    warehouse_codes: Optional[list[str]] = Query(None),
    channel: Optional[str] = Query(None, description="dealer | project"),
    dataset: str = Query("sales", description="sales (default) | chat."),
    compare_to: Optional[str] = Query(
        None, description="previous_period (the same number of days just before) | last_year (the same dates)."
    ),
    mine: bool = Query(False, description="A salesperson's own customers only."),
    company: Optional[str] = Query(
        None, description="A company name, code or id; narrows the contact's own companies to that one (403 if not theirs)."
    ),
    spec: Optional[list[str]] = Query(
        None,
        description="key:value product spec; the same key repeated = any of, different keys = all of. "
        "Applied through the spec registry (a number may carry its unit).",
    ),
    subjects: Optional[list[str]] = Query(None, description="Chat only: subject (domain) codes."),
    askers: Optional[list[str]] = Query(None, description="Chat only: dealer | salesperson | staff | unclassified."),
    contact_id: Optional[str] = Query(None, description="Respond.io contact id. Required with space_id."),
    space_id: Optional[str] = Query(None, description="Respond.io workspace id. Required with contact_id."),
    current_user: dict = Depends(require_permission_with_api_key("order_management.orders.view")),
    db: Session = Depends(get_db),
):
    contact_id = (contact_id or "").strip() or None
    space_id = (space_id or "").strip() or None
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
    dataset_norm = (dataset or "").strip().lower()
    if dataset_norm not in ask.DATASETS:
        raise _unprocessable(f"Unknown dataset '{dataset}'", "unknown_dataset", _allowed(ask.DATASETS))
    if dataset_norm == "chat":
        return _chat_report_ask(
            request, db, date_from=date_from, date_to=date_to, basis=basis, measure=measure,
            group_by=group_by, top_n=top_n, sort=sort, subjects=subjects, product_ids=product_ids,
            customer_ids=customer_ids, contact_id=contact_id, space_id=space_id, askers=askers,
            category_ids=category_ids, brand_ids=brand_ids,
        )
    for key in request.query_params.keys():
        if key not in _PARAMS:
            raise _unprocessable(f"Unknown parameter '{key}'", "unknown_param", key)

    # An outstanding basis may leave the period off (both dates or neither): absent = every date.
    all_dates = (basis or "").strip().lower() in ask.OPEN_BASES and date_from is None and date_to is None
    if all_dates:
        date_from, date_to = date(_MIN_YEAR, 1, 1), date(_MAX_YEAR, 12, 31)
    if date_from is None or date_to is None:
        raise _unprocessable("date_from and date_to are required", "period_required")
    if not all(_MIN_YEAR <= d.year <= _MAX_YEAR for d in (date_from, date_to)):
        raise _unprocessable(
            f"Dates must fall in {_MIN_YEAR} to {_MAX_YEAR}", "date_out_of_range", "date_from, date_to"
        )
    if date_from > date_to:
        raise _unprocessable("date_from is after date_to", "date_range_inverted")
    if len(spec or []) > _MAX_VALUES:
        raise _unprocessable(f"Too many values for 'spec' (max {_MAX_VALUES})", "too_many_values", "spec")
    try:
        spec_terms = spec_set.parse(spec or [])
    except ValueError as exc:
        raise _unprocessable(f"'{exc}' is not key:value", "invalid_spec", "spec") from exc

    basis_norm = (basis or "").strip().lower()
    if basis_norm not in ask.CATALOGUE["sales"]:
        raise _unprocessable(f"Unknown basis '{basis}'", "unknown_basis", _allowed(ask.CATALOGUE["sales"]))
    measure_norm = (measure or "").strip().lower()
    if measure_norm not in ask.SALES_MEASURES:
        raise _unprocessable(f"Unknown measure '{measure}'", "unknown_measure", _allowed(ask.SALES_MEASURES))
    sort_norm = (sort or "").strip().lower()
    if sort_norm not in ("desc", "asc"):
        raise _unprocessable(f"Unknown sort '{sort}'", "unknown_sort", _allowed(("desc", "asc")))
    group_norm = (group_by or "").strip().lower() or None
    dimensions = ask.CATALOGUE["sales"][basis_norm]["dimensions"]
    spec_group = group_norm is not None and group_norm.startswith(ask.SPEC_GROUP)
    spec_key = group_norm[len(ask.SPEC_GROUP):] if spec_group else None
    spec_rows = spec_set.registry(db) if spec_group else {}
    if group_norm is not None and not (
        ("product" in dimensions and spec_key in spec_rows) if spec_group else group_norm in dimensions
    ):
        raise _unprocessable(f"Unknown group_by value '{group_by}'", "unknown_group_by", _allowed(dimensions))
    if group_norm is not None and top_n is None:
        raise _unprocessable("A ranking needs top_n", "top_n_required")
    if top_n is not None and not 1 <= top_n <= TOP_SELLING_N_CEILING:
        raise _unprocessable(f"top_n must be between 1 and {TOP_SELLING_N_CEILING}", "top_n_out_of_range")
    compare_norm = (compare_to or "").strip().lower() or None
    if compare_norm is not None and compare_norm not in ask.COMPARE_TO:
        raise _unprocessable(f"Unknown compare_to '{compare_to}'", "unknown_compare_to", _allowed(ask.COMPARE_TO))
    if compare_norm is not None and all_dates:
        raise _unprocessable("compare_to needs a period", "period_required", "date_from, date_to")
    if compare_norm is not None and (group_by or "").strip().lower() == "month":
        # Rows are matched by name and a month's name is its month: nothing would match.
        raise _unprocessable("compare_to does not apply to a month breakdown", "compare_by_month", "compare_to")
    channel_norm = (channel or "").strip().lower() or None
    if channel_norm is not None and channel_norm not in _CHANNELS:
        raise _unprocessable(f"Unknown channel value '{channel}'", "invalid_channel", _allowed(_CHANNELS))
    code = (product_code or "").strip()
    if code and len(code) < 3:
        raise _unprocessable("product_code must be at least 3 characters", "product_code_too_short")

    named_customers = parse_uuid_list(customer_ids, param_name="customer_ids")
    named_products = parse_uuid_list(product_ids, param_name="product_ids")
    brands = parse_uuid_list(brand_ids, param_name="brand_ids")
    categories = parse_uuid_list(category_ids, param_name="category_ids")
    agents = _agent_values(sales_agent_ids, "sales_agent_ids")
    card_agents = _agent_values(customer_agent_ids, "customer_agent_ids")
    codes = _normalize_entities(warehouse_codes) or []
    if basis_norm == "invoiced":
        # Finance data: the reports' own slug on the act-as principal, not only orders.view
        # (SALES-UNIFIED security review M1).
        from app.services.sales.invoiced_sales import require_invoiced_access

        require_invoiced_access(db, current_user)
    if basis_norm == "invoiced" and (codes or group_norm == "location"):
        # A billing document line has no warehouse (SALES-UNIFIED, contract section 7).
        raise _unprocessable(
            "Invoiced sales have no location; ask delivered or ordered sales by location",
            "location_needs_order_basis", "basis",
        )
    resolved_filters = {
        "product_code": code,
        "product_ids": named_products,
        "brand_ids": brands,
        "category_ids": categories,
        "sales_agent_ids": agents,
        "customer_ids": named_customers,
        "warehouse_codes": codes,
        "channel": channel_norm,
        "customer_agent_ids": card_agents,
    }
    for name in _FILTER_PARAMS:
        if name in request.query_params.keys() and not resolved_filters[name]:
            raise _unprocessable(f"'{name}' was given but names nothing", "empty_filter", name)
    for name in (
        "product_ids", "brand_ids", "category_ids", "sales_agent_ids", "customer_ids", "warehouse_codes",
        "customer_agent_ids",
    ):
        if len(resolved_filters[name] or []) > _MAX_VALUES:
            raise _unprocessable(f"Too many values for '{name}' (max {_MAX_VALUES})", "too_many_values", name)

    # The reveal grant, off the resolved contact (the sales report route's own gate).
    from app.services.contact_field_reveal_service import granted_keys
    from app.services.field_access import resolve_contact_with_null_workspace_fallback

    resolved = resolve_contact_with_null_workspace_fallback(db, contact_id=contact_id, space_id=space_id)
    keys = granted_keys(db, resolved) if resolved else []
    # The reveal follows the basis: the outstanding kinds need the Outstanding reveal (and no Sales report one), the
    # sales bases the Sales report one. A linked contact is forced to its own customers on every basis below.
    outstanding_kind = basis_norm in ask.OPEN_BASES
    granted = (OUTSTANDING_GRANT if outstanding_kind else GRANT) in keys
    # Owner 28 Oct 08:40: ONE rule for totals and rankings, set by the contact's linked customer. A contact with no
    # linked customer sees ALL figures, a live salesperson without the reveal included; a linked contact is forced to its
    # customers below (`enforce_customer_scope`). Only a "my ..." ask is narrowed to a salesperson's own book.
    # The one rule the chatbot seams share (`contact_asker.may_ask_sales_ranking`).
    decision, book = contact_asker.may_ask_sales_ranking(db, str(resolved) if resolved else None, granted=granted)
    if decision == "not_granted" and basis_norm == "pending_delivery" and resolved and contact_asker.pending_delivery_open(db, str(resolved)):
        # Owner 29 Oct (REPORT-OUTSTANDING-SUMMARY, #b6e9): as before #1922, pending delivery needs no reveal; undelivered
        # orders and unpaid invoices do. Only a contact the company knows: office staff (every customer) or a linked
        # contact (its own customers, `enforce_customer_scope` below). An unknown contact stays refused. A live
        # salesperson never reaches here (its decision is its own book, Q6). `granted` stays False: the agent axis and
        # filters stay refused below (`own_book_only`), as pre-#1922 pending delivery had none (security S1).
        decision = "granted"
    if decision == "not_granted":
        if outstanding_kind:
            raise AppException(403, "Outstanding is not enabled for your account.", code="outstanding_not_enabled")
        raise AppException(403, "Sales report is not enabled for your account.", code="sales_report_not_enabled")
    # The 08:40 ruling is about SALES figures. The outstanding kinds keep Q6 (the Outstanding reveal): a salesperson without
    # it stays on its own book there and never takes the agent axes.
    # Owner 28 Oct: unpaid invoices are receivables. They need the Outstanding reveal for everyone, a salesperson with a
    # book included (no own-book exception), AND `finance.billing_documents.view` on the act-as user.
    if basis_norm == "unpaid":
        if not granted:
            raise AppException(403, "Outstanding is not enabled for your account.", code="outstanding_not_enabled")
        from app.services.sales.invoiced_sales import require_unpaid_access

        require_unpaid_access(db, current_user)
    own_book_only = outstanding_kind and not granted
    if own_book_only and (group_norm == "sales_agent" or agents or card_agents):
        raise AppException(403, _DEALER_MESSAGE, code="report_dimension_not_allowed")
    narrowed = book is not None and (mine or own_book_only)

    # Brand scope off the contact this route already resolved, whatever the key: the router
    # dependency stamps it only for the legacy shared key (security H1). Stamped before any
    # query below, the echo lookups included. Unscoped: nothing set.
    brand_scope = contact_brand_scope(db, contact_id, space_id)
    if brand_scope:
        set_brand_scope(db, brand_scope)
        if basis_norm == "unpaid":
            # A document has no brand: a brand-scoped contact cannot be held to its brands here.
            raise AppException(403, _DEALER_MESSAGE, code="report_dimension_not_allowed")
    per_document = basis_norm == "unpaid"
    hidden: set[str] = set()
    if (spec_terms and not per_document) or spec_group:
        from app.services.spec_visibility import contact_hidden_keys

        hidden = contact_hidden_keys(db, contact_id, space_id)
    if spec_group and spec_key in hidden:
        raise _unprocessable(f"Unknown group_by value '{group_by}'", "unknown_group_by", _allowed(dimensions))
    if spec_group and measure_norm in ask.COUNT_MEASURES:
        # Distinct counts do not add up across the products of a group. After the hidden-key check, so a hidden key
        # answers exactly as an unregistered one does.
        raise _unprocessable("A spec breakdown ranks by amount or qty", "unknown_measure", _allowed(ask.MEASURES))

    common = {
        "basis": basis_norm,
        "basis_label": ask.CATALOGUE["sales"][basis_norm]["label"],
        "measure": measure_norm,
        "sort": sort_norm,
        "group_by": group_norm,
        "group_label": spec_rows[spec_key].label if spec_group else ask.GROUP_LABELS[group_norm] if group_norm else None,
        "date_from": None if all_dates else date_from.isoformat(),
        "date_to": None if all_dates else date_to.isoformat(),
    }

    from app.services import rate_limit

    limit, window_minutes = _rate_limit_setting(db)
    if not rate_limit.hit(
        "report_ask", str(resolved), limit=limit, window_seconds=window_minutes * 60
    ).allowed:
        unit = "1 minute" if window_minutes == 1 else f"{window_minutes} minutes"
        return _response(
            {**ask._empty("busy", f"Too many reports in the last {unit}."), **common, "filters": []}
        )

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
            or bool(card_agents)
            or bool(codes)
            or channel_norm is not None
        )
        if outside:
            raise AppException(403, _DEALER_MESSAGE, code="report_dimension_not_allowed")

    # The contact's OWN companies (the sales analysis route's read), never the session scope.
    grants = {
        str(c)
        for (c,) in db.query(RespondContactCompany.company_id)
        .filter(RespondContactCompany.respond_contact_id == str(resolved))
        .all()
        if c
    }

    company_name: Optional[str] = None
    if (company or "").strip():
        # REPORT-UNIFY (phase 3, R1): one of the contact's OWN companies, by name, code or id (the sales analysis
        # route's reading). One that does not exist and one the contact does not hold are the same 403, so no company
        # name can be probed; of several sharing a name or code, the one the contact holds wins.
        wanted = company.strip().casefold()
        everyone = db.query(Company.id, Company.name, Company.code).all()
        found = [
            str(i) for i, name, code in everyone
            if wanted in (str(i).casefold(), str(name or "").casefold(), str(code or "").casefold())
        ]
        chosen = next((f for f in found if f in grants), None)
        if chosen is None:
            raise AppException(403, "You do not have access to that company", code="COMPANY_FORBIDDEN")
        grants = {chosen}
        company_name = next(str(n) for i, n, _c in everyone if str(i) == chosen)

    if brands:
        # A brand named by id that belongs to a company outside the contact's own is dropped
        # silently (one brand name can exist per company); 404 only when none remain, so
        # nothing tells the caller another company's brand exists, and none is ever echoed.
        cond = or_(Brand.company_id.is_(None), Brand.company_id.in_(sorted(grants))) if grants else Brand.company_id.is_(None)
        with company_scope(db, None):
            own = {str(i) for (i,) in db.query(Brand.id).filter(Brand.id.in_(brands), cond).all()}
        brands = [b for b in brands if b in own]
        if not brands:
            raise handle_not_found("Brand", brand_ids[0] if brand_ids else "")

    # Matched inside the contact's companies, like every other lookup and the run itself.
    with company_scope(db, frozenset(grants)):
        products = _resolve_products(db, code) if code else []
    if code and not products:
        raise handle_not_found("Product", product_code)
    product_filter: Optional[list[str]] = [str(p.id) for p in products] if code else None
    product_names: list[str] = []
    if named_products:
        # Ids naming no product inside the contact's companies are 404; ANDed with the
        # prefix when both are given (an empty AND is zero rows in `run_ask`, never "no filter").
        by_id = dict(
            _lookup_pairs(db, Product, Product.product_code, named_products, grants, "Product")
        )
        if product_filter is None:
            product_filter = list(named_products)
        else:
            by_prefix = set(product_filter)
            product_filter = [i for i in named_products if i in by_prefix]
        product_names = sorted({by_id[i] for i in product_filter} or set(by_id.values()))
    customers = scoped if scoped is not None else named_customers
    if narrowed:
        # Inside the book (and the contact's own customers when it is customer-linked too); an
        # empty result is zero rows in `run_ask`, never "no filter".
        customers = (
            [c for c in scoped if c in book]
            if scoped is not None
            else [c for c in (named_customers or sorted(book)) if c in book]
        )
    echo = _echo(
        db,
        grants,
        product_code=code,
        product_names=product_names,
        customers=[c for c in named_customers if c in set(customers)] if narrowed and named_customers else named_customers,
        brands=brands,
        categories=categories,
        agents=agents,
        warehouse_codes=codes,
        channel=channel_norm,
        card_agents=card_agents,
    )
    if company_name:
        echo.insert(0, {"key": "company", "label": ask.FILTER_LABELS["company"], "values": [company_name]})
    not_applied: list[dict[str, str]] = []
    spec_ids: Optional[list[str]] = None
    if per_document:
        # A document has no product, place or channel: those words are answered under `not_applied`.
        not_applied = [{"filter": "spec", "value": f"{k}:{v}", "reason": "per_document"} for k, v in spec_terms]
        for entry in [e for e in echo if e["key"] in ask.PER_DOCUMENT_FILTERS]:
            echo.remove(entry)
            not_applied.append({"filter": entry["key"], "value": ", ".join(entry["values"]), "reason": "per_document"})
    elif spec_terms:
        spec_ids, spec_values, not_applied = spec_set.resolve(db, spec_terms, hidden, grants)
        if spec_values:
            echo.append({"key": "spec", "label": ask.FILTER_LABELS["spec"], "values": spec_values})
        if spec_ids is not None:
            # ANDed with the named products, never widening them (an empty AND is zero rows in `run_ask`).
            product_filter = spec_ids if product_filter is None else [i for i in product_filter if i in set(spec_ids)]
    if narrowed:
        echo.append({"key": "book", "label": _BOOK_LABEL, "values": [_BOOK_VALUE]})
    if spec_ids is not None and not spec_ids:
        return _response(
            {**ask._empty("no_products", "No product has that specification."), **common, "filters": echo,
             "not_applied": not_applied}
        )

    filters: dict[str, list[str]] = {}
    if customers or narrowed:
        filters["customer"] = customers
    if product_filter is not None and not per_document:
        filters["product"] = product_filter
    if brands and not per_document:
        filters["brand"] = brands
    if categories and not per_document:
        filters["category"] = categories
    if agents:
        filters["sales_agent"] = agents
    if card_agents:
        filters["customer_agent"] = card_agents
    if channel_norm and not per_document:
        filters["channel"] = [channel_norm]

    from app.services.stock_visibility import resolve_policy

    policy = resolve_policy(db, resolved, space_id) if resolved else None
    run = dict(
        basis=basis_norm, measure=measure_norm, group_by=group_norm, filters=filters, warehouse_codes=codes,
        policy=policy, company_grants=grants, sort=sort_norm,
    )
    data = ask.run_ask(db, date_from=date_from, date_to=date_to, top_n=top_n, **run)
    product_subject = bool(code or named_products)
    customer_subject = bool(named_customers) or scoped is not None
    if (
        basis_norm in ask.SUMMARY_BASES and compare_norm is None and not spec_group
        and (product_subject or customer_subject) and data.get("status") == "ok"
    ):
        # REPORT-OUTSTANDING-SUMMARY (owner 29 Oct): an outstanding kind naming a product or a customer gets the
        # pre-#1922 summary. Default breakdowns: by location (unless a location was named), then by customer for a
        # product, by product for a customer, neither when both were named (R13). An axis the user named replaces the
        # defaults. A dealer keeps to its own keys.
        if group_norm is not None:
            axes = [group_norm]
        else:
            axes = [] if codes else ["location"]
            if product_subject != customer_subject:
                axes.append("customer" if product_subject else "product")
        if scoped is not None:
            axes = [a for a in axes if a in ask.DEALER_KEYS]
        data = {
            **data,
            "summary": ask.outstanding_summary(
                db, basis=basis_norm, axes=axes, date_from=date_from, date_to=date_to,
                filters=filters, warehouse_codes=codes, policy=policy, company_grants=grants,
            ),
        }
    if compare_norm is not None and data.get("status") == "ok":
        # REPORT-SMART-1021: the earlier window, every row (matched by name), one call.
        earlier_from, earlier_to = ask.compare_window(compare_norm, date_from, date_to)
        earlier = ask.run_ask(db, date_from=earlier_from, date_to=earlier_to, top_n=None, **run)
        data = ask.attach_compare(data, earlier, measure_norm)
        common.update(
            compare_to=compare_norm, compare_from=earlier_from.isoformat(), compare_until=earlier_to.isoformat()
        )
    if agents and group_norm in ("product", "category") and data.get("status") == "ok" and not (narrowed and not (customers or [])):
        # REPORT-SMART-L R3b: the old top selling note, by its own computation (`sales_report_service.top_selling`
        # builds `sales_agent_fill_rate` only with an agent filter): the share of the window's sales orders that
        # carry any sales agent, over the period, customer, channel, category and brand filters (never the agent
        # filter itself, by the rate's own definition).
        from app.models.order import SalesOrder
        from app.services import sales_report_service as srs
        from app.services.contact_brand_scope import brand_predicate

        try:
            # ONE count query (`srs.sales_agent_fill_rate`), with the contact's company, brand and customer
            # scope applied EXPLICITLY (a column query is not reached by the session listeners). It does not
            # apply the ranking's product, location (warehouse) or customer card agent filters, so with one of
            # those set the rate is over more sales orders than the ranking it annotates counts.
            _extra = [SalesOrder.company_id.in_(sorted(grants)) if grants else false()]
            if brand_scope:
                _extra.append(brand_predicate(brand_scope, Product.brand_id, Product.company_id))
            _fill = srs.sales_agent_fill_rate(
                db, group="category" if group_norm == "category" else "item",
                filters=srs._ranking_filters(
                    bucket_expr=srs._bucket_expr(), customer_query=None,
                    customer_ids=list(customers or []) or None, channel=channel_norm,
                    date_from=date_from, date_to=date_to,
                    category_ids=list(categories or []) or None, brand_ids=list(brands or []) or None,
                ),
                extra_filters=_extra,
            )
        except Exception:  # noqa: BLE001 - the note is a caveat, never a failed ranking
            _fill = None
        if _fill is not None:
            data = {**data, "sales_agent_fill_rate": _fill}
    return _response({**data, **common, "filters": echo, "not_applied": not_applied})


# ----------------------------------------------------------------------- chat (CA-3)


def _chat_response(data: dict) -> JSONResponse:
    return JSONResponse(content=ReportAskChatResponse(**data).model_dump(mode="json"))


def _chat_report_ask(
    request: Request,
    db: Session,
    *,
    date_from: Optional[date],
    date_to: Optional[date],
    basis: str,
    measure: str,
    group_by: Optional[str],
    top_n: Optional[int],
    sort: str,
    subjects: Optional[list[str]],
    product_ids: Optional[list[str]],
    customer_ids: Optional[list[str]],
    contact_id: str,
    space_id: str,
    askers: Optional[list[str]] = None,
    category_ids: Optional[list[str]] = None,
    brand_ids: Optional[list[str]] = None,
):
    """`dataset=chat`: the bot's chat analytics (asks, turns, failures, contacts). Same gates
    as the sales report in the same order, with the `chatbot.analytics` reveal in place of the
    sales one, and a dealer or salesman held to their own customers' asks."""
    present = request.query_params.keys()
    for key in present:
        if key not in _CHAT_PARAMS:
            raise _unprocessable(f"Unknown parameter '{key}'", "unknown_param", key)
    if date_from is None or date_to is None:
        raise _unprocessable("date_from and date_to are required", "period_required")
    if not all(_MIN_YEAR <= d.year <= _MAX_YEAR for d in (date_from, date_to)):
        raise _unprocessable(
            f"Dates must fall in {_MIN_YEAR} to {_MAX_YEAR}", "date_out_of_range", "date_from, date_to"
        )
    if date_from > date_to:
        raise _unprocessable("date_from is after date_to", "date_range_inverted")

    basis_norm = (basis if "basis" in present else _CHAT_DEFAULT_BASIS).strip().lower()
    if basis_norm not in ask.CATALOGUE["chat"]:
        raise _unprocessable(f"Unknown basis '{basis}'", "unknown_basis", _allowed(ask.CATALOGUE["chat"]))
    measure_norm = (measure if "measure" in present else _CHAT_DEFAULT_MEASURE).strip().lower()
    if measure_norm not in ask.CHAT_MEASURES:
        raise _unprocessable(f"Unknown measure '{measure}'", "unknown_measure", _allowed(ask.CHAT_MEASURES))
    sort_norm = (sort or "").strip().lower()
    if sort_norm not in ("desc", "asc"):
        raise _unprocessable(f"Unknown sort '{sort}'", "unknown_sort", _allowed(("desc", "asc")))
    group_norm = (group_by or "").strip().lower() or None
    if group_norm is not None and group_norm not in ask.CHAT_DIMENSIONS:
        raise _unprocessable(
            f"Unknown group_by value '{group_by}'", "unknown_group_by", _allowed(ask.CHAT_DIMENSIONS)
        )
    if top_n is not None and not 1 <= top_n <= TOP_SELLING_N_CEILING:
        raise _unprocessable(f"top_n must be between 1 and {TOP_SELLING_N_CEILING}", "top_n_out_of_range")

    subject_codes = [
        p.strip().lower() for item in (subjects or []) for p in str(item or "").split(",") if p.strip()
    ]
    named_customers = parse_uuid_list(customer_ids, param_name="customer_ids")
    named_products = parse_uuid_list(product_ids, param_name="product_ids")
    asker_words = [
        p.strip().lower() for item in (askers or []) for p in str(item or "").split(",") if p.strip()
    ]
    for word in asker_words:
        if word not in contact_asker.ASKERS:
            raise _unprocessable(f"Unknown asker '{word}'", "unknown_asker", _allowed(contact_asker.ASKERS))
    named_categories = parse_uuid_list(category_ids, param_name="category_ids")
    named_brands = parse_uuid_list(brand_ids, param_name="brand_ids")
    for name, values in (
        ("subjects", subject_codes), ("customer_ids", named_customers), ("product_ids", named_products),
        ("askers", asker_words), ("category_ids", named_categories), ("brand_ids", named_brands),
    ):
        if name in present and not values:
            raise _unprocessable(f"'{name}' was given but names nothing", "empty_filter", name)
        if len(values or []) > _MAX_VALUES:
            raise _unprocessable(f"Too many values for '{name}' (max {_MAX_VALUES})", "too_many_values", name)

    if subject_codes:
        known = {n for (n,) in db.execute(text("SELECT name FROM chatbot_domains")).all()}
        # No domain rows (a blank schema) leaves nothing to check against.
        unknown = [c for c in subject_codes if known and c not in known]
        if unknown:
            raise _unprocessable(f"Unknown subject '{unknown[0]}'", "unknown_subject", unknown[0])

    from app.services.contact_field_reveal_service import granted_keys
    from app.services.field_access import resolve_contact_with_null_workspace_fallback

    contact_id, space_id = contact_id.strip(), space_id.strip()
    resolved = resolve_contact_with_null_workspace_fallback(db, contact_id=contact_id, space_id=space_id)
    keys = granted_keys(db, resolved) if resolved else []
    if CHAT_GRANT not in keys:
        raise AppException(403, "Chat analytics is not enabled for your account.", code="chat_analytics_not_enabled")

    if measure_norm in ("failed", "failure_rate"):
        basis_norm = "turns"  # a failure is counted on messages, never on split asks
    unit = {"contacts": "contacts", "failure_rate": "%"}.get(measure_norm, basis_norm)
    common = {
        "dataset": "chat",
        "basis": basis_norm,
        "measure": measure_norm,
        "unit": unit,
        "sort": sort_norm,
        "group_by": group_norm,
        "group_label": ask.CHAT_GROUP_LABELS[group_norm] if group_norm else None,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }

    from app.services import rate_limit

    limit, window_minutes = _rate_limit_setting(db)
    if not rate_limit.hit(
        "report_ask", str(resolved), limit=limit, window_seconds=window_minutes * 60
    ).allowed:
        minutes = "1 minute" if window_minutes == 1 else f"{window_minutes} minutes"
        return _chat_response(
            {
                "status": "busy", "message": f"Too many reports in the last {minutes}.", **common,
                "total": {"value": 0},
            }
        )

    # The asking contact is scoped by the one asker rule (`contact_asker`): a dealer is forced to
    # its own customers (a named one outside them is the helper's own 403) and to the dealer's
    # breakdowns; a salesperson to the customers whose card agent is theirs; staff, and a contact
    # nobody classified that holds the grant, see all.
    asker = contact_asker.classify(db, str(resolved))
    scoped = None
    if asker == "dealer":
        scoped = enforce_customer_scope(
            db, contact_id=contact_id, space_id=space_id, customer_ids=named_customers, customer_query=None
        )
        if scoped is not None and group_norm is not None and group_norm not in ask.CHAT_DEALER_KEYS:
            raise AppException(403, _DEALER_MESSAGE, code="report_dimension_not_allowed")
    customers = scoped if scoped is not None else named_customers
    scope_customers: list[str] | None = list(scoped) if scoped is not None else None
    # Narrowed to its own book only when it has an agent link; a salesperson without one sees all.
    own = contact_asker.own_book(db, str(resolved)) if asker == "salesperson" else None
    scoped_book = own is not None
    if scoped_book:
        customers = [c for c in (named_customers or own) if c in own]
        scope_customers = sorted(own)

    grants = {
        str(c)
        for (c,) in db.query(RespondContactCompany.company_id)
        .filter(RespondContactCompany.respond_contact_id == str(resolved))
        .all()
        if c
    }
    echo: list[tuple[str, list[str]]] = []
    if subject_codes:
        from app.services.reports.datasets import chat_asks

        words = dict(chat_asks.subject_options(db))
        echo.append(("subject", sorted(words.get(c, c) for c in subject_codes)))
    if named_products:
        echo.append(("product", _lookup(db, Product, Product.product_code, named_products, grants, "Product")))
    if named_customers:
        # Only the customers left after scoping: a name outside the contact's own is never echoed.
        shown = [c for c in named_customers if c in set(customers)]
        if shown:
            echo.append(("customer", _lookup(db, Customer, Customer.customer_name, shown, grants, "Customer")))

    filters: dict[str, list[str]] = {}
    if subject_codes:
        filters["subject"] = subject_codes
    if named_products:
        filters["product"] = named_products
    if scoped is not None or named_customers or customers != named_customers or scoped_book:
        filters["customer"] = customers
    if asker_words:
        filters["asker"] = asker_words
        echo.append(("asker", [w.capitalize() for w in asker_words]))
    if named_categories:
        filters["category"] = named_categories
        echo.append(("category", sorted(set(_lookup(db, ProductCategory, ProductCategory.category_name, named_categories, grants, "Category")))))
    if named_brands:
        filters["brand"] = named_brands
        echo.append(("brand", sorted(set(_lookup(db, Brand, Brand.brand_name, named_brands, grants, "Brand")))))

    data = ask.run_ask(
        db,
        dataset="chat",
        basis=basis_norm,
        measure=measure_norm,
        group_by=group_norm,
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        warehouse_codes=[],
        policy=None,
        sort=sort_norm,
        top_n=top_n,
        scope_customers=scope_customers,
    )
    return _chat_response(
        {
            **data,
            **common,
            "date_from": data["date_from"],
            "date_to": data["date_to"],
            "filters": [
                {"key": key, "label": ask.CHAT_FILTER_LABELS[key], "values": values} for key, values in echo if values
            ],
        }
    )
