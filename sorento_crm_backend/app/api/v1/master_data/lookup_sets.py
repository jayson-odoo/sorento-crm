"""Lookup sets admin API + nested options/bindings."""
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.lookup import (
    LookupSetCreate, LookupSetUpdate, LookupSetResponse,
    LookupOptionCreate, LookupOptionUpdate, LookupOptionResponse,
    LookupBindingCreate, LookupBindingResponse,
)
from app.services.error_handler import handle_internal_error
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService

router = APIRouter()


# ----- Sets -----

@router.get("/", response_model=ListResponse[LookupSetResponse])
async def list_sets(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
    db: Session = Depends(get_db),
):
    try:
        return LookupSetService(db).list(page=page, limit=limit, query=query)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=LookupSetResponse, status_code=status.HTTP_201_CREATED)
async def create_set(
    data: LookupSetCreate,
    current_user=Depends(require_permission("master_data.lookup_sets.add")),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    try:
        svc = LookupSetService(db)
        set_obj = svc.create(data)
        if data.initial_binding:
            LookupBindingService(db).create(set_obj.id, data.initial_binding)
        return _set_to_response(db, set_obj)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{set_id}", response_model=LookupSetResponse)
async def get_set(
    set_id: str,
    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        return _set_to_response(db, LookupSetService(db).get(set_id))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{set_id}", response_model=LookupSetResponse)
async def update_set(
    set_id: str,
    data: LookupSetUpdate,
    current_user=Depends(require_permission("master_data.lookup_sets.edit")),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        return _set_to_response(db, LookupSetService(db).update(set_id, data))
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{set_id}")
async def delete_set(
    set_id: str,
    current_user=Depends(require_permission("master_data.lookup_sets.delete")),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        return LookupSetService(db).delete(set_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


def _set_to_response(db: Session, s) -> dict:
    from app.models.lookup import LookupOption, LookupBinding
    opt_count = db.query(LookupOption).filter(LookupOption.set_id == s.id).count()
    bind_count = db.query(LookupBinding).filter(LookupBinding.set_id == s.id).count()
    return {
        "id": s.id,
        "tenant_id": s.tenant_id,
        "set_key": s.set_key,
        "name": s.name,
        "description": s.description,
        "is_active": s.is_active,
        "option_count": opt_count,
        "binding_count": bind_count,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


# ----- Options nested -----

@router.get("/{set_id}/options", response_model=ListResponse[LookupOptionResponse])
async def list_options(
    set_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=MAX_PAGE_LIMIT),
    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        return LookupOptionService(db).list(set_id, page=page, limit=limit)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{set_id}/options", response_model=LookupOptionResponse, status_code=status.HTTP_201_CREATED)
async def create_option(
    set_id: str,
    data: LookupOptionCreate,
    current_user=Depends(require_permission("master_data.lookup_sets.edit")),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        return LookupOptionService(db).create(set_id, data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{set_id}/options/{option_id}", response_model=LookupOptionResponse)
async def update_option(
    set_id: str,
    option_id: str,
    data: LookupOptionUpdate,
    current_user=Depends(require_permission("master_data.lookup_sets.edit")),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        return LookupOptionService(db).update(option_id, data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{set_id}/options/{option_id}")
async def delete_option(
    set_id: str,
    option_id: str,
    current_user=Depends(require_permission("master_data.lookup_sets.edit")),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        return LookupOptionService(db).delete(option_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


# ----- Bindings nested -----

@router.get("/{set_id}/bindings", response_model=list[LookupBindingResponse])
async def list_bindings(
    set_id: str,
    current_user=Depends(require_permission_with_api_key("master_data.lookup_sets.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        rows = LookupBindingService(db).list_for_set(set_id)
        return [_binding_with_labels(b) for b in rows]
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{set_id}/bindings", response_model=LookupBindingResponse, status_code=status.HTTP_201_CREATED)
async def add_binding(
    set_id: str,
    data: LookupBindingCreate,
    current_user=Depends(require_permission("master_data.lookup_sets.edit")),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        b = LookupBindingService(db).create(set_id, data)
        return _binding_with_labels(b)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{set_id}/bindings/{binding_id}")
async def remove_binding(
    set_id: str,
    binding_id: str,
    current_user=Depends(require_permission("master_data.lookup_sets.edit")),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    try:
        validate_uuid_path(set_id, resource="Lookup Set")
        return LookupBindingService(db).delete(binding_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


def _binding_with_labels(b) -> dict:
    from app.services.lookup_eligibility import get_eligibility
    elig = get_eligibility(b.table_name, b.column_name)
    return {
        "id": b.id,
        "tenant_id": b.tenant_id,
        "set_id": b.set_id,
        "table_name": b.table_name,
        "column_name": b.column_name,
        "table_label": elig.table_label if elig else None,
        "column_label": elig.column_label if elig else None,
        "created_at": b.created_at,
    }
