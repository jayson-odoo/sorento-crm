"""Mask sign-in and portal OTP codes out of every CRM read of a WhatsApp thread.

Fix lane round 2 (reviewer B2, #1280). A sign-in code goes out as a WhatsApp
message to the user's own contact, and the CRM reads that contact's history
back in several places: the conversation thread (Respond lane, local
``chat_histories`` lane, in-thread search), the ticket drawer, and every
screen that calls ``RespondClient.list_messages``. Without this, anyone who
can open the thread could read "Your Sorento sign-in code is 123456" and sign
in as that user, an admin included.

Three shapes carry a code:

- the in-window free texts ("... sign-in code is 123456", "... verification
  code is 123456"), matched by :data:`OTP_TEXT_RE`;
- a ``portal_otp`` / ``login_otp`` template send, whose body parameters mapped
  to ``otp_code`` (``respond_template_defaults.param_mapping``) hold it;
- an authentication template's copy-code button parameter.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

MASK = "******"
OTP_USE_CASES = ("portal_otp", "login_otp")
OTP_TEXT_RE = re.compile(r"((?:sign-in|verification) code is\s+)\d{4,8}", re.IGNORECASE)


def mask_otp_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    return OTP_TEXT_RE.sub(lambda m: m.group(1) + MASK, text)


def otp_template_code_slots(db: Any = None) -> dict[str, set[int]]:
    """``{template name: {1-based body positions mapped to otp_code}}`` for the
    templates currently set as the OTP use cases' defaults. Opens its own
    session when none is given; an unreadable table answers ``{}``."""
    from app.models.respond_template import RespondTemplateDefault

    own = db is None
    if own:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        rows = (
            db.query(
                RespondTemplateDefault.template_name_snapshot,
                RespondTemplateDefault.param_mapping,
            )
            .filter(RespondTemplateDefault.use_case.in_(OTP_USE_CASES))
            .all()
        )
    except Exception as e:  # noqa: BLE001 - masking falls back to the text rule
        logger.warning("OTP template lookup failed: %s", type(e).__name__)
        return {}
    finally:
        if own:
            db.close()

    out: dict[str, set[int]] = {}
    for name, mapping in rows:
        slots = {
            int(k)
            for k, v in (mapping or {}).items()
            if v == "otp_code" and str(k).isdigit()
        }
        if name and slots:
            out[name] = slots
    return out


def _scrub(value: Any, needles: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for needle in needles:
            value = value.replace(needle, MASK)
        return value
    if isinstance(value, dict):
        return {k: _scrub(v, needles) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, needles) for v in value]
    return value


def _template_codes(message: dict, slots: dict[str, set[int]]) -> set[str]:
    template = message.get("template") if isinstance(message.get("template"), dict) else {}
    positions = slots.get(str(template.get("name") or ""), set())
    codes: set[str] = set()
    for comp in template.get("components") or []:
        if not isinstance(comp, dict):
            continue
        params = [p for p in (comp.get("parameters") or []) if isinstance(p, dict)]
        kind = str(comp.get("type") or "").lower()
        if kind == "body":
            for i, param in enumerate(params, start=1):
                if i in positions and param.get("text"):
                    codes.add(str(param["text"]))
        elif kind == "button" and str(comp.get("sub_type") or "").lower() == "copy_code":
            for param in params:
                for key in ("coupon_code", "text"):
                    if param.get(key):
                        codes.add(str(param[key]))
    # A short value would mangle unrelated text; every code is 6 digits.
    return {c for c in codes if len(c) >= 4}


def _is_template(item: Any) -> bool:
    message = item.get("message") if isinstance(item, dict) else None
    return isinstance(message, dict) and str(message.get("type") or "").lower() == "whatsapp_template"


def redact_otp_item(item: Any, slots: Optional[dict[str, set[int]]] = None) -> Any:
    """Mask the code in one Respond message item, in place (and returned)."""
    if not isinstance(item, dict):
        return item
    message = item.get("message")
    if isinstance(message, dict):
        if _is_template(item):
            if slots is None:
                slots = otp_template_code_slots()
            codes = _template_codes(message, slots)
            if codes:
                message = _scrub(message, tuple(codes))
                item["message"] = message
        if isinstance(message.get("text"), str):
            message["text"] = mask_otp_text(message["text"])
    reply_to = item.get("replyTo")
    if isinstance(reply_to, dict) and isinstance(reply_to.get("message"), dict):
        quoted = reply_to["message"]
        if isinstance(quoted.get("text"), str):
            quoted["text"] = mask_otp_text(quoted["text"])
    return item


def redact_otp_payload(payload: Any, slots: Optional[dict[str, set[int]]] = None) -> Any:
    """Mask every item of a Respond ``message/list`` payload, in place."""
    if not isinstance(payload, dict):
        return payload
    items = payload.get("items")
    if not isinstance(items, list):
        items = payload.get("data") if isinstance(payload.get("data"), list) else []
    if slots is None and any(_is_template(i) for i in items):
        slots = otp_template_code_slots()
    for item in items:
        redact_otp_item(item, slots or {})
    return payload
