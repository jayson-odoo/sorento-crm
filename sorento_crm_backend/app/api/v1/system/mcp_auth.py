"""What the MCP server asks for its valid bearer tokens (MCP-TOKEN-UI).

The MCP server has no database and no env token any more: it calls this with the X-API-Key it
already holds and caches the answer (`sorento_crm_mcp/sorento_crm_mcp/auth.py`). The answer is
SHA-256 digests of 256-bit random tokens plus the Enforce switch, which tells a key holder
nothing it could replay, so any valid integration key may read it, the same gate
`tool_capabilities` uses. A new permission slug here would 403 an MCP whose act-as user lacks
the grant, and an MCP that cannot read this answers 503: the chatbot outage the lane exists to
prevent.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.services import mcp_auth_token

router = APIRouter(prefix="/mcp-auth")


@router.get("")
def get_mcp_auth(
    response: Response,
    current_user: dict[str, Any] = Depends(get_external_api_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _ = current_user  # auth dependency: a valid integration key
    response.headers["Cache-Control"] = "no-store"
    return mcp_auth_token.mcp_answer(db)
