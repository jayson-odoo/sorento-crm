"""Phone number normalization.

Deterministic MY-default normaliser to E.164 *digits* (no leading ``+``),
e.g. ``012-345 6789`` / ``+60123456789`` / ``0123456789`` -> ``60123456789``.

Used by user phone capture, the user<->RespondContact phone matcher, and the
migration that backfills + de-duplicates ``users.contact_number``. We keep the
stored form as bare digits with the ``60`` country code because
``respond_contacts.phone_number`` is stored that way; matching both sides
through this function makes the link deterministic.

MY-only by design (the business is single-region). If multi-region is ever
needed, swap the body for the ``phonenumbers`` library — the call sites only
depend on this function's contract.
"""
import re
from typing import Optional

_MY_CC = "60"


def normalize_msisdn(raw: Optional[str], default_region: str = "MY") -> Optional[str]:
    """Return E.164 digits (no ``+``) or ``None`` when there is nothing usable.

    Idempotent: ``normalize_msisdn(normalize_msisdn(x)) == normalize_msisdn(x)``.
    """
    if raw is None:
        return None
    s = re.sub(r"[^\d+]", "", str(raw))
    if not s:
        return None
    if s.startswith("+"):
        s = s[1:]
    # strip an international access prefix like 00...
    if s.startswith("00"):
        s = s[2:]
    if not s:
        return None
    if default_region == "MY":
        if s.startswith("0"):
            # national format -> drop trunk 0, prepend country code
            s = _MY_CC + s[1:]
        elif not s.startswith(_MY_CC):
            # bare subscriber number without trunk 0 or country code
            if 9 <= len(s) <= 10:
                s = _MY_CC + s
    return s or None
