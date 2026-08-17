"""Composer message snippet routes (UAC AC-L4, slice S4.4).

Admin CRUD for the listing page, plus the one read the ticket composer's "/"
picker uses. Snippets are workspace-global in v1, so there is no scope
parameter anywhere here.

Permissions split the two audiences deliberately: `.view` is what the picker
needs (everyone who works tickets), while add/edit/delete gate the admin page.
Migration 329 copies `.view` onto every role that can already see conversation
SLA tracking, so the picker is never silently empty for an existing role.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.message_snippet import (
    MessageSnippetCreate,
    MessageSnippetOption,
    MessageSnippetResponse,
    MessageSnippetUpdate,
)
from app.services.error_handler import handle_internal_error, handle_not_found
from app.services.message_snippet_service import (
    MessageSnippetService,
    SnippetContext,
    snippet_context_for_tracking,
)
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "sla_management.message_snippets.view"
ADD = "sla_management.message_snippets.add"
EDIT = "sla_management.message_snippets.edit"
DELETE = "sla_management.message_snippets.delete"


@router.get("/", response_model=ListResponse[MessageSnippetResponse])
async def list_message_snippets(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    sort: Optional[str] = Query("name"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """Admin listing: every snippet, active or not."""
    try:
        return MessageSnippetService(db).list_snippets(
            page=page,
            limit=limit,
            query=query,
            is_active=is_active,
            sort_field=sort or "name",
            sort_dir=dir or "asc",
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))


@router.get("/select", response_model=List[MessageSnippetOption])
async def list_message_snippets_for_composer(
    query: Optional[str] = Query(None),
    tracking_id: Optional[str] = Query(
        None,
        description=(
            "Conversation SLA tracking the composer is open on. Supplied, every "
            "body comes back with its $variables resolved from that ticket."
        ),
    ),
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    """The "/" picker's list: ACTIVE snippets with their bodies resolved.

    Without ``tracking_id`` the bodies still come back resolved, using the
    neutral fallbacks - a picker that shows raw ``$contact_name`` when a ticket
    is not resolvable would leak the token straight into a customer's WhatsApp.

    Scoped exactly like the drawer it is opened from: a viewer who cannot act on
    the ticket gets a 404 (never a 403 - no existence leak), the same rule as
    ``GET .../{tracking_id}/ticket``.
    """
    context = SnippetContext()
    if tracking_id:
        from app.services.sla_service import ConversationSLATrackingService

        sla = ConversationSLATrackingService(db)
        tracking = sla.get_tracking(tracking_id, load_event_logs=False)
        if not tracking or not sla.can_user_act_on_tracking(current_user["id"], tracking):
            raise handle_not_found("Conversation SLA tracking", tracking_id)
        context = snippet_context_for_tracking(
            tracking, viewer_name=(current_user.get("name") or "").strip() or None
        )
    try:
        return MessageSnippetService(db).list_for_composer(query=query, context=context)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))


@router.get("/{snippet_id}", response_model=MessageSnippetResponse)
async def get_message_snippet(
    snippet_id: str,
    current_user: dict = Depends(require_permission_with_api_key(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(snippet_id, resource="Message Snippet")
        return MessageSnippetService(db).get_snippet(snippet_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))


@router.post("/", response_model=MessageSnippetResponse, status_code=status.HTTP_201_CREATED)
async def create_message_snippet(
    payload: MessageSnippetCreate,
    current_user: dict = Depends(require_permission(ADD)),
    db: Session = Depends(get_db),
):
    try:
        return MessageSnippetService(db).create_snippet(
            payload, created_by=current_user.get("id")
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))


@router.put("/{snippet_id}", response_model=MessageSnippetResponse)
async def update_message_snippet(
    snippet_id: str,
    payload: MessageSnippetUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(snippet_id, resource="Message Snippet")
        return MessageSnippetService(db).update_snippet(snippet_id, payload)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))


@router.delete("/{snippet_id}", status_code=status.HTTP_200_OK)
async def delete_message_snippet(
    snippet_id: str,
    current_user: dict = Depends(require_permission(DELETE)),
    db: Session = Depends(get_db),
):
    """Hard delete (product standard); the FE confirms first."""
    try:
        validate_uuid_path(snippet_id, resource="Message Snippet")
        return MessageSnippetService(db).delete_snippet(snippet_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise handle_internal_error(str(e))
