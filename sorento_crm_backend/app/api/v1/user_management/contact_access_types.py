"""Contact access types catalog API (for promotion/attachment access levels and contact classification)."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.user import (
    ContactAccessTypeCreate,
    ContactAccessTypeUpdate,
    ContactAccessTypeResponse,
    RespondAccessTypeMappingCreate,
    RespondAccessTypeMappingUpdate,
    RespondAccessTypeMappingResponse,
)
from app.services.contact_access_type_service import ContactAccessTypeService
from app.services.error_handler import handle_internal_error
from app.services.error_handler import AppException

router = APIRouter()


def _service(db: Session) -> ContactAccessTypeService:
    return ContactAccessTypeService(db)


@router.get("/", response_model=list)
async def list_contact_access_types(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active contact access types for use in access_levels (promotions, attachments). Returns [{code, name, description, sort_order}]."""
    try:
        return _service(db).list_types_for_api()
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


# --- Respond access type mappings (must be registered before /{code} so /mappings is not matched as code) ---

mappings_router = APIRouter(prefix="/mappings", tags=["contact-access-types-mappings"])


@mappings_router.get("", response_model=list[RespondAccessTypeMappingResponse])
@mappings_router.get("/", response_model=list[RespondAccessTypeMappingResponse], include_in_schema=False)
async def list_respond_mappings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all Respond access type mappings for admin UI."""
    try:
        return _service(db).list_mappings()
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


@mappings_router.get("/{mapping_id}", response_model=RespondAccessTypeMappingResponse)
async def get_respond_mapping(
    mapping_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single mapping by id."""
    try:
        row = _service(db).get_mapping_by_id(mapping_id)
        if not row:
            from app.services.error_handler import handle_not_found
            raise handle_not_found("Mapping", mapping_id)
        return row
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


@mappings_router.post("", response_model=RespondAccessTypeMappingResponse, status_code=status.HTTP_201_CREATED)
@mappings_router.post("/", response_model=RespondAccessTypeMappingResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_respond_mapping(
    data: RespondAccessTypeMappingCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new Respond value to access type mapping."""
    try:
        return _service(db).create_mapping(data.model_dump())
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


@mappings_router.put("/{mapping_id}", response_model=RespondAccessTypeMappingResponse)
async def update_respond_mapping(
    mapping_id: str,
    data: RespondAccessTypeMappingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a mapping."""
    try:
        return _service(db).update_mapping(mapping_id, data.model_dump(exclude_unset=True))
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


@mappings_router.delete("/{mapping_id}", status_code=status.HTTP_200_OK)
async def delete_respond_mapping(
    mapping_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a mapping."""
    try:
        _service(db).delete_mapping(mapping_id)
        return {"message": "Deleted"}
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


router.include_router(mappings_router)


# --- Admin: contact access type catalog CRUD ---

@router.get("/all", response_model=list[ContactAccessTypeResponse])
async def list_all_contact_access_types(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all contact access types (including inactive) for admin UI."""
    try:
        return _service(db).list_all_types()
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


@router.get("/{code}", response_model=ContactAccessTypeResponse)
async def get_contact_access_type(
    code: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single contact access type by code."""
    try:
        row = _service(db).get_type_by_code(code)
        if not row:
            from app.services.error_handler import handle_not_found
            raise handle_not_found("Contact access type", code)
        return row
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


@router.post("/", response_model=ContactAccessTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_contact_access_type(
    data: ContactAccessTypeCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new contact access type."""
    try:
        return _service(db).create_type(data.model_dump())
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


@router.put("/{code}", response_model=ContactAccessTypeResponse)
async def update_contact_access_type(
    code: str,
    data: ContactAccessTypeUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a contact access type."""
    try:
        return _service(db).update_type(code, data.model_dump(exclude_unset=True))
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()


@router.delete("/{code}", status_code=status.HTTP_200_OK)
async def delete_contact_access_type(
    code: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a contact access type."""
    try:
        _service(db).delete_type(code)
        return {"message": "Deleted"}
    except AppException:
        raise
    except Exception:
        raise handle_internal_error()
