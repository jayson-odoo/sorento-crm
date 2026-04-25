"""Complaints API routes."""
import logging

from fastapi import APIRouter, Depends, Query, HTTPException, status, Request, Body
from sqlalchemy.orm import Session
from typing import Optional, Union, List, Any
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.complaints_service import ComplaintService
from app.services.integration_service import IntegrationLogService
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

_COMPLAINT_DO_LOOKUP_FIELDS: tuple[str, ...] = ("customer_name", "product_code", "order_date_from", "order_date_to")


def _request_has_valid_external_api_key(request: Optional[Request]) -> bool:
    """True when X-API-Key header matches configured external API key (same as get_current_user_or_api_key)."""
    if request is None:
        return False
    key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    valid = getattr(app_settings, "external_api_key", None)
    if not key or not valid:
        return False
    return key.strip() == str(valid).strip()


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
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort: Optional[str] = Query("complaint_date"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get complaints with pagination, search, assignee/status filters, and sorting."""
    try:
        service = ComplaintService(db)
        result = service.list_complaints(
            page=page,
            limit=limit,
            query=query,
            assigned_to=assigned_to,
            status=status,
            sort_field=sort or "complaint_date",
            sort_dir=dir or "asc"
        )
        return result
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

        service = ComplaintService(db)
        complaint = service.get_complaint(complaint_id)
        identifier = service._identifier_from_respond_inbox_url(
            getattr(complaint, "respond_inbox_url", None)
        )
        if not identifier:
            return {"items": [], "pagination": {}, "error": "No Respond.io contact linked"}
        client = RespondClient()
        return client.list_messages(identifier, limit=limit, cursor=cursor)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint(
    complaint_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single complaint by ID."""
    try:
        service = ComplaintService(db)
        complaint = service.get_complaint_with_attachments(complaint_id)
        return complaint
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
    )


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
) -> None:
    detail: dict[str, Any] = {
        "status": status_value,
        "next_action": "collect_do_lookup_filters",
        "message": message,
        "required_filters": list(_COMPLAINT_DO_LOOKUP_FIELDS),
        "missing_fields": list(_COMPLAINT_DO_LOOKUP_FIELDS),
    }
    if invalid_do_numbers:
        detail["invalid_delivery_order_numbers"] = invalid_do_numbers
    if valid_do_numbers:
        detail["valid_delivery_order_numbers"] = valid_do_numbers
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _enforce_delivery_order_first(service: ComplaintService, complaint_data: ComplaintCreate) -> dict[str, Any]:
    """Validate DO selection first; request customer+product+order_date filters when DO is missing.

    Returns inferred customer/product hints from the selected DO(s).
    """
    resolved_do_numbers, invalid_do_numbers, provided_do_numbers = service.resolve_delivery_order_numbers(
        complaint_data.delivery_order_number
    )
    if not provided_do_numbers:
        _raise_do_lookup_guidance(
            status_value="needs_do_lookup",
            message=(
                "Delivery order number is required before complaint details. "
                "Please provide customer name, product, and order date range so we can search DO numbers."
            ),
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
        _raise_do_lookup_guidance(
            status_value="needs_do_lookup",
            message=(
                "No matching delivery order found. Please provide customer name, product, and order date range "
                "to search for valid DO number(s)."
            ),
            invalid_do_numbers=invalid_do_numbers or provided_do_numbers,
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
) -> None:
    """Structured response for incomplete complaint details after DO selection."""
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
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


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
        do_context = _enforce_delivery_order_first(service, complaint_data)
        _prefill_complaint_fields_from_do(complaint_data, do_context, integration_payload)
        requires_user_confirm = is_integration_payload or _request_has_valid_external_api_key(request)
        if requires_user_confirm:
            if integration_payload is not None:
                _validate_integration_payload_completeness(integration_payload)
            # Enforce missing-field validation before confirmation gating.
            missing_fields = service.get_submission_missing_fields(complaint_data)
            if missing_fields:
                _raise_needs_more_fields_guidance(missing_fields=missing_fields, do_context=do_context)
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
        do_context = _enforce_delivery_order_first(service, complaint_data)
        _prefill_complaint_fields_from_do(complaint_data, do_context, payload)
        # Validate payload completeness after DO validation; only then enforce explicit confirmation.
        _validate_integration_payload_completeness(payload)
        missing_fields = service.get_submission_missing_fields(complaint_data)
        if missing_fields:
            _raise_needs_more_fields_guidance(missing_fields=missing_fields, do_context=do_context)
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
