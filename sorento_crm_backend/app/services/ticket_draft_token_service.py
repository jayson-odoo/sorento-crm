"""Signed token for the public ticket-draft portal page.

Used by WhatsApp / n8n flow: the intake mints a token and embeds it in the
URL sent back to the contact. Opening the URL hits the public page which
calls a public verify endpoint to fetch the draft, then a public submit
endpoint to promote it. Token carries ticket_id + 7-day expiry; signed
with the same JWT_SECRET as the rest of the app so no extra config is
needed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status

from app.config import settings


_TOKEN_PURPOSE = "ticket_draft"
_TOKEN_TTL_DAYS = 7


def mint_draft_token(ticket_id: str) -> str:
    """Sign a short-lived token granting submit/cancel rights on one draft."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "purpose": _TOKEN_PURPOSE,
        "ticket_id": str(ticket_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=_TOKEN_TTL_DAYS)).timestamp()),
    }
    return jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


def verify_draft_token(token: str) -> str:
    """Decode the token, raise 401 on invalid/expired, return the ticket_id."""
    try:
        decoded = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Draft link has expired. Ask the assistant to create a new ticket.",
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid draft link.",
        ) from e
    if decoded.get("purpose") != _TOKEN_PURPOSE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not valid for the ticket-draft portal.",
        )
    ticket_id = decoded.get("ticket_id")
    if not ticket_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing ticket_id.",
        )
    return str(ticket_id)
