"""Shared WHO-phone resolver for form-detail banners (PLAN-form-banner-person-links).

Every status/notice banner rendered above a form (handling lock, SLA escalation,
SLA extension, rejection) shows WHO did the thing and links their name to
``https://wa.me/{digits}``. This module is the ONE place a banner DTO turns a
person id into those digits — no per-feature phone lookup.

Phone digits come bare (e.g. ``60123456789``, no ``+``) from
``respond_contacts.phone_number`` via ``normalize_msisdn`` / ``resolve_user_respond_contact``,
which is exactly what ``wa.me/{digits}`` wants. Never re-add ``+``.

All helpers are best-effort: a missing / garbage id (or no linked contact) returns
``None`` and never raises.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.respond_link_service import resolve_user_respond_contact

logger = logging.getLogger(__name__)


def _display_name(user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    return (user.name or user.email) or None


def _phone_for_user(db: Session, user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    try:
        rc = resolve_user_respond_contact(db, user)
    except Exception as exc:  # best-effort; never break a read path
        logger.warning("banner phone resolve failed for user %s: %s", getattr(user, "id", "?"), exc)
        return None
    phone = getattr(rc, "phone_number", None) if rc else None
    if not phone:
        return None
    # wa.me wants bare digits (country code, no ``+``/spaces/dashes). Stored
    # ``respond_contacts.phone_number`` may carry a leading ``+`` — strip it here so
    # every consumer of this contract gets link-ready digits, not just the FE.
    digits = re.sub(r"\D", "", str(phone))
    return digits or None


def _user_by_id(db: Session, user_id: Optional[str]) -> Optional[User]:
    if not user_id or not str(user_id).strip():
        return None
    try:
        return db.query(User).filter(User.id == str(user_id)).first()
    except Exception as exc:
        logger.warning("banner user-by-id lookup failed for %s: %s", user_id, exc)
        return None


def _user_by_respond_user_id(db: Session, respond_user_id: Optional[str]) -> Optional[User]:
    if not respond_user_id or not str(respond_user_id).strip():
        return None
    try:
        return db.query(User).filter(User.respond_user_id == str(respond_user_id)).first()
    except Exception as exc:
        logger.warning("banner user-by-respond-id lookup failed for %s: %s", respond_user_id, exc)
        return None


def wa_phone_for_user_id(db: Session, user_id: Optional[str]) -> Optional[str]:
    """Bare wa.me digits for a ``users.id``, or ``None``. Never raises. (PR-1/2/3/5/6)"""
    return _phone_for_user(db, _user_by_id(db, user_id))


def wa_phone_for_respond_user_id(db: Session, respond_user_id: Optional[str]) -> Optional[str]:
    """Bare wa.me digits for a ``users.respond_user_id``, or ``None``. Never raises. (PR-4)"""
    return _phone_for_user(db, _user_by_respond_user_id(db, respond_user_id))


def name_and_wa_phone_for_user_id(
    db: Session, user_id: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(display_name, wa_phone)`` for a ``users.id``. Both ``None`` on miss.

    Mirrors the ``_resolve_user_display_name`` convention so DTOs can emit the
    ``{*_name, *_wa_phone}`` pair together in one lookup.
    """
    user = _user_by_id(db, user_id)
    return _display_name(user), _phone_for_user(db, user)


def name_and_wa_phone_for_respond_user_id(
    db: Session, respond_user_id: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(display_name, wa_phone)`` for a ``users.respond_user_id``."""
    user = _user_by_respond_user_id(db, respond_user_id)
    return _display_name(user), _phone_for_user(db, user)
