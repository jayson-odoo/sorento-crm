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
