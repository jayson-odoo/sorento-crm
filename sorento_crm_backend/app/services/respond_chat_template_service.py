"""Shared manual WhatsApp-template send + window-state for chat panels.

The complaint / stock-inquiry / purchase-request chat panels each fetch their
conversation from an entity-specific ``/conversation`` route (not the generic
activities adapter, which only covers tickets). This module is the single
implementation those routes — and ``activities_service`` — delegate to, so the
manual template flow can't drift across the four surfaces.

Validation raises ``AppException`` (handled globally → JSON), per backend
conventions. Plan: docs/plans/PLAN-whatsapp-template-fallback.md
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.error_handler import handle_not_found, handle_validation_error

logger = logging.getLogger(__name__)


def get_window_state_for(
    db: Session,
    *,
    identifier: str,
    respond_contact_id: Optional[str] = None,
) -> Dict[str, Any]:
    from app.services.respond_messaging_service import get_window_state

    return get_window_state(db, identifier, respond_contact_id=respond_contact_id)


def _validate_and_resolve_params(template, params: Dict[str, str]) -> List[str]:
    from app.services.respond_messaging_service import sanitize_param

    if template.status != "approved":
        raise handle_validation_error("Only approved templates can be sent.")
    missing = [
        str(i)
        for i in range(1, template.param_count + 1)
        if not str((params or {}).get(str(i)) or "").strip()
    ]
    if missing:
        raise handle_validation_error(
            f"Missing template parameters: {', '.join(missing)}"
        )
    return [
        sanitize_param((params or {}).get(str(i)))
        for i in range(1, template.param_count + 1)
    ]


def render_filled_body(body_text: str, parameters: List[str]) -> str:
    rendered = body_text
    for i, value in enumerate(parameters, start=1):
        rendered = rendered.replace(f"{{{{{i}}}}}", value)
    return rendered


def send_manual_template_for(
    db: Session,
    *,
    identifier: str,
    template_id: str,
    params: Dict[str, str],
    business_table: str,
    business_id: str,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Send an approved template by id with explicit positional params.

    Writes a best-effort integration log; returns the Respond response, the
    filled body (for an activity/event row) and the sanitized parameters.
    Raises on Respond.io failure after logging.
    """
    from app.models.respond_template import RespondMessageTemplate
    from app.schemas.integration import IntegrationLogCreate
    from app.services.integration_service import IntegrationLogService, RespondClient

    template = (
        db.query(RespondMessageTemplate)
        .filter(RespondMessageTemplate.id == template_id)
        .first()
    )
    if template is None:
        raise handle_not_found("Template", template_id)
    parameters = _validate_and_resolve_params(template, params)

    log_service = IntegrationLogService(db)
    request_payload = {
        "message": {
            "type": "whatsapp_template",
            "template_name": template.name,
            "template_id": str(template.id),
            "parameters": parameters,
        }
    }
    try:
        response = RespondClient().send_template_message(
            identifier,
            channel_id=template.channel.respond_channel_id,
            template_name=template.name,
            language_code=template.language_code,
            body_text=template.body_text,
            parameters=parameters,
        )
    except Exception as e:
        logger.exception(
            "Respond.io template send failed for %s %s", business_table, business_id
        )
        try:
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
                    error_message=str(e),
                    created_by=created_by,
                ),
                request_payload_dict=request_payload,
            )
        except Exception:
            logger.exception("Failed to write failed-template integration_log")
        raise

    try:
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
                created_by=created_by,
            ),
            request_payload_dict=request_payload,
        )
    except Exception:
        logger.exception("Failed to write success-template integration_log")

    return {
        "response": response,
        "template_name": template.name,
        "parameters": parameters,
        "rendered_body": render_filled_body(template.body_text, parameters),
    }
