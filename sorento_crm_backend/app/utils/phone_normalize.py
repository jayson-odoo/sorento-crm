"""Normalize phone numbers for lookups (digits only, optional leading +)."""
from __future__ import annotations

import re


def normalize_phone(raw: str | None) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    return digits


def phones_match(a: str | None, b: str | None) -> bool:
    return normalize_phone(a) == normalize_phone(b) and bool(normalize_phone(a))
