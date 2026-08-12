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
from typing import Any, Callable, Dict, List, Optional

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


def precheck_manual_template(
    db: Session,
    *,
    template_id: str,
    params: Dict[str, str],
) -> Dict[str, Any]:
    """DB-only validation for a manual template send, run in-request BEFORE the
    async worker send. Surfaces fixable input errors inline (template not found /
    not approved / missing params) instead of burying them in the outbox.

    Returns ``{template_name, parameters, rendered_body}``. Never calls Respond.io.
    The worker (``send_manual_template_for``) re-validates cheaply before sending.
    """
    from app.models.respond_template import RespondMessageTemplate

    template = (
        db.query(RespondMessageTemplate)
        .filter(RespondMessageTemplate.id == template_id)
        .first()
    )
    if template is None:
        raise handle_not_found("Template", template_id)
    parameters = _validate_and_resolve_params(template, params)
    return {
        "template_name": template.name,
        "parameters": parameters,
        "rendered_body": render_filled_body(template.body_text, parameters),
    }


def precheck_chat_send(
    db: Session,
    *,
    identifier: str,
    respond_contact_id: Optional[str],
    chat_use_case: str,
) -> Dict[str, Any]:
    """DB-only pre-send checks for the async smart chat send, run in-request BEFORE
    enqueuing the worker so ``sent_as`` (text vs template) is known optimistically and
    the ``no_chat_template`` case still surfaces inline. Never calls Respond.io.

    Returns ``{sent_as, window_state}``. Raises ``AppException`` 422
    (``no_chat_template``) when the window is closed and no valid ``*_chat`` default is
    configured (mirrors the guard ``send_chat_message_for`` raises out-of-window).
    """
    from app.services.error_handler import AppException
    from app.services.respond_messaging_service import get_window_state
    from app.services.respond_template_service import get_default_row, serialize_default

    window = get_window_state(db, identifier, respond_contact_id=respond_contact_id)
    window_state = {
        "open": window.get("open"),
        "last_incoming_at": window.get("last_incoming_at"),
        "checked_at": window.get("checked_at"),
    }
    if window.get("open"):
        return {"sent_as": "text", "window_state": window_state}

    serialized = serialize_default(chat_use_case, get_default_row(db, chat_use_case))
    if not serialized.get("is_valid"):
        raise AppException(
            status_code=422,
            message="No chat reply template configured for this form.",
            detail="/integration-management/whatsapp-templates",
            code="no_chat_template",
        )
    return {"sent_as": "template", "window_state": window_state}


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


def _resolve_contact_name(db: Session, *, respond_contact_id: Optional[str], identifier: str) -> str:
    """Contact display name (name -> joined -> phone), falling back to the identifier."""
    from app.models.access import RespondContact

    if respond_contact_id:
        contact = (
            db.query(RespondContact)
            .filter(RespondContact.id == str(respond_contact_id))
            .first()
        )
        if contact is not None:
            return (
                contact.name
                or " ".join(filter(None, [contact.first_name, contact.last_name]))
                or contact.phone_number
            )
    return identifier


def get_chat_template_preview(
    db: Session,
    *,
    identifier: str,
    respond_contact_id: Optional[str] = None,
    chat_use_case: str,
    sender_name: str,
    entity_id: str,
    context_builder: Optional[Callable[[Session, str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Describe the form's ``*_chat`` template so the composer can render it inline
    with the non-message params pre-filled and the ``message`` param left as an
    editable field. Reads the DB only — never calls Respond.io.

    Returns:
      {configured: False, settings_url}  — no valid chat template default; or
      {configured: True, template_name, body_text,
       slots: {"1": {variable, value, editable}, ...}}
    where exactly one slot has ``variable == "message"`` and ``editable == True``
    (value None); the rest carry their resolved value.
    """
    from app.services.respond_template_service import get_default_row, serialize_default

    row = get_default_row(db, chat_use_case)
    serialized = serialize_default(chat_use_case, row)
    if not serialized.get("is_valid") or row is None or getattr(row, "template", None) is None:
        return {
            "configured": False,
            "settings_url": "/integration-management/whatsapp-templates",
        }
    template = row.template
    contact_name = _resolve_contact_name(
        db, respond_contact_id=respond_contact_id, identifier=identifier
    )
    extra_context: Dict[str, Any] = {}
    if context_builder is not None:
        try:
            extra_context = context_builder(db, entity_id) or {}
        except Exception:
            logger.exception("chat-template preview context_builder failed for %s", entity_id)
            extra_context = {}
    # Row-derived vars (entity_number, status, customer, project, …) so a mapped
    # placeholder like {{entity_number}} renders its real value in the inline
    # preview — same resolution the actual send uses. build_context_vars never
    # raises (missing → "-"). Chat-specific vars below override any collision.
    from app.services.respond_messaging_service import build_context_vars

    base_context = build_context_vars(
        db, use_case=chat_use_case, business_id=str(entity_id), identifier=identifier
    )
    context: Dict[str, Any] = {
        **base_context,
        "sender_name": sender_name,
        "contact_name": contact_name,
        **extra_context,
    }
    mapping = {str(k): str(v) for k, v in (row.param_mapping or {}).items()}
    slots: Dict[str, Any] = {}
    for i in range(1, (template.param_count or 0) + 1):
        var = mapping.get(str(i))
        is_message = var == "message"
        slots[str(i)] = {
            "variable": var,
            "value": None if is_message else str(context.get(var, "") or ""),
            "editable": is_message,
        }
    return {
        "configured": True,
        "template_name": template.name,
        "body_text": template.body_text or "",
        "slots": slots,
    }


def send_chat_message_for(
    db: Session,
    *,
    identifier: str,
    respond_contact_id: Optional[str] = None,
    text: str,
    chat_use_case: str,
    business_table: str,
    business_id: str,
    sender_name: str,
    created_by: Optional[str] = None,
    context_builder: Optional[Callable[[Session, str], Dict[str, Any]]] = None,
    precomputed_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pure smart chat send: in-window the RAW typed text (verbatim, formatting
    preserved), out-of-window the form's ``*_chat`` WhatsApp template carrying
    ``sender_name`` + the typed ``message`` (flattened into one param).

    This deliberately does NOT go through ``send_text_or_template`` — that choke
    point renders the template body in-window too (cross-window "uniformity" for
    status-update templates), which is the OPPOSITE of what a free-text chat reply
    wants. Here in-window means plain text, unchanged.

    NEVER mutates the entity. Writes an integration_log outbox on success AND
    failure (best-effort — a logging failure never 500s a delivered send).
    Returns ``{sent_as, rendered_text, flattened, window_state}``.

    Raises ``AppException`` 422 (``no_chat_template``) when the window is closed
    and no valid chat template default is configured, and 502
    (``respond_send_failed``) when the Respond.io send itself fails.
    """
    from app.models.access import RespondContact
    from app.schemas.integration import IntegrationLogCreate
    from app.services.error_handler import AppException
    from app.services.integration_service import IntegrationLogService, RespondClient
    from app.services.respond_messaging_service import (
        get_window_state,
        sanitize_param,
        send_template_for_use_case,
    )
    from app.services.respond_template_service import get_default_row, serialize_default

    # Human display name for the contact (fallbacks: joined name -> phone -> identifier).
    contact_name: Optional[str] = None
    if respond_contact_id:
        contact = (
            db.query(RespondContact)
            .filter(RespondContact.id == str(respond_contact_id))
            .first()
        )
        if contact is not None:
            contact_name = (
                contact.name
                or " ".join(filter(None, [contact.first_name, contact.last_name]))
                or contact.phone_number
            )
    if not contact_name:
        contact_name = identifier

    stripped = (text or "").strip()
    window = get_window_state(db, identifier, respond_contact_id=respond_contact_id)
    log_service = IntegrationLogService(db)
    endpoint = f"https://api.respond.io/v2/contact/id:{identifier or ''}/message"

    def _log(status: str, *, request_payload: Any, response: Any = None, error: str = None) -> None:
        # Best-effort outbox write — never mask a delivered send / never 500 a success.
        try:
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table=business_table,
                    business_id=business_id,
                    external_reference=identifier or "",
                    direction="outbound",
                    endpoint=endpoint,
                    http_method="POST",
                    status=status,
                    response_payload=(str(response)[:50000] if response else None),
                    error_message=error,
                    created_by=created_by,
                ),
                request_payload_dict=request_payload,
            )
        except Exception:
            logger.exception("Failed to write %s chat integration_log", status)

    def _window_state_out() -> Dict[str, Any]:
        return {
            "open": window.get("open"),
            "last_incoming_at": window.get("last_incoming_at"),
            "checked_at": window.get("checked_at"),
        }

    # ---- In-window: deliver the RAW typed text verbatim (UAC-1/UAC-8). ----
    if window.get("open"):
        request_payload = {"message": {"type": "text", "text": text}}
        try:
            response = RespondClient().send_message(identifier, text)
        except Exception as e:
            logger.exception("Chat text send failed for %s %s", business_table, business_id)
            _log("failed", request_payload=request_payload, error=str(e))
            raise AppException(
                status_code=502,
                message="Failed to send the message. Please try again.",
                detail=str(e),
                code="respond_send_failed",
            )
        _log("success", request_payload=request_payload, response=response)
        return {
            "sent_as": "text",
            "rendered_text": stripped,
            "flattened": False,  # raw text sent unaltered — no flatten in-window.
            "window_state": _window_state_out(),
        }

    # ---- Out-of-window: a template is the only deliverable channel. ----
    serialized = serialize_default(chat_use_case, get_default_row(db, chat_use_case))
    if not serialized.get("is_valid"):
        raise AppException(
            status_code=422,
            message="No chat reply template configured for this form.",
            detail="/integration-management/whatsapp-templates",
            code="no_chat_template",
        )

    # Sanitize FOR THE TEMPLATE PARAM ONLY (collapse newlines/tabs/space-runs, strip,
    # truncate). flatten is reported ONLY on the template path (UAC-8).
    sanitized = sanitize_param(text)
    flattened = sanitized != stripped

    # Entity context (portal/view link) is only needed for the template. When the
    # caller already resolved it in-request (the async path pre-builds it so a
    # callable need not cross the RQ boundary), use that verbatim; otherwise build it
    # lazily here, guarded, so a builder error degrades to no-link instead of 500ing
    # the send. (In-window sends never pay this cost.)
    extra_context: Dict[str, Any] = {}
    if precomputed_context is not None:
        extra_context = precomputed_context
    elif context_builder is not None:
        try:
            extra_context = context_builder(db, business_id) or {}
        except Exception:
            logger.exception(
                "Chat context_builder failed for %s %s", business_table, business_id
            )
            extra_context = {}

    # Row-derived vars (entity_number, status, customer, project, …) so a mapped
    # placeholder like {{entity_number}} renders its real value on the send — not
    # just the chat-specific message/sender. build_context_vars never raises
    # (missing → "-"). The chat-specific vars below override any collision.
    from app.services.respond_messaging_service import build_context_vars

    base_context = build_context_vars(
        db, use_case=chat_use_case, business_id=business_id, identifier=identifier
    )
    context_vars: Dict[str, Any] = {
        **base_context,
        "message": sanitized,
        "sender_name": sender_name,
        "contact_name": contact_name,
        **extra_context,
    }

    try:
        result = send_template_for_use_case(
            db,
            identifier=identifier,
            use_case=chat_use_case,
            context_vars=context_vars,
        )
    except Exception as e:
        logger.exception("Chat template send failed for %s %s", business_table, business_id)
        request_payload = getattr(e, "request_payload", None) or {
            "message": {
                "type": "whatsapp_template",
                "use_case": chat_use_case,
                "parameters_context": context_vars,
            }
        }
        _log("failed", request_payload=request_payload, error=str(e))
        raise AppException(
            status_code=502,
            message="Failed to send the message. Please try again.",
            detail=str(e),
            code="respond_send_failed",
        )

    body_text = (result.get("request_payload") or {}).get("message", {}).get("body_text") or ""
    rendered_text = render_filled_body(body_text, result.get("params") or []) or sanitized
    request_payload = {
        "message": {
            "type": "whatsapp_template",
            "template_name": result.get("template_name"),
            "template_id": result.get("template_id"),
            "use_case": chat_use_case,
            "parameters": result.get("params"),
            "button": result.get("button"),
        },
        "window_state": window,
    }
    _log("success", request_payload=request_payload, response=result.get("response"))

    return {
        "sent_as": "template",
        "rendered_text": rendered_text,
        "flattened": flattened,
        "window_state": _window_state_out(),
    }


_ATTACHMENT_KIND_BY_MIME_PREFIX = (
    ("image/", "image"),
    ("video/", "video"),
    ("audio/", "audio"),
)


def respond_attachment_kind(mime: Optional[str]) -> str:
    """Map a MIME type to the Respond.io attachment subtype (R1: image / video /
    audio / file only — no sticker). Unrecognised/binary mimes fall back to
    ``file``, never raise — the composer accepts any file type."""
    lower = (mime or "").lower()
    for prefix, kind in _ATTACHMENT_KIND_BY_MIME_PREFIX:
        if lower.startswith(prefix):
            return kind
    return "file"


def upload_chat_attachment(
    *,
    business_table: str,
    business_id: str,
    content: bytes,
    filename: str,
    mime: Optional[str],
) -> Dict[str, str]:
    """Upload a composer-attached file to CRM storage; return ``{url, kind}``.

    WhatsApp/Meta reject CMYK JPEGs, so the bytes are normalized to RGB first —
    the same rule the attachments upload API applies. The URL is the
    PERMANENT, non-expiring CDN link when the active storage provider serves
    one unsigned (R2); S3/CloudFront has no unsigned route, so a long-lived
    (7 day) signed URL is used instead of the 1h read-time default — a short
    presign would go stale by the time anyone re-opens this ticket's thread to
    see what was actually sent (R2 research item, PLAN-conversation-
    intervention-tickets.md).
    """
    import uuid

    from app.services.image_normalizer import ensure_rgb_image
    from app.services.storage_router import (
        PROVIDER_R2,
        cdn_base_url,
        default_provider,
        get_backend,
        sanitize_storage_filename,
    )

    normalized_content, normalized_filename, normalized_mime = ensure_rgb_image(
        content, filename, mime
    )
    kind = respond_attachment_kind(normalized_mime)
    safe_name = sanitize_storage_filename(normalized_filename) or "file"
    key = f"{business_table}/{business_id}/{uuid.uuid4()}_{safe_name}"
    provider = default_provider()
    backend = get_backend(provider)
    backend.upload_file(
        file_content=normalized_content, file_path=key, content_type=normalized_mime
    )
    url = (
        cdn_base_url(provider, key)
        if provider == PROVIDER_R2
        else backend.get_signed_url(key, expires_in=60 * 60 * 24 * 7)
    )
    return {"url": url, "kind": kind}


def send_chat_attachment_for(
    db: Session,
    *,
    identifier: str,
    respond_contact_id: Optional[str],
    attachment_type: str,
    url: str,
    business_table: str,
    business_id: str,
    created_by: Optional[str] = None,
    window: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send a single Respond.io attachment message (image/video/audio/file — R1).

    In-window only: Respond.io has no attachment-carrying template (R1), so
    unlike ``send_chat_message_for`` there is no closed-window fallback — a
    closed window is a hard, upfront refusal (mirrors the ``no_chat_template``
    guard's "nothing attempted yet, nothing logged" shape), not a send that
    silently gets dropped by WhatsApp. Writes an ``integration_log`` outbox row
    on success AND failure of the actual Respond call; NEVER mutates the
    entity (mirrors ``send_chat_message_for``).

    ``window``: pass an ALREADY-RESOLVED window state (``get_window_state``'s
    return shape) to skip this function's own lookup — the multi-attachment
    caller (``ConversationSLATrackingService.send_ticket_message``) resolves
    the window ONCE for the whole send instead of once per file (each a live
    Respond HTTP call, 15s timeout). Omit to keep the single-call contract
    (this function resolves it itself) for any other caller.
    """
    from app.services.error_handler import AppException
    from app.services.integration_service import RespondClient, log_respond_send
    from app.services.respond_messaging_service import get_window_state

    if window is None:
        window = get_window_state(db, identifier, respond_contact_id=respond_contact_id)
    if not window.get("open"):
        raise AppException(
            status_code=422,
            message="Cannot send an attachment outside the 24h messaging window.",
            detail=(
                "Respond.io has no attachment-carrying template; only text "
                "falls back to the reply template."
            ),
            code="attachment_window_closed",
        )

    request_payload = {
        "message": {"type": "attachment", "attachment": {"type": attachment_type, "url": url}}
    }
    try:
        response = RespondClient.for_identifier(db, identifier).send_attachment(
            identifier, attachment_type, url
        )
    except Exception as e:
        logger.exception(
            "Chat attachment send failed for %s %s", business_table, business_id
        )
        log_respond_send(
            db,
            business_table=business_table,
            business_id=business_id,
            identifier=identifier or "",
            request_payload=request_payload,
            exc=e,
        )
        raise AppException(
            status_code=502,
            message="Failed to send the attachment. Please try again.",
            detail=str(e),
            code="respond_send_failed",
        )
    log_respond_send(
        db,
        business_table=business_table,
        business_id=business_id,
        identifier=identifier or "",
        request_payload=request_payload,
        response=response,
    )
    return {"response": response, "attachment_type": attachment_type, "url": url}
