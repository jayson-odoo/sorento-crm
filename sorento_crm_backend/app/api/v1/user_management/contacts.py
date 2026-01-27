"""Respond contacts API routes."""
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import logging
import httpx
from app.database import get_db
from app.dependencies import get_current_user
from app.services.contact_service import ContactService
from app.schemas.user import RespondContactResponse, RespondContactCreate, RespondContactUpdate, ContactAgentAccessResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)

router = APIRouter()


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
        return RespondContactResponse.model_validate(contact)
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
        return RespondContactResponse.model_validate(contact)
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
        # Convert to dict for validation
        contact_dict = {
            'id': str(contact.id),
            'phone_number': contact.phone_number,
            'name': contact.name,
            'created_at': contact.created_at,
            'updated_at': contact.updated_at,
            'created_by': contact.created_by,
        }
        return RespondContactResponse.model_validate(contact_dict)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating contact {contact_id}: {str(e)}", exc_info=True)
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
        # Convert to dict for validation
        contact_dict = {
            'id': str(contact.id),
            'phone_number': contact.phone_number,
            'name': contact.name,
            'created_at': contact.created_at,
            'updated_at': contact.updated_at,
            'created_by': contact.created_by,
        }
        return RespondContactResponse.model_validate(contact_dict)
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
