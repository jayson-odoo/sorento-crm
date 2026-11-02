"""Project party (organisation master) API - UAC Group D."""
from __future__ import annotations

from typing import Optional

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v1.projects._common import acting_company_id, permission_slugs
from app.database import get_db
from app.dependencies import require_any_permission, require_permission
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.projects import (
    ProjectPartyContactCreate,
    ProjectPartyContactResponse,
    ProjectPartyContactUpdate,
    ProjectPartyCreate,
    ProjectPartyResponse,
    ProjectPartyUpdate,
)
from app.services import project_reference_service as refs
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path
from app.utils.multi_value import multi_values

router = APIRouter()

VIEW = "projects.parties.view"
EDIT = "projects.parties.edit"
#: A salesperson who submits registrations searches parties without the parties grant.
SUBMIT = "projects.registrations.submit"


@router.get("/", response_model=ListResponse[ProjectPartyResponse])
def list_parties(
    party_type: Optional[list[str]] = Query(None),
    query: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    _user: dict = Depends(require_any_permission([VIEW, SUBMIT])),
    db: Session = Depends(get_db),
):
    try:
        company_id = acting_company_id(db)
        rows, total = refs.list_parties(
            db,
            company_id=company_id,
            party_type=multi_values(party_type),
            search=query,
            include_inactive=include_inactive,
            page=page,
            limit=limit,
            sort=sort,
            direction=dir,
        )
        data = refs.serialize_parties(db, rows)
        if VIEW not in permission_slugs(db, _user["id"]):
            # A salesperson with the submit grant only needs to pick a party (D8).
            data = [{k: row.get(k) for k in ("id", "name", "party_type")} for row in data]
            return JSONResponse(
                {
                    "data": data,
                    "pagination": {"total": total, "page": page, "limit": limit},
                    "empty": total == 0,
                }
            )
        return {
            "data": data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/", response_model=ProjectPartyResponse, status_code=status.HTTP_201_CREATED
)
def create_party(
    payload: ProjectPartyCreate,
    response: Response,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    try:
        company_id = acting_company_id(db)
        party, created = refs.create_party(
            db,
            company_id=company_id,
            payload=payload.model_dump(exclude_unset=True),
            actor_user_id=current_user["id"],
        )
        db.commit()
        db.refresh(party)
        if not created:
            response.status_code = status.HTTP_200_OK
        return refs.serialize_parties(db, [party])[0]
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.get("/{party_id}", response_model=ProjectPartyResponse)
def get_party(
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
def update_party(
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
def delete_party(
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


# ------------------------------------------------------------- contacts (PS-REGISTRATION-V3 rule 4)


def _company_party_or_404(db: Session, party_id: str):
    """A party of the acting company; another company's reads as not found."""
    validate_uuid_path(party_id, resource="Party")
    party = refs.get_party_or_404(db, party_id)
    if str(party.company_id) != str(acting_company_id(db)):
        from app.services.error_handler import AppException

        raise AppException(status_code=404, message="Party not found.", code="project_party_not_found")
    return party


@router.get("/{party_id}/contacts")
def list_party_contacts(
    party_id: str,
    include_inactive: bool = Query(False),
    _user: dict = Depends(require_any_permission([VIEW, SUBMIT])),
    db: Session = Depends(get_db),
):
    """The people at a party. A salesperson with the submit grant reads them to pick at
    registration (rule 5), as it reads the parties themselves."""
    from app.services import project_party_contact_service as contacts

    try:
        party = _company_party_or_404(db, party_id)
        rows = contacts.list_contacts(db, party, include_inactive=include_inactive)
        data = [contacts.serialize_contact(r) for r in rows]
        if VIEW not in permission_slugs(db, _user["id"]):
            # Picking needs the name only; phone and email stay with the parties grant
            # (security review L1). Register copies them from the database itself.
            keep = ("id", "party_id", "name", "job_title", "is_active")
            data = [{k: row.get(k) for k in keep} for row in data]
        return {"data": data}
    except Exception as exc:
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.post(
    "/{party_id}/contacts",
    response_model=ProjectPartyContactResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_party_contact(
    party_id: str,
    payload: ProjectPartyContactCreate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    from app.services import project_party_contact_service as contacts

    try:
        party = _company_party_or_404(db, party_id)
        row = contacts.create_contact(db, party, payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(row)
        return contacts.serialize_contact(row)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.put("/{party_id}/contacts/{contact_id}", response_model=ProjectPartyContactResponse)
def update_party_contact(
    party_id: str,
    contact_id: str,
    payload: ProjectPartyContactUpdate,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    from app.services import project_party_contact_service as contacts

    try:
        party = _company_party_or_404(db, party_id)
        validate_uuid_path(contact_id, resource="Contact")
        row = contacts.get_contact_or_404(db, party, contact_id)
        contacts.update_contact(db, row, payload.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(row)
        return contacts.serialize_contact(row)
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))


@router.delete("/{party_id}/contacts/{contact_id}")
def delete_party_contact(
    party_id: str,
    contact_id: str,
    _user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    from app.services import project_party_contact_service as contacts

    try:
        party = _company_party_or_404(db, party_id)
        validate_uuid_path(contact_id, resource="Contact")
        row = contacts.get_contact_or_404(db, party, contact_id)
        name = row.name
        contacts.delete_contact(db, row)
        db.commit()
        return {"message": f"{name} deleted"}
    except Exception as exc:
        db.rollback()
        raise exc if hasattr(exc, "status_code") else handle_internal_error(str(exc))
