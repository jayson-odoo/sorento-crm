"""Commercial lead ↔ respond_contacts junction and primary phone linking on lead creation."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.access import RespondContact
from app.modules.commercial_core.models import CommercialLead, CommercialLeadRespondContact
from app.models.order import Customer
from app.models.respond_workspace import RespondWorkspace
from app.modules.commercial_core.schemas.lead_respond_contact import LeadRespondContactCreate, LeadRespondContactUpdate
from app.utils.phone_normalize import normalize_phone


def extract_primary_phone_for_lead(qualification: Dict[str, Any], customer: Customer) -> Optional[str]:
    """Best-effort phone used when creating/linking primary respond contact."""
    q = qualification or {}
    for key in ("client_phone", "phone", "phone_number", "mobile"):
        v = q.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    contacts = q.get("contacts") or []
    if isinstance(contacts, list):
        for c in contacts:
            if not isinstance(c, dict):
                continue
            role = (c.get("role") or c.get("contact_role") or "").lower()
            if role == "main":
                p = c.get("phone") or c.get("phone_number")
                if p is not None and str(p).strip():
                    return str(p).strip()
    phone = getattr(customer, "phone_number", None)
    if phone and str(phone).strip():
        return str(phone).strip()
    return None


class LeadRespondContactService:
    def __init__(self, db: Session):
        self.db = db

    def _get_lead(self, lead_id: str) -> CommercialLead:
        lead = self.db.query(CommercialLead).filter(CommercialLead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return lead

    def _workspace_must_match(self, lead: CommercialLead, contact: RespondContact) -> None:
        lw = getattr(lead, "respond_workspace_id", None)
        cw = getattr(contact, "respond_workspace_id", None)
        if lw is None or cw is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Lead and contact must both have a Respond workspace assigned",
            )
        if str(lw) != str(cw):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Contact belongs to a different Respond workspace than this lead",
            )

    def search_contacts(
        self,
        workspace_id: str,
        q: Optional[str] = None,
        *,
        limit: int = 50,
    ) -> List[RespondContact]:
        ws = self.db.query(RespondWorkspace).filter(RespondWorkspace.id == workspace_id).first()
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Respond workspace not found")
        query = self.db.query(RespondContact).filter(RespondContact.respond_workspace_id == workspace_id)
        if q and q.strip():
            term = f"%{q.strip()}%"
            query = query.filter(or_(RespondContact.phone_number.ilike(term), RespondContact.name.ilike(term)))
        return query.order_by(RespondContact.phone_number.asc()).limit(limit).all()

    def list_for_lead(self, lead_id: str) -> List[CommercialLeadRespondContact]:
        self._get_lead(lead_id)
        rows = (
            self.db.query(CommercialLeadRespondContact)
            .options(joinedload(CommercialLeadRespondContact.respond_contact))
            .filter(CommercialLeadRespondContact.lead_id == lead_id)
            .order_by(CommercialLeadRespondContact.sort_order.asc(), CommercialLeadRespondContact.created_at.asc())
            .all()
        )
        return rows

    def find_contact_by_phone(self, workspace_id: str, phone_raw: str) -> Optional[RespondContact]:
        target = normalize_phone(phone_raw)
        if not target:
            return None
        rows = (
            self.db.query(RespondContact).filter(RespondContact.respond_workspace_id == workspace_id).all()
        )
        for r in rows:
            if normalize_phone(r.phone_number) == target:
                return r
        return None

    def create_local_contact(
        self,
        workspace_id: str,
        phone_raw: str,
        name: Optional[str] = None,
    ) -> RespondContact:
        ws = self.db.query(RespondWorkspace).filter(RespondWorkspace.id == workspace_id).first()
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Respond workspace not found")
        existing = self.find_contact_by_phone(workspace_id, phone_raw)
        if existing:
            return existing
        row = RespondContact(
            id=str(uuid.uuid4()),
            respond_workspace_id=workspace_id,
            phone_number=phone_raw.strip(),
            name=(name or "").strip() or None,
        )
        try:
            with self.db.begin_nested():
                self.db.add(row)
                self.db.flush()
        except IntegrityError:
            existing_after = self.find_contact_by_phone(workspace_id, phone_raw)
            if existing_after:
                return existing_after
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contact phone already exists in workspace")
        return row

    def _demote_other_mains(self, lead_id: str, except_id: Optional[str] = None) -> None:
        q = self.db.query(CommercialLeadRespondContact).filter(
            CommercialLeadRespondContact.lead_id == lead_id,
            CommercialLeadRespondContact.contact_role == "main",
        )
        if except_id:
            q = q.filter(CommercialLeadRespondContact.id != except_id)
        for row in q.all():
            row.contact_role = "stakeholder"

    def create_link(self, lead_id: str, data: LeadRespondContactCreate) -> CommercialLeadRespondContact:
        lead = self._get_lead(lead_id)
        contact = self.db.query(RespondContact).filter(RespondContact.id == data.respond_contact_id).first()
        if not contact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Respond contact not found")
        self._workspace_must_match(lead, contact)
        if data.contact_role == "main":
            self._demote_other_mains(lead_id)
        row = CommercialLeadRespondContact(
            id=str(uuid.uuid4()),
            lead_id=lead_id,
            respond_contact_id=contact.id,
            contact_role=data.contact_role,
            sort_order=data.sort_order,
        )
        self.db.add(row)
        try:
            self.db.commit()
            self.db.refresh(row)
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contact already linked to this lead")
        return row

    def link_by_phone(self, lead_id: str, phone: str, name: Optional[str], contact_role: str, sort_order: int) -> CommercialLeadRespondContact:
        lead = self._get_lead(lead_id)
        if not lead.respond_workspace_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Set respond_workspace_id on the lead before linking contacts",
            )
        contact = self.create_local_contact(str(lead.respond_workspace_id), phone, name=name)
        return self.create_link(
            lead_id,
            LeadRespondContactCreate(
                respond_contact_id=contact.id,
                contact_role=contact_role,  # type: ignore[arg-type]
                sort_order=sort_order,
            ),
        )

    def update_link(self, lead_id: str, link_id: str, data: LeadRespondContactUpdate) -> CommercialLeadRespondContact:
        self._get_lead(lead_id)
        row = (
            self.db.query(CommercialLeadRespondContact)
            .filter(CommercialLeadRespondContact.id == link_id, CommercialLeadRespondContact.lead_id == lead_id)
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
        try:
            if data.contact_role == "main":
                # Demote and flush first so one-main unique constraints don't trip on promotion.
                self._demote_other_mains(lead_id, except_id=link_id)
                self.db.flush()
            if data.contact_role is not None:
                row.contact_role = data.contact_role
            if data.sort_order is not None:
                row.sort_order = data.sort_order
            self.db.commit()
            self.db.refresh(row)
            return row
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unable to update contact link due to a role/order conflict",
            )

    def delete_link(self, lead_id: str, link_id: str) -> None:
        self._get_lead(lead_id)
        row = (
            self.db.query(CommercialLeadRespondContact)
            .filter(CommercialLeadRespondContact.id == link_id, CommercialLeadRespondContact.lead_id == lead_id)
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
        self.db.delete(row)
        self.db.commit()

    def sync_primary_from_lead_creation(self, lead: CommercialLead, customer: Customer) -> None:
        """After lead row exists: if workspace + phone, ensure main contact link. Does not commit (caller commits)."""
        if not lead.respond_workspace_id:
            return
        phone = extract_primary_phone_for_lead(dict(lead.qualification or {}), customer)
        if not phone:
            return
        contact = self.find_contact_by_phone(str(lead.respond_workspace_id), phone)
        if not contact:
            display = (customer.customer_name or "").strip() or "Contact"
            contact = self.create_local_contact(str(lead.respond_workspace_id), phone, name=display)
        exists = (
            self.db.query(CommercialLeadRespondContact)
            .filter(
                CommercialLeadRespondContact.lead_id == lead.id,
                CommercialLeadRespondContact.respond_contact_id == contact.id,
            )
            .first()
        )
        if exists:
            self._demote_other_mains(str(lead.id), except_id=str(exists.id))
            exists.contact_role = "main"
            exists.sort_order = 0
            return
        self._demote_other_mains(str(lead.id))
        row = CommercialLeadRespondContact(
            id=str(uuid.uuid4()),
            lead_id=str(lead.id),
            respond_contact_id=contact.id,
            contact_role="main",
            sort_order=0,
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError:
            raise

    def _lead_contact_pair(
        self, lead_id: str, respond_contact_id: str
    ) -> Tuple[CommercialLead, RespondContact]:
        """Return lead + respond_contacts row if that contact is linked to the lead."""
        lead = self._get_lead(lead_id)
        link = (
            self.db.query(CommercialLeadRespondContact)
            .options(joinedload(CommercialLeadRespondContact.respond_contact))
            .filter(
                CommercialLeadRespondContact.lead_id == lead_id,
                CommercialLeadRespondContact.respond_contact_id == respond_contact_id,
            )
            .first()
        )
        if not link or not link.respond_contact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not linked to this lead")
        contact = link.respond_contact
        self._workspace_must_match(lead, contact)
        return lead, contact

    def fetch_respond_conversation_for_contact(
        self,
        lead_id: str,
        respond_contact_id: str,
        *,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> dict:
        _, contact = self._lead_contact_pair(lead_id, respond_contact_id)
        ident = (getattr(contact, "respond_io_id", None) or "").strip()
        ws_row = (
            self.db.query(RespondWorkspace)
            .filter(RespondWorkspace.id == contact.respond_workspace_id)
            .first()
        )
        space_id = getattr(ws_row, "space_id", None) if ws_row else None
        inbox_url: Optional[str] = None
        if space_id and ident:
            inbox_url = f"https://app.respond.io/space/{space_id}/inbox/{ident}"

        if not ident:
            return {"items": [], "pagination": {}, "inbox_url": inbox_url, "unavailable": True}

        from app.services.integration_service import RespondClient

        client = RespondClient.from_workspace(self.db, str(contact.respond_workspace_id))
        result = client.list_messages(ident, limit=limit, cursor=cursor)
        if not isinstance(result, dict):
            result = {"items": [], "pagination": {}}
        result["inbox_url"] = inbox_url
        return result

    def send_respond_reply_for_contact(
        self,
        lead_id: str,
        respond_contact_id: str,
        message: str,
        *,
        respond_user_id: str,
        crm_sender_user_id: Optional[str] = None,
    ) -> dict:
        import logging

        logger = logging.getLogger(__name__)
        _lead, contact = self._lead_contact_pair(lead_id, respond_contact_id)
        ident = (getattr(contact, "respond_io_id", None) or "").strip()
        text = (message or "").strip()
        if not text:
            from app.services.error_handler import handle_validation_error

            raise handle_validation_error("message is required.")
        if not ident:
            from app.services.error_handler import handle_validation_error

            raise handle_validation_error("Contact is not linked to Respond.")

        from app.services.integration_service import RespondClient
        from app.services.crm_chat_outbound_webhook import enqueue_crm_chat_outbound_webhook

        client = RespondClient.from_workspace(self.db, str(contact.respond_workspace_id))
        try:
            response = client.send_message(ident, text)
        except Exception:
            logger.exception("Respond send failed for lead %s contact %s", lead_id, respond_contact_id)
            raise

        ws_row = (
            self.db.query(RespondWorkspace)
            .filter(RespondWorkspace.id == contact.respond_workspace_id)
            .first()
        )
        space_id = getattr(ws_row, "space_id", None) if ws_row else None
        enqueue_crm_chat_outbound_webhook(
            self.db,
            business_table="commercial_leads",
            business_id=str(lead_id),
            contact_respond_io_id=ident,
            message_text=text,
            respond_api_response=response if isinstance(response, dict) else None,
            space_id=str(space_id) if space_id else None,
            crm_sender_user_id=crm_sender_user_id,
            respond_user_id_fallback=respond_user_id,
            assignee_respond_user_id=None,
        )
        return response if isinstance(response, dict) else {}
