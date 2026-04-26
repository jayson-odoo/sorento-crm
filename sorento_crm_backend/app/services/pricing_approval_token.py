"""Signed tokens for pricing approval links in email (no session cookie)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Tuple

from jose import JWTError, jwt

from app.config import settings

TOKEN_TYP = "mq_pricing_approval"


def mint_mq_pricing_approval_token(master_quotation_id: str, approver_user_id: str) -> str:
    payload = {
        "typ": TOKEN_TYP,
        "mq_id": str(master_quotation_id),
        "sub": str(approver_user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_mq_pricing_approval_token(token: str) -> Tuple[str, str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise ValueError("Invalid or expired approval link.") from e
    if payload.get("typ") != TOKEN_TYP:
        raise ValueError("Invalid approval token type.")
    mid = str(payload.get("mq_id") or "").strip()
    uid = str(payload.get("sub") or "").strip()
    if not mid or not uid:
        raise ValueError("Invalid approval token payload.")
    return mid, uid
