"""External X-API-Key endpoint exposing per-contact active access codes.

Discovery surface for MCP agents that need to pass `access_levels` to
gated promotion / attachment tools. Replaces the legacy two-call protocol
(call gated tool without access_levels → 422 + allowed list) with a
dedicated read tool that n8n can call first.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services.contact_access_type_service import ContactAccessTypeService

router = APIRouter()


@router.get("/active", response_model=list)
def list_active_access_levels_for_contact(
    contact_id: str = Query(..., description="Respond.io contact id (respond_io_id)."),
    space_id: str = Query(..., description="Respond.io space id (matches respond_workspaces.space_id)."),
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Return [{code, name, description}] for the contact's currently-active access codes.

    Empty list when the contact has no active codes (still 200). 404 when the
    (contact_id, space_id) pair does not match an existing Respond contact.
    """
    contact_id = (contact_id or "").strip()
    space_id = (space_id or "").strip()
    if not contact_id or not space_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contact_id and space_id are both required.")
    return ContactAccessTypeService(db).resolve_active_access_levels_for_contact(contact_id, space_id)
