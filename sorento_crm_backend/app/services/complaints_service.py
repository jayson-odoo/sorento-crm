"""Complaints service for business logic."""
import secrets
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, inspect
from typing import Optional, Any
from app.config import settings
from app.models.complaints import Complaint, ComplaintAttachment
from app.models.resources import Attachment, AttachmentType
from app.models.procurement import ViewToken
from app.schemas.complaints import ComplaintCreate, ComplaintUpdate
from app.services.error_handler import handle_not_found, handle_conflict
from app.services.s3_service import S3Service


def _attachment_response_from_link(link: ComplaintAttachment, resolve_url: Any) -> dict[str, Any]:
    """Build response-shaped dict from ComplaintAttachment link (with .attachment loaded)."""
    att = link.attachment
    if not att:
        return {
            "id": link.id,
            "attachment_id": link.attachment_id,
            "complaint_id": link.complaint_id,
            "file_name": None,
            "original_filename": None,
            "file_url": None,
            "file_size_bytes": None,
            "uploaded_at": link.created_at,
            "link_type": "complaint_attachment",
        }
    return {
        "id": link.id,
        "attachment_id": link.attachment_id,
        "complaint_id": link.complaint_id,
        "file_name": att.original_filename,
        "original_filename": att.original_filename,
        "file_url": resolve_url(att.file_path),
        "file_size_bytes": att.file_size_bytes,
        "uploaded_at": att.uploaded_at or link.created_at,
        "link_type": "complaint_attachment",
    }


class ComplaintService:
    """Service for complaint operations."""
    
    def __init__(self, db: Session):
        self.db = db

    def _resolve_attachment_url(self, file_path: Optional[str]) -> Optional[str]:
        if not file_path:
            return None
        if file_path.startswith(("http://", "https://")):
            return file_path
        try:
            return S3Service().get_file_url(file_path)
        except Exception:
            return file_path

    def _get_complaint_document_type_id(self) -> Optional[str]:
        """Return attachment_type id for code 'complaint_document'."""
        row = self.db.query(AttachmentType.id).filter(AttachmentType.code == "complaint_document").first()
        return row[0] if row else None

    def _build_respond_inbox_url(self, contact_id: Optional[str], space_id: Optional[str]) -> Optional[str]:
        """Build respond.io inbox URL: {base}/space/{space_id}/inbox/{contact_id}."""
        if not contact_id or not space_id:
            return None
        base = (settings.respond_app_base_url or "").rstrip("/")
        if not base:
            return None
        return f"{base}/space/{space_id.strip()}/inbox/{contact_id.strip()}"

    def _resolve_user_display_name(self, user_id: Optional[str]) -> Optional[str]:
        """Resolve user id (CRM id or respond_user_id) to display name (name or email)."""
        if not user_id or not str(user_id).strip():
            return None
        from app.models.user import User
        user = (
            self.db.query(User)
            .filter(
                or_(User.id == user_id, User.respond_user_id == user_id)
            )
            .first()
        )
        if not user:
            return None
        return user.name or user.email or None

    def _serialize_complaint(self, complaint: Complaint) -> dict:
        """Serialize complaint with attachments from complaint_attachments table only."""
        data = {attr.key: getattr(complaint, attr.key) for attr in inspect(complaint).mapper.column_attrs}
        link_attachments = [
            _attachment_response_from_link(link, self._resolve_attachment_url)
            for link in (complaint.attachments or [])
            if link.attachment is not None
        ]
        data["attachments"] = link_attachments
        if data.get("last_responded_by"):
            data["last_responded_by_name"] = self._resolve_user_display_name(data["last_responded_by"])
        else:
            data["last_responded_by_name"] = None
        if data.get("assigned_to"):
            data["assigned_to_name"] = self._resolve_user_display_name(data["assigned_to"])
        else:
            data["assigned_to_name"] = None
        return data
    
    def list_complaints(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        assigned_to: Optional[str] = None,
        status: Optional[str] = None,
        sort_field: str = "complaint_date",
        sort_dir: str = "asc"
    ):
        """List complaints. assigned_to filters by respond_user_id (assignee). status filters by complaint status."""
        q = self.db.query(Complaint).options(
            joinedload(Complaint.attachments).joinedload(ComplaintAttachment.attachment)
        )
        
        if query:
            q = q.filter(
                or_(
                    Complaint.delivery_order_number.ilike(f"%{query}%"),
                    Complaint.customer_name.ilike(f"%{query}%"),
                    Complaint.product_code.ilike(f"%{query}%"),
                    Complaint.defect_description.ilike(f"%{query}%"),
                    Complaint.project_title.ilike(f"%{query}%")
                )
            )
        if assigned_to is not None and str(assigned_to).strip():
            if str(assigned_to).strip().lower() == "__unassigned__":
                q = q.filter(
                    (Complaint.assigned_to.is_(None)) | (Complaint.assigned_to == "")
                )
            else:
                q = q.filter(Complaint.assigned_to == assigned_to.strip())
        if status and str(status).strip():
            q = q.filter(Complaint.status == status.strip())
        
        sort_map = {
            "complaint_date": Complaint.complaint_date,
            "created_at": Complaint.created_at,
            "delivery_order_number": Complaint.delivery_order_number,
            "customer_name": Complaint.customer_name,
            "product_code": Complaint.product_code,
            "assigned_to": Complaint.assigned_to,
            "status": Complaint.status,
        }
        sort_column = sort_map.get(sort_field, Complaint.complaint_date)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        complaints = q.offset(offset).limit(limit).all()
        complaint_data = [self._serialize_complaint(complaint) for complaint in complaints]
        
        return {
            "data": complaint_data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_complaint(self, complaint_id: str):
        """Get a complaint by ID."""
        complaint = (
            self.db.query(Complaint)
            .options(joinedload(Complaint.attachments).joinedload(ComplaintAttachment.attachment))
            .filter(Complaint.id == complaint_id)
            .first()
        )
        if not complaint:
            raise handle_not_found("Complaint", complaint_id)
        return complaint

    def get_complaint_with_attachments(self, complaint_id: str) -> dict:
        """Get a complaint with attachments from complaint_attachments table."""
        complaint = self.get_complaint(complaint_id)
        return self._serialize_complaint(complaint)

    def get_or_create_view_token(self, complaint_id: str) -> str:
        """Get or create a reusable view token for this complaint. Returns the token string."""
        self.get_complaint(complaint_id)  # ensure exists
        row = (
            self.db.query(ViewToken)
            .filter(
                ViewToken.entity_type == "complaint",
                ViewToken.entity_id == complaint_id,
            )
            .first()
        )
        if row:
            return row.token
        token_value = secrets.token_urlsafe(32)
        view_token = ViewToken(
            entity_type="complaint",
            entity_id=complaint_id,
            token=token_value,
        )
        self.db.add(view_token)
        self.db.flush()
        return token_value

    def get_complaint_summary_by_token(self, token_value: str) -> dict:
        """Return read-only complaint summary for the given view token. No auth required."""
        view_token = (
            self.db.query(ViewToken)
            .filter(ViewToken.token == token_value, ViewToken.entity_type == "complaint")
            .first()
        )
        if not view_token or not view_token.entity_id:
            raise handle_not_found("View link", "(invalid token)")
        complaint = self.get_complaint(str(view_token.entity_id))
        # Build public summary (read-only; no internal IDs like contact_id/space_id if desired)
        link_attachments = [
            _attachment_response_from_link(link, self._resolve_attachment_url)
            for link in (complaint.attachments or [])
            if link.attachment is not None
        ]
        return {
            "entity_type": "complaint",
            "entity_id": complaint.id,
            "delivery_order_number": getattr(complaint, "delivery_order_number", None),
            "complaint_date": getattr(complaint, "complaint_date", None),
            "customer_type": getattr(complaint, "customer_type", None),
            "customer_type_others": getattr(complaint, "customer_type_others", None),
            "within_warranty": getattr(complaint, "within_warranty", None),
            "product_type": getattr(complaint, "product_type", None),
            "defects_discovered": getattr(complaint, "defects_discovered", None),
            "complaint_type": getattr(complaint, "complaint_type", None),
            "defect_description": getattr(complaint, "defect_description", None),
            "product_code": getattr(complaint, "product_code", None),
            "salesperson": getattr(complaint, "salesperson", None),
            "customer_name": getattr(complaint, "customer_name", None),
            "contact_person": getattr(complaint, "contact_person", None),
            "contact_number": getattr(complaint, "contact_number", None),
            "customer_address": getattr(complaint, "customer_address", None),
            "project_title": getattr(complaint, "project_title", None),
            "technical_team_response": getattr(complaint, "technical_team_response", None),
            "status": getattr(complaint, "status", None),
            "last_responded_at": getattr(complaint, "last_responded_at", None),
            "created_at": getattr(complaint, "created_at", None),
            "attachments": link_attachments,
        }

    def create_complaint(self, complaint_data: ComplaintCreate):
        """Create a new complaint with attachments (each becomes Attachment + ComplaintAttachment link)."""
        complaint_dict = complaint_data.model_dump(
            exclude={"attachments", "assigned_to_name", "last_responded_by_name"}
        )
        contact_id = complaint_dict.get("contact_id")
        space_id = complaint_dict.get("space_id")
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            complaint_dict["respond_inbox_url"] = respond_inbox_url
        complaint = Complaint(**complaint_dict)
        self.db.add(complaint)
        self.db.flush()

        type_id = self._get_complaint_document_type_id()
        if complaint_data.attachments:
            for sort_order, att_data in enumerate(complaint_data.attachments):
                file_name = (att_data.file_name or "document")[:255]
                file_url = att_data.file_url or ""
                stored = file_name[:255] if len(file_name) > 255 else file_name
                file_path = (file_url[:500]) if file_url else "/"
                size = int(att_data.file_size_bytes) if att_data.file_size_bytes is not None else None
                resource_att = Attachment(
                    attachment_type_id=type_id,
                    original_filename=file_name,
                    stored_filename=stored,
                    file_path=file_path,
                    file_size_bytes=size,
                )
                self.db.add(resource_att)
                self.db.flush()
                link = ComplaintAttachment(
                    complaint_id=complaint.id,
                    attachment_id=resource_att.id,
                    is_primary=(sort_order == 0),
                    sort_order=sort_order,
                )
                self.db.add(link)

        self.db.commit()
        self.db.refresh(complaint)
        return complaint
    
    def update_complaint(self, complaint_id: str, complaint_data: ComplaintUpdate):
        """Update a complaint."""
        complaint = self.get_complaint(complaint_id)

        update_data = complaint_data.model_dump(exclude_unset=True)
        contact_id = update_data.get("contact_id") if "contact_id" in update_data else complaint.contact_id
        space_id = update_data.get("space_id") if "space_id" in update_data else complaint.space_id
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            update_data["respond_inbox_url"] = respond_inbox_url
        elif contact_id is None and space_id is None:
            update_data["respond_inbox_url"] = None

        if "technical_team_response" in update_data and getattr(complaint, "status", None) != "responded":
            update_data["status"] = "updated"

        for key, value in update_data.items():
            setattr(complaint, key, value)

        self.db.commit()
        self.db.refresh(complaint)
        return complaint

    def _identifier_from_respond_inbox_url(self, respond_inbox_url: Optional[str]) -> Optional[str]:
        """Extract contact identifier from respond_inbox_url (last path segment)."""
        if not respond_inbox_url or not respond_inbox_url.strip():
            return None
        parts = [p for p in respond_inbox_url.rstrip("/").split("/") if p]
        return parts[-1] if parts else None

    def update_complaint_and_reply(
        self,
        complaint_id: str,
        complaint_data: "ComplaintUpdate",
        respond_user_id: str,
        request_url: str = "",
    ):
        """
        Update complaint, send technical team response to Respond.io, update SLA tracking to responded, set status=responded.
        All integration calls are logged via IntegrationLogService.
        """
        import logging
        from datetime import datetime, timezone
        from app.services.integration_service import RespondClient, IntegrationLogService
        from app.schemas.integration import IntegrationLogCreate
        from app.services.sla_service import ConversationSLATrackingService
        from app.schemas.sla import ConversationSLATrackingUpdate

        logger = logging.getLogger(__name__)
        log_service = IntegrationLogService(self.db)

        complaint = self.get_complaint(complaint_id)
        update_data = complaint_data.model_dump(exclude_unset=True)
        contact_id = update_data.get("contact_id") if "contact_id" in update_data else complaint.contact_id
        space_id = update_data.get("space_id") if "space_id" in update_data else complaint.space_id
        respond_inbox_url = self._build_respond_inbox_url(contact_id, space_id)
        if respond_inbox_url is not None:
            update_data["respond_inbox_url"] = respond_inbox_url
        elif contact_id is None and space_id is None:
            update_data["respond_inbox_url"] = None

        message_text = update_data.get("technical_team_response") or getattr(complaint, "technical_team_response", None)
        if not (message_text and str(message_text).strip()):
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error("technical_team_response is required to reply.")

        for key, value in update_data.items():
            setattr(complaint, key, value)
        self.db.flush()

        identifier = self._identifier_from_respond_inbox_url(getattr(complaint, "respond_inbox_url", None))
        if not identifier:
            from app.services.error_handler import handle_validation_error
            raise handle_validation_error("respond_inbox_url is missing or invalid; cannot send message.")

        do_number = (getattr(complaint, "delivery_order_number", None) or "").strip()
        do_spec = f" for delivery order {do_number}" if do_number else ""
        technical_response = str(message_text).strip()
        display_message = f"There has been an update regarding your complaint{do_spec}: {technical_response}"

        try:
            client = RespondClient()
            response = client.send_message(identifier, display_message)
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="complaints",
                    business_id=complaint_id,
                    external_reference=identifier,
                    direction="outbound",
                    endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message",
                    http_method="POST",
                    status="success",
                    response_payload=str(response)[:50000] if response else None,
                ),
                request_payload_dict={"message": {"type": "text", "text": display_message}},
            )
        except Exception as e:
            logger.exception("Respond.io send_message failed for complaint %s", complaint_id)
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="complaints",
                    business_id=complaint_id,
                    external_reference=identifier or "",
                    direction="outbound",
                    endpoint=f"https://api.respond.io/v2/contact/id:{identifier or ''}/message",
                    http_method="POST",
                    status="failed",
                    error_message=str(e),
                ),
                request_payload_dict={"message": {"type": "text", "text": display_message}},
            )
            raise

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        sla_service = ConversationSLATrackingService(self.db)
        tracking = sla_service.get_tracking_by_source_entity("complaint", complaint_id)
        if tracking:
            try:
                sla_service.update_tracking(
                    str(tracking.id),
                    ConversationSLATrackingUpdate(
                        is_responded=True,
                        responded_at=now_utc,
                        responded_by=respond_user_id,
                    ),
                )
                log_service.create_integration_log(
                    IntegrationLogCreate(
                        integration_channel="sla_management",
                        business_table="conversation_sla_tracking",
                        business_id=str(tracking.id),
                        external_reference=complaint_id,
                        direction="inbound",
                        endpoint=request_url or "/api/v1/complaints-management/complaints/update-and-reply",
                        http_method="POST",
                        status="success",
                    ),
                    request_payload_dict={"is_responded": True, "responded_by": respond_user_id},
                )
            except Exception as sla_err:
                logger.warning("SLA tracking update failed for complaint %s: %s", complaint_id, sla_err)
                log_service.create_integration_log(
                    IntegrationLogCreate(
                        integration_channel="sla_management",
                        business_table="conversation_sla_tracking",
                        business_id=str(tracking.id),
                        external_reference=complaint_id,
                        direction="inbound",
                        endpoint=request_url or "/api/v1/complaints-management/complaints/update-and-reply",
                        http_method="POST",
                        status="failed",
                        error_message=str(sla_err),
                    ),
                    request_payload_dict={"is_responded": True, "responded_by": respond_user_id},
                )

        complaint.status = "responded"
        complaint.last_responded_by = respond_user_id
        complaint.last_responded_at = now_utc
        self.db.commit()
        self.db.refresh(complaint)
        return complaint

    def sync_assignee_from_respond(self, complaint_id: str) -> dict:
        """
        Fetch contact from Respond.io by complaint's contact_id, get assignee.id,
        match to CRM user by respond_user_id, and update complaint.assigned_to.
        """
        import json
        import logging
        from app.models.user import User
        from app.services.integration_service import RespondClient, IntegrationLogService
        from app.schemas.integration import IntegrationLogCreate
        from app.services.error_handler import handle_validation_error

        logger = logging.getLogger(__name__)
        complaint = self.get_complaint(complaint_id)
        contact_id = (complaint.contact_id or "").strip()
        if not contact_id:
            raise handle_validation_error(
                "No contact_id for this complaint; cannot sync assignee from Respond.io. Set Contact ID (from respond.io) on the complaint."
            )

        log_service = IntegrationLogService(self.db)
        endpoint_path = f"/v2/contact/id:{contact_id}"

        try:
            client = RespondClient()
            payload = client.get_contact_by_identifier(contact_id)
        except ValueError as e:
            logger.warning("Respond.io not configured or error: %s", e)
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="complaints",
                    business_id=complaint_id,
                    direction="outbound",
                    endpoint=endpoint_path,
                    http_method="GET",
                    status="failed",
                    error_message=str(e),
                ),
                request_payload_dict={"action": "sync_assignee", "contact_id": contact_id},
            )
            raise handle_validation_error(f"Respond.io API is not configured or error: {e!s}")
        except Exception as e:
            logger.exception("Respond.io get_contact failed for complaint %s", complaint_id)
            resp_payload = None
            if hasattr(e, "response") and getattr(e.response, "text", None):
                resp_payload = e.response.text[:2000] if len(e.response.text) > 2000 else e.response.text
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="complaints",
                    business_id=complaint_id,
                    direction="outbound",
                    endpoint=endpoint_path,
                    http_method="GET",
                    status="failed",
                    error_message=str(e),
                    response_payload=resp_payload,
                ),
                request_payload_dict={"action": "sync_assignee", "contact_id": contact_id},
            )
            raise

        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table="complaints",
                business_id=complaint_id,
                direction="outbound",
                endpoint=endpoint_path,
                http_method="GET",
                status="success",
                response_payload=json.dumps(payload, indent=2),
            ),
            request_payload_dict={"action": "sync_assignee", "contact_id": contact_id},
        )

        assignee = payload.get("assignee")
        if not assignee or assignee.get("id") is None:
            complaint.assigned_to = None
            self.db.commit()
            return {"updated": True, "message": "Sync successful. No assignee in Respond.io; Assigned To cleared."}

        assignee_respond_id = str(assignee.get("id"))
        user = self.db.query(User).filter(User.respond_user_id == assignee_respond_id).first()
        if not user:
            return {
                "updated": False,
                "message": f"Sync successful. No user in CRM with respond_user_id '{assignee_respond_id}'; Assigned To unchanged. Link Respond.io user ID in User Management to sync.",
            }

        if complaint.assigned_to == assignee_respond_id:
            return {"updated": False, "message": "Sync successful. Assignee already in sync."}

        complaint.assigned_to = assignee_respond_id
        self.db.commit()
        self.db.refresh(complaint)
        return {
            "updated": True,
            "message": "Assignee synced from Respond.io.",
            "assigned_to": user.name or user.email or assignee_respond_id,
            "assigned_to_id": str(user.id),
        }

    def delete_complaint(self, complaint_id: str) -> None:
        """Delete a complaint and its related attachments."""
        complaint = self.get_complaint(complaint_id)
        self.db.delete(complaint)
        self.db.commit()

    def bulk_delete_complaints(self, complaint_ids: list[str]) -> dict:
        """Delete multiple complaints by ID. Returns deleted_count."""
        if not complaint_ids:
            return {"message": "No complaints to delete.", "deleted_count": 0}
        deleted = self.db.query(Complaint).filter(Complaint.id.in_(complaint_ids)).delete(synchronize_session=False)
        self.db.commit()
        return {"message": f"Deleted {deleted} complaint(s).", "deleted_count": deleted}

    def link_attachment_to_complaint(self, complaint_id: str, attachment_id: str, created_by: Optional[str] = None):
        """Link an existing attachment to a complaint (complaint_attachments table)."""
        self.get_complaint(complaint_id)  # ensure complaint exists
        attachment = (
            self.db.query(Attachment)
            .filter(Attachment.id == attachment_id)
            .first()
        )
        if not attachment:
            raise handle_not_found("Attachment", attachment_id)

        existing = (
            self.db.query(ComplaintAttachment)
            .filter(
                ComplaintAttachment.complaint_id == complaint_id,
                ComplaintAttachment.attachment_id == attachment_id,
            )
            .first()
        )
        if existing:
            raise handle_conflict("Attachment is already linked to this complaint.")

        count = self.db.query(ComplaintAttachment).filter(ComplaintAttachment.complaint_id == complaint_id).count()
        link = ComplaintAttachment(
            complaint_id=complaint_id,
            attachment_id=attachment_id,
            is_primary=(count == 0),
            sort_order=count,
            created_by=created_by,
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    def delete_complaint_attachment(self, link_id: str):
        """Delete a complaint-attachment link (from complaint_attachments table)."""
        link = (
            self.db.query(ComplaintAttachment)
            .filter(ComplaintAttachment.id == link_id)
            .first()
        )
        if not link:
            raise handle_not_found("Complaint attachment link", link_id)
        self.db.delete(link)
        self.db.commit()
        return link
