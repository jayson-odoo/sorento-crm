"""Integration management API (AC-AC-08).

JWT-authenticated admin surface for creating integrations and minting their
credentials. Deliberately **not** reachable with ``X-API-Key``: an integration
must not be able to mint credentials for itself or read the roster of other
integrations. That would let a compromise of one caller escalate into a
compromise of every caller, which is the precise blast radius this group exists
to contain.

Key management sits behind its own permission (``manage_keys``) rather than
riding on ``edit``. Renaming an integration and issuing a working credential for
it are very different levels of trust.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.integration_admin import (
    IntegrationCreate,
    IntegrationUpdate,
    IssuedKeyResponse,
    RotateKeyRequest,
)
from app.services.integration_admin_service import IntegrationAdminService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def list_integrations(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("integration.integrations.view")),
):
    service = IntegrationAdminService(db)
    return {"data": [service.serialise(row) for row in service.list()]}


@router.get("/{integration_id}")
async def get_integration(
    integration_id: str = Path(...),
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("integration.integrations.view")),
):
    integration_id = validate_uuid_path(integration_id, resource="Integration")
    service = IntegrationAdminService(db)
    return service.serialise(service.get(integration_id))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_integration(
    payload: IntegrationCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("integration.integrations.add")),
):
    service = IntegrationAdminService(db)
    row = service.create(
        name=payload.name,
        type_=payload.type,
        act_as_user_id=payload.act_as_user_id,
        config_json=payload.config_json,
        credentials_json=payload.credentials_json,
        is_active=payload.is_active,
    )
    db.commit()
    return service.serialise(row)


@router.patch("/{integration_id}")
async def update_integration(
    payload: IntegrationUpdate,
    integration_id: str = Path(...),
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("integration.integrations.edit")),
):
    integration_id = validate_uuid_path(integration_id, resource="Integration")
    service = IntegrationAdminService(db)
    row = service.update(
        service.get(integration_id),
        name=payload.name,
        type_=payload.type,
        act_as_user_id=payload.act_as_user_id,
        config_json=payload.config_json,
        # None here means "keep existing" all the way down (AC-AC-07).
        credentials_json=payload.credentials_json,
        is_active=payload.is_active,
    )
    db.commit()
    return service.serialise(row)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: str = Path(...),
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("integration.integrations.delete")),
):
    integration_id = validate_uuid_path(integration_id, resource="Integration")
    service = IntegrationAdminService(db)
    service.delete(service.get(integration_id))
    db.commit()


@router.post(
    "/{integration_id}/keys",
    response_model=IssuedKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_key(
    integration_id: str = Path(...),
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("integration.integrations.manage_keys")),
):
    """Mint a key. The plaintext in this response is never retrievable again."""
    integration_id = validate_uuid_path(integration_id, resource="Integration")
    service = IntegrationAdminService(db)
    issued = service.issue_key(service.get(integration_id))
    db.commit()
    return issued


@router.post("/{integration_id}/keys/rotate", response_model=IssuedKeyResponse)
async def rotate_key(
    payload: RotateKeyRequest | None = None,
    integration_id: str = Path(...),
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("integration.integrations.manage_keys")),
):
    """Issue a replacement and start the grace window on the current key(s).

    ``grace_days=0`` kills the old key immediately -- the right answer for a
    leaked credential, disruptive for a routine rotation.
    """
    integration_id = validate_uuid_path(integration_id, resource="Integration")
    service = IntegrationAdminService(db)
    grace = payload.grace_days if payload is not None else 7
    issued = service.rotate_key(service.get(integration_id), grace_days=grace)
    db.commit()
    return issued


@router.post("/{integration_id}/keys/{key_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    integration_id: str = Path(...),
    key_id: str = Path(...),
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("integration.integrations.manage_keys")),
):
    integration_id = validate_uuid_path(integration_id, resource="Integration")
    key_id = validate_uuid_path(key_id, resource="Key")
    service = IntegrationAdminService(db)
    service.revoke_key(service.get(integration_id), key_id)
    db.commit()
