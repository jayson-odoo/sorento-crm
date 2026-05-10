"""RQ tasks for Respond.io message sends.

Decouples the external Respond.io API call from the request lifecycle so a 4xx/5xx
from Respond.io does not fail the surrounding business write (status update,
SLA tracking, etc.). Failed sends land in the RQ FailedJobRegistry and an
``integration_logs`` row with ``status='failed'``.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def send_complaint_respond_message(
    complaint_id: str,
    identifier: str,
    display_message: str,
    respond_user_id: str,
    crm_sender_user_id: Optional[str],
    space_id: Optional[str],
) -> dict:
    """Worker-side: send Respond.io message, fire outbound webhook, write log.

    Re-raises on Respond.io failure so RQ records the job as FAILED.
    """
    from app.database import SessionLocal
    from app.services.integration_service import RespondClient, IntegrationLogService
    from app.schemas.integration import IntegrationLogCreate
    from app.services.crm_chat_outbound_webhook import (
        enqueue_crm_chat_outbound_webhook,
        resolve_sla_assignee_respond_user_id,
    )

    db = SessionLocal()
    try:
        log_service = IntegrationLogService(db)
        try:
            client = RespondClient()
            response = client.send_message(identifier, display_message)
            enqueue_crm_chat_outbound_webhook(
                db,
                business_table="complaints",
                business_id=complaint_id,
                contact_respond_io_id=identifier,
                message_text=display_message,
                respond_api_response=response if isinstance(response, dict) else None,
                space_id=space_id,
                crm_sender_user_id=crm_sender_user_id,
                respond_user_id_fallback=respond_user_id,
                assignee_respond_user_id=resolve_sla_assignee_respond_user_id(
                    db, "complaint", complaint_id
                ),
            )
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
            return {"complaint_id": complaint_id, "status": "success"}
        except Exception as e:
            logger.exception(
                "Respond.io send_message failed (queued task) for complaint %s",
                complaint_id,
            )
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
    finally:
        db.close()
