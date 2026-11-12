"""The one "does this request carry the configured external API key" check.

Shared by order_management/orders.py (external row caps) and complaints/complaints.py
(user-confirmation gate, external-created notification). One definition: complaints.py lost
its own copy on 20 May while its callers stayed (COMPLAINT-CREATE-500).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request

from app.config import settings as app_settings


def request_has_valid_external_api_key(request: Optional[Request]) -> bool:
    """True when X-API-Key header matches configured external API key."""
    if request is None:
        return False
    key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    valid = getattr(app_settings, "external_api_key", None)
    if not key or not valid:
        return False
    return key.strip() == str(valid).strip()
