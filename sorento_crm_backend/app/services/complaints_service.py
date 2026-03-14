"""Complaints service for business logic."""
import logging
import secrets
from sqlalchemy.orm import Session
from sqlalchemy import or_, inspect
from typing import List, Optional
from app.config import settings
from app.models.complaints import Complaint
from app.models.procurement import ViewToken
from app.schemas.complaints import ComplaintCreate, ComplaintUpdate
from app.services.error_handler import handle_not_found
from app.services.entity_attachment_service import EntityAttachmentService


class ComplaintService:
    """Service for complaint operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.entity_attachment_service = EntityAttachmentService(db)

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

    def _serialize_complaint(
        self,
        complaint: Complaint,
        links_override: Optional[list] = None,
    ) -> dict:
        """Serialize complaint with attachments from generic entity_attachment_links table."""
        data = {attr.key: getattr(complaint, attr.key) for attr in inspect(complaint).mapper.column_attrs}
        links = links_override if links_override is not None else self.entity_attachment_service.list_links("complaint", str(complaint.id))
        data["attachments"] = [
            self.entity_attachment_service.serialize_link(
                link,
                entity_key="complaint_id",
                link_type="complaint_attachment",
            )
            for link in links
        ]
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
        q = self.db.query(Complaint)
        
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
        links_map = self.entity_attachment_service.list_links_for_entities(
            "complaint",
            [str(c.id) for c in complaints],
        )
        complaint_data = [
            self._serialize_complaint(complaint, links_override=links_map.get(str(complaint.id), []))
            for complaint in complaints
        ]
        
        return {
            "data": complaint_data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_complaint(self, complaint_id: str):
        """Get a complaint by ID."""
        complaint = (
            self.db.query(Complaint)
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

    def _get_team_user_ids_for_agent_team_assignment(
        self, agent_code: str, team_assignment_code: str
    ) -> List[str]:
        """Return user IDs of the team assigned to the agent with the given team assignment code (e.g. project_sales)."""
        from app.services.user_service import AccessAgentService
        from app.models.access import TeamMember

        agent_svc = AccessAgentService(self.db)
        agent_id = agent_svc.get_agent_id_by_code(agent_code)
        if not agent_id:
            logging.getLogger(__name__).debug("No access agent found for code=%s", agent_code)
            return []
        team_id = agent_svc.get_team_id_by_code(agent_id, team_assignment_code)
        if not team_id:
            logging.getLogger(__name__).debug(
                "No team assignment found for agent %s with code=%s",
                agent_code,
                team_assignment_code,
            )
            return []
        rows = self.db.query(TeamMember.user_id).filter(TeamMember.team_id == team_id).all()
        return [str(r[0]) for r in rows if r and r[0]]

    def _build_complaint_view_url(self, complaint_id: str, base_url_override: Optional[str] = None) -> str:
        """Build shareable (no-auth) frontend link for a complaint using view token."""
        from app.models.user import SystemSetting

        view_token = self.get_or_create_view_token(complaint_id)
        base_url = (base_url_override or "").strip().rstrip("/")
        if not base_url:
            base_url = (getattr(settings, "frontend_base_url", None) or "").strip().rstrip("/")
        if not base_url:
            sys_settings = self.db.query(SystemSetting).first()
            if sys_settings and getattr(sys_settings, "website_url", None):
                base_url = (sys_settings.website_url or "").strip().rstrip("/")
        return f"{base_url}/view/complaint?token={view_token}" if base_url else f"/view/complaint?token={view_token}"

    def notify_team_complaint_external_created(
        self,
        complaint_id: str,
        base_url_override: Optional[str] = None,
        sync_email: bool = False,
    ) -> None:
        """Notify project_sales team under complaint agent when complaint is created externally (in-app + one email to all). Email is enqueued by default so API returns quickly."""
        from datetime import datetime
        from app.models.user import User
        from app.models.notification import Notification, NotificationDelivery
        from app.services.notification_service import NotificationService

        logger = logging.getLogger(__name__)
        user_ids = self._get_team_user_ids_for_agent_team_assignment("complaint", "project_sales")
        if not user_ids:
            logger.warning(
                "No team members found for agent 'complaint' with assignment 'project_sales'. "
                "Create an Access Agent with code 'complaint' and a Team Assignment with code 'project_sales'."
            )
            return
        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        emails = [u.email for u in users if getattr(u, "email", None) and str(u.email).strip()]
        if not emails:
            logger.warning("Team members for complaint/project_sales have no email addresses; skipping email.")
        title = "New Complaint created"
        intro_plain = (
            "Dear Project Sales Team,\n\n"
            "A new complaint has been created via system integration and requires your review."
        )
        intro_html = (
            "Dear Project Sales Team,<br /><br />"
            "A new complaint has been created via system integration and requires your review."
        )
        view_url = self._build_complaint_view_url(complaint_id, base_url_override=base_url_override)
        body_plain = (
            f"{intro_plain}\n\n"
            f"{view_url}\n\n"
            "This is a system generated email. Please do not reply."
        )
        body_html = (
            f"<p>{intro_html}</p>\n"
            f'<p><a href="{view_url}">{view_url}</a></p>\n'
            "<p>This is a system generated email. Please do not reply.</p>"
        )
        notif_svc = NotificationService(self.db)
        first_uid = user_ids[0]
        if emails:
            notification = Notification(
                user_id=first_uid,
                type="complaint_notification",
                title=title,
                body=body_plain,
                data={"recipient_emails": emails, "single_email_to_all": True, "body_html": body_html},
                source_entity_type="complaint",
                source_entity_id=complaint_id,
                event_type="external_created",
            )
            self.db.add(notification)
            self.db.flush()
            self.db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel="in_app",
                    status="sent",
                    sent_at=datetime.utcnow(),
                )
            )
            self.db.add(NotificationDelivery(notification_id=notification.id, channel="email", status="pending"))
            self.db.commit()
            self.db.refresh(notification)
            try:
                if sync_email:
                    from app.tasks import notification_tasks
                    notification_tasks.send_notification_deliveries(str(notification.id))
                else:
                    from app.services.queue_service import enqueue_job
                    from app.tasks import notification_tasks
                    enqueue_job(
                        notification_tasks.send_notification_deliveries,
                        str(notification.id),
                        queue_name="notifications",
                    )
            except Exception as e:
                logger.warning("Failed to send/enqueue notification deliveries: %s", e)
        for uid in user_ids:
            if uid == first_uid and emails:
                continue
            try:
                notif_svc.create_in_app_only(
                    user_id=uid,
                    type="complaint_notification",
                    title=title,
                    body=body_plain,
                    source_entity_type="complaint",
                    source_entity_id=complaint_id,
                    event_type="external_created",
                )
            except Exception as e:
                logger.warning("Failed to create in-app notification for user %s: %s", uid, e)

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
        links = self.entity_attachment_service.list_links("complaint", str(complaint.id))
        link_attachments = [
            self.entity_attachment_service.serialize_link(
                link,
                entity_key="complaint_id",
                link_type="complaint_attachment",
            )
            for link in links
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
        """Create a new complaint with attachments (generic entity_attachment_links)."""
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

        if complaint_data.attachments:
            for att_data in complaint_data.attachments:
                self.entity_attachment_service.create_attachment_and_link(
                    entity_type="complaint",
                    entity_id=str(complaint.id),
                    file_url=att_data.file_url or "",
                    file_name=att_data.file_name or "document",
                    file_size_bytes=(
                        int(att_data.file_size_bytes)
                        if att_data.file_size_bytes is not None
                        else None
                    ),
                    attachment_type_code="complaint_document",
                )

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
        do_number = (getattr(complaint, "delivery_order_number", None) or "").strip()
        technical_response = str(message_text).strip() if message_text else ""
        # If frontend sent the full composed message (with view link), use as-is; else prepend intro
        if technical_response.startswith("There has been an update"):
            display_message = technical_response
        else:
            do_spec = f" for delivery order {do_number}" if do_number else ""
            display_message = f"There has been an update regarding your complaint{do_spec}: {technical_response}"

        if identifier:
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
        else:
            logger.info(
                "Complaint %s update-and-reply: no respond_inbox_url; complaint updated but message not sent to Respond.",
                complaint_id,
            )

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
        self.entity_attachment_service.delete_links_for_entity("complaint", str(complaint.id))
        self.db.delete(complaint)
        self.db.commit()

    def bulk_delete_complaints(self, complaint_ids: list[str]) -> dict:
        """Delete multiple complaints by ID. Returns deleted_count."""
        if not complaint_ids:
            return {"message": "No complaints to delete.", "deleted_count": 0}
        for complaint_id in complaint_ids:
            self.entity_attachment_service.delete_links_for_entity("complaint", str(complaint_id))
        deleted = self.db.query(Complaint).filter(Complaint.id.in_(complaint_ids)).delete(synchronize_session=False)
        self.db.commit()
        return {"message": f"Deleted {deleted} complaint(s).", "deleted_count": deleted}

    def link_attachment_to_complaint(self, complaint_id: str, attachment_id: str, created_by: Optional[str] = None):
        """Link an existing attachment to a complaint (generic entity_attachment_links table)."""
        self.get_complaint(complaint_id)  # ensure complaint exists
        link = self.entity_attachment_service.link_existing_attachment(
            entity_type="complaint",
            entity_id=str(complaint_id),
            attachment_id=str(attachment_id),
            created_by=created_by,
        )
        self.db.commit()
        self.db.refresh(link)
        return link

    def delete_complaint_attachment(self, link_id: str):
        """Delete a complaint-attachment link (from generic entity_attachment_links table)."""
        link = self.entity_attachment_service.delete_link(link_id, entity_type="complaint")
        self.db.commit()
        return link
