"""Resolve an integration API key to the RBAC principal it acts as.

This is the join between the key lifecycle and Sorento's existing RBAC. Once a
key resolves to a ``users`` row, every ordinary permission check applies with no
special casing -- which is the whole reason integrations act as real users
rather than carrying a parallel scope vocabulary.

What it replaces: ``get_external_api_user`` returned a hardcoded
``{"id": "system", "role_id": "system"}`` that matches no row in the database,
applied no permission check whatsoever, and compared the key with ``!=``.

**Everything here fails closed.** A key that resolves to an integration with no
principal, a deleted principal or a trashed one is refused, never downgraded to
an anonymous session. The refusal carries a stable machine-readable code so an
operator can distinguish a closed grace window from a key that was never valid --
but never the key itself (AC-AC-39).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.integration import Integration
from app.models.user import User
from app.services.integration_key_service import AuthFailure, IntegrationKeyService

logger = logging.getLogger(__name__)

# Reported when a key is structurally fine but its principal is unusable. Kept
# distinct from invalid_key so a misconfigured integration is diagnosable, and
# deliberately vague about which of the several causes applied -- that detail is
# for our logs, not for whoever is holding the key.
_PRINCIPAL_UNAVAILABLE = "integration_principal_unavailable"


def _unauthorized(code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": "API key authentication failed"},
    )


def resolve_integration_principal(db: Session, presented_key: Optional[str]) -> dict:
    """Authenticate ``presented_key`` and return the user dict it acts as.

    Raises 401 with a stable ``code`` on every refusal. Never returns a partial
    or anonymous principal.
    """
    integration, failure = IntegrationKeyService(db).resolve(presented_key)

    if failure is not None:
        # The code is safe to return; the key is not, and must never reach a log
        # line or an error body.
        logger.warning("integration.auth_refused code=%s", failure.value)
        raise _unauthorized(failure.value)

    assert integration is not None  # resolve() returns one or the other

    if not integration.act_as_user_id:
        # Nullable until the seed migration populates it. Continuing without a
        # principal would hand an unauthenticated caller an unchecked session.
        logger.error(
            "integration.no_principal integration=%s -- act_as_user_id is unset",
            integration.name,
        )
        raise _unauthorized(_PRINCIPAL_UNAVAILABLE)

    user = (
        db.query(User)
        .filter(User.id == integration.act_as_user_id, User.is_trashed.is_(False))
        .first()
    )
    if user is None:
        # Either deleted or trashed. Trashing the principal is how an admin
        # disables an integration's access, so it must actually stop it.
        logger.error(
            "integration.principal_missing integration=%s user_id=%s",
            integration.name,
            integration.act_as_user_id,
        )
        raise _unauthorized(_PRINCIPAL_UNAVAILABLE)

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar": user.avatar,
        "status": user.status,
        "role_id": None,
        "role_name": None,
        # Which integration made the call. Two integrations could legitimately
        # share a principal, and the audit trail must still tell them apart.
        "integration_id": integration.id,
        "integration_name": integration.name,
        "auth_method": "integration_api_key",
    }


def integration_display_name(db: Session, integration_id: str) -> Optional[str]:
    """Name for audit rendering, without exposing the integration record itself."""
    row = db.query(Integration).filter(Integration.id == integration_id).first()
    return row.name if row else None
