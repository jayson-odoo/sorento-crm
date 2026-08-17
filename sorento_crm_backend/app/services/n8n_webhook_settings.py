"""Resolve n8n webhook URLs from system_settings with env fallback where supported."""
from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import SystemSetting

logger = logging.getLogger(__name__)

# Shared secret header on every DIRECT CRM -> n8n webhook call (UAC AC-J6). The n8n
# side gates the human-intervened branch on it fail-closed, so an unauthenticated
# call cannot arm the bot-pause lane.
CRM_WEBHOOK_SECRET_HEADER = "X-CRM-Webhook-Secret"


def _normalize_webhook_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith(("http://", "https://")):
        return u
    if u.startswith("//"):
        return "https:" + u
    return "https://" + u


def get_n8n_attachment_webhook_url(db: Session) -> str:
    """Attachment uploads: prefer DB column, else N8N_WEBHOOK_URL env."""
    row = db.query(SystemSetting).first()
    u = (getattr(row, "n8n_attachment_webhook_url", None) or "").strip() if row else ""
    if u:
        return _normalize_webhook_url(u)
    return _normalize_webhook_url(os.getenv("N8N_WEBHOOK_URL", "").strip())


def get_n8n_crm_chat_outbound_webhook_url(db: Session) -> str:
    """CRM Chat Records reply: system_settings only (no env default)."""
    row = db.query(SystemSetting).first()
    u = (getattr(row, "n8n_crm_chat_outbound_webhook_url", None) or "").strip() if row else ""
    return _normalize_webhook_url(u) if u else ""


def get_n8n_crm_webhook_secret() -> str:
    """Shared secret for the CRM's direct n8n webhook calls (env only, AC-J6).

    Deliberately NOT a system_settings column: it is a credential, not an
    operator-editable setting, and it is provisioned on the n8n side as an
    environment credential at promote time.
    """
    from app.config import settings

    configured = (getattr(settings, "n8n_crm_webhook_secret", None) or "").strip()
    return configured or os.getenv("N8N_CRM_WEBHOOK_SECRET", "").strip()


def crm_webhook_auth_headers() -> dict[str, str]:
    """Auth headers for a direct CRM -> n8n webhook call (AC-J6).

    An unset secret is NOT an error: the call still goes out, unauthenticated,
    and the n8n gate refuses to arm the bot-pause lane. That way a misconfigured
    deploy degrades to "bot-pause inert" instead of blocking a staff reply that
    already reached the contact. It is warned about so the inert state is never
    silent.
    """
    secret = get_n8n_crm_webhook_secret()
    if not secret:
        logger.warning(
            "N8N_CRM_WEBHOOK_SECRET is not configured: the CRM -> n8n webhook is "
            "sent WITHOUT %s, so the n8n human-intervened gate stays closed.",
            CRM_WEBHOOK_SECRET_HEADER,
        )
        return {}
    return {CRM_WEBHOOK_SECRET_HEADER: secret}


def get_n8n_close_convo_webhook_url() -> str:
    """Direct ``respond-close-convo`` webhook the CRM calls on a resolve (AC-M3).

    Env / settings only, same family as the shared secret: it is deployment
    wiring for a specific n8n workflow, not an operator-editable business
    setting. An empty value means "not wired yet" and the caller skips the call
    with a warning - a resolve must never depend on it.
    """
    from app.config import settings

    configured = (getattr(settings, "n8n_close_convo_webhook_url", None) or "").strip()
    if not configured:
        configured = os.getenv("N8N_CLOSE_CONVO_WEBHOOK_URL", "").strip()
    return _normalize_webhook_url(configured) if configured else ""


def get_n8n_stock_inquiry_revise_webhook_url(db: Session) -> str:
    """Public stock inquiry revise requests: system_settings only (no env default)."""
    row = db.query(SystemSetting).first()
    u = (getattr(row, "n8n_stock_inquiry_revise_webhook_url", None) or "").strip() if row else ""
    return _normalize_webhook_url(u) if u else ""
