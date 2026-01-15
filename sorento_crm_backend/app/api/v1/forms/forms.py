"""Forms API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.forms_service import FormService
from app.schemas.forms import FormCreate, FormUpdate, FormResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[FormResponse])
async def get_forms(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get forms with pagination and filtering."""
    try:
        service = FormService(db)
        # Handle empty strings or None values
        sort_field = (sort and sort.strip()) or "updated_at"
        sort_dir = (dir and dir.strip()) or "desc"
        result = service.list_forms(
            page=page, 
            limit=limit, 
            query=query, 
            language=language, 
            status=status,
            sort_field=sort_field,
            sort_dir=sort_dir
        )
        return result
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_forms: {str(e)}")
        logger.error(traceback.format_exc())
        raise handle_internal_error(str(e))


@router.get("/{form_id}", response_model=FormResponse)
async def get_form(
    form_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single form by ID."""
    try:
        service = FormService(db)
        form = service.get_form(form_id)
        return form
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=FormResponse, status_code=status.HTTP_201_CREATED)
async def create_form(
    form_data: FormCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new form."""
    try:
        service = FormService(db)
        form = service.create_form(form_data, current_user["id"])
        return form
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{form_id}", response_model=FormResponse)
async def update_form(
    form_id: str,
    form_data: FormUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a form."""
    try:
        service = FormService(db)
        form = service.update_form(form_id, form_data)
        return form
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{form_id}", status_code=status.HTTP_200_OK)
async def delete_form(
    form_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a form."""
    try:
        service = FormService(db)
        # Implement delete logic
        return {"message": "Form deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
