"""S6 - the two masters the dispatch board needs, and why neither is a user or a supplier.

**Technicians are not users** (AC-F8, AC-F21). No account, no login, no `users` row. They
are reached on WhatsApp through a portal link. That is the premise the whole
clocks-off-the-SLA-engine decision rests on: form SLA resolves assignees through
`agent_teams -> team_members -> users`, so giving a technician an account would quietly put
them back inside an engine that cannot schedule them and must not try.

**External providers are not suppliers** (AC-M28). `suppliers` carries payment terms, lead
times and SPO linkage; reusing it would couple after-sales to procurement for nothing. And
it is generic rather than a `plumbers` table, because the discovery study already shows the
role blurring ("forward the details to the plumber; can be an outstation technician") - a
role-specific table would need a sibling within the month.

Hard delete with a confirmation dialog on the front end, per the CRUD standard. Neither
table carries history: an assignment references a technician with `ON DELETE SET NULL`, so
removing somebody who left does not destroy the record that a visit happened.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.service_jobs import ExternalProvider, Technician
from app.services.error_handler import AppException, handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
provider_router = APIRouter()

VIEW_PERMISSION = "complaint_management.service_jobs.view"
MANAGE_PERMISSION = "complaint_management.service_jobs.dispatch"

# employee | contractor. Open on purpose beyond these two? No: a third value would be a
# reporting question nobody has asked, and the study describes exactly these two.
EMPLOYMENT_TYPES = ("employee", "contractor")


class TechnicianCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)
    employment_type: Optional[str] = Field(None, max_length=20)
    respond_contact_id: Optional[str] = None
    is_active: bool = True


class TechnicianUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)
    employment_type: Optional[str] = Field(None, max_length=20)
    respond_contact_id: Optional[str] = None
    is_active: Optional[bool] = None


class ExternalProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    provider_type: str = Field(..., min_length=1, max_length=32)
    phone: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = None
    is_active: bool = True


class ExternalProviderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    provider_type: Optional[str] = Field(None, min_length=1, max_length=32)
    phone: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


def _technician(row: Technician) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "phone": row.phone,
        "employment_type": row.employment_type,
        "respond_contact_id": row.respond_contact_id,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _provider(row: ExternalProvider) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "provider_type": row.provider_type,
        "phone": row.phone,
        "notes": row.notes,
        "is_active": row.is_active,
        "created_at": row.created_at,
    }


def _assert_employment_type(value: Optional[str]) -> None:
    if value and value not in EMPLOYMENT_TYPES:
        raise AppException(
            status_code=422,
            message=f"Employment type must be one of: {', '.join(EMPLOYMENT_TYPES)}.",
            code="technician_employment_type_invalid",
        )


# ------------------------------------------------------------- technicians


@router.get("/")
async def list_technicians(
    query: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key(VIEW_PERMISSION)),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    try:
        q = db.query(Technician)
        if query:
            q = q.filter(Technician.name.ilike(f"%{query}%"))
        if is_active is not None:
            q = q.filter(Technician.is_active.is_(is_active))
        return [_technician(row) for row in q.order_by(Technician.name.asc()).all()]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/")
async def create_technician(
    payload: TechnicianCreate,
    current_user: dict = Depends(require_permission(MANAGE_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        import uuid
        from datetime import datetime

        _assert_employment_type(payload.employment_type)
        row = Technician(
            id=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            **payload.model_dump(),
        )
        db.add(row)
        db.commit()
        return _technician(row)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.put("/{technician_id}")
async def update_technician(
    payload: TechnicianUpdate,
    technician_id: str,
    current_user: dict = Depends(require_permission(MANAGE_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        technician_id = validate_uuid_path(technician_id, resource="Technician")
        from datetime import datetime

        row = db.query(Technician).filter(Technician.id == technician_id).first()
        if row is None:
            raise AppException(
                status_code=404, message="Technician not found.", code="technician_not_found"
            )
        values = payload.model_dump(exclude_unset=True)
        _assert_employment_type(values.get("employment_type"))
        for field, value in values.items():
            setattr(row, field, value)
        row.updated_at = datetime.utcnow()
        db.commit()
        return _technician(row)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.delete("/{technician_id}")
async def delete_technician(
    technician_id: str,
    current_user: dict = Depends(require_permission(MANAGE_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Hard delete, per the CRUD standard. Past assignments survive: the FK is
    ON DELETE SET NULL, so removing somebody who left does not erase the record that
    a visit happened.
    """
    try:
        technician_id = validate_uuid_path(technician_id, resource="Technician")
        row = db.query(Technician).filter(Technician.id == technician_id).first()
        if row is None:
            raise AppException(
                status_code=404, message="Technician not found.", code="technician_not_found"
            )
        db.delete(row)
        db.commit()
        return {"success": True}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


# ------------------------------------------------------- external providers


@provider_router.get("/")
async def list_external_providers(
    query: Optional[str] = Query(None),
    provider_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key(VIEW_PERMISSION)),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    try:
        q = db.query(ExternalProvider)
        if query:
            q = q.filter(ExternalProvider.name.ilike(f"%{query}%"))
        if provider_type:
            q = q.filter(ExternalProvider.provider_type == provider_type)
        if is_active is not None:
            q = q.filter(ExternalProvider.is_active.is_(is_active))
        return [_provider(row) for row in q.order_by(ExternalProvider.name.asc()).all()]
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@provider_router.post("/")
async def create_external_provider(
    payload: ExternalProviderCreate,
    current_user: dict = Depends(require_permission(MANAGE_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        import uuid
        from datetime import datetime

        row = ExternalProvider(
            id=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            **payload.model_dump(),
        )
        db.add(row)
        db.commit()
        return _provider(row)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@provider_router.put("/{provider_id}")
async def update_external_provider(
    payload: ExternalProviderUpdate,
    provider_id: str,
    current_user: dict = Depends(require_permission(MANAGE_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        provider_id = validate_uuid_path(provider_id, resource="External provider")
        row = db.query(ExternalProvider).filter(ExternalProvider.id == provider_id).first()
        if row is None:
            raise AppException(
                status_code=404,
                message="External provider not found.",
                code="external_provider_not_found",
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        db.commit()
        return _provider(row)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@provider_router.delete("/{provider_id}")
async def delete_external_provider(
    provider_id: str,
    current_user: dict = Depends(require_permission(MANAGE_PERMISSION)),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Hard delete. Cost lines keep their amount: the FK is ON DELETE SET NULL, so
    deleting a provider loses who was paid, never how much a case cost.
    """
    try:
        provider_id = validate_uuid_path(provider_id, resource="External provider")
        row = db.query(ExternalProvider).filter(ExternalProvider.id == provider_id).first()
        if row is None:
            raise AppException(
                status_code=404,
                message="External provider not found.",
                code="external_provider_not_found",
            )
        db.delete(row)
        db.commit()
        return {"success": True}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))
