"""Respond.io outbox: read-only list of outgoing WhatsApp/Respond messages.

A presentation view over ``integration_log`` rows where
``integration_channel='respond_io'`` and ``direction='outbound'`` — the same
rows every send already writes. Parses the stored request_payload into readable
columns (message text / template, status, the linked complaint/inquiry, who
sent it, when) and resolves the contact name/phone from respond_contacts.
"""
import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.access import RespondContact
from app.models.integration import IntegrationLog
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.respond_outbox import RespondOutboxRowResponse
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)

router = APIRouter()


def _render_template_body(body_text: Optional[str], parameters) -> Optional[str]:
    """Substitute WhatsApp {{1}},{{2}}… placeholders in body_text with the
    resolved parameters so the outbox shows the actual filled message, not just
    the template name. parameters is the ordered list of resolved param strings."""
    if not body_text:
        return None
    params = parameters if isinstance(parameters, list) else []

    def _sub(m):
        idx = int(m.group(1)) - 1
        return str(params[idx]) if 0 <= idx < len(params) else m.group(0)

    return re.sub(r"\{\{(\d+)\}\}", _sub, body_text)


def _button_final_url(msg: dict) -> Optional[str]:
    """Assemble the final URL-button link from a stored button payload.

    button = {"text", "url" (with {{1}}), "suffix"}. The contact taps
    ``url`` with {{1}} replaced by ``suffix`` — so a host mismatch shows up as a
    double-host link (https://prod/http://localhost/...). Surface it verbatim.
    """
    btn = msg.get("button")
    if not isinstance(btn, dict):
        return None
    url = str(btn.get("url") or "")
    suffix = str(btn.get("suffix") or "")
    if not url:
        return None
    return re.sub(r"\{\{\d+\}\}", lambda _m: suffix, url)


def _parse_payload(
    raw: Optional[str],
) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Return (sent_as, message_text, template_name, button_url) from a payload."""
    if not raw:
        return "text", None, None, None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return "text", raw[:2000], None, None
    msg = (data or {}).get("message") or {}
    mtype = (msg.get("type") or "text").lower()
    if mtype in ("whatsapp_template", "template"):
        # message_text = the template body with variables filled in (falls back to
        # any literal text, then the raw param list) so the column is never "—".
        rendered = _render_template_body(msg.get("body_text"), msg.get("parameters"))
        if not rendered:
            rendered = msg.get("text")
        if not rendered and isinstance(msg.get("parameters"), list) and msg["parameters"]:
            rendered = " | ".join(str(p) for p in msg["parameters"])
        template_name = msg.get("template_name") or msg.get("template_id")
        return "template", rendered or None, template_name, _button_final_url(msg)
    return "text", msg.get("text") or None, None, None


@router.get("/respond-outbox", response_model=ListResponse[RespondOutboxRowResponse])
async def list_respond_outbox(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    status_filter: Optional[str] = Query(None, alias="status"),
    business_table: Optional[str] = Query(None),
    query: Optional[str] = Query(None, description="Search message text or contact"),
    current_user: dict = Depends(require_permission("system.respond_outbox.view")),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(IntegrationLog).filter(
            IntegrationLog.integration_channel == "respond_io",
            IntegrationLog.direction == "outbound",
        )
        if status_filter:
            q = q.filter(IntegrationLog.status == status_filter.strip())
        if business_table:
            q = q.filter(IntegrationLog.business_table == business_table.strip())
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    IntegrationLog.request_payload.ilike(term),
                    IntegrationLog.external_reference.ilike(term),
                )
            )
        total = q.count()
        offset = (page - 1) * limit
        rows = (
            q.order_by(IntegrationLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Batch-resolve contact name/phone by respond_io_id (external_reference).
        ids = {str(r.external_reference) for r in rows if r.external_reference}
        contacts: dict[str, RespondContact] = {}
        if ids:
            for c in (
                db.query(RespondContact)
                .filter(RespondContact.respond_io_id.in_(list(ids)))
                .all()
            ):
                if c.respond_io_id:
                    contacts[str(c.respond_io_id)] = c

        data = []
        for r in rows:
            sent_as, text, tpl, button_url = _parse_payload(r.request_payload)
            c = contacts.get(str(r.external_reference)) if r.external_reference else None
            data.append(
                RespondOutboxRowResponse(
                    id=str(r.id),
                    created_at=r.created_at,
                    business_table=r.business_table,
                    business_id=str(r.business_id) if r.business_id else None,
                    contact_identifier=r.external_reference,
                    contact_name=getattr(c, "name", None) if c else None,
                    contact_phone=getattr(c, "phone_number", None) if c else None,
                    sent_as=sent_as,
                    message_text=text,
                    template_name=tpl,
                    button_url=button_url,
                    status=r.status,
                    status_code=r.status_code,
                    error_message=r.error_message,
                    response_payload=(r.response_payload or None),
                    created_by=str(r.created_by) if r.created_by else None,
                )
            )
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise handle_internal_error(str(exc))
