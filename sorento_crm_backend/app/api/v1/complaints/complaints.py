"""Complaints API routes."""
import logging

from fastapi import APIRouter, Depends, Query, HTTPException, status, Request, Body
from sqlalchemy.orm import Session
from typing import Optional, Union, List, Any
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.complaints_service import ComplaintService
from app.services.integration_service import IntegrationLogService
from app.services.order_service import OrderService
from app.schemas.complaints import (
    ComplaintCreate,
    ComplaintUpdate,
    ComplaintResponse,
    ComplaintAttachmentLinkRequest,
    BulkDeleteComplaintsRequest,
)
from app.schemas.external.complaints import ComplaintIntegrationCreate
from app.schemas.integration import IntegrationLogCreate
from app.schemas.common import ListResponse
from app.schemas.procurement import ViewLinkRequest, ViewLinkResponse
from app.services.error_handler import handle_internal_error
from app.config import settings as app_settings
from app.modules.runtime.guards import require_public_view_links_enabled

logger = logging.getLogger(__name__)

router = APIRouter()

_COMPLAINT_DO_LOOKUP_FIELDS: tuple[str, ...] = (
    "customer_name",
    "product_code",
    "order_year",
    "order_date_from",
    "order_date_to",
)


_COMPLAINT_FIELD_RECOMMENDED: dict[str, dict[str, Any]] = {
    "complaint_type": {
        "description": "What kind of issue. Free-text but the typical bucket is one of these.",
        "recommended_values": ["Broken", "Damaged", "Scratch", "Wrong Item", "Missing Parts", "Defect", "Other"],
    },
    "customer_type": {
        "description": "Who the complainant is.",
        "recommended_values": ["dealer", "end_user", "project", "other"],
        "note": "If 'other', also set customer_type_other with a short description.",
    },
    "within_warranty": {
        "description": "Warranty status as known to the customer.",
        "recommended_values": ["Yes", "No", "Not sure"],
    },
    "product_type": {
        "description": "Generic product category. Free-text; use a short label such as the items below.",
        "recommended_values": ["bathtub", "basin", "water closet", "kitchen sink", "faucet", "shower", "accessory"],
    },
    "defect_description": {
        "description": "One- or two-line description of the defect. Free-text. Example: 'Cracked basin near drain hole, leaking on use.'",
    },
    "defects_discovered": {
        "description": "When the defect was discovered (date YYYY-MM-DD or short phrase like 'on delivery', 'after 1 week of use').",
    },
    "quantity": {
        "description": "Affected unit count. Integer >= 1.",
    },
    "sales_person": {
        "description": "Sales rep handling this customer. Free-text name.",
    },
    "address": {
        "description": "Site / delivery address relevant to the complaint. Free-text.",
    },
    "contact_person": {
        "description": "Person to contact about this complaint at the customer side. Free-text.",
    },
    "project_title": {
        "description": "Project name when the complaint is for a project order; otherwise customer label.",
    },
    "delivery_order_numbers": {
        "description": (
            "One or more DO numbers (comma-separated). MUST be supplied first. "
            "If not known, submit any combination of customer_name / product_code / order_year / "
            "order_date_from / order_date_to and this tool returns candidate_delivery_orders for selection."
        ),
    },
}


_COMPLAINT_FIELD_OBSERVED_COLUMNS: tuple[str, ...] = (
    "complaint_type",
    "customer_type",
    "within_warranty",
    "product_type",
)


def _query_observed_field_values(service: ComplaintService, column: str, limit: int = 8) -> list[str]:
    """Return top distinct non-empty values for a column from existing complaints. Best-effort, swallows errors."""
    from sqlalchemy import text as _text

    try:
        rows = service.db.execute(
            _text(
                f"SELECT {column} AS v, COUNT(*) AS c FROM complaints "
                f"WHERE {column} IS NOT NULL AND {column} <> '' "
                f"GROUP BY {column} ORDER BY c DESC LIMIT :lim"
            ),
            {"lim": limit},
        ).all()
        return [str(r._mapping["v"]) for r in rows]
    except Exception:
        return []


def _lookup_options_for_complaint_field(service: ComplaintService, column: str) -> Optional[dict[str, Any]]:
    """If complaints.<column> is bound to a LookupSet, return strict option list + per-option keywords.

    Returns None when no binding exists (field stays free-text).
    Shape: {set_key, set_name, strict, options:[{value, label, keywords:[...]}], instruction}.
    """
    from app.models.lookup import LookupBinding, LookupOption, LookupOptionKeyword, LookupSet  # local: avoid cycle

    binding = (
        service.db.query(LookupBinding)
        .filter(LookupBinding.table_name == "complaints", LookupBinding.column_name == column)
        .first()
    )
    if binding is None:
        return None
    s = service.db.query(LookupSet).filter(LookupSet.id == binding.set_id).first()
    if s is None or not s.is_active:
        return None
    rows = (
        service.db.query(LookupOption)
        .filter(LookupOption.set_id == s.id, LookupOption.is_active.is_(True))
        .order_by(LookupOption.sort_order.asc(), LookupOption.label.asc())
        .all()
    )
    options: list[dict[str, Any]] = []
    for o in rows:
        kws = (
            service.db.query(LookupOptionKeyword)
            .filter(LookupOptionKeyword.option_id == o.id)
            .all()
        )
        options.append({
            "value": o.value,
            "label": o.label,
            "keywords": [k.keyword for k in kws],
        })
    return {
        "set_key": s.set_key,
        "set_name": s.name,
        "strict": True,
        "options": options,
        "instruction": (
            "Strict dropdown. Submit ONLY one of the listed `value` strings exactly — do not invent or paraphrase. "
            "Map the user's free text to a value via the per-option `keywords` (case-insensitive). "
            "If no keyword matches, ask the user to pick from the listed `label`s. "
            "Submitting an unlisted value will fail validation (HTTP 422 invalid_lookup_value)."
        ),
    }


def _build_complaint_field_guidance(service: ComplaintService) -> dict[str, dict[str, Any]]:
    """Per-field help: description + (lookup options w/ keywords when bound) OR static recommended values + observed examples."""
    guidance: dict[str, dict[str, Any]] = {}
    for field, meta in _COMPLAINT_FIELD_RECOMMENDED.items():
        entry: dict[str, Any] = {"description": meta.get("description")}
        lookup_info = _lookup_options_for_complaint_field(service, field)
        if lookup_info is not None:
            entry["lookup"] = lookup_info
            entry["strict"] = True
            entry["recommended_values"] = [o["value"] for o in lookup_info["options"]]
        else:
            if "recommended_values" in meta:
                entry["recommended_values"] = list(meta["recommended_values"])
            if field in _COMPLAINT_FIELD_OBSERVED_COLUMNS:
                entry["observed_examples"] = _query_observed_field_values(service, field)
        if "note" in meta:
            entry["note"] = meta["note"]
        guidance[field] = entry
    return guidance


def _request_has_valid_external_api_key(request: Optional[Request]) -> bool:
    """True when X-API-Key header matches configured external API key (same as get_current_user_or_api_key)."""
    if request is None:
        return False
    key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    valid = getattr(app_settings, "external_api_key", None)
    if not key or not valid:
        return False
    return key.strip() == str(valid).strip()


def _require_contact_scope_for_external(
    *,
    request: Optional[Request],
    contact_id: Optional[str],
    space_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """For external API key callers, require both contact_id and space_id to scope the result."""
    c = (contact_id or "").strip() or None
    s = (space_id or "").strip() or None
    if _request_has_valid_external_api_key(request) and (not c or not s):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="contact_id and space_id are required for external complaint list/get requests.",
        )
    return c, s


def _respond_user_id_from_current_user(current_user: dict) -> str:
    """Get respond_user_id for SLA/response tracking; fallback to user id."""
    rid = (current_user or {}).get("respond_user_id") or (current_user or {}).get("respondUserId")
    if rid and str(rid).strip():
        return str(rid).strip()
    uid = (current_user or {}).get("id")
    if uid and str(uid).strip():
        return str(uid).strip()
    raise HTTPException(status_code=400, detail="User respond_user_id or id is required for Update & Reply.")


@router.get("/", response_model=ListResponse[ComplaintResponse])
async def get_complaints(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    contact_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    sort: Optional[str] = Query("complaint_date"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get complaints with pagination, search, assignee/status filters, and sorting.

    External API-key callers MUST pass contact_id and space_id to scope the result.
    """
    try:
        service = ComplaintService(db)
        filter_contact_id, filter_space_id = _require_contact_scope_for_external(
            request=request,
            contact_id=contact_id,
            space_id=space_id,
        )
        result = service.list_complaints(
            page=page,
            limit=limit,
            query=query,
            assigned_to=assigned_to,
            status=status,
            sort_field=sort or "complaint_date",
            sort_dir=dir or "asc",
            contact_id=filter_contact_id,
            space_id=filter_space_id,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_complaints(
    body: BulkDeleteComplaintsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk delete complaints by ID. Body: { ids: string[] }."""
    try:
        service = ComplaintService(db)
        return service.bulk_delete_complaints(body.ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/attachments/{link_id}", status_code=status.HTTP_200_OK)
async def delete_complaint_attachment(
    link_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unlink an attachment from a complaint (complaint_attachments link)."""
    try:
        service = ComplaintService(db)
        service.delete_complaint_attachment(link_id)
        return {"message": "Attachment unlinked successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{complaint_id}/attachments", status_code=status.HTTP_201_CREATED)
async def link_attachment_to_complaint(
    complaint_id: str,
    body: ComplaintAttachmentLinkRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Link an existing attachment to a complaint (complaint_attachments table)."""
    try:
        service = ComplaintService(db)
        created_by = (current_user.get("id") or None) if isinstance(current_user.get("id"), str) and len(str(current_user.get("id"))) == 36 else None
        link = service.link_attachment_to_complaint(
            complaint_id=complaint_id,
            attachment_id=body.attachment_id,
            created_by=created_by,
        )
        return {"message": "Attachment linked successfully", "link_id": link.id}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{complaint_id}/conversation")
async def get_complaint_conversation(
    complaint_id: str,
    limit: int = Query(50, ge=1, le=50),
    cursor: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get Respond.io conversation messages for this complaint (contact from respond_inbox_url)."""
    try:
        from app.services.integration_service import RespondClient
        from app.models.access import RespondContact

        service = ComplaintService(db)
        complaint = service.get_complaint(complaint_id)
        identifier = service._identifier_from_respond_inbox_url(
            getattr(complaint, "respond_inbox_url", None)
        )
        contact_meta: Optional[dict] = None
        contact_id_val = getattr(complaint, "contact_id", None)
        if contact_id_val:
            row = (
                db.query(RespondContact)
                .filter(
                    (RespondContact.id == contact_id_val)
                    | (RespondContact.respond_io_id == contact_id_val)
                )
                .first()
            )
            if row is not None:
                contact_meta = {"name": row.name, "phone": row.phone_number}
        if not identifier:
            return {
                "items": [],
                "pagination": {},
                "error": "No Respond.io contact linked",
                "contact": contact_meta,
            }
        client = RespondClient()
        result = client.list_messages(identifier, limit=limit, cursor=cursor)
        if isinstance(result, dict):
            result["contact"] = contact_meta
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint(
    complaint_id: str,
    request: Request,
    contact_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single complaint by ID. External API-key callers MUST pass contact_id and space_id to scope the lookup."""
    try:
        service = ComplaintService(db)
        filter_contact_id, filter_space_id = _require_contact_scope_for_external(
            request=request,
            contact_id=contact_id,
            space_id=space_id,
        )
        return service.get_complaint_for_response(
            complaint_id,
            contact_id=filter_contact_id,
            space_id=filter_space_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/{complaint_id}/view-link",
    response_model=ViewLinkResponse,
    dependencies=[Depends(require_public_view_links_enabled())],
)
async def get_or_create_complaint_view_link(
    complaint_id: str,
    data: Optional[ViewLinkRequest] = Body(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get or create a shareable view link for this complaint (no login required to view)."""
    try:
        service = ComplaintService(db)
        service.get_complaint(complaint_id)  # ensure exists and user can access
        token = service.get_or_create_view_token(complaint_id)
        db.commit()
        base = ((data.base_url if data else None) or getattr(app_settings, "frontend_base_url", "") or "").rstrip("/")
        view_url = f"{base}/view/complaint?token={token}" if base else f"/view/complaint?token={token}"
        return ViewLinkResponse(view_token=token, view_url=view_url)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


def _is_integration_payload(body: Any) -> bool:
    """True if body looks like integration payload (date_of_complaint, sales_person, delivery_order_numbers, defect_discovered_when)."""
    if isinstance(body, list):
        body = body[0] if body else {}
    if not isinstance(body, dict):
        return False
    return any(
        body.get(k) is not None
        for k in ("date_of_complaint", "sales_person", "delivery_order_numbers", "defect_discovered_when")
    ) or any(body.get(k) is not None for k in ("complaint_number", "system_id"))


def _validate_integration_payload_completeness(payload: ComplaintIntegrationCreate) -> None:
    """Require integration complaint fields that are not persisted in ComplaintCreate."""
    required_fields: tuple[str, ...] = (
        "defect_discovered_when",
        "sales_person",
        "address",
        "customer_type",
        "within_warranty",
        "product_type",
        "quantity",
        "contact_person",
        "project_title",
        "contact_id",
        "space_id",
    )
    payload_dict = payload.model_dump()
    missing: list[str] = []
    for key in required_fields:
        value = payload_dict.get(key)
        if value is None:
            missing.append(key)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(key)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Complaint submission is incomplete. Required integration fields: "
                + ", ".join(required_fields)
                + f". Missing or empty: {', '.join(missing)}."
            ),
        )


def _raise_do_lookup_guidance(
    *,
    status_value: str,
    message: str,
    invalid_do_numbers: Optional[list[str]] = None,
    valid_do_numbers: Optional[list[str]] = None,
    provided_filters: Optional[dict[str, str]] = None,
    next_action: str = "collect_do_lookup_filters",
    field_guidance: Optional[dict[str, dict[str, Any]]] = None,
    candidate_delivery_orders: Optional[list[dict[str, Any]]] = None,
) -> None:
    detail: dict[str, Any] = {
        "status": status_value,
        "next_action": next_action,
        "message": message,
        "available_filters": list(_COMPLAINT_DO_LOOKUP_FIELDS),
        "filter_requirement": "any_one_of",
        "filter_hint": (
            "All filters are optional. Provide at least one of "
            f"{', '.join(_COMPLAINT_DO_LOOKUP_FIELDS)} to search DO numbers; combining filters narrows results."
        ),
    }
    if field_guidance:
        detail["field_guidance"] = field_guidance
        detail["field_guidance_usage"] = (
            "If the user is asking what values they can input for a specific complaint field "
            "(e.g. 'what options for complaint_type', 'what can I put for customer_type'), answer from "
            "field_guidance directly — do NOT insist on DO lookup or block the question. "
            "Only proceed to DO lookup when the user actually wants to file the complaint."
        )
    if provided_filters:
        detail["provided_filters"] = provided_filters
    if candidate_delivery_orders is not None:
        detail["candidate_delivery_orders"] = candidate_delivery_orders
        detail["candidate_count"] = len(candidate_delivery_orders)
        detail["resubmit_hint"] = (
            "Pick one (or more) delivery_order_number(s) from candidate_delivery_orders and resubmit "
            "this tool with delivery_order_numbers set to the chosen DO(s). Do NOT call any other tool — "
            "this submit tool already searched for you."
        )
    elif provided_filters:
        # Back-compat fallback — kept only when inline search was not run (e.g., search disabled).
        detail["recommended_tools"] = [
            "crm_order_management_orders_by_product_list",
            "crm_order_management_orders_list",
        ]
        detail["recommended_tool_arg_mapping"] = {
            "customer_name": "customer_query",
            "product_code": "product_query",
            "order_date_from": "order_date_from",
            "order_date_to": "order_date_to",
        }
    if invalid_do_numbers:
        detail["invalid_delivery_order_numbers"] = invalid_do_numbers
    if valid_do_numbers:
        detail["valid_delivery_order_numbers"] = valid_do_numbers
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _collect_provided_do_filters(
    complaint_data: ComplaintCreate,
    integration_payload: Optional[ComplaintIntegrationCreate] = None,
) -> dict[str, str]:
    """Collect already-supplied DO lookup filters from the complaint payload."""
    provided: dict[str, str] = {}
    customer = (getattr(complaint_data, "customer_name", None) or "").strip()
    if customer:
        provided["customer_name"] = customer
    product = (getattr(complaint_data, "product_code", None) or "").strip()
    if product:
        provided["product_code"] = product
    if integration_payload is not None:
        order_year = (getattr(integration_payload, "order_year", None) or "").strip()
        if order_year:
            provided["order_year"] = order_year
        order_date_from = (getattr(integration_payload, "order_date_from", None) or "").strip()
        if order_date_from:
            provided["order_date_from"] = order_date_from
        order_date_to = (getattr(integration_payload, "order_date_to", None) or "").strip()
        if order_date_to:
            provided["order_date_to"] = order_date_to
    return provided


def _resolve_do_lookup_date_range(
    provided_filters: dict[str, str],
) -> tuple[Optional["datetime"], Optional["datetime"]]:
    """Translate order_year / order_date_from / order_date_to filters into datetime range."""
    from datetime import datetime as _dt

    def _parse(s: str) -> Optional["datetime"]:
        s = (s or "").strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return _dt.strptime(s, fmt)
            except ValueError:
                continue
        return None

    date_from = _parse(provided_filters.get("order_date_from", ""))
    date_to = _parse(provided_filters.get("order_date_to", ""))
    order_year = (provided_filters.get("order_year") or "").strip()
    if order_year and (date_from is None and date_to is None):
        try:
            yr = int(order_year)
            if 1900 <= yr <= 9999:
                date_from = _dt(yr, 1, 1)
                date_to = _dt(yr, 12, 31, 23, 59, 59)
        except ValueError:
            pass
    return date_from, date_to


_DO_INLINE_SEARCH_LIMIT = 25


def _serialize_candidate_order(order: Any) -> dict[str, Any]:
    """Compact candidate DO row for LLM consumption."""
    products: list[str] = []
    seen: set[str] = set()
    for line in getattr(order, "lines", None) or []:
        product = getattr(line, "product", None)
        code = (getattr(product, "product_code", None) or "").strip() if product else ""
        if code and code not in seen:
            seen.add(code)
            products.append(code)
    order_date_value = getattr(order, "order_date", None)
    return {
        "delivery_order_number": getattr(order, "order_number", None),
        "order_date": order_date_value.isoformat() if order_date_value else None,
        "debtor_name": getattr(order, "debtor_name", None),
        "debtor_code": getattr(order, "debtor_code", None),
        "products": products,
    }


def _run_inline_do_search(
    db: "Session",
    provided_filters: dict[str, str],
) -> list[dict[str, Any]]:
    """Search delivery orders matching supplied filters; return compact candidate list."""
    if not provided_filters:
        return []
    customer_query = provided_filters.get("customer_name") or None
    product_query = provided_filters.get("product_code") or None
    date_from, date_to = _resolve_do_lookup_date_range(provided_filters)
    order_service = OrderService(db)
    result = order_service.list_orders_by_product(
        page=1,
        limit=_DO_INLINE_SEARCH_LIMIT,
        customer_query=customer_query,
        product_query=product_query,
        order_date_from=date_from,
        order_date_to=date_to,
        sort_field="order_date",
        sort_dir="desc",
    )
    orders = result.get("data") or []
    return [_serialize_candidate_order(o) for o in orders]


def _enforce_delivery_order_first(
    service: ComplaintService,
    complaint_data: ComplaintCreate,
    integration_payload: Optional[ComplaintIntegrationCreate] = None,
) -> dict[str, Any]:
    """Validate DO selection first; request customer+product+order_date filters when DO is missing.

    When filters are supplied but no DO is chosen, search delivery orders inline and return
    candidate_delivery_orders so the caller can pick one without invoking another tool.

    Returns inferred customer/product hints from the selected DO(s).
    """
    resolved_do_numbers, invalid_do_numbers, provided_do_numbers = service.resolve_delivery_order_numbers(
        complaint_data.delivery_order_number
    )
    if not provided_do_numbers:
        provided_filters = _collect_provided_do_filters(complaint_data, integration_payload)
        guidance = _build_complaint_field_guidance(service)
        if provided_filters:
            shown = ", ".join(f"{k}={v!r}" for k, v in provided_filters.items())
            candidates = _run_inline_do_search(service.db, provided_filters)
            if candidates:
                _raise_do_lookup_guidance(
                    status_value="needs_do_selection",
                    next_action="select_delivery_order",
                    message=(
                        f"Found {len(candidates)} matching delivery order(s) for filters: {shown}. "
                        "Pick one (or more) delivery_order_number(s) from candidate_delivery_orders "
                        "and resubmit this tool with delivery_order_numbers set to the chosen DO(s)."
                    ),
                    provided_filters=provided_filters,
                    candidate_delivery_orders=candidates,
                    field_guidance=guidance,
                )
            _raise_do_lookup_guidance(
                status_value="needs_do_lookup",
                next_action="refine_do_lookup_filters",
                message=(
                    f"No delivery orders matched the supplied filters: {shown}. "
                    "Ask the user to refine filters (different customer name, product code, or order date range) "
                    "and resubmit. Do NOT call any other tool."
                ),
                provided_filters=provided_filters,
                candidate_delivery_orders=[],
                field_guidance=guidance,
            )
        _raise_do_lookup_guidance(
            status_value="needs_do_lookup",
            message=(
                "Delivery order number is required before complaint details. "
                "Please provide at least one of: customer name, product, or an order date range "
                "(any one is enough to search DO numbers; more filters narrow results)."
            ),
            field_guidance=guidance,
        )
    if resolved_do_numbers and invalid_do_numbers:
        _raise_do_lookup_guidance(
            status_value="needs_do_selection",
            message=(
                "Some delivery order numbers could not be matched. Please choose only valid DO number(s) "
                "from order search results, then continue complaint submission."
            ),
            invalid_do_numbers=invalid_do_numbers,
            valid_do_numbers=resolved_do_numbers,
        )
    if not resolved_do_numbers:
        provided_filters = _collect_provided_do_filters(complaint_data, integration_payload)
        guidance = _build_complaint_field_guidance(service)
        if provided_filters:
            shown = ", ".join(f"{k}={v!r}" for k, v in provided_filters.items())
            candidates = _run_inline_do_search(service.db, provided_filters)
            if candidates:
                _raise_do_lookup_guidance(
                    status_value="needs_do_selection",
                    next_action="select_delivery_order",
                    message=(
                        f"The supplied DO number(s) did not match. Found {len(candidates)} other matching "
                        f"delivery order(s) for filters: {shown}. Pick valid DO(s) from candidate_delivery_orders "
                        "and resubmit."
                    ),
                    provided_filters=provided_filters,
                    invalid_do_numbers=invalid_do_numbers or provided_do_numbers,
                    candidate_delivery_orders=candidates,
                    field_guidance=guidance,
                )
            _raise_do_lookup_guidance(
                status_value="needs_do_lookup",
                next_action="refine_do_lookup_filters",
                message=(
                    f"No matching delivery order found for the supplied DO(s) or filters: {shown}. "
                    "Ask the user to refine filters and resubmit."
                ),
                provided_filters=provided_filters,
                invalid_do_numbers=invalid_do_numbers or provided_do_numbers,
                candidate_delivery_orders=[],
                field_guidance=guidance,
            )
        _raise_do_lookup_guidance(
            status_value="needs_do_lookup",
            message=(
                "No matching delivery order found. Provide at least one of: customer name, product, "
                "or an order date range to search for valid DO number(s) (any one is enough; combining narrows results)."
            ),
            invalid_do_numbers=invalid_do_numbers or provided_do_numbers,
            field_guidance=guidance,
        )
    complaint_data.delivery_order_number = ", ".join(resolved_do_numbers)
    return service.infer_complaint_defaults_from_delivery_orders(resolved_do_numbers)


def _prefill_complaint_fields_from_do(
    complaint_data: ComplaintCreate,
    do_context: dict[str, Any],
    integration_payload: Optional[ComplaintIntegrationCreate] = None,
) -> None:
    """Reduce data entry by auto-filling customer_name/product_code from selected DO(s)."""
    inferred_customer_name = str(do_context.get("customer_name") or "").strip()
    inferred_product_code = str(do_context.get("product_code") or "").strip()
    if not (complaint_data.customer_name or "").strip() and inferred_customer_name:
        complaint_data.customer_name = inferred_customer_name
        if integration_payload is not None:
            integration_payload.customer_name = inferred_customer_name
    if not (complaint_data.product_code or "").strip() and inferred_product_code:
        complaint_data.product_code = inferred_product_code
        if integration_payload is not None:
            integration_payload.product_code = inferred_product_code


def _raise_needs_more_fields_guidance(
    *,
    missing_fields: list[str],
    do_context: dict[str, Any],
    field_guidance: Optional[dict[str, dict[str, Any]]] = None,
) -> None:
    """Structured response for incomplete complaint details after DO selection.

    When ``field_guidance`` is supplied, each lookup-bound field carries a strict
    ``lookup`` block with options + keywords; the LLM must submit only ``value`` strings.
    """
    detail: dict[str, Any] = {
        "status": "needs_more_fields",
        "next_action": "collect_complaint_details",
        "message": "Complaint details are incomplete after DO selection.",
        "missing_fields": missing_fields,
    }
    inferred_customer_name = do_context.get("customer_name")
    inferred_product_code = do_context.get("product_code")
    product_codes = do_context.get("product_codes") or []
    product_names = do_context.get("product_names") or []
    customer_candidates = do_context.get("customer_name_candidates") or []
    detail["do_lookup_context"] = {
        "delivery_order_numbers": do_context.get("delivery_order_numbers") or [],
        "customer_name": inferred_customer_name,
        "customer_name_candidates": customer_candidates,
        "product_code": inferred_product_code,
        "product_codes": product_codes,
        "product_names": product_names,
    }
    detail["prefill_fields"] = {
        "customer_name": inferred_customer_name,
        "product_code": inferred_product_code,
    }
    if field_guidance:
        detail["field_guidance"] = field_guidance
        detail["field_guidance_usage"] = (
            "For each missing field consult field_guidance[<field>]. If a `lookup` block is present (strict=true), "
            "you MUST submit one of the exact `value` strings from `lookup.options` — map the user's free text to "
            "a value via per-option `keywords`. Unlisted values are rejected. If a field has no `lookup` block, it "
            "is free-text; use `recommended_values` / `observed_examples` as soft hints only."
        )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _resolve_complaint_update_identifier(payload: ComplaintIntegrationCreate) -> Optional[str]:
    """Return complaint identifier from integration payload for submit-as-edit flow."""
    system_id = str(payload.system_id or "").strip()
    if system_id:
        return system_id
    complaint_number = str(payload.complaint_number or "").strip()
    if complaint_number:
        return complaint_number
    return None


def _build_merged_complaint_create_for_validation(
    *,
    existing: Any,
    incoming: ComplaintCreate,
) -> ComplaintCreate:
    """Merge existing complaint row + incoming values to validate submit completeness on edit."""
    merged: dict[str, Any] = {}
    for field_name in ComplaintCreate.model_fields:
        if field_name == "attachments":
            continue
        merged[field_name] = getattr(existing, field_name, None)
    merged.update(incoming.model_dump(exclude_none=True))
    return ComplaintCreate.model_validate(merged)


@router.post("/", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
async def create_complaint(
    request: Request,
    body: Any = Body(..., embed=False),
    current_user: dict = Depends(get_current_user_or_api_key),  # Support both JWT and API key
    db: Session = Depends(get_db)
):
    """Create a new complaint with attachments.
    Accepts either:
    - Standard ComplaintCreate (complaint_date, salesperson, delivery_order_number, ...), or
    - Integration payload (date_of_complaint, sales_person, delivery_order_numbers, defect_discovered_when, ...), single object or [{ ... }].
    """
    try:
        is_integration_payload = False
        user_confirmed: Optional[bool] = None
        integration_payload: Optional[ComplaintIntegrationCreate] = None
        if isinstance(body, list) and body and _is_integration_payload(body):
            integration_payload = ComplaintIntegrationCreate.model_validate(body[0])
            user_confirmed = integration_payload.user_confirmed
            complaint_data = integration_payload.to_complaint_create()
            is_integration_payload = True
        elif isinstance(body, dict) and _is_integration_payload(body):
            integration_payload = ComplaintIntegrationCreate.model_validate(body)
            user_confirmed = integration_payload.user_confirmed
            complaint_data = integration_payload.to_complaint_create()
            is_integration_payload = True
        else:
            raw = body[0] if isinstance(body, list) and body else body
            if isinstance(raw, dict):
                _uc = raw.get("user_confirmed")
                user_confirmed = _uc if isinstance(_uc, bool) else None
                raw = {k: v for k, v in raw.items() if k != "user_confirmed"}
            complaint_data = ComplaintCreate.model_validate(raw)

        service = ComplaintService(db)
        requires_user_confirm = is_integration_payload or _request_has_valid_external_api_key(request)
        update_identifier = (
            _resolve_complaint_update_identifier(integration_payload)
            if integration_payload is not None
            else None
        )
        if update_identifier:
            existing = service.get_complaint(update_identifier)
            if str(getattr(existing, "status", "") or "").strip().lower() != "rejected":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Complaint identifier {update_identifier!r} exists with status "
                        f"{getattr(existing, 'status', None)!r}. "
                        "Edit via submit is allowed only for rejected complaints."
                    ),
                )
            merged_for_validation = _build_merged_complaint_create_for_validation(
                existing=existing,
                incoming=complaint_data,
            )
            do_context = _enforce_delivery_order_first(service, merged_for_validation, integration_payload)
            _prefill_complaint_fields_from_do(merged_for_validation, do_context, integration_payload)
            if requires_user_confirm:
                missing_fields = service.get_submission_missing_fields(merged_for_validation)
                if missing_fields:
                    _raise_needs_more_fields_guidance(
                        missing_fields=missing_fields,
                        do_context=do_context,
                        field_guidance=_build_complaint_field_guidance(service),
                    )
                if user_confirmed is not True:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "Explicit user confirmation is required before submission. "
                            "Set user_confirmed to true only after the user explicitly confirms the final summary "
                            "(e.g. OK, YES, CONFIRM)."
                        ),
                    )

            update_payload = ComplaintUpdate.model_validate(
                complaint_data.model_dump(exclude_none=True, exclude={"attachments"})
            )
            service.update_complaint(str(existing.id), update_payload)
            db.commit()
            return service.get_complaint_with_attachments(str(existing.id))

        do_context = _enforce_delivery_order_first(service, complaint_data, integration_payload)
        _prefill_complaint_fields_from_do(complaint_data, do_context, integration_payload)
        if requires_user_confirm:
            if integration_payload is not None:
                _validate_integration_payload_completeness(integration_payload)
            # Enforce missing-field validation before confirmation gating.
            missing_fields = service.get_submission_missing_fields(complaint_data)
            if missing_fields:
                _raise_needs_more_fields_guidance(
                    missing_fields=missing_fields,
                    do_context=do_context,
                    field_guidance=_build_complaint_field_guidance(service),
                )
        if requires_user_confirm and user_confirmed is not True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Explicit user confirmation is required before submission. "
                    "Set user_confirmed to true only after the user explicitly confirms the final summary "
                    "(e.g. OK, YES, CONFIRM)."
                ),
            )

        complaint = service.create_complaint(complaint_data)
        db.commit()
        should_notify_handlers = is_integration_payload or _request_has_valid_external_api_key(request)
        if should_notify_handlers:
            try:
                service.notify_team_complaint_external_created(
                    complaint_id=str(complaint.id),
                    sync_email=False,
                )
            except Exception as e:
                logger.warning(
                    "Complaint notify (create) failed for complaint %s: %s",
                    getattr(complaint, "id", None),
                    e,
                    exc_info=True,
                )
        complaint_id = str(getattr(complaint, "id"))
        return service.get_complaint_with_attachments(complaint_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/integration", status_code=status.HTTP_200_OK)
async def create_complaint_integration(
    request: Request,
    body: Union[List[ComplaintIntegrationCreate], ComplaintIntegrationCreate] = Body(..., embed=False),
    db: Session = Depends(get_db),
):
    """Create a complaint from integration and log the request.
    Accepts integration payload with date_of_complaint, defect_discovered_when, delivery_order_numbers,
    sales_person, address (and other fields). Single object or array of one element."""
    try:
        if isinstance(body, list):
            if not body:
                raise HTTPException(status_code=400, detail="At least one complaint payload is required")
            payload = body[0]
        else:
            payload = body
        service = ComplaintService(db)
        complaint_data = payload.to_complaint_create()
        do_context = _enforce_delivery_order_first(service, complaint_data, payload)
        _prefill_complaint_fields_from_do(complaint_data, do_context, payload)
        # Validate payload completeness after DO validation; only then enforce explicit confirmation.
        _validate_integration_payload_completeness(payload)
        missing_fields = service.get_submission_missing_fields(complaint_data)
        if missing_fields:
            _raise_needs_more_fields_guidance(
                missing_fields=missing_fields,
                do_context=do_context,
                field_guidance=_build_complaint_field_guidance(service),
            )
        if payload.user_confirmed is not True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Explicit user confirmation is required before submission. "
                    "Set user_confirmed to true only after the user explicitly confirms the final summary "
                    "(e.g. OK, YES, CONFIRM)."
                ),
            )
        complaint = service.create_complaint(complaint_data)

        try:
            service.notify_team_complaint_external_created(
                complaint_id=str(complaint.id),
                sync_email=False,
            )
        except Exception as e:
            logger.warning(
                "Complaint notify (integration) failed for complaint %s: %s",
                getattr(complaint, "id", None),
                e,
                exc_info=True,
            )

        log_service = IntegrationLogService(db)
        complaint_id = str(getattr(complaint, "id"))
        external_reference = getattr(complaint, "delivery_order_number", None)
        external_reference_value = str(external_reference) if external_reference is not None else None
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="complaints_api",
                business_table="complaints",
                business_id=complaint_id,
                external_reference=external_reference_value,
                direction="inbound",
                endpoint=str(request.url),
                http_method="POST",
                status="success"
            ),
            request_payload_dict=payload.model_dump()
        )

        return {"status": "success", "message": "Complaint created successfully.", "complaint_id": complaint.id}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{complaint_id}/sync-assignee", status_code=status.HTTP_200_OK)
async def sync_complaint_assignee(
    complaint_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync assignee from Respond.io: fetch contact by complaint's contact_id, get assignee, match to CRM user by respond_user_id, update complaint.assigned_to."""
    try:
        service = ComplaintService(db)
        result = service.sync_assignee_from_respond(complaint_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{complaint_id}", response_model=ComplaintResponse)
async def update_complaint(
    complaint_id: str,
    complaint_data: ComplaintUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a complaint."""
    try:
        service = ComplaintService(db)
        service.update_complaint(complaint_id, complaint_data)
        db.commit()
        return service.get_complaint_with_attachments(complaint_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{complaint_id}/update-and-reply", response_model=ComplaintResponse)
async def update_complaint_and_reply(
    complaint_id: str,
    complaint_data: ComplaintUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update complaint, send technical team response to customer via Respond.io, and mark SLA as responded."""
    try:
        respond_user_id = _respond_user_id_from_current_user(current_user)
        service = ComplaintService(db)
        service.update_complaint_and_reply(
            complaint_id,
            complaint_data,
            respond_user_id=respond_user_id,
            request_url=str(request.url) if request else "",
            crm_sender_user_id=current_user.get("id"),
        )
        db.commit()
        return service.get_complaint_with_attachments(complaint_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{complaint_id}", status_code=status.HTTP_200_OK)
async def delete_complaint(
    complaint_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a complaint."""
    try:
        service = ComplaintService(db)
        service.delete_complaint(complaint_id)
        return {"message": "Complaint deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
