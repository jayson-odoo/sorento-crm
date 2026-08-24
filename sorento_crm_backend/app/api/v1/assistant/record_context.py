"""Record-context assembler route for the in-system AI bubble.

JWT-only. The dependency is ``get_current_user`` (not the ``_or_api_key``
variant), so an ``EXTERNAL_API_KEY`` / ``X-API-Key`` principal is denied - this
keeps the assembler out of n8n/WhatsApp reach (UAC §3.6 / Q7).

RBAC is resolved per entity_type via ``record_context_view_permission``: the
complaint type requires ``complaint_management.complaints.view``; the other
form types are auth-only (no extra permission).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services.error_handler import AppException
from app.services.record_context_service import (
    RecordContextService,
    record_context_view_permission,
)
from app.services.user_service import UserPermissionService

router = APIRouter()


@router.get("/assistant/record-context/{entity_type}/{id}")
def get_record_context(
    entity_type: str,
    id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Assemble the deterministic record-context bundle for a viewed record.

    Resolves the per-entity view permission: when one is required and the user
    lacks it, raises 403. Raises 400 for unsupported entity types and 404 when
    the record is missing (both via ``AppException`` from the service layer).
    """
    required_slug = record_context_view_permission(entity_type)
    if required_slug is not None:
        if not UserPermissionService(db).check_user_has_permission(
            current_user["id"], required_slug
        ):
            raise AppException(
                status_code=403,
                message="You do not have permission to view this record.",
                code="FORBIDDEN",
            )
    return RecordContextService(db).assemble(entity_type, id)
