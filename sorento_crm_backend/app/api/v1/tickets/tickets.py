"""Tickets endpoints (Jira-style internal ticketing).

Mounted at ``/api/v1/tickets-management/tickets``. Visibility for
non-admins is enforced server-side (raised_by / assigned_to / watcher
membership) by ``tickets_service``; ``tickets.tickets.view_all`` unlocks
the full pool.

Phase 1 wires the surface; Phase 2 fills the service implementation.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    require_permission,
    require_permission_with_api_key,
)
from app.schemas.tickets import (
    BulkDeleteTicketsRequest,
    TicketAssignRequest,
    TicketCreate,
    TicketKanbanResponse,
    TicketResolutionUpdate,
    TicketResponse,
    TicketResponseUpdate,
    TicketStatusChangeRequest,
    TicketUpdate,
    TicketWatchersUpdate,
)

router = APIRouter()


@router.get("/tickets")
def list_tickets(
    status: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    raised_by: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    due_before: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Title/description/ticket-number search"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission_with_api_key("tickets.tickets.view")
    ),
):
    from app.services.tickets_service import list_tickets as _impl
    return _impl(
        db,
        filters={
            "status": status,
            "assigned_to": assigned_to,
            "raised_by": raised_by,
            "priority": priority,
            "category": category,
            "due_before": due_before,
            "q": q,
        },
        page=page,
        limit=limit,
        current_user=current_user,
    )


@router.get("/tickets/kanban", response_model=TicketKanbanResponse)
def kanban(
    status: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    raised_by: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission_with_api_key("tickets.tickets.view")
    ),
):
    from app.services.tickets_service import kanban as _impl
    return _impl(
        db,
        filters={
            "status": status,
            "assigned_to": assigned_to,
            "raised_by": raised_by,
            "priority": priority,
            "category": category,
        },
        current_user=current_user,
    )


@router.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(
    body: TicketCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.add")),
):
    from app.services.tickets_service import create_ticket as _impl
    return _impl(db, data=body, current_user=current_user)


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission_with_api_key("tickets.tickets.view")
    ),
):
    from app.services.tickets_service import get_ticket as _impl
    return _impl(db, ticket_id=ticket_id, current_user=current_user)


@router.patch("/tickets/{ticket_id}", response_model=TicketResponse)
def update_ticket(
    ticket_id: str,
    body: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.edit")),
):
    from app.services.tickets_service import update_ticket as _impl
    return _impl(db, ticket_id=ticket_id, data=body, current_user=current_user)


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.delete")),
):
    from app.services.tickets_service import delete_ticket as _impl
    _impl(db, ticket_id=ticket_id, current_user=current_user)


@router.post("/tickets/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
def bulk_delete_tickets(
    body: BulkDeleteTicketsRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.delete")),
):
    from app.services.tickets_service import bulk_delete_tickets as _impl
    _impl(db, ids=body.ids, current_user=current_user)


@router.post("/tickets/{ticket_id}/status", response_model=TicketResponse)
def change_status(
    ticket_id: str,
    body: TicketStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.edit")),
):
    from app.services.tickets_service import change_status as _impl
    return _impl(
        db,
        ticket_id=ticket_id,
        new_status=body.new_status,
        note=body.note,
        current_user=current_user,
    )


@router.post("/tickets/{ticket_id}/assign", response_model=TicketResponse)
def assign(
    ticket_id: str,
    body: TicketAssignRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.assign")),
):
    from app.services.tickets_service import assign as _impl
    return _impl(
        db,
        ticket_id=ticket_id,
        assignee_id=body.assignee_id,
        current_user=current_user,
    )


@router.put("/tickets/{ticket_id}/response", response_model=TicketResponse)
def update_response(
    ticket_id: str,
    body: TicketResponseUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.edit")),
):
    from app.services.tickets_service import update_response as _impl
    return _impl(
        db,
        ticket_id=ticket_id,
        response_html=body.response_html,
        response_text=body.response_text,
        current_user=current_user,
    )


@router.put("/tickets/{ticket_id}/resolution", response_model=TicketResponse)
def update_resolution(
    ticket_id: str,
    body: TicketResolutionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.edit")),
):
    from app.services.tickets_service import update_resolution as _impl
    return _impl(
        db,
        ticket_id=ticket_id,
        resolution_html=body.resolution_html,
        resolution_text=body.resolution_text,
        current_user=current_user,
    )


@router.post("/tickets/{ticket_id}/watchers", response_model=TicketResponse)
def add_watchers(
    ticket_id: str,
    body: TicketWatchersUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.edit")),
):
    from app.services.tickets_service import add_watchers as _impl
    return _impl(
        db,
        ticket_id=ticket_id,
        user_ids=body.user_ids,
        current_user=current_user,
    )


@router.delete(
    "/tickets/{ticket_id}/watchers/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_watcher(
    ticket_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.edit")),
):
    from app.services.tickets_service import remove_watcher as _impl
    _impl(db, ticket_id=ticket_id, user_id=user_id, current_user=current_user)


@router.post("/tickets/{ticket_id}/attachments")
def link_attachment(
    ticket_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.edit")),
):
    from app.services.tickets_service import link_attachment as _impl
    return _impl(
        db,
        ticket_id=ticket_id,
        attachment_id=attachment_id,
        current_user=current_user,
    )


@router.delete(
    "/tickets/attachments/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unlink_attachment(
    link_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("tickets.tickets.edit")),
):
    from app.services.tickets_service import unlink_attachment as _impl
    _impl(db, link_id=link_id, current_user=current_user)
