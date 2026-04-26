"""Commercial lead ↔ respond_contacts junction (links, roles, order)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.commercial_core.models import CommercialLeadRespondContact
from app.modules.commercial_core.schemas.lead_respond_contact import (
    LeadRespondContactCreate,
    LeadRespondContactLinkByPhone,
    LeadRespondContactRow,
    LeadRespondContactUpdate,
    RespondContactBrief,
)
from app.services.error_handler import handle_internal_error
from app.modules.commercial_core.services.lead_respond_contact_service import LeadRespondContactService
from app.services.user_service import UserPermissionService

router = APIRouter()


class LeadRespondConversationReplyBody(BaseModel):
    message: str = Field(..., min_length=1)


def _reply_respond_user_id(current_user: dict) -> str:
    rid = (current_user or {}).get("respond_user_id") or (current_user or {}).get("respondUserId")
    if rid and str(rid).strip():
        return str(rid).strip()
    uid = (current_user or {}).get("id")
    if uid and str(uid).strip():
        return str(uid).strip()
    raise HTTPException(
        status_code=400,
        detail="User respond_user_id or id is required to send a message.",
    )


def _require_leads_view(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    svc = UserPermissionService(db)
    uid = current_user["id"]
    if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return current_user
    if not svc.check_user_has_permission(uid, "commercial_core.leads.view"):
        raise HTTPException(status_code=403, detail="Permission required: commercial_core.leads.view")
    return current_user


def _require_leads_edit(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    svc = UserPermissionService(db)
    uid = current_user["id"]
    if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return current_user
    if not svc.check_user_has_permission(uid, "commercial_core.leads.edit"):
        raise HTTPException(status_code=403, detail="Permission required: commercial_core.leads.edit")
    return current_user


def _load_link(db: Session, lead_id: str, link_id: str) -> Optional[CommercialLeadRespondContact]:
    return (
        db.query(CommercialLeadRespondContact)
        .options(joinedload(CommercialLeadRespondContact.respond_contact))
        .filter(
            CommercialLeadRespondContact.lead_id == lead_id,
            CommercialLeadRespondContact.id == link_id,
        )
        .first()
    )


def _link_row(link: CommercialLeadRespondContact) -> LeadRespondContactRow:
    c = link.respond_contact
    if c is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Linked contact failed to load")
    return LeadRespondContactRow(
        id=str(link.id),
        lead_id=str(link.lead_id),
        respond_contact_id=str(link.respond_contact_id),
        contact_role=link.contact_role,
        sort_order=link.sort_order,
        created_at=link.created_at,
        updated_at=link.updated_at,
        contact=RespondContactBrief(
            id=str(c.id),
            phone_number=c.phone_number,
            name=c.name,
            first_name=getattr(c, "first_name", None),
            last_name=getattr(c, "last_name", None),
            respond_io_id=getattr(c, "respond_io_id", None),
            access_type_code=getattr(c, "access_type_code", None),
            respond_workspace_id=str(c.respond_workspace_id),
        ),
    )


@router.get("/{lead_id}/respond-contacts", response_model=list[LeadRespondContactRow])
async def list_lead_respond_contacts(
    lead_id: str,
    _user: dict = Depends(_require_leads_view),
    db: Session = Depends(get_db),
):
    try:
        svc = LeadRespondContactService(db)
        rows = svc.list_for_lead(lead_id)
        return [_link_row(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{lead_id}/respond-contacts", response_model=LeadRespondContactRow, status_code=status.HTTP_201_CREATED)
async def create_lead_respond_contact_link(
    lead_id: str,
    data: LeadRespondContactCreate,
    _user: dict = Depends(_require_leads_edit),
    db: Session = Depends(get_db),
):
    try:
        svc = LeadRespondContactService(db)
        row = svc.create_link(lead_id, data)
        loaded = _load_link(db, lead_id, str(row.id))
        return _link_row(loaded or row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{lead_id}/respond-contacts/from-phone", response_model=LeadRespondContactRow, status_code=status.HTTP_201_CREATED)
async def create_lead_respond_contact_from_phone(
    lead_id: str,
    data: LeadRespondContactLinkByPhone,
    _user: dict = Depends(_require_leads_edit),
    db: Session = Depends(get_db),
):
    try:
        svc = LeadRespondContactService(db)
        row = svc.link_by_phone(
            lead_id,
            data.phone,
            data.name,
            data.contact_role,
            data.sort_order,
        )
        loaded = _load_link(db, lead_id, str(row.id))
        return _link_row(loaded or row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{lead_id}/respond-contacts/{link_id}", response_model=LeadRespondContactRow)
async def update_lead_respond_contact_link(
    lead_id: str,
    link_id: str,
    data: LeadRespondContactUpdate,
    _user: dict = Depends(_require_leads_edit),
    db: Session = Depends(get_db),
):
    try:
        svc = LeadRespondContactService(db)
        row = svc.update_link(lead_id, link_id, data)
        loaded = _load_link(db, lead_id, link_id)
        return _link_row(loaded or row)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{lead_id}/respond-contacts/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead_respond_contact_link(
    lead_id: str,
    link_id: str,
    _user: dict = Depends(_require_leads_edit),
    db: Session = Depends(get_db),
):
    try:
        svc = LeadRespondContactService(db)
        svc.delete_link(lead_id, link_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{lead_id}/respond-conversation")
async def get_lead_respond_conversation(
    lead_id: str,
    respond_contact_id: str = Query(..., description="respond_contacts.id for a contact linked to this lead"),
    limit: int = Query(50, ge=1, le=50),
    cursor: Optional[str] = Query(None),
    _user: dict = Depends(_require_leads_view),
    db: Session = Depends(get_db),
):
    try:
        svc = LeadRespondContactService(db)
        return svc.fetch_respond_conversation_for_contact(
            lead_id, respond_contact_id, limit=limit, cursor=cursor
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{lead_id}/respond-conversation/reply")
async def post_lead_respond_conversation_reply(
    lead_id: str,
    body: LeadRespondConversationReplyBody,
    respond_contact_id: str = Query(..., description="respond_contacts.id for a contact linked to this lead"),
    current_user: dict = Depends(_require_leads_edit),
    db: Session = Depends(get_db),
):
    try:
        respond_user_id = _reply_respond_user_id(current_user)
        svc = LeadRespondContactService(db)
        svc.send_respond_reply_for_contact(
            lead_id,
            respond_contact_id,
            body.message,
            respond_user_id=respond_user_id,
            crm_sender_user_id=current_user.get("id"),
        )
        db.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
