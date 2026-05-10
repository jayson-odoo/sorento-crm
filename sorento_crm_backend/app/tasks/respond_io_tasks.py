"""RQ tasks for Respond.io message sends.

Decouples the external Respond.io API call from the request lifecycle so a 4xx/5xx
from Respond.io does not fail the surrounding business write (status update,
SLA tracking, etc.). Failed sends land in the RQ FailedJobRegistry and an
``integration_logs`` row with ``status='failed'``.
"""
import logging
import time
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


def send_stock_inquiry_respond_message(
    inquiry_id: str,
    identifier: str,
    message_text: str,
    respond_user_id: str,
    crm_sender_user_id: Optional[str],
    space_id: Optional[str],
    verify_delivery: bool = True,
) -> dict:
    """Worker-side: send Respond.io message for a stock inquiry, verify delivery, fire webhook + log.

    When ``verify_delivery`` is True, polls the Respond.io message status endpoint
    up to 3 times to detect ``failed`` delivery and writes a ``status='failed'``
    integration_log with the carrier message. Re-raises on send/verify exceptions
    so RQ marks the job as FAILED.
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
            response = client.send_message(identifier, message_text)

            delivery_failed_message: Optional[str] = None
            message_id = response.get("messageId") if isinstance(response, dict) else None
            if verify_delivery and message_id is not None:
                for attempt in range(3):
                    try:
                        sent_message = client.get_message(identifier, message_id)
                        log_service.create_integration_log(
                            IntegrationLogCreate(
                                integration_channel="respond_io",
                                business_table="stock_inquiries",
                                business_id=inquiry_id,
                                external_reference=f"{identifier}:{message_id}",
                                direction="outbound",
                                endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message/{message_id}",
                                http_method="GET",
                                status="success",
                                response_payload=str(sent_message)[:50000] if sent_message else None,
                            ),
                        )
                        statuses = sent_message.get("status") if isinstance(sent_message, dict) else None
                        if isinstance(statuses, list):
                            failed = next(
                                (
                                    s for s in statuses
                                    if isinstance(s, dict) and str(s.get("value", "")).lower() == "failed"
                                ),
                                None,
                            )
                            if failed:
                                delivery_failed_message = (failed.get("message") or "").strip()
                            break
                    except Exception as status_check_err:
                        log_service.create_integration_log(
                            IntegrationLogCreate(
                                integration_channel="respond_io",
                                business_table="stock_inquiries",
                                business_id=inquiry_id,
                                external_reference=f"{identifier}:{message_id}",
                                direction="outbound",
                                endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message/{message_id}",
                                http_method="GET",
                                status="failed",
                                error_message=str(status_check_err),
                            ),
                        )
                        if attempt == 2:
                            logger.warning(
                                "Unable to verify Respond message status for stock_inquiry %s (message_id=%s): %s",
                                inquiry_id, message_id, status_check_err,
                            )
                    if attempt < 2:
                        time.sleep(0.6)

            enqueue_crm_chat_outbound_webhook(
                db,
                business_table="stock_inquiries",
                business_id=inquiry_id,
                contact_respond_io_id=identifier,
                message_text=message_text,
                respond_api_response=response if isinstance(response, dict) else None,
                space_id=space_id,
                crm_sender_user_id=crm_sender_user_id,
                respond_user_id_fallback=respond_user_id,
                assignee_respond_user_id=resolve_sla_assignee_respond_user_id(
                    db, "stock_inquiry", inquiry_id
                ),
            )

            send_status = "failed" if delivery_failed_message else "success"
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="stock_inquiries",
                    business_id=inquiry_id,
                    external_reference=identifier,
                    direction="outbound",
                    endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message",
                    http_method="POST",
                    status=send_status,
                    error_message=delivery_failed_message,
                    response_payload=str(response)[:50000] if response else None,
                ),
                request_payload_dict={"message": {"type": "text", "text": message_text}},
            )
            if delivery_failed_message:
                raise RuntimeError(f"Respond.io delivery failed: {delivery_failed_message}")
            return {"inquiry_id": inquiry_id, "status": "success"}
        except Exception as e:
            logger.exception(
                "Respond.io send_message failed (queued task) for stock_inquiry %s",
                inquiry_id,
            )
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="stock_inquiries",
                    business_id=inquiry_id,
                    external_reference=identifier or "",
                    direction="outbound",
                    endpoint=f"https://api.respond.io/v2/contact/id:{identifier or ''}/message",
                    http_method="POST",
                    status="failed",
                    error_message=str(e),
                ),
                request_payload_dict={"message": {"type": "text", "text": message_text}},
            )
            raise
    finally:
        db.close()
