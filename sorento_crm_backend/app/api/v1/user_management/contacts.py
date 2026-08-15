"""Respond contacts API routes."""
from fastapi import APIRouter, Depends, Query, status, HTTPException, Body, Request
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import logging
import httpx
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.access import RespondContact
from app.models.respond_workspace import RespondWorkspace
from app.services.contact_service import ContactService
from app.services.portal_service import PortalService
from app.schemas.user import RespondContactResponse, RespondContactCreate, RespondContactUpdate, ContactAgentAccessResponse
from app.schemas.common import ListResponse
from app.schemas.market_segment import MarketSegmentCodesUpdate
from app.services.error_handler import handle_internal_error, handle_not_found

logger = logging.getLogger(__name__)

router = APIRouter()


class ContactCompaniesUpdateRequest(BaseModel):
    company_ids: list[str]


class ContactAttachmentTypesUpdate(BaseModel):
    attachment_type_ids: list[str]


def _resolve_space_id(db: Session, contact_id: str) -> tuple[RespondContact, str]:
    """Look up contact and resolve its workspace's space_id.

    Raises 404 if the contact does not exist; raises 422 (with a "workspace"
    message) if the contact is not associated with a usable workspace.
    """
    contact = db.query(RespondContact).filter(RespondContact.id == contact_id).first()
    if contact is None:
        raise handle_not_found("Contact", contact_id)
    if not contact.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact has no workspace; cannot mint portal link.",
        )
    workspace = (
        db.query(RespondWorkspace)
        .filter(RespondWorkspace.id == contact.workspace_id)
        .first()
    )
    if workspace is None or not workspace.space_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact has no workspace; cannot mint portal link.",
        )
    return contact, workspace.space_id


def _effective_base_url(request: Request, payload_base_url: Optional[str]) -> Optional[str]:
    """Resolve the FE base URL for portal links.

    Order: explicit payload override > settings.frontend_base_url > derived from
    request (scheme://host). Ensures the response always carries an absolute URL
    so QR codes and Respond.io chat messages render correctly.
    """
    if payload_base_url:
        return payload_base_url
    from app.config import settings as _settings
    if (_settings.frontend_base_url or "").strip():
        return _settings.frontend_base_url
    base = str(request.base_url).rstrip("/")
    return base or None


@router.get("/", response_model=ListResponse[RespondContactResponse])
async def get_contacts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all respond contacts with pagination and filtering."""
    try:
        service = ContactService(db)
        result = service.list_contacts(
            page=page,
            limit=limit,
            query=query,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_contacts: {str(e)}", exc_info=True)
        raise handle_internal_error(str(e))


class BulkDeleteContactsRequest(BaseModel):
    ids: list[str]


class BulkSyncContactsRequest(BaseModel):
    ids: list[str]


class PortalLinkRequest(BaseModel):
    base_url: Optional[str] = None
    submission_type: Optional[str] = None


class PortalLinkResponse(BaseModel):
    token: str
    expires_at: str
    portal_url: str
    reused: bool


class PortalLinkSendResponse(BaseModel):
    token: str
    expires_at: str
    portal_url: str
    reused: bool
    sent: bool


@router.post("/bulk-sync", status_code=status.HTTP_200_OK)
async def bulk_sync_contacts(
    body: BulkSyncContactsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sync multiple contacts from Respond.io (name, first/last name, respond_io_id)."""
    try:
        service = ContactService(db)
        result = service.bulk_sync_contacts_from_respond(body.ids)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk_sync_contacts: {str(e)}", exc_info=True)
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_contacts(
    body: BulkDeleteContactsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bulk delete contacts by ID. Related access records are removed."""
    try:
        service = ContactService(db)
        result = service.bulk_delete_contacts(body.ids)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk_delete_contacts: {str(e)}", exc_info=True)
        raise handle_internal_error(str(e))


@router.get("/{contact_id}", response_model=RespondContactResponse)
async def get_contact(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single contact by ID."""
    try:
        service = ContactService(db)
        contact = service.get_contact(contact_id)
        return RespondContactResponse.model_validate(ContactService.contact_to_response_dict(contact))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=RespondContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_data: RespondContactCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new respond contact."""
    try:
        service = ContactService(db)
        contact = service.create_contact(contact_data)
        return RespondContactResponse.model_validate(ContactService.contact_to_response_dict(contact))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{contact_id}", response_model=RespondContactResponse)
async def update_contact(
    contact_id: str,
    contact_data: RespondContactUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a respond contact."""
    try:
        service = ContactService(db)
        contact = service.update_contact(contact_id, contact_data)
        return RespondContactResponse.model_validate(ContactService.contact_to_response_dict(contact))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating contact {contact_id}: {str(e)}", exc_info=True)
        raise handle_internal_error(str(e))


# No permission dependency by design: the gate is in the handler body, which calls
# `_require_superadmin(db, current_user)` before reading anything. See
# `documentation/plans/security/PLAN-user-management-read-gates.md`.
@router.get("/{contact_id}/companies")
async def get_contact_companies(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List companies granted to a contact as [{id,name,code}]. Superadmin-only."""
    from app.api.v1.system.companies import _require_superadmin
    try:
        _require_superadmin(db, current_user)
        return ContactService(db).list_contact_companies(contact_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{contact_id}/companies", status_code=status.HTTP_200_OK)
async def set_contact_companies(
    contact_id: str,
    body: ContactCompaniesUpdateRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Replace a contact's company grants with the given company_ids. Superadmin-only."""
    from app.api.v1.system.companies import _require_superadmin
    try:
        _require_superadmin(db, current_user)
        return ContactService(db).set_contact_companies(contact_id, body.company_ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a respond contact. Related access records are cascade-deleted; SLA tracking references are set to null."""
    try:
        service = ContactService(db)
        service.delete_contact(contact_id)
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting contact {contact_id}: {str(e)}", exc_info=True)
        raise handle_internal_error(str(e))


@router.post("/{contact_id}/sync", response_model=RespondContactResponse)
async def sync_contact(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync contact name from Respond.io API."""
    try:
        service = ContactService(db)
        contact = service.sync_contact_name(contact_id)
        return RespondContactResponse.model_validate(ContactService.contact_to_response_dict(contact))
    except HTTPException:
        raise
    except ValueError as e:
        # Configuration error - API key not set
        logger.error(f"Configuration error syncing contact {contact_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to sync contact. Respond.io API is not configured.",
                "detail": str(e),
                "code": "CONFIGURATION_ERROR"
            }
        )
    except Exception as e:
        logger.error(f"Error syncing contact {contact_id}: {str(e)}", exc_info=True)
        
        # Handle httpx exceptions
        if isinstance(e, httpx.HTTPStatusError):
            status_code = e.response.status_code
            if status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "message": "Contact not found in Respond.io",
                        "detail": "The contact does not exist in Respond.io system.",
                        "code": "CONTACT_NOT_FOUND"
                    }
                )
            elif status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "message": "Unauthorized access to Respond.io API",
                        "detail": "Invalid API key or insufficient permissions.",
                        "code": "UNAUTHORIZED"
                    }
                )
            else:
                error_detail = f"HTTP {status_code}: {e.response.text if hasattr(e.response, 'text') else str(e)}"
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "message": "Respond.io API error",
                        "detail": error_detail,
                        "code": f"HTTP_{status_code}"
                    }
                )
        elif isinstance(e, httpx.TimeoutException):
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={
                    "message": "Request to Respond.io API timed out",
                    "detail": "The API request took too long to complete.",
                    "code": "TIMEOUT_ERROR"
                }
            )
        elif isinstance(e, httpx.ConnectError):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Failed to connect to Respond.io API",
                    "detail": "Unable to establish connection to Respond.io servers.",
                    "code": "CONNECTION_ERROR"
                }
            )
        
        # Generic error
        error_detail = str(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to sync contact from Respond.io",
                "detail": error_detail,
                "code": "SYNC_ERROR"
            }
        )


class CsRoutingPinRequest(BaseModel):
    cs_pic_user_id: str
    # Predicate set [{field, operator, value}], AND-combined, matched against the
    # form header fields. Empty/omitted = wildcard. Lower `priority` wins among
    # matching rows for a form (pure admin order).
    match_conditions: Optional[list] = None
    priority: int = 0


@router.get("/cs-routing/candidates")
async def list_cs_routing_candidates(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tier-1 members of the procurement customer-service team (pin dropdown options)."""
    try:
        from app.services.cs_routing_service import CsRoutingService

        return {"candidates": CsRoutingService(db).list_candidates()}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{contact_id}/cs-routing")
async def get_contact_cs_routing(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List a salesman's CS-PIC pins (one per procurement use_case)."""
    try:
        from app.services.cs_routing_service import CsRoutingService

        return {"pins": CsRoutingService(db).list_for_contact(contact_id)}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{contact_id}/cs-routing/{use_case}")
async def upsert_contact_cs_routing(
    contact_id: str,
    use_case: str,
    payload: CsRoutingPinRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pin this salesman to a CS PIC for ``use_case`` (purchase_request | sponsorship_form)."""
    try:
        from app.services.cs_routing_service import CsRoutingService

        row = CsRoutingService(db).upsert(
            contact_id,
            use_case,
            payload.cs_pic_user_id,
            match_conditions=payload.match_conditions,
            priority=payload.priority,
            created_by=current_user.get("id"),
        )
        return {
            "id": row.id,
            "use_case": row.use_case,
            "cs_pic_user_id": row.cs_pic_user_id,
            "match_conditions": row.match_conditions or [],
            "priority": row.priority or 0,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/cs-routing/fields")
async def list_cs_routing_fields(
    use_case: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Routable predicate fields for a use_case's form (lookup + curated header fields)."""
    try:
        from app.services.cs_routing_service import CsRoutingService

        return {"fields": CsRoutingService(db).routable_fields(use_case)}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{contact_id}/cs-routing/{use_case}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact_cs_routing(
    contact_id: str,
    use_case: str,
    row_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Clear routing rows for a use_case (or one ``row_id``) → reverts to round-robin."""
    try:
        from app.services.cs_routing_service import CsRoutingService

        CsRoutingService(db).delete(contact_id, use_case, row_id=row_id)
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{contact_id}/market-segments")
async def get_contact_market_segments(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List a contact's assigned market segments (retail / project). Empty = matches all CS members."""
    try:
        from app.services.market_segment_service import MarketSegmentService

        return {"codes": MarketSegmentService(db).get_contact_segment_codes(contact_id)}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{contact_id}/market-segments")
async def set_contact_market_segments(
    contact_id: str,
    payload: MarketSegmentCodesUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replace a contact's market segments with the supplied set (empty = clear → matches all)."""
    try:
        from app.services.market_segment_service import MarketSegmentService

        return {
            "codes": MarketSegmentService(db).set_contact_segments(contact_id, payload.codes)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{contact_id}/attachment-types")
async def get_contact_attachment_types(
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Document types this contact may retrieve, on top of the direct-access baseline.

    Returns the whole catalog with a `granted` flag so the dialog can show what is
    grantable, not only what is granted.
    """
    try:
        from app.services.contact_attachment_access import list_grants

        return list_grants(db, contact_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{contact_id}/attachment-types")
async def set_contact_attachment_types(
    contact_id: str,
    payload: ContactAttachmentTypesUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replace this contact's attachment-type grants (empty = baseline only)."""
    try:
        from app.services.contact_attachment_access import set_grants

        return set_grants(
            db,
            contact_id,
            payload.attachment_type_ids,
            actor=str(current_user.get("id") or current_user.get("sub") or ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{contact_id}/access-agents", response_model=ListResponse[ContactAgentAccessResponse])
async def get_contact_access_agents(
    contact_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all access agents for a specific contact."""
    try:
        from app.services.user_service import AccessAgentService
        from app.schemas.user import ContactAgentAccessResponse

        service = AccessAgentService(db)
        # List contact accesses filtered by respond_contact_id
        result = service.list_all_contact_accesses(
            page=page,
            limit=limit,
            respond_contact_id=contact_id,
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{contact_id}/portal-link", response_model=PortalLinkResponse)
async def get_contact_portal_link(
    contact_id: str,
    request: Request,
    payload: PortalLinkRequest = Body(default_factory=PortalLinkRequest),
    current_user: dict = Depends(require_permission("user_management.contacts.portal_link")),
    db: Session = Depends(get_db),
):
    """Mint or reuse a 7-day user-submission portal token for the contact."""
    _, space_id = _resolve_space_id(db, contact_id)
    service = PortalService(db)
    token, reused = service.get_or_mint_token(contact_id, space_id)
    base_url = _effective_base_url(request, payload.base_url)
    return PortalLinkResponse(
        token=token.token,
        expires_at=token.expires_at.isoformat(),
        portal_url=service.build_portal_url(
            token.token, base_url, payload.submission_type, token_row=token
        ),
        reused=reused,
    )


@router.post("/{contact_id}/portal-link/send", response_model=PortalLinkSendResponse)
async def send_contact_portal_link(
    contact_id: str,
    request: Request,
    payload: PortalLinkRequest = Body(default_factory=PortalLinkRequest),
    current_user: dict = Depends(require_permission("user_management.contacts.portal_link")),
    db: Session = Depends(get_db),
):
    """Mint or reuse a portal token and send the link to the contact via Respond.io."""
    contact, space_id = _resolve_space_id(db, contact_id)
    if not (contact.respond_io_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact has no Respond.io identifier; cannot send link.",
        )
    service = PortalService(db)
    base_url = _effective_base_url(request, payload.base_url)
    try:
        result = service.send_link_via_respond_io(
            contact_id, space_id, base_url, payload.submission_type
        )
    except httpx.HTTPStatusError as exc:
        upstream = ""
        try:
            upstream = exc.response.text[:500]
        except Exception:
            pass
        raise HTTPException(
            status_code=502,
            detail=f"Respond.io upstream failure: {upstream or str(exc)}",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Respond.io upstream timed out.",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Respond.io upstream unreachable: {exc.__class__.__name__}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )
    return PortalLinkSendResponse(**result)
