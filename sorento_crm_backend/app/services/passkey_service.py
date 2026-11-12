"""Passkey sign-in for CRM staff (PASSKEY-LOGIN).

Contract: documentation/plans/identity/passkey-login-12nov-acceptance-criteria.md.

- Which browser origins may use passkeys is configuration (`settings.webauthn_rp_ids`); the RP
  ID is the origin's hostname (:func:`origin_allowed`).
- Every ceremony is bound to a one-time challenge kept in Redis for 5 minutes and taken with
  GETDEL, so it is used once. The record holds the origin and RP ID the options were issued for,
  and (for registration) the user. Redis down = passkeys unavailable: an assertion is never
  accepted without its stored challenge.
- WebAuthn itself (signature, RP ID hash, origin, challenge, user verification, sign counter) is
  checked by py_webauthn.
- A passed sign-in ends in the same tail as every other sign-in
  (`phone_signin_service.finish_sign_in`).

The router (`app/api/v1/auth.py`) only rate-limits and hands over the request.
"""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from typing import Any, Optional
from urllib.parse import urlsplit

import bcrypt
from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.user_passkey import UserPasskey
from app.schemas.auth import LoginResponse
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

CHALLENGE_TTL_SECONDS = 300
_CHALLENGE_PREFIX = "passkey:challenge:"
_KIND_SIGN_IN = "sign_in"
_KIND_REGISTER = "register"

PASSKEY_FAILED_MESSAGE = "That passkey didn't work. Sign in another way."

# AC-29: the WebAuthn transport hints a browser may report; anything else is dropped.
KNOWN_TRANSPORTS = ("usb", "nfc", "ble", "internal", "hybrid", "smart-card", "cable")


def _unavailable() -> AppException:
    return AppException(
        status_code=status.HTTP_400_BAD_REQUEST,
        message="Passkeys are not available here.",
        code="PASSKEYS_UNAVAILABLE",
    )


def _sign_in_failed() -> AppException:
    # One body for every sign-in refusal (AC-12): it never says what was wrong.
    return AppException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        message=PASSKEY_FAILED_MESSAGE,
        code="PASSKEY_FAILED",
    )


def _register_failed() -> AppException:
    return AppException(
        status_code=status.HTTP_400_BAD_REQUEST,
        message="That passkey could not be added. Try again.",
        code="PASSKEY_FAILED",
    )


def _not_enabled() -> AppException:
    return AppException(
        status_code=status.HTTP_403_FORBIDDEN,
        message="Passkey sign-in is not turned on for your account.",
        code="PASSKEY_NOT_ENABLED",
    )


def _reauth_failed(message: str) -> AppException:
    return AppException(status_code=status.HTTP_401_UNAUTHORIZED, message=message, code="REAUTH_FAILED")


def _too_many(retry_after_seconds: int) -> AppException:
    from app.services.phone_signin_service import rate_limited_minutes_message

    return AppException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        message=rate_limited_minutes_message(retry_after_seconds),
        code="RATE_LIMITED",
    )


# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------


def _rp_ids() -> list[str]:
    return [h.strip().lower() for h in (settings.webauthn_rp_ids or "").split(",") if h.strip()]


def enabled() -> bool:
    """AC-03: passkeys are on exactly when at least one hostname is listed."""
    return bool(_rp_ids())


def origin_allowed(origin: Optional[str]) -> Optional[str]:
    """The RP ID (the hostname) for an allowed origin, else None (AC-02).

    Allowed: the hostname is listed AND the scheme is https (any port), or the scheme is http
    and the hostname is localhost.
    """
    if not origin or not isinstance(origin, str):
        return None
    try:
        parts = urlsplit(origin.strip())
        host = (parts.hostname or "").lower()
        parts.port  # noqa: B018 - a garbled port raises here
    except ValueError:
        return None
    if not host or host not in _rp_ids():
        return None
    if parts.scheme == "https" or (parts.scheme == "http" and host == "localhost"):
        return host
    return None


def _require_enabled() -> None:
    if not enabled():
        raise _unavailable()


def _require_origin(origin: Optional[str]) -> str:
    _require_enabled()
    rp_id = origin_allowed(origin)
    if rp_id is None:
        raise _unavailable()
    return rp_id


# --------------------------------------------------------------------------------------
# One-time challenges (Redis)
# --------------------------------------------------------------------------------------


def _redis():
    from app.services.queue_service import redis_conn

    return redis_conn


def _store_challenge(record: dict) -> str:
    challenge_id = secrets.token_urlsafe(24)
    try:
        _redis().setex(_CHALLENGE_PREFIX + challenge_id, CHALLENGE_TTL_SECONDS, json.dumps(record))
    except Exception as e:  # noqa: BLE001 - Redis down: fail closed
        logger.warning("Passkey: challenge store unavailable (%s)", type(e).__name__)
        raise _unavailable() from e
    return challenge_id


def _take_challenge(challenge_id: str) -> Optional[dict]:
    """The stored record, deleted in the same call so it can be used once. None when unknown
    or expired; PASSKEYS_UNAVAILABLE when Redis cannot be reached."""
    try:
        raw = _redis().getdel(_CHALLENGE_PREFIX + str(challenge_id or ""))
    except Exception as e:  # noqa: BLE001 - Redis down: fail closed
        logger.warning("Passkey: challenge store unavailable (%s)", type(e).__name__)
        raise _unavailable() from e
    if raw is None:
        return None
    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _b64url(data: bytes) -> str:
    from webauthn.helpers import bytes_to_base64url

    return bytes_to_base64url(data)


def _b64url_bytes(value: str) -> bytes:
    from webauthn.helpers import base64url_to_bytes

    return base64url_to_bytes(value)


# --------------------------------------------------------------------------------------
# Sign in (AC-10 to AC-15)
# --------------------------------------------------------------------------------------


def sign_in_options(origin: Optional[str]) -> dict:
    """Discoverable-credential request options: no allowCredentials, so no email is asked and
    nothing is enumerable."""
    from webauthn import generate_authentication_options
    from webauthn.helpers import options_to_json_dict
    from webauthn.helpers.structs import UserVerificationRequirement

    rp_id = _require_origin(origin)
    options = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED
    )
    challenge_id = _store_challenge(
        {
            "kind": _KIND_SIGN_IN,
            "challenge": _b64url(options.challenge),
            "origin": origin.strip(),
            "rp_id": rp_id,
        }
    )
    return {"challenge_id": challenge_id, "options": options_to_json_dict(options)}


def _credential_id(credential: dict) -> Optional[str]:
    value = credential.get("id") if isinstance(credential, dict) else None
    return value if isinstance(value, str) and value else None


def verify_sign_in(
    db: Session,
    challenge_id: str,
    credential: dict,
    *,
    user_agent: Optional[str],
    ip_address: Optional[str],
) -> LoginResponse:
    """A valid assertion from a stored passkey of an enabled, untrashed user signs them in.
    Every refusal raises the one PASSKEY_FAILED 401; a user who is not ACTIVE gets the 403
    `/auth/login` answers (from the shared tail)."""
    from webauthn import verify_authentication_response

    from app.services.audit_service import log_audit
    from app.services.phone_signin_service import finish_sign_in, require_active
    from app.services.user_session_service import _utcnow

    _require_enabled()
    record = _take_challenge(challenge_id)
    if record is None or record.get("kind") != _KIND_SIGN_IN:
        raise _sign_in_failed()
    stored_origin, stored_rp_id = record.get("origin"), record.get("rp_id")
    # The hostname list may have changed since the options were issued.
    if origin_allowed(stored_origin) != stored_rp_id:
        raise _sign_in_failed()

    cred_id = _credential_id(credential)
    passkey = (
        db.query(UserPasskey).filter(UserPasskey.credential_id == cred_id).first() if cred_id else None
    )
    if passkey is None:
        raise _sign_in_failed()

    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=_b64url_bytes(record["challenge"]),
            expected_rp_id=stored_rp_id,
            expected_origin=stored_origin,
            credential_public_key=bytes(passkey.public_key),
            credential_current_sign_count=int(passkey.sign_count or 0),
            require_user_verification=True,
        )
    except Exception as e:  # noqa: BLE001 - any defect in the assertion is the same refusal
        logger.info("Passkey sign-in refused: %s", type(e).__name__)
        raise _sign_in_failed() from e

    # A discoverable passkey returns its user handle (the user id, UTF-8); it must be the
    # passkey owner's.
    handle = (credential.get("response") or {}).get("userHandle")
    if handle:
        try:
            if _b64url_bytes(handle) != str(passkey.user_id).encode("utf-8"):
                raise _sign_in_failed()
        except AppException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _sign_in_failed() from e

    user = db.query(User).filter(User.id == passkey.user_id).first()
    if user is None or bool(user.is_trashed) or not bool(user.passkey_enabled):
        raise _sign_in_failed()
    require_active(user)

    # AC-29: the counter moves under a row lock, so two parallel assertions carrying the same
    # counter cannot both pass. The lock is re-read and re-compared, then released by the
    # commit inside the shared tail.
    locked = (
        db.query(UserPasskey)
        .filter(UserPasskey.id == passkey.id)
        .populate_existing()
        .with_for_update()
        .one()
    )
    new_count, stored_count = int(verified.new_sign_count), int(locked.sign_count or 0)
    if (new_count > 0 or stored_count > 0) and new_count <= stored_count:
        db.rollback()
        raise _sign_in_failed()
    locked.sign_count = new_count
    locked.last_used_at = _utcnow()
    db.add(locked)
    log_audit(
        db,
        "user_passkeys",
        str(locked.id),
        "UPDATE",
        user_id=str(user.id),
        ip_address=ip_address,
        event="passkey_sign_in",
        description="Signed in with a passkey",
    )
    return finish_sign_in(
        db, user, user_agent=user_agent, ip_address=ip_address, auth_method="passkey"
    )


# --------------------------------------------------------------------------------------
# Own passkeys (AC-20 to AC-27)
# --------------------------------------------------------------------------------------


def serialize(row: UserPasskey) -> dict:
    """The AC-20 item: no credential id, no key material."""
    return {
        "id": str(row.id),
        "name": row.name,
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
    }


def list_passkeys(db: Session, user_id: str) -> list[UserPasskey]:
    return (
        db.query(UserPasskey)
        .filter(UserPasskey.user_id == str(user_id))
        .order_by(UserPasskey.created_at.desc())
        .all()
    )


def count_passkeys(db: Session, user_id: str) -> int:
    return db.query(UserPasskey).filter(UserPasskey.user_id == str(user_id)).count()


def list_own(db: Session, user: User) -> list[UserPasskey]:
    """AC-26: with the switch off the list is empty, whatever is stored."""
    if not bool(user.passkey_enabled):
        return []
    return list_passkeys(db, str(user.id))


def _require_switch(user: User) -> None:
    if not bool(user.passkey_enabled):
        raise _not_enabled()


def _own_phone_contact(db: Session, user: User):
    """The user's own verified WhatsApp contact, or None (AC-27 NO_PHONE)."""
    from app.services.phone_signin_service import eligible_user_for_contact

    if user.phone_verified_at is None or not user.respond_contact_id:
        return None
    if eligible_user_for_contact(db, user.respond_contact_id) is None:
        return None
    from app.models.access import RespondContact

    return db.query(RespondContact).filter(RespondContact.id == user.respond_contact_id).first()


def _no_phone() -> AppException:
    return AppException(
        status_code=status.HTTP_400_BAD_REQUEST,
        message="There is no verified phone on your account.",
        code="NO_PHONE",
    )


def send_reauth_code(db: Session, user: User) -> dict:
    """AC-27: send a WhatsApp code to the user's OWN verified phone, through the phone
    sign-in send path. It is stored with purpose 'reauth', so `/auth/phone/verify` can never
    consume it (Redis up or down)."""
    from app.services import phone_signin_service as phone

    _require_enabled()
    _require_switch(user)
    contact = _own_phone_contact(db, user)
    if contact is None:
        raise _no_phone()
    phone.send_signin_code(db, contact, purpose="reauth")
    return {"sent_to": phone.mask(phone.normalize_msisdn(contact.phone_number) or "") or ""}


def _check_password(user: User, password: str, ip_address: Optional[str]) -> None:
    """The same throttle as `/auth/login`: locked = 429, a wrong password counts."""
    from app.services import login_throttle

    ident = user.email or str(user.id)
    gate = login_throttle.check(ident, ip_address)
    if not gate.allowed:
        raise _too_many(gate.retry_after_seconds or login_throttle.LOCK_WINDOW_SECONDS)
    stored = (user.password or "").strip()
    try:
        ok = bool(stored) and bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except Exception:  # noqa: BLE001
        ok = False
    if not ok:
        login_throttle.record_failure(ident, ip_address)
        raise _reauth_failed("That password is not right.")
    login_throttle.clear(ident, ip_address)


def _check_phone_code(db: Session, user: User, code: str) -> None:
    """The phone sign-in code check (one shared function) and its per-number budget; no
    session is minted."""
    from app.services import phone_signin_service as phone

    contact = _own_phone_contact(db, user)
    if contact is None:
        raise _no_phone()
    num = phone.normalize_msisdn(contact.phone_number) or ""
    reservation = phone.reserve_verify_attempt(num)
    if reservation.locked:
        raise _too_many(reservation.retry_after_seconds or 900)
    if phone.check_code(db, contact, code, purpose="reauth"):
        phone.clear_redis_state(num)
        return
    status_code, body = phone.wrong_code_refusal(num, reservation, code="REAUTH_FAILED")
    raise AppException(status_code=status_code, message=body["message"], code=body["code"])


def registration_options(
    db: Session,
    user: User,
    origin: Optional[str],
    *,
    password: Optional[str],
    phone_code: Optional[str],
    ip_address: Optional[str],
) -> dict:
    """AC-27 then AC-21: only a passed re-check issues the registration challenge, so the
    challenge record is the proof (single use, 5 minutes)."""
    from webauthn import generate_registration_options
    from webauthn.helpers import options_to_json_dict
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    rp_id = _require_origin(origin)
    _require_switch(user)
    if password is not None:
        _check_password(user, password, ip_address)
    else:
        _check_phone_code(db, user, phone_code or "")

    existing = list_passkeys(db, str(user.id))
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.webauthn_rp_name,
        user_name=user.email or user.contact_number or user.name or str(user.id),
        user_id=str(user.id).encode("utf-8"),
        user_display_name=user.name or user.email or "",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=_b64url_bytes(p.credential_id)) for p in existing
        ],
    )
    challenge_id = _store_challenge(
        {
            "kind": _KIND_REGISTER,
            "challenge": _b64url(options.challenge),
            "origin": origin.strip(),
            "rp_id": rp_id,
            "user_id": str(user.id),
        }
    )
    return {"challenge_id": challenge_id, "options": options_to_json_dict(options)}


def register(
    db: Session,
    user: User,
    challenge_id: str,
    credential: dict,
    *,
    name: Optional[str],
    user_agent: Optional[str],
) -> UserPasskey:
    """AC-22: verify against THIS user's registration challenge and store the passkey."""
    from webauthn import verify_registration_response

    from app.services.user_session_service import device_label_from_ua

    _require_enabled()
    _require_switch(user)
    record = _take_challenge(challenge_id)
    if (
        record is None
        or record.get("kind") != _KIND_REGISTER
        or record.get("user_id") != str(user.id)
        or origin_allowed(record.get("origin")) != record.get("rp_id")
    ):
        raise _register_failed()

    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=_b64url_bytes(record["challenge"]),
            expected_rp_id=record["rp_id"],
            expected_origin=record["origin"],
            require_user_verification=True,
        )
    except Exception as e:  # noqa: BLE001 - any defect in the attestation is the same refusal
        logger.info("Passkey registration refused: %s", type(e).__name__)
        raise _register_failed() from e

    credential_id = _b64url(verified.credential_id)
    if db.query(UserPasskey.id).filter(UserPasskey.credential_id == credential_id).first():
        raise _already_added()

    reported = (credential.get("response") or {}).get("transports")
    transports = [t for t in reported if t in KNOWN_TRANSPORTS] if isinstance(reported, list) else None
    row = UserPasskey(
        user_id=str(user.id),
        credential_id=credential_id,
        public_key=verified.credential_public_key,
        sign_count=int(verified.sign_count or 0),
        transports=transports,
        aaguid=verified.aaguid or None,
        backed_up=bool(verified.credential_backed_up),
        name=((name or "").strip() or device_label_from_ua(user_agent))[:100],
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _already_added() from e
    db.refresh(row)
    return row


def _already_added() -> AppException:
    return AppException(
        status_code=status.HTTP_409_CONFLICT,
        message="This passkey is already added.",
        code="PASSKEY_EXISTS",
    )


def _own_row(db: Session, user_id: str, passkey_id: str) -> UserPasskey:
    try:
        uuid.UUID(str(passkey_id))
    except (TypeError, ValueError):
        row = None
    else:
        row = (
            db.query(UserPasskey)
            .filter(UserPasskey.id == str(passkey_id), UserPasskey.user_id == str(user_id))
            .first()
        )
    if row is None:
        from app.services.error_handler import handle_not_found

        raise handle_not_found("Passkey", passkey_id)
    return row


def rename(db: Session, user: User, passkey_id: str, name: str) -> UserPasskey:
    """AC-23: the caller's own passkey only (anyone else's answers 404)."""
    _require_enabled()
    _require_switch(user)
    row = _own_row(db, str(user.id), passkey_id)
    row.name = name.strip()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def owner_id(db: Session, passkey_id: str) -> Optional[str]:
    """Whose passkey this is, or None when there is no such passkey (park-time check)."""
    try:
        uuid.UUID(str(passkey_id))
    except (TypeError, ValueError):
        return None
    value = db.query(UserPasskey.user_id).filter(UserPasskey.id == str(passkey_id)).scalar()
    return str(value) if value is not None else None


def remove_passkey(db: Session, passkey_id: str) -> Any:
    """AC-24: the ONE removal, behind the `user_passkey.delete` record action (own and admin
    alike). Hard delete."""
    row = db.query(UserPasskey).filter(UserPasskey.id == str(passkey_id)).first()
    if row is None:
        from app.services.error_handler import handle_not_found

        raise handle_not_found("Passkey", passkey_id)
    from app.services.user_session_service import revoke_for_auth_method

    user_id = str(row.user_id)
    db.delete(row)
    db.commit()
    # AC-28: a removed passkey ends the user's passkey sessions; password / phone ones stay.
    revoke_for_auth_method(db, user_id, "passkey")
    return None


def set_enabled(db: Session, user: User, enabled_value: bool) -> dict:
    """AC-33: the per-user switch. Turning it off keeps the stored passkeys."""
    from app.services.user_session_service import revoke_for_auth_method

    user.passkey_enabled = bool(enabled_value)
    db.add(user)
    db.commit()
    if not user.passkey_enabled:
        # AC-28: switching off ends the user's passkey sessions too.
        revoke_for_auth_method(db, str(user.id), "passkey")
    return {"user_id": str(user.id), "passkey_enabled": bool(user.passkey_enabled)}
