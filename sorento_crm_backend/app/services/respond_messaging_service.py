"""24h-window-aware Respond.io sending: plain text OR default WhatsApp template.

WhatsApp only delivers free-form messages inside the 24-hour customer service
window (contact's last *incoming* message < 24h ago). Respond.io still returns
success for sends outside the window — they are silently dropped. So every
auto-send branches up front:

- window open  → plain text (existing behaviour)
- window closed → the use case's default approved template
  (``respond_template_defaults``), params resolved from context vars.

Window source of truth is the Respond.io message list (chat_history misses
messages when ``is_human_intervened``); on API error we degrade to
chat_history; with no data at all the window is treated as closed (template is
the safe branch). A 23h margin avoids boundary drops.

Plan: docs/plans/PLAN-whatsapp-template-fallback.md
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

WINDOW_HOURS = 23
PARAM_MAX_LEN = 900

_URL_RE = re.compile(r"https?://\S+")
_WS_RUN_RE = re.compile(r"[ \t]{2,}")


class TemplateSendSkipped(Exception):
    """Window closed but no valid default template for the use case.

    Raised instead of silently dropping a plain text send into a closed
    window; callers log it as a failed integration log.
    """

    def __init__(self, use_case: str, reason: str):
        self.use_case = use_case
        self.reason = reason
        super().__init__(
            f"24h window closed and template send skipped for use case "
            f"'{use_case}': {reason}"
        )


def _attach_send_context(exc: Exception, request_payload: dict, window: dict, sent_as: str) -> None:
    """Stamp the attempted payload / window / branch onto a send exception so the
    caller's outbox log reflects what was actually attempted (text vs template),
    instead of a hardcoded default. Best-effort — never raises."""
    try:
        exc.request_payload = request_payload  # type: ignore[attr-defined]
        exc.window_state = window  # type: ignore[attr-defined]
        exc.sent_as = sent_as  # type: ignore[attr-defined]
    except Exception:
        pass


def sanitize_param(
    value: Optional[str], *, max_len: int = PARAM_MAX_LEN, flatten: bool = True
) -> str:
    """Coerce a value into a template parameter, length-bounded.

    ``flatten=True`` (WhatsApp template params): newlines/tabs/4+ spaces are
    rejected by WhatsApp, so newlines become ``" | "`` and runs collapse.
    ``flatten=False`` (in-window free text): newlines are legal and nicer, so
    keep them — only normalise tabs and bound length. See PLAN-whatsapp-inwindow-
    template-uniformity.md (richer-multiline decision).
    """
    text = str(value or "").strip()
    if not text:
        return "-"
    if flatten:
        text = re.sub(r"\s*\n+\s*", " | ", text)
        text = text.replace("\t", " ")
        text = _WS_RUN_RE.sub(" ", text)
    else:
        text = text.replace("\t", " ")
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def extract_first_url(text: Optional[str]) -> Optional[str]:
    m = _URL_RE.search(text or "")
    if not m:
        return None
    # `\S+` greedily includes trailing sentence punctuation (e.g. a URL written
    # `…/{uuid}: status`); strip it so the extracted link is the bare URL. Hit by
    # portal deep links whose path ends in a UUID followed by a colon.
    return m.group(0).rstrip(").,:;!?'\"")


def _ms_to_utc(ts: Any) -> Optional[datetime]:
    try:
        ms = int(ts)
    except (TypeError, ValueError):
        return None
    if ms > 10**12:  # milliseconds
        return datetime.utcfromtimestamp(ms / 1000.0)
    return datetime.utcfromtimestamp(ms)


def _message_timestamp(item: dict) -> Optional[datetime]:
    """Best creation timestamp (UTC naive) for a Respond.io message item.

    Outgoing messages carry delivery ``status`` entries (epoch ms); incoming
    messages have ``status: []`` and instead encode their time in ``messageId``,
    which Respond emits as epoch MICROSECONDS. The earlier code only read
    ``status[0].timestamp`` and so silently dropped every inbound message —
    making the 24h window look permanently closed even right after a reply.
    """
    statuses = item.get("status") or []
    if isinstance(statuses, list) and statuses:
        dts = [
            _ms_to_utc(s.get("timestamp"))
            for s in statuses
            if isinstance(s, dict) and s.get("timestamp") is not None
        ]
        dts = [d for d in dts if d is not None]
        if dts:
            return min(dts)  # 'pending'/creation time, not 'delivered'
    mid = item.get("messageId")
    if mid is not None:
        try:
            # microseconds -> milliseconds for _ms_to_utc's >1e12 branch.
            return _ms_to_utc(int(mid) // 1000)
        except (TypeError, ValueError):
            return None
    return None


def _last_incoming_from_respond(identifier: str) -> Optional[datetime]:
    """Latest incoming-message timestamp from the Respond.io API (UTC naive).

    Scans one page (newest 50). No incoming message in the page means the
    last reply is old → closed either way.
    """
    from app.services.integration_service import RespondClient

    raw = RespondClient().list_messages(identifier, limit=50)
    items = (raw or {}).get("items") or []
    latest: Optional[datetime] = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if (item.get("traffic") or "").lower() not in ("incoming", "inbound"):
            continue
        dt = _message_timestamp(item)
        if dt is not None and (latest is None or dt > latest):
            latest = dt
    return latest


def _last_incoming_from_chat_history(
    db: Session, respond_contact_id: Optional[str]
) -> Optional[datetime]:
    if not respond_contact_id:
        return None
    from sqlalchemy import func as sa_func

    from app.models.chat_history import ChatHistory

    return (
        db.query(sa_func.max(ChatHistory.sent_at))
        .filter(
            ChatHistory.contact_id == str(respond_contact_id),
            ChatHistory.type == "incoming",
        )
        .scalar()
    )


def get_window_state(
    db: Session,
    identifier: str,
    *,
    respond_contact_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Whether the contact's 24h WhatsApp window is open (23h margin).

    ``identifier`` is the Respond.io send identifier (same value the existing
    send paths use). ``respond_contact_id`` (internal ``respond_contacts.id``)
    enables the chat_history fallback when the Respond API errors.
    """
    now = datetime.utcnow()
    last_incoming: Optional[datetime] = None
    source = "respond_api"
    try:
        last_incoming = _last_incoming_from_respond(identifier)
    except Exception as e:
        logger.warning(
            "Window check: Respond.io list_messages failed for %s (%s); "
            "falling back to chat_history",
            identifier,
            e,
        )
        source = "chat_history"
        try:
            last_incoming = _last_incoming_from_chat_history(db, respond_contact_id)
        except Exception:
            logger.exception("Window check: chat_history fallback failed")
            last_incoming = None
            source = "none"
        if last_incoming is None and source == "chat_history":
            source = "none"

    is_open = bool(last_incoming and last_incoming >= now - timedelta(hours=WINDOW_HOURS))
    return {
        "open": is_open,
        "last_incoming_at": last_incoming.isoformat() if last_incoming else None,
        "checked_at": now.isoformat(),
        "source": source,
    }


def resolve_template_params(
    *,
    param_mapping: Dict[str, str],
    param_count: int,
    context_vars: Dict[str, Any],
    flatten: bool = True,
) -> List[str]:
    """Positional params ["1".."n"] resolved via mapping + sanitized.

    ``flatten=False`` keeps newlines in values (in-window free-text render).
    """
    params: List[str] = []
    for i in range(1, param_count + 1):
        var = param_mapping.get(str(i)) or ""
        params.append(sanitize_param(context_vars.get(var), flatten=flatten))
    return params


def send_template_for_use_case(
    db: Session,
    *,
    identifier: str,
    use_case: str,
    context_vars: Dict[str, Any],
) -> Dict[str, Any]:
    """Send the use case's default template. Raises TemplateSendSkipped when
    no valid default is configured."""
    from app.services.integration_service import RespondClient
    from app.services.respond_template_service import (
        get_default_row,
        serialize_default,
    )

    row = get_default_row(db, use_case)
    serialized = serialize_default(use_case, row)
    if not serialized["is_valid"] or row is None or row.template is None:
        if serialized["template_removed"]:
            reason = "configured template was removed on sync"
        elif serialized["template_id"] is None:
            reason = "no default template configured"
        elif serialized["template_status"] != "approved":
            reason = f"template is not approved (status: {serialized['template_status']})"
        else:
            reason = "param mapping does not cover every template parameter"
        raise TemplateSendSkipped(use_case, reason)

    template = row.template
    params = resolve_template_params(
        param_mapping=dict(row.param_mapping or {}),
        param_count=template.param_count,
        context_vars=context_vars,
    )
    # Full resolved template payload — identical shape whether the send below
    # succeeds OR fails, so the Respond outbox renders the template name + filled
    # params (not "—") in every case. body_text lets the UI render the message
    # with variables substituted.
    request_payload = {
        "message": {
            "type": "whatsapp_template",
            "template_name": template.name,
            "template_id": str(template.id),
            "use_case": use_case,
            "language_code": template.language_code,
            "body_text": template.body_text,
            "parameters": params,
        }
    }
    # Single-workspace today: RespondClient() resolves the default workspace key.
    # Switch to RespondClient.for_identifier(db, identifier) when multi-workspace
    # routing per contact is needed.
    try:
        response = RespondClient().send_template_message(
            identifier,
            channel_id=template.channel.respond_channel_id,
            template_name=template.name,
            language_code=template.language_code,
            body_text=template.body_text,
            parameters=params,
        )
    except Exception as e:
        _attach_send_context(e, request_payload, {"open": False}, "template")
        raise
    return {
        "response": response,
        "template_name": template.name,
        "template_id": str(template.id),
        "params": params,
        "request_payload": request_payload,
    }


def render_in_window_text(
    db: Session,
    *,
    use_case: str,
    context_vars: Dict[str, Any],
    fallback_text: str,
) -> str:
    """Render the use-case default template body for an in-window (free-text)
    send, so the message reads the same as the out-of-window template.

    Returns ``fallback_text`` unchanged when the use case has no valid configured
    default — uniformity rolls out per use-case, never breaks an unconfigured one.
    Newlines in values are preserved (``flatten=False``). Best-effort: any
    resolution error degrades to the raw text.
    """
    try:
        from app.services.respond_template_service import (
            get_default_row,
            serialize_default,
        )
        from app.services.respond_chat_template_service import render_filled_body

        row = get_default_row(db, use_case)
        serialized = serialize_default(use_case, row)
        if not serialized["is_valid"] or row is None or row.template is None:
            return fallback_text
        template = row.template
        params = resolve_template_params(
            param_mapping=dict(row.param_mapping or {}),
            param_count=template.param_count,
            context_vars=context_vars,
            flatten=False,
        )
        return render_filled_body(template.body_text, params)
    except Exception:
        logger.exception(
            "render_in_window_text: falling back to raw text for use case '%s'",
            use_case,
        )
        return fallback_text


def send_text_or_template(
    db: Session,
    *,
    identifier: str,
    text: str,
    use_case: str,
    context_vars: Optional[Dict[str, Any]] = None,
    respond_contact_id: Optional[str] = None,
) -> Dict[str, Any]:
    """The choke point for every CRM auto-send to a Respond.io contact.

    Returns {sent_as, response, window_state, template_name?, request_payload}
    — callers attach ``request_payload`` to their integration log so template
    sends are distinguishable. Raises on Respond errors and on
    TemplateSendSkipped (so RQ/json callers record a failed log).

    Variable resolution (``message`` / ``portal_url`` defaulting) happens ONCE,
    before the window branch, so in-window text and out-of-window template render
    from identical context — the uniformity guarantee.
    """
    from app.services.integration_service import RespondClient

    window = get_window_state(db, identifier, respond_contact_id=respond_contact_id)

    vars_resolved = dict(context_vars or {})
    vars_resolved.setdefault("message", text)
    if not vars_resolved.get("portal_url"):
        url = extract_first_url(text)
        if url:
            vars_resolved["portal_url"] = url

    if window["open"]:
        # Render the same template body the closed-window branch would send, so
        # the message is uniform across the 24h boundary. Falls back to raw text
        # when the use case has no configured default.
        out_text = render_in_window_text(
            db, use_case=use_case, context_vars=vars_resolved, fallback_text=text
        )
        text_payload = {"message": {"type": "text", "text": out_text}}
        try:
            response = RespondClient().send_message(identifier, out_text)
        except Exception as e:
            # Attach the actual attempted payload + window so callers log the
            # truth in the Respond outbox (was a hardcoded text default before).
            _attach_send_context(e, text_payload, window, "text")
            raise
        return {
            "sent_as": "text",
            "response": response,
            "window_state": window,
            "request_payload": text_payload,
        }

    try:
        result = send_template_for_use_case(
            db,
            identifier=identifier,
            use_case=use_case,
            context_vars=vars_resolved,
        )
    except Exception as e:
        # Window closed -> a TEMPLATE was attempted. send_template_for_use_case
        # already stamps the FULL resolved payload (name + filled params) when the
        # template resolved and only the HTTP send failed. Only fall back to a
        # minimal payload when nothing was attached (e.g. TemplateSendSkipped:
        # no template configured), so the outbox still shows it as a template row.
        if not hasattr(e, "request_payload"):
            _attach_send_context(
                e,
                {
                    "message": {
                        "type": "whatsapp_template",
                        "use_case": use_case,
                        "parameters_context": vars_resolved,
                    }
                },
                window,
                "template",
            )
        raise
    return {
        "sent_as": "template",
        "response": result["response"],
        "window_state": window,
        "template_name": result["template_name"],
        "request_payload": {
            "message": {
                "type": "whatsapp_template",
                "template_name": result["template_name"],
                "template_id": result["template_id"],
                "use_case": use_case,
                "parameters": result["params"],
            },
            "window_state": window,
        },
    }


def build_context_vars(
    db: Session,
    *,
    use_case: str,
    business_id: str,
    identifier: str,
) -> Dict[str, Any]:
    """Best-effort variable resolution for auto-sends (RQ tasks / sync sites).

    Never raises — a missing var resolves to "-" at param fill time.
    """
    vars_out: Dict[str, Any] = {}
    try:
        from app.models.access import RespondContact

        ident = identifier.split(":", 1)[-1] if identifier else ""
        contact = (
            db.query(RespondContact)
            .filter(RespondContact.respond_io_id == ident)
            .first()
        )
        if contact:
            vars_out["contact_name"] = (
                contact.name
                or " ".join(filter(None, [contact.first_name, contact.last_name]))
                or contact.phone_number
            )
    except Exception:
        logger.exception("build_context_vars: contact lookup failed")

    try:
        if use_case == "complaint":
            from app.models.complaints import Complaint

            row = db.query(Complaint).filter(Complaint.id == business_id).first()
            if row:
                vars_out["entity_number"] = row.complaint_number
                vars_out["status"] = row.status
                vars_out["reason"] = row.rejection_reason
        elif use_case == "stock_inquiry":
            from app.models.procurement import StockInquiry

            row = db.query(StockInquiry).filter(StockInquiry.id == business_id).first()
            if row:
                vars_out["entity_number"] = row.inquiry_number
                vars_out["status"] = row.status
                vars_out["reason"] = row.rejection_reason
        elif use_case in ("purchase_request", "sponsorship_form"):
            from app.models.procurement import PurchaseRequestHeader

            row = (
                db.query(PurchaseRequestHeader)
                .filter(PurchaseRequestHeader.id == business_id)
                .first()
            )
            if row:
                vars_out["entity_number"] = row.request_number
                vars_out["status"] = row.approval_status or row.status
    except Exception:
        logger.exception("build_context_vars: entity lookup failed (%s)", use_case)

    return {k: v for k, v in vars_out.items() if v}


def use_case_for_purchase_request(header) -> str:
    """purchase_requests rows carry both PRs and sponsorship forms."""
    return (
        "sponsorship_form"
        if getattr(header, "request_type", None) == "sponsorship_form"
        else "purchase_request"
    )
