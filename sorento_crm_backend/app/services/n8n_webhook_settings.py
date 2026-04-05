"""Resolve n8n webhook URLs from system_settings with env fallback where supported."""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import SystemSetting


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


def get_n8n_stock_inquiry_revise_webhook_url(db: Session) -> str:
    """Public stock inquiry revise requests: system_settings only (no env default)."""
    row = db.query(SystemSetting).first()
    u = (getattr(row, "n8n_stock_inquiry_revise_webhook_url", None) or "").strip() if row else ""
    return _normalize_webhook_url(u) if u else ""
