"""Proof that this backend is answering a staff member, carried on the panel agent's MCP reads (AI-TOOLS-WAVE2).

An identity read (`X-Staff-User` on the shared key, AGENTIC-UNIFY) asks every slug of BOTH the named staff member
and the key's act-as user (`user_service.gate_user_ids`), because anyone holding the key could name a stronger user.
The panel agent is not anyone: the backend runs its turn for the signed-in staff member and calls the MCP server
itself. It sends this proof beside the staff id; the MCP server relays both (`x-mcp-staff-proof` -> `X-Staff-Proof`)
and only after the caller proved it holds the MCP token. A valid proof makes the gate the staff member's alone
(crew pass, 5 Nov: the act-as user's missing sales report reveal refused a staff member who holds it).

The proof is an HMAC over the staff id and an expiry, keyed from JWT_SECRET with its own label, so the MCP server,
n8n or a log reader cannot mint one; it lives five minutes.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

TTL_SECONDS = 300
_LABEL = b"sorento-staff-identity-proof/v1"


def _key() -> bytes:
    from app.config import settings

    return hmac.new(str(settings.jwt_secret).encode(), _LABEL, hashlib.sha256).digest()


def _sign(staff_id: str, expires: int) -> str:
    return hmac.new(_key(), f"{staff_id}|{expires}".encode(), hashlib.sha256).hexdigest()


def mint(staff_id: str, *, now: Optional[float] = None) -> str:
    expires = int((time.time() if now is None else now) + TTL_SECONDS)
    return f"v1.{expires}.{_sign(str(staff_id), expires)}"


def verify(staff_id: Optional[str], proof: Optional[str], *, now: Optional[float] = None) -> bool:
    """True only for an unexpired proof minted here for exactly this staff id."""
    if not staff_id or not proof or len(proof) > 200:
        return False
    parts = proof.strip().split(".")
    if len(parts) != 3 or parts[0] != "v1" or not parts[1].isdigit():
        return False
    expires = int(parts[1])
    current = time.time() if now is None else now
    if expires < current or expires > current + TTL_SECONDS + 60:
        return False
    return hmac.compare_digest(parts[2], _sign(str(staff_id), expires))
