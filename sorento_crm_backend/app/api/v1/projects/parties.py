"""Project party (organisation master) API — UAC Group D."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id
from app.database import get_db
from app.dependencies import require_permission
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.projects import (
    ProjectPartyCreate,
    ProjectPartyResponse,
    ProjectPartyUpdate,
)
from app.services import project_reference_service as refs
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "projects.parties.view"
EDIT = "projects.parties.edit"


@router.get("/", response_model=ListResponse[ProjectPartyResponse])
async def list_parties(
    party_type: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        company_id = acting_company_id(db)
        rows, total = refs.list_parties(
            db,
            company_id=company_id,
            party_type=party_type,
            search=query,
            include_inactive=include_inactive,
            page=page,
            limit=limit,
        )
        return {
            "data": refs.serialize_parties(db, rows),
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/", response_model=ProjectPartyResponse, status_code=status.HTTP_201_CREATED
)
async def create_party(
    payload: ProjectPartyCreate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        company_id = acting_company_id(db)
        party = refs.create_party(
            db,
            company_id=company_id,
            payload=payload.model_dump(exclude_unset=True),
            actor_user_id=current_user["id"],
        )
        db.commit()
        db.refresh(party)
        return refs.serialize_parties(db, [party])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/{party_id}", response_model=ProjectPartyResponse)
async def get_party(
    party_id: str,
    _user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(party_id, resource="Party")
        party = refs.get_party_or_404(db, party_id)
        return refs.serialize_parties(db, [party])[0]
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/{party_id}", response_model=ProjectPartyResponse)
async def update_party(
    party_id: str,
    payload: ProjectPartyUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(party_id, resource="Party")
        party = refs.get_party_or_404(db, party_id)
        refs.update_party(db, party, payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(party)
        return refs.serialize_parties(db, [party])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/{party_id}")
async def delete_party(
    party_id: str,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(party_id, resource="Party")
        party = refs.get_party_or_404(db, party_id)
        name = party.name
        refs.delete_party(db, party)
        db.commit()
        return {"message": f"{name} deleted"}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
