"""Respond.io WhatsApp template sync + per-use-case default configuration.

Sync pulls channels (``GET /v2/space/channel``) and per-channel WhatsApp
templates (``GET /v2/space/channel/{channelId}/template``) for every active
``respond_workspaces`` row, upserting into ``respond_channels`` /
``respond_message_templates`` and hard-deleting rows gone from the API.

Defaults: one row per use case (complaint / stock_inquiry / purchase_request /
sponsorship_form) selecting the approved template + positional param mapping
used by ``respond_messaging_service.send_text_or_template`` when the contact's
24h window is closed.

Plan: docs/plans/PLAN-whatsapp-template-fallback.md
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.respond_template import (
    CHAT_TEMPLATE_USE_CASES,
    TEMPLATE_DEFAULT_USE_CASES,
    RespondChannel,
    RespondMessageTemplate,
    RespondTemplateDefault,
)
from app.models.respond_workspace import RespondWorkspace
from app.services.error_handler import handle_not_found, handle_validation_error

logger = logging.getLogger(__name__)

# Variables resolvable per use case by respond_messaging_service.
PARAM_VARIABLES = (
    "contact_name",
    "entity_number",
    "status",
    "reason",
    "portal_url",
    "message",
    # Portal OTP code — used by the ``portal_otp`` use case template.
    "otp_code",
    # SLA daily summary counts — keys match the context_vars emitted by
    # user_sla_daily_summary_service (``outstanding`` / ``escalated_last_24h`` /
    # ``resolved_last_24h``); the deep link maps to ``portal_url``.
    "outstanding",
    "escalated_last_24h",
    "resolved_last_24h",
    # Product-discontinued batch notification: count of newly-discontinued products
    # and a deep link to the product list filtered to that batch. ``discontinued_link``
    # can also be mapped via ``portal_url`` for templates that reuse the link slot.
    "discontinued_count",
    "discontinued_link",
    # Generic helpers usable by any template: today's date (DD/MM/YYYY, Malaysia) and
    # the CRM base URL. Each use case's service must supply these in context_vars.
    "today_date",
    "system_url",
    # SLA assignment / escalation deadlines (KL wall time) — "Respond by" / "Resolve by".
    "respond_due_at",
    "resolve_due_at",
    # SLA assignment / escalation destination link: the form record for routed types,
    # or the Respond inbox for ticket / conversation — same target as clicking the task.
    "form_url",
    # Structured complaint update template (PLAN-complaint-structured-update-template.md):
    # discrete fields so the body reads as labelled lines (Project / Customer / DO) with
    # the bare action core after "Update:" — instead of one verbose run-on sentence.
    # ``update`` = the bare core (tech response / status change / resolution);
    # ``project`` / ``customer`` / ``delivery_order`` auto-resolve from the complaint row.
    "update",
    "project",
    "customer",
    "delivery_order",
    # Stock-inquiry product code line.
    "product_code",
    # Read-only public view link (token URL) — distinct from ``portal_url`` which
    # is the interactive portal the contact can act/resubmit on. Complaint sends
    # thread both via extra_context_vars.
    "view_url",
    # SLA takeover: the initiator (teammate who started the takeover) — the
    # "Requested by" line in the takeover-pending template.
    "initiator",
    # Form handling-lock: the staff member who currently holds (or just claimed /
    # released) the "I'm handling this" lock. Used by the sla_handling_* templates.
    "handler_name",
    # Sender name — the staff member who replied. Runtime-filled from the logged-in
    # user's ``users.name`` (falls back to "Customer Service" for API-key/system
    # principals). Used by the chat reply templates so the contact knows who replied.
    "sender_name",
)

# Use cases whose template MUST map a slot to a specific variable, or the message
# loses its whole point. portal_otp without ``otp_code`` mapped renders a login
# message with no code — locking users out — yet would otherwise pass the
# "every slot mapped to *something*" check. Enforced in set_default.
REQUIRED_PARAM_VARIABLE: Dict[str, str] = {
    "portal_otp": "otp_code",
}

_PARAM_RE = re.compile(r"\{\{(\d+)\}\}")


def _now() -> datetime:
    return datetime.utcnow()


def _body_text_of(components: List[dict]) -> str:
    for comp in components or []:
        if isinstance(comp, dict) and comp.get("type") == "body":
            return str(comp.get("text") or "")
    return ""


def _param_count_of(body_text: str) -> int:
    nums = [int(m) for m in _PARAM_RE.findall(body_text or "")]
    return max(nums) if nums else 0


# Reserved (non-numeric) param_mapping key for a template's dynamic URL button.
# Body slots stay "1".."n"; the button link var lives under this key so it never
# collides with a positional body param.
BUTTON_URL_KEY = "button_url"


def url_button_of(components: List[dict]) -> Optional[dict]:
    """The dynamic-URL CTA button from a respond.io ``buttons`` component, or None.

    respond.io shape: ``{"type":"buttons","buttons":[{"type":"url",
    "url":"https://x/{{1}}","parameters":[...]}]}``. "Dynamic" = the url carries a
    ``{{n}}`` placeholder; a static url button (no placeholder) is ignored — there
    is nothing to fill at send time.
    """
    for comp in components or []:
        if not isinstance(comp, dict) or comp.get("type") != "buttons":
            continue
        for btn in comp.get("buttons") or []:
            if (
                isinstance(btn, dict)
                and btn.get("type") == "url"
                and _PARAM_RE.search(str(btn.get("url") or ""))
            ):
                return btn
    return None


def button_url_base(button: Optional[dict]) -> Optional[str]:
    """Static prefix of a dynamic URL button (everything before the ``{{n}}``)."""
    if not button:
        return None
    url = str(button.get("url") or "")
    m = _PARAM_RE.search(url)
    return url[: m.start()] if m else None


def is_copy_code_button(button: Optional[dict]) -> bool:
    """True for a WhatsApp Authentication COPY_CODE button.

    These render as a dynamic URL button (the url carries ``{{1}}``), but the
    param is the OTP code itself — Meta copies the button parameter, not a CRM
    link. Admins must NOT map a link variable for it; the send path reuses the
    code already mapped to the body. Detected by the copy-code URL signature.
    """
    if not button:
        return False
    url = str(button.get("url") or "").lower()
    return "otp_type=copy_code" in url or "whatsapp.com/otp" in url


def _client_for_workspace(workspace: RespondWorkspace):
    from app.services.integration_service import RespondClient
    from app.utils.field_encryption import decrypt_secret

    api_key: Optional[str] = None
    try:
        api_key = decrypt_secret(workspace.api_key_ciphertext)
    except ValueError:
        logger.warning(
            "respond_templates sync: cannot decrypt api key for workspace %s; using env key",
            workspace.space_id,
        )
    return RespondClient(api_key=api_key, base_url=workspace.base_url or None)


def sync_templates(db: Session) -> Dict[str, int]:
    """Sync channels + templates for all active workspaces.

    Upsert by natural keys; hard-delete template/channel rows missing from the
    API (defaults survive via ``ON DELETE SET NULL`` + name snapshot).
    """
    workspaces = (
        db.query(RespondWorkspace).filter(RespondWorkspace.is_active.is_(True)).all()
    )
    if not workspaces:
        raise handle_validation_error(
            "No active Respond.io workspace configured. Add one under Respond.io Workspaces first."
        )

    now = _now()
    channels_seen = 0
    synced = 0
    deleted = 0

    for ws in workspaces:
        client = _client_for_workspace(ws)
        api_channels = client.list_channels()

        existing_channels = {
            c.respond_channel_id: c
            for c in db.query(RespondChannel).filter(RespondChannel.workspace_id == ws.id).all()
        }
        api_channel_ids = set()

        for item in api_channels:
            try:
                rid = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            api_channel_ids.add(rid)
            channel = existing_channels.get(rid)
            if channel is None:
                channel = RespondChannel(workspace_id=ws.id, respond_channel_id=rid)
                db.add(channel)
                existing_channels[rid] = channel
            channel.name = item.get("name")
            channel.source = item.get("source")
            channel.synced_at = now
            channels_seen += 1

        # Hard-delete channels gone from the API (cascades their templates).
        for rid, channel in list(existing_channels.items()):
            if rid not in api_channel_ids:
                db.delete(channel)
                del existing_channels[rid]

        db.flush()

        for channel in existing_channels.values():
            try:
                api_templates = client.list_message_templates(channel.respond_channel_id)
            except Exception as e:  # non-WhatsApp channels have no template endpoint
                logger.info(
                    "respond_templates sync: channel %s (%s) has no templates (%s)",
                    channel.respond_channel_id,
                    channel.source,
                    e,
                )
                continue

            existing_templates = {
                t.respond_template_id: t
                for t in db.query(RespondMessageTemplate)
                .filter(RespondMessageTemplate.channel_id == channel.id)
                .all()
            }
            api_template_ids = set()

            for item in api_templates:
                try:
                    rid = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                api_template_ids.add(rid)
                row = existing_templates.get(rid)
                if row is None:
                    row = RespondMessageTemplate(
                        channel_id=channel.id, respond_template_id=rid
                    )
                    db.add(row)
                    existing_templates[rid] = row
                components = item.get("components") or []
                body_text = _body_text_of(components)
                row.name = str(item.get("name") or "")
                row.language_code = str(item.get("languageCode") or "en")
                row.category = item.get("category")
                row.status = str(item.get("status") or "pending")
                row.status_detail = item.get("statusDetail")
                row.meta_template_id = (
                    str(item.get("templateId")) if item.get("templateId") else None
                )
                row.namespace = item.get("namespace")
                row.components = components
                row.body_text = body_text
                row.param_count = _param_count_of(body_text)
                row.synced_at = now
                synced += 1

            for rid, row in existing_templates.items():
                if rid not in api_template_ids:
                    db.delete(row)
                    deleted += 1

    db.commit()
    return {"synced": synced, "deleted": deleted, "channels": channels_seen}


def list_templates(
    db: Session,
    *,
    page: int = 1,
    limit: int = 50,
    query: Optional[str] = None,
    status: Optional[str] = None,
    sort: str = "name",
    direction: str = "asc",
) -> Dict[str, Any]:
    q = db.query(RespondMessageTemplate).options(
        joinedload(RespondMessageTemplate.channel)
    )
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(
            RespondMessageTemplate.name.ilike(like)
            | RespondMessageTemplate.body_text.ilike(like)
        )
    if status and status != "all":
        q = q.filter(RespondMessageTemplate.status == status)

    sort_col = {
        "name": RespondMessageTemplate.name,
        "language_code": RespondMessageTemplate.language_code,
        "category": RespondMessageTemplate.category,
        "status": RespondMessageTemplate.status,
        "param_count": RespondMessageTemplate.param_count,
        "synced_at": RespondMessageTemplate.synced_at,
    }.get(sort, RespondMessageTemplate.name)
    q = q.order_by(sort_col.desc() if direction == "desc" else sort_col.asc())

    total = q.count()
    rows = q.offset(max(0, (page - 1)) * limit).limit(limit).all()
    return {
        "data": [serialize_template(t) for t in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
    }


def serialize_template(t: RespondMessageTemplate) -> Dict[str, Any]:
    url_button = url_button_of(t.components)
    return {
        "id": str(t.id),
        "respond_template_id": str(t.respond_template_id),
        "name": t.name,
        "language": t.language_code,
        "category": t.category,
        "status": t.status,
        "body_text": t.body_text,
        "param_count": t.param_count,
        # Dynamic URL button: lets the defaults modal show the extra "Button link"
        # mapping row and require it before saving.
        "has_url_button": url_button is not None,
        "button_url_base": button_url_base(url_button),
        "button_text": (url_button.get("text") if url_button else None),
        # COPY_CODE auth buttons: no link var to map (the OTP code auto-fills).
        "button_is_copy_code": is_copy_code_button(url_button),
        "channel_name": t.channel.name if t.channel else None,
        "synced_at": t.synced_at.isoformat() if t.synced_at else None,
    }


def _default_is_valid(row: Optional[RespondTemplateDefault]) -> bool:
    if row is None or row.template_id is None or row.template is None:
        return False
    if row.template.status != "approved":
        return False
    mapping = row.param_mapping or {}
    needed = {str(i + 1) for i in range(row.template.param_count)}
    if not (needed <= set(mapping.keys())):
        return False
    # A dynamic URL button needs its link variable mapped, or the button has
    # nothing to fill (Meta rejects a missing button param). COPY_CODE auth
    # buttons are exempt — their param is the OTP code, auto-filled at send.
    _btn = url_button_of(getattr(row.template, "components", None))
    if _btn and not is_copy_code_button(_btn) and not mapping.get(BUTTON_URL_KEY):
        return False
    return True


def serialize_default(
    use_case: str, row: Optional[RespondTemplateDefault]
) -> Dict[str, Any]:
    template = row.template if row is not None else None
    template_name = None
    if template is not None:
        template_name = template.name
    elif row is not None and row.template_name_snapshot:
        template_name = row.template_name_snapshot
    url_button = (
        url_button_of(getattr(template, "components", None))
        if template is not None
        else None
    )
    mapping = dict(row.param_mapping or {}) if row else {}
    return {
        "use_case": use_case,
        "template_id": str(row.template_id) if row and row.template_id else None,
        "template_name": template_name,
        "template_status": template.status if template else None,
        "param_mapping": mapping,
        # Dynamic URL button metadata so the admin modal can render the extra
        # "Button link → [var]" mapping row and know the static base.
        "has_url_button": url_button is not None,
        "button_url_base": button_url_base(url_button),
        "button_url_var": mapping.get(BUTTON_URL_KEY),
        # COPY_CODE auth buttons: no link var to map (the OTP code auto-fills).
        "button_is_copy_code": is_copy_code_button(url_button),
        # True only when the template exists, is approved and fully mapped.
        "is_valid": _default_is_valid(row),
        # Template was set once but hard-deleted by a later sync.
        "template_removed": bool(
            row and row.template_id is None and row.template_name_snapshot
        ),
    }


def get_defaults(db: Session) -> List[Dict[str, Any]]:
    rows = {
        r.use_case: r
        for r in db.query(RespondTemplateDefault)
        .options(
            joinedload(RespondTemplateDefault.template).joinedload(
                RespondMessageTemplate.channel
            )
        )
        .all()
    }
    return [serialize_default(uc, rows.get(uc)) for uc in TEMPLATE_DEFAULT_USE_CASES]


def get_default_row(db: Session, use_case: str) -> Optional[RespondTemplateDefault]:
    return (
        db.query(RespondTemplateDefault)
        .options(
            joinedload(RespondTemplateDefault.template).joinedload(
                RespondMessageTemplate.channel
            )
        )
        .filter(RespondTemplateDefault.use_case == use_case)
        .first()
    )


def set_default(
    db: Session,
    use_case: str,
    *,
    template_id: str,
    param_mapping: Dict[str, str],
) -> Dict[str, Any]:
    if use_case not in TEMPLATE_DEFAULT_USE_CASES:
        raise handle_validation_error(f"Unknown use_case: {use_case}")

    template = (
        db.query(RespondMessageTemplate)
        .filter(RespondMessageTemplate.id == template_id)
        .first()
    )
    if template is None:
        raise handle_not_found("Template", template_id)
    if template.status != "approved":
        raise handle_validation_error(
            "Only approved templates can be set as default."
        )

    mapping = {str(k): str(v) for k, v in (param_mapping or {}).items()}
    needed = {str(i + 1) for i in range(template.param_count)}
    missing = sorted(needed - set(mapping.keys()), key=int)
    if missing:
        raise handle_validation_error(
            f"param_mapping must cover every template parameter; missing: {', '.join(missing)}"
        )
    invalid_vars = sorted({v for v in mapping.values() if v not in PARAM_VARIABLES})
    if invalid_vars:
        raise handle_validation_error(
            f"Unknown param variables: {', '.join(invalid_vars)}. Allowed: {', '.join(PARAM_VARIABLES)}"
        )
    # Drop mapping entries beyond the template's params (stale keys from a
    # previously-selected template). Keep the reserved BUTTON_URL_KEY — it is not
    # a positional body slot.
    mapping = {k: v for k, v in mapping.items() if k in needed or k == BUTTON_URL_KEY}

    # Dynamic URL button: require its link variable mapped (else Meta rejects the
    # button param). No button → drop a stale button_url key. COPY_CODE auth
    # buttons are exempt — their param is the OTP code (auto-filled at send), so
    # admins map no link variable; drop any stale key.
    _url_btn = url_button_of(template.components)
    if _url_btn and not is_copy_code_button(_url_btn):
        if not mapping.get(BUTTON_URL_KEY):
            raise handle_validation_error(
                "This template has a dynamic URL button; map 'button_url' to a "
                "link variable (e.g. portal_url)."
            )
    else:
        mapping.pop(BUTTON_URL_KEY, None)

    # Some use cases must carry a specific variable (e.g. OTP must contain the
    # code). Checked after the trim so a slot beyond the body's params doesn't
    # count. Covers both the in-window render and the closed-window template.
    required_var = REQUIRED_PARAM_VARIABLE.get(use_case)
    if required_var and required_var not in mapping.values():
        raise handle_validation_error(
            f"The '{use_case}' template must map a parameter to '{required_var}'."
        )

    # Chat reply templates carry the admin's typed message in a body param — a
    # default with no slot mapped to ``message`` would drop the reply entirely.
    # ``sender_name`` unmapped is allowed (it only labels who replied), so do NOT
    # hard-fail on it here (the FE surfaces a soft warning).
    if use_case in CHAT_TEMPLATE_USE_CASES and "message" not in mapping.values():
        raise handle_validation_error(
            "Chat templates must map a parameter to the typed message (variable: message)."
        )

    row = (
        db.query(RespondTemplateDefault)
        .filter(RespondTemplateDefault.use_case == use_case)
        .first()
    )
    if row is None:
        row = RespondTemplateDefault(use_case=use_case)
        db.add(row)
    row.template_id = template.id
    row.template_name_snapshot = template.name
    row.param_mapping = mapping
    db.commit()
    return serialize_default(use_case, get_default_row(db, use_case))


def clear_default(db: Session, use_case: str) -> Dict[str, Any]:
    if use_case not in TEMPLATE_DEFAULT_USE_CASES:
        raise handle_validation_error(f"Unknown use_case: {use_case}")
    row = (
        db.query(RespondTemplateDefault)
        .filter(RespondTemplateDefault.use_case == use_case)
        .first()
    )
    if row is not None:
        db.delete(row)
        db.commit()
    return serialize_default(use_case, None)


def run_respond_templates_sync(db: Session, task) -> Dict[str, Any]:
    """Scheduled-task handler (key: respond_templates_sync)."""
    return sync_templates(db)
