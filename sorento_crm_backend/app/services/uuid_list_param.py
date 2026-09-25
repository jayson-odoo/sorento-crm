"""Shared parser for `<entity>_ids` query params.

Accepts repeated values, comma-separated string, or JSON array string. Validates
every element as a UUID. Raises HTTP 400 on invalid input so the MCP envelope
wrapper can surface `status=error code=INVALID_UUID`.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from fastapi import HTTPException, status


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def parse_uuid_list(raw: Optional[list[str]], *, param_name: str) -> Optional[list[str]]:
    """Flatten + validate a `<entity>_ids` param.

    Returns None when no values provided (caller treats as "no filter"). Returns a
    deduplicated list of canonical lowercase UUIDs otherwise. Raises 400 on any
    element that fails UUID parsing.
    """
    if raw is None:
        return None
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item is None:
            continue
        s = str(item).strip()
        if not s:
            continue
        # JSON array form, e.g. ["uuid1","uuid2"]
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    for p in parsed:
                        _consume(p, out, seen, param_name)
                    continue
            except json.JSONDecodeError:
                pass
        # CSV form, e.g. "uuid1,uuid2"
        for piece in s.split(","):
            _consume(piece, out, seen, param_name)
    return out or None


def _consume(value, out: list[str], seen: set[str], param_name: str) -> None:
    s = str(value or "").strip()
    if not s:
        return
    if not _UUID_RE.match(s):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_UUID",
                "message": f"`{param_name}` contains a non-UUID value: {s!r}",
                "param": param_name,
            },
        )
    canonical = s.lower()
    if canonical in seen:
        return
    seen.add(canonical)
    out.append(canonical)


def parse_requested_quantities(
    raw: Optional[str], *, param_name: str = "requested_quantities"
) -> Optional[dict]:
    """Ported from PR #1118 (feat/chatbot-dealer-stock-verdict, not merged, owner
    ruling 24 Sep 2026) for chatbot-stock-ask-v2 S3 parity.

    `requested_quantities`: a JSON object, product UUID -> int, over `<entity>_ids`'
    plumbing rather than a list.

    Returns None for a blank/absent value. Raises 400 on anything that is not a JSON
    object, a key that fails UUID parsing, or a value that is not a plain int (a bool
    is rejected too - `isinstance(True, int)` is true in Python, but a bare `true` is
    never a quantity).
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_REQUESTED_QUANTITIES",
                "message": f"`{param_name}` must be a JSON object.",
                "param": param_name,
            },
        )
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_REQUESTED_QUANTITIES",
                "message": f"`{param_name}` must be a JSON object, not a {type(parsed).__name__}.",
                "param": param_name,
            },
        )
    out: dict[str, int] = {}
    for key, value in parsed.items():
        key_s = str(key).strip()
        if not _UUID_RE.match(key_s):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_UUID",
                    "message": f"`{param_name}` contains a non-UUID key: {key_s!r}",
                    "param": param_name,
                },
            )
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_REQUESTED_QUANTITIES",
                    "message": f"`{param_name}` value for {key_s!r} must be an integer.",
                    "param": param_name,
                },
            )
        out[key_s.lower()] = value
    return out or None
