"""RQ tasks for Respond.io message sends.

Decouples the external Respond.io API call from the request lifecycle so a 4xx/5xx
from Respond.io does not fail the surrounding business write (status update,
SLA tracking, etc.). Failed sends land in the RQ FailedJobRegistry and an
``integration_logs`` row with ``status='failed'``.

Sends are 24h-window-aware (``respond_messaging_service.send_text_or_template``):
window open → plain text; closed → the use case's default WhatsApp template.
Outside-window plain sends are pointless — Respond.io reports success but
WhatsApp silently drops them, which is also why the old per-send delivery
polling was removed (plan: docs/plans/PLAN-whatsapp-template-fallback.md).
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _send_and_log(
    *,
    use_case: str,
    business_table: str,
    business_id: str,
    identifier: str,
    message_text: str,
    respond_user_id: str,
    crm_sender_user_id: Optional[str],
    space_id: Optional[str],
    sla_entity_type: str,
    extra_context_vars: Optional[dict] = None,
    emit_outbound_webhook: bool = True,
) -> dict:
    """Shared worker body: window-aware send, outbound webhook, integration log.

    Re-raises on failure so RQ records the job as FAILED.

    ``extra_context_vars`` merges into the resolved template context (e.g. the
    portal OTP code, which has no business-entity row to derive). Set
    ``emit_outbound_webhook=False`` for system messages (OTP) that should be
    logged in the Respond outbox but NOT mirrored into the CRM chat thread.
    """
    from app.database import SessionLocal
    from app.schemas.integration import IntegrationLogCreate
    from app.services.crm_chat_outbound_webhook import (
        enqueue_crm_chat_outbound_webhook,
        resolve_sla_assignee_respond_user_id,
    )
    from app.services.integration_service import IntegrationLogService
    from app.services.respond_messaging_service import (
        build_context_vars,
        send_text_or_template,
    )

    db = SessionLocal()
    try:
        log_service = IntegrationLogService(db)
        request_payload = {"message": {"type": "text", "text": message_text}}
        try:
            context_vars = build_context_vars(
                db,
                use_case=use_case,
                business_id=business_id,
                identifier=identifier,
            )
            if extra_context_vars:
                context_vars.update(extra_context_vars)
            result = send_text_or_template(
                db,
                identifier=identifier,
                text=message_text,
                use_case=use_case,
                context_vars=context_vars,
            )
            request_payload = result["request_payload"]
            response = result["response"]

            if emit_outbound_webhook:
                enqueue_crm_chat_outbound_webhook(
                    db,
                    business_table=business_table,
                    business_id=business_id,
                    contact_respond_io_id=identifier,
                    message_text=message_text,
                    respond_api_response=response if isinstance(response, dict) else None,
                    space_id=space_id,
                    crm_sender_user_id=crm_sender_user_id,
                    respond_user_id_fallback=respond_user_id,
                    assignee_respond_user_id=resolve_sla_assignee_respond_user_id(
                        db, sla_entity_type, business_id
                    ),
                )
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table=business_table,
                    business_id=business_id,
                    external_reference=identifier,
                    direction="outbound",
                    endpoint=f"https://api.respond.io/v2/contact/id:{identifier}/message",
                    http_method="POST",
                    status="success",
                    response_payload=str(response)[:50000] if response else None,
                ),
                request_payload_dict=request_payload,
            )
            return {
                "business_id": business_id,
                "status": "success",
                "sent_as": result["sent_as"],
            }
        except Exception as e:
            logger.exception(
                "Respond.io send failed (queued task) for %s %s",
                business_table,
                business_id,
            )
            # Capture Respond.io's actual HTTP response (status + body) on 4xx/5xx
            # so the failure is diagnosable (e.g. WHY a 403 — WAF block vs window
            # vs channel error) instead of just "403 Forbidden for url ...".
            resp = getattr(e, "response", None)
            resp_code = None
            resp_body = None
            if resp is not None:
                try:
                    resp_code = resp.status_code
                except Exception:
                    resp_code = None
                try:
                    resp_body = (resp.text or "")[:50000]
                except Exception:
                    resp_body = None
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table=business_table,
                    business_id=business_id,
                    external_reference=identifier or "",
                    direction="outbound",
                    endpoint=f"https://api.respond.io/v2/contact/id:{identifier or ''}/message",
                    http_method="POST",
                    status="failed",
                    status_code=resp_code,
                    response_payload=resp_body,
                    error_message=str(e),
                ),
                request_payload_dict=request_payload,
            )
            raise
    finally:
        db.close()


def send_portal_otp_respond_message(
    otp_id: str,
    identifier: str,
    message_text: str,
    otp_code: str,
    space_id: Optional[str],
) -> dict:
    """Worker-side: window-aware Respond.io send for a portal login OTP.

    Logged in the Respond outbox (``integration_logs``, business_table
    ``portal_otp_codes``) like every other send — including a ``status='failed'``
    row when the send can't go out (e.g. local dev with no Respond.io
    connectivity), whose ``request_payload`` carries the code so it can be read
    back for testing. Not mirrored into the CRM chat thread (system message).
    """
    return _send_and_log(
        use_case="portal_otp",
        business_table="portal_otp_codes",
        business_id=otp_id,
        identifier=identifier,
        message_text=message_text,
        respond_user_id="",
        crm_sender_user_id=None,
        space_id=space_id,
        sla_entity_type="",
        extra_context_vars={"otp_code": otp_code},
        emit_outbound_webhook=False,
    )


def send_complaint_respond_message(
    complaint_id: str,
    identifier: str,
    display_message: str,
    respond_user_id: str,
    crm_sender_user_id: Optional[str],
    space_id: Optional[str],
) -> dict:
    """Worker-side: window-aware Respond.io send for a complaint update."""
    return _send_and_log(
        use_case="complaint",
        business_table="complaints",
        business_id=complaint_id,
        identifier=identifier,
        message_text=display_message,
        respond_user_id=respond_user_id,
        crm_sender_user_id=crm_sender_user_id,
        space_id=space_id,
        sla_entity_type="complaint",
    )


def send_stock_inquiry_respond_message(
    inquiry_id: str,
    identifier: str,
    message_text: str,
    respond_user_id: str,
    crm_sender_user_id: Optional[str],
    space_id: Optional[str],
    verify_delivery: bool = True,
) -> dict:
    """Worker-side: window-aware Respond.io send for a stock inquiry update.

    ``verify_delivery`` is accepted for enqueue-signature compatibility but
    ignored — post-send delivery polling was removed in favour of the up-front
    window check.
    """
    return _send_and_log(
        use_case="stock_inquiry",
        business_table="stock_inquiries",
        business_id=inquiry_id,
        identifier=identifier,
        message_text=message_text,
        respond_user_id=respond_user_id,
        crm_sender_user_id=crm_sender_user_id,
        space_id=space_id,
        sla_entity_type="stock_inquiry",
    )
