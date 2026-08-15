"""Shared guard for `{id}` path params on detail GET endpoints.

A malformed (non-UUID) path id would otherwise reach the DB layer and raise a
generic exception that the route's `except Exception` turns into a 500 (leaking
an error + masking the real "not found"). Calling `validate_uuid_path` first
turns that into a clean 404 — a malformed id is, from the client's view, a
guaranteed-missing row.

Sibling of `uuid_list_param.parse_uuid_list` (which guards `<entity>_ids` query
params and raises 400 for the MCP envelope).
"""
from __future__ import annotations

import re

from fastapi import HTTPException, status

from app.services.error_handler import handle_not_found

#: Exported so an optional UUID **query** param can be validated declaratively
#: (`Query(None, pattern=UUID_PATTERN)`), which answers 422 through FastAPI's own
#: validation handler. A query param has no "missing row" reading, so the 404 the
#: function below returns would be a lie there.
UUID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_UUID_RE = re.compile(UUID_PATTERN)


def validate_uuid_path(value: str, *, resource: str = "Resource") -> str:
    """Return the canonical lowercase UUID, or raise HTTP 404 if not a UUID.

    Use at the top of a detail GET handler before the id reaches the service:
        validate_uuid_path(campaign_id, resource="Campaign")
    """
    s = (value or "").strip()
    if not _UUID_RE.match(s):
        # 404 (not 422) — a bad-format id is just a guaranteed-missing row, and
        # we already return 404 for genuinely-absent rows; one code for clients.
        raise handle_not_found(resource, value)
    return s.lower()
